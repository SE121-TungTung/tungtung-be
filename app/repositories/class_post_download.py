"""
Repository: ClassPostDownloadRepository
Truy vấn và ghi nhận lịch sử tải tệp đính kèm bài viết lớp học.
"""

from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.class_post_download import ClassPostDownload
from app.repositories.base import BaseRepository


class ClassPostDownloadRepository(BaseRepository[ClassPostDownload]):
    """Repository cho class_post_downloads."""

    def record_download(
        self,
        db: Session,
        post_id: UUID,
        user_id: UUID,
        file_name: str,
        file_url: Optional[str] = None,
    ) -> Tuple[ClassPostDownload, bool]:
        """Ghi nhận lượt tải tệp đính kèm của học viên (idempotent theo post_id, user_id, file_name)."""
        existing = (
            db.query(self.model)
            .filter(
                self.model.post_id == post_id,
                self.model.user_id == user_id,
                self.model.file_name == file_name,
            )
            .first()
        )
        if existing:
            return existing, False

        new_download = self.model(
            post_id=post_id,
            user_id=user_id,
            file_name=file_name,
            file_url=file_url,
            downloaded_at=datetime.now(timezone.utc),
        )
        db.add(new_download)
        db.commit()
        db.refresh(new_download)
        return new_download, True

    def get_downloads_for_post(
        self,
        db: Session,
        post_id: UUID,
    ) -> List[ClassPostDownload]:
        """Lấy tất cả các bản ghi tải tệp đính kèm của bài viết."""
        return (
            db.query(self.model)
            .filter(self.model.post_id == post_id)
            .order_by(self.model.downloaded_at.desc())
            .all()
        )


class_post_download_repo = ClassPostDownloadRepository(ClassPostDownload)
