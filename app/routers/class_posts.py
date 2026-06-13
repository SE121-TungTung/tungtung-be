from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional, Any
import json

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.academic import Class
from app.models.class_post import ClassPost, ClassPostType
from app.repositories.class_post import class_post_repo
from app.schemas.class_post import ClassPostResponse
from app.services.cloudinary import handle_cloudinary_upload
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException

router = APIRouter(prefix="/classes", tags=["Class Posts"], route_class=ResponseWrapperRoute)

@router.post("/{class_id}/posts", response_model=ApiResponse[ClassPostResponse])
async def create_class_post(
    class_id: UUID,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    post_type: str = Form("announcement"),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Check if class exists
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise APIException(status_code=404, code="NOT_FOUND", message="Class not found")
        
    # 2. Check authorization: current user must be class teacher, sub teacher, TA, or Admin/CenterAdmin
    is_authorized = (
        current_user.role in ["admin", "center_admin"] or
        str(class_obj.teacher_id) == str(current_user.id) or
        (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == str(current_user.id)) or
        (class_obj.ta_id and str(class_obj.ta_id) == str(current_user.id))
    )
    if not is_authorized:
        raise APIException(status_code=403, code="FORBIDDEN", message="You are not authorized to post in this class")

    # 3. Handle file uploads to Cloudinary if post_type is material
    attachments = []
    if files and post_type == "material":
        for file in files:
            if file.filename: # avoid empty file parts
                try:
                    upload_res = await handle_cloudinary_upload(file, folder_name="class_materials")
                    attachments.append({
                        "file_name": file.filename,
                        "file_url": upload_res["file_url"],
                        "file_size": upload_res["bytes"],
                        "mime_type": file.content_type
                    })
                except Exception as e:
                    raise APIException(status_code=500, code="UPLOAD_FAILED", message=f"Failed to upload file {file.filename}: {str(e)}")

    # 4. Create class post
    post_type_enum = ClassPostType.MATERIAL if post_type == "material" else ClassPostType.ANNOUNCEMENT
    
    db_post = ClassPost(
        class_id=class_id,
        author_id=current_user.id,
        title=title,
        content=content,
        post_type=post_type_enum,
        attachments=attachments,
        created_by=current_user.id,
        updated_by=current_user.id
    )
    
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    
    return ApiResponse(data=db_post, message="Tạo bài viết thành công")

@router.get("/{class_id}/posts", response_model=PaginationResponse[ClassPostResponse])
def get_class_posts(
    class_id: UUID,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if user is enrolled or teaches the class, or is admin
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise APIException(status_code=404, code="NOT_FOUND", message="Class not found")
    
    # Check if student is enrolled
    is_student_enrolled = any(str(enroll.student_id) == str(current_user.id) for enroll in class_obj.enrollments)
    is_authorized = (
        current_user.role in ["admin", "center_admin"] or
        str(class_obj.teacher_id) == str(current_user.id) or
        (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == str(current_user.id)) or
        (class_obj.ta_id and str(class_obj.ta_id) == str(current_user.id)) or
        is_student_enrolled
    )
    
    if not is_authorized:
        raise APIException(status_code=403, code="FORBIDDEN", message="You are not authorized to view posts of this class")

    skip = (page - 1) * limit
    posts = class_post_repo.get_by_class(db, class_id=class_id, skip=skip, limit=limit)
    total = class_post_repo.count_by_class(db, class_id=class_id)
    
    return PaginationResponse(data=posts, total=total, page=page, limit=limit)

@router.delete("/{class_id}/posts/{post_id}", response_model=ApiResponse[Any])
def delete_class_post(
    class_id: UUID,
    post_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    post = db.query(ClassPost).filter(ClassPost.id == post_id, ClassPost.class_id == class_id).first()
    if not post:
        raise APIException(status_code=404, code="NOT_FOUND", message="Post not found")
        
    # Only author or Admin can delete
    if str(post.author_id) != str(current_user.id) and current_user.role not in ["admin", "center_admin"]:
        raise APIException(status_code=403, code="FORBIDDEN", message="You are not authorized to delete this post")
        
    db.delete(post)
    db.commit()
    return ApiResponse(data={}, message="Xóa bài viết thành công")
