from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.route import ResponseWrapperRoute
from app.core.database import get_db
from app.schemas.base_schema import ApiResponse
from app.services.dictionary_service import dictionary_service
from app.dependencies import require_non_guest

router = APIRouter(
    tags=["Dictionary"],
    prefix="/dictionary",
    route_class=ResponseWrapperRoute,
)

@router.get("/lookup", response_model=ApiResponse)
async def lookup_word(
    word: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_non_guest)
):
    """
    **Tra từ điển (tự động lưu cache)**
    
    Tìm trong DB trước. Nếu chưa có, gọi Free Dictionary API, bóc tách dữ liệu và lưu DB.
    """
    result = await dictionary_service.lookup_word(db, word)
    if not result:
        # Trả về 200 nhưng rỗng hoặc 404 tuỳ quy ước. Chọn 404 để frontend báo lỗi dễ hơn
        raise HTTPException(status_code=404, detail="Word not found in dictionary")
    
    return ApiResponse(
        data=result,
        message="Lookup successful"
    )
