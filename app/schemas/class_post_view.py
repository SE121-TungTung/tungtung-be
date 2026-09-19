"""
Schema: Class Post Views & Engagement Analytics
Định nghĩa Request và Response schemas cho tính năng theo dõi lượt xem, tương tác (reaction/comment),
và tải tệp đính kèm bài viết lớp học.
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


class RecordDownloadRequest(BaseModel):
    """Payload ghi nhận học viên tải tệp đính kèm."""
    file_name: str
    file_url: Optional[str] = None


class RecordDownloadResponse(BaseModel):
    """Response sau khi ghi nhận tải tệp đính kèm."""
    post_id:       UUID
    file_name:     str
    downloaded:    bool
    downloaded_at: Optional[datetime] = None


class ViewerInfo(BaseModel):
    """Thông tin học viên và trạng thái xem bài viết."""
    user_id:    UUID
    name:       str
    email:      str
    avatar_url: Optional[str]      = None
    viewed_at:  Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InteractedStudentInfo(BaseModel):
    """Thông tin học viên đã tương tác (thả reaction hoặc bình luận)."""
    user_id:            UUID
    name:               str
    email:              str
    avatar_url:         Optional[str]      = None
    reactions:          List[str]          = []
    comment_count:      int                = 0
    last_interacted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DownloadedStudentInfo(BaseModel):
    """Thông tin học viên và lịch sử tải file đính kèm."""
    user_id:            UUID
    name:               str
    email:              str
    avatar_url:         Optional[str]      = None
    downloaded_files:   List[str]          = []
    last_downloaded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ViewsMetrics(BaseModel):
    """Chỉ số lượt xem bài viết."""
    count:       int
    percentage:  int
    viewers:     List[ViewerInfo] = []
    non_viewers: List[ViewerInfo] = []


class InteractionsMetrics(BaseModel):
    """Chỉ số tương tác (reaction/comment)."""
    count:           int
    percentage:      int
    interacted:      List[InteractedStudentInfo] = []
    not_interacted:  List[InteractedStudentInfo] = []


class DownloadsMetrics(BaseModel):
    """Chỉ số tải tệp đính kèm."""
    has_attachments: bool
    count:           int
    percentage:      int
    downloaded:      List[DownloadedStudentInfo] = []
    not_downloaded:  List[DownloadedStudentInfo] = []


class PostEngagementSummaryResponse(BaseModel):
    """Báo cáo thống kê toàn diện tương tác bài viết (Views, Reactions/Comments, Downloads)."""
    post_id:          UUID
    total_students:   int
    views:            ViewsMetrics
    interactions:     InteractionsMetrics
    downloads:        DownloadsMetrics

    # Backward compatibility fields cho các client cũ dùng ViewersSummaryResponse
    viewed_count:     int
    not_viewed_count: int
    viewers:          List[ViewerInfo] = []
    non_viewers:      List[ViewerInfo] = []


# Alias để tương thích ngược
ViewersSummaryResponse = PostEngagementSummaryResponse
