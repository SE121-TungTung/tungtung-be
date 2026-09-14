"""
Schema: Class Post Views (View Tracking & Viewers Summary)
Định nghĩa Request và Response schemas cho tính năng theo dõi lượt xem bài viết lớp học.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class RecordViewResponse(BaseModel):
    """Response sau khi ghi nhận lượt xem."""
    post_id:   UUID
    viewed:    bool
    viewed_at: Optional[datetime] = None
    view_count: int = 0


class ViewerInfo(BaseModel):
    """Thông tin học viên và trạng thái xem bài viết."""
    user_id:    UUID
    name:       str
    email:      str
    avatar_url: Optional[str]      = None
    viewed_at:  Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ViewersSummaryResponse(BaseModel):
    """Báo cáo tỷ lệ đã xem cho GV/TA/Admin."""
    post_id:          UUID
    total_students:   int
    viewed_count:     int
    not_viewed_count: int
    viewers:          List[ViewerInfo] = []
    non_viewers:      List[ViewerInfo] = []
