import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from app.core.config import settings
import logging
from fastapi import UploadFile
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from app.models.file_upload import FileUpload, UploadType, ProcessingStatus, ScanStatus, AccessLevel

# Configuration       
cloudinary.config( 
    cloud_name = settings.CLOUDINARY_CLOUD_NAME, 
    api_key = settings.CLOUDINARY_API_KEY, 
    api_secret = settings.CLOUDINARY_API_SECRET,
    secure=True
)

logger = logging.getLogger(__name__)

async def handle_cloudinary_upload(uploaded_file: UploadFile, folder_name: str) -> dict:
    """
    Đọc UploadFile từ FastAPI và tải lên Cloudinary.
    """
    
    # 1. Đọc Nội dung File (Sử dụng await vì đây là I/O bất đồng bộ)
    try:
        file_content = await uploaded_file.read()
    except Exception as e:
        logger.error(f"Failed to read file content: {e}")
        # Trả về Exception phù hợp
        raise

    # 2. Tạo Public ID duy nhất — giữ lại extension gốc để download đúng định dạng
    original_filename = uploaded_file.filename or ""
    ext = ""
    if "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()
    unique_id = uuid4()
    public_id = f"{folder_name}/{unique_id}{ext}"
    
    # 3. Thực hiện Upload
    try:
        upload_result = cloudinary.uploader.upload(
            file_content, # 🌟 Truyền trực tiếp dữ liệu nhị phân (bytes)
            public_id=public_id,
            resource_type="auto", # Tự động phát hiện image/video/raw
            folder=folder_name
        )
        
        # 4. Trả về thông tin cần thiết
        return {
            "file_url": upload_result["secure_url"],
            "public_id": upload_result["public_id"],
            "resource_type": upload_result["resource_type"],
            "bytes": upload_result["bytes"]
        }
    
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
        # Xử lý lỗi kết nối/API key
        raise

async def upload_and_save_metadata(
    db: Session, 
    uploaded_file: UploadFile, 
    user_id: UUID,
    folder: str = "user_avatars",
    upload_type_value: str = UploadType.AVATAR.value, 
    access_level_value: str = AccessLevel.PRIVATE.value 
) -> FileUpload:
    """
    Tải file lên Cloudinary và lưu metadata đầy đủ vào bảng file_uploads.
    """
    
    # 1. Đọc nội dung file và Upload lên Cloudinary
    # 🌟 GỌI HÀM CLOUDINARY UPLOAD Ở ĐÂY
    upload_info = await handle_cloudinary_upload(uploaded_file, folder)
    
    # Lấy Public ID và URL từ kết quả upload
    public_id = upload_info["public_id"]
    file_url = upload_info["file_url"]
    
    # 2. Tạo đối tượng FileUpload (Cung cấp tất cả các trường NOT NULL)
    
    # Lấy giá trị Enum Python từ chuỗi
    upload_type_enum = UploadType(upload_type_value)
    access_level_enum = AccessLevel(access_level_value)
    
    # 🌟 Dữ liệu được ánh xạ chính xác tới các cột Model
    metadata_data = {
        # --- NOT NULL FIELDS ---
        "filename": public_id, # Public ID dùng làm ID duy nhất
        "original_filename": uploaded_file.filename,
        "file_path": file_url,
        "file_size": upload_info["bytes"], # Kích thước file
        "mime_type": uploaded_file.content_type,
        "upload_type": upload_type_enum.value, # 🌟 MAPPING ENUM
        "uploaded_by": user_id,
        
        # --- STATUS FIELDS (Có giá trị DEFAULT) ---
        "is_processed": False,
        "processing_status": ProcessingStatus.PENDING.value, # Giá trị mặc định
        "virus_scan_status": ScanStatus.PENDING.value,       # Giá trị mặc định
        "access_level": access_level_enum.value,             # MAPPING ENUM
        
        # --- OPTIONAL FIELDS ---
        "file_hash": None, 
        "virus_scan_result": None,
        "associated_id": None,
        "expires_at": None,
    }
    
    # 3. Tạo record và Commit DB
    db_metadata = FileUpload(**metadata_data)
    
    db.add(db_metadata)
    # Khác với service mẫu trước, ta không cần db.commit() và db.refresh() ở đây
    # nếu hàm này được gọi trong một transaction lớn hơn (ví dụ: update_user_with_avatar)
    # Tuy nhiên, ta giữ lại để đảm bảo tính độc lập của logic lưu metadata
    db.commit()
    db.refresh(db_metadata)
    
    return db_metadata

def delete_cloudinary_file(public_id: str):
    """Xóa file khỏi Cloudinary bằng public ID."""
    try:
        cloudinary.uploader.destroy(public_id)
        logger.info(f"Successfully destroyed file: {public_id}")
    except Exception as e:
        logger.error(f"Failed to destroy file {public_id}: {e}")
        # Xử lý nếu file không tồn tại
        pass