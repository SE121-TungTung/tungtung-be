"""
Repository: ClassPostViewRepository
Truy vấn dữ liệu lượt xem (view tracking) & Thống kê tương tác bài viết (views, reactions/comments, downloads).
"""

from typing import List, Optional, Tuple, Dict, Set
from uuid import UUID
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.class_post_view import ClassPostView
from app.models.academic import ClassEnrollment
from app.models.user import User
from app.models.class_post import ClassPost
from app.models.class_post_reaction import ClassPostReaction
from app.models.class_post_comment import ClassPostComment
from app.models.class_post_download import ClassPostDownload
from app.schemas.class_post_view import (
    ViewerInfo,
    InteractedStudentInfo,
    DownloadedStudentInfo,
    ViewsMetrics,
    InteractionsMetrics,
    DownloadsMetrics,
    PostEngagementSummaryResponse,
    ViewersSummaryResponse,
)
from app.repositories.base import BaseRepository


class ClassPostViewRepository(BaseRepository[ClassPostView]):
    """Repository cho class_post_views & engagement metrics."""

    def record_view(
        self,
        db: Session,
        post_id: UUID,
        user_id: UUID,
    ) -> Tuple[ClassPostView, bool]:
        """Ghi nhận lượt xem của user trên bài viết.

        Returns:
            (view_record, is_new): is_new = True nếu vừa ghi nhận lần đầu.
        """
        existing = (
            db.query(self.model)
            .filter(
                self.model.post_id == post_id,
                self.model.user_id == user_id,
            )
            .first()
        )
        if existing:
            return existing, False

        new_view = self.model(post_id=post_id, user_id=user_id)
        db.add(new_view)
        db.commit()
        db.refresh(new_view)
        return new_view, True

    def get_view_count(self, db: Session, post_id: UUID) -> int:
        """Đếm tổng số lượt xem duy nhất trên 1 bài viết."""
        return (
            db.query(func.count(self.model.id))
            .filter(self.model.post_id == post_id)
            .scalar()
            or 0
        )

    def get_view_counts_batch(self, db: Session, post_ids: List[UUID]) -> dict:
        """Đếm số lượt xem cho nhiều bài viết cùng lúc."""
        if not post_ids:
            return {}
        rows = (
            db.query(self.model.post_id, func.count(self.model.id))
            .filter(self.model.post_id.in_(post_ids))
            .group_by(self.model.post_id)
            .all()
        )
        return {post_id: count for post_id, count in rows}

    def get_viewers_summary(
        self,
        db: Session,
        post_id: UUID,
        class_id: UUID,
    ) -> PostEngagementSummaryResponse:
        """Lấy báo cáo tổng hợp tương tác bài viết (Views, Reactions/Comments, Downloads)."""
        # 1. Danh sách học viên hợp lệ ghi danh trong lớp
        enrollment_rows = (
            db.query(ClassEnrollment, User)
            .join(User, ClassEnrollment.student_id == User.id)
            .filter(
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .all()
        )

        # 2. Lấy thông tin bài viết để kiểm tra có tệp đính kèm không
        post_obj = (
            db.query(ClassPost)
            .filter(ClassPost.id == post_id)
            .first()
        )
        has_attachments = bool(post_obj and post_obj.attachments and len(post_obj.attachments) > 0)

        # 3. Lấy toàn bộ lượt xem của bài viết này
        views = (
            db.query(self.model)
            .filter(self.model.post_id == post_id)
            .all()
        )
        view_map: Dict[UUID, datetime] = {v.user_id: v.viewed_at for v in views}

        # 4. Lấy toàn bộ lượt reactions của bài viết này
        reactions = (
            db.query(ClassPostReaction)
            .filter(ClassPostReaction.post_id == post_id)
            .all()
        )
        reaction_map: Dict[UUID, List[str]] = {}
        reaction_time_map: Dict[UUID, datetime] = {}
        for r in reactions:
            reaction_map.setdefault(r.user_id, []).append(r.reaction_type)
            if r.user_id not in reaction_time_map or r.created_at > reaction_time_map[r.user_id]:
                reaction_time_map[r.user_id] = r.created_at

        # 5. Lấy toàn bộ bình luận của bài viết này (chỉ đếm bình luận chưa bị xóa)
        comments = (
            db.query(ClassPostComment)
            .filter(
                ClassPostComment.post_id == post_id,
                ClassPostComment.deleted_at.is_(None),
            )
            .all()
        )
        comment_count_map: Dict[UUID, int] = {}
        comment_time_map: Dict[UUID, datetime] = {}
        for c in comments:
            comment_count_map[c.author_id] = comment_count_map.get(c.author_id, 0) + 1
            if c.author_id not in comment_time_map or c.created_at > comment_time_map[c.author_id]:
                comment_time_map[c.author_id] = c.created_at

        # 6. Lấy toàn bộ lịch sử tải tệp đính kèm của bài viết này
        downloads = (
            db.query(ClassPostDownload)
            .filter(ClassPostDownload.post_id == post_id)
            .all()
        )
        download_map: Dict[UUID, List[str]] = {}
        download_time_map: Dict[UUID, datetime] = {}
        for d in downloads:
            if d.file_name not in download_map.setdefault(d.user_id, []):
                download_map[d.user_id].append(d.file_name)
            if d.user_id not in download_time_map or d.downloaded_at > download_time_map[d.user_id]:
                download_time_map[d.user_id] = d.downloaded_at

        # 7. Tổng hợp danh sách học viên theo từng loại chỉ số
        viewers: List[ViewerInfo] = []
        non_viewers: List[ViewerInfo] = []

        interacted_list: List[InteractedStudentInfo] = []
        not_interacted_list: List[InteractedStudentInfo] = []

        downloaded_list: List[DownloadedStudentInfo] = []
        not_downloaded_list: List[DownloadedStudentInfo] = []

        seen_users: Set[UUID] = set()
        for enrollment, user in enrollment_rows:
            if user.id in seen_users:
                continue
            seen_users.add(user.id)

            full_name = f"{user.first_name} {user.last_name}".strip() or user.email

            # Views metric
            viewed_at = view_map.get(user.id)
            v_info = ViewerInfo(
                user_id=user.id,
                name=full_name,
                email=user.email,
                avatar_url=user.avatar_url,
                viewed_at=viewed_at,
            )
            if viewed_at is not None:
                viewers.append(v_info)
            else:
                non_viewers.append(v_info)

            # Interactions metric
            user_reactions = reaction_map.get(user.id, [])
            user_comments = comment_count_map.get(user.id, 0)
            # Mốc thời gian tương tác gần nhất
            last_interaction: Optional[datetime] = None
            r_time = reaction_time_map.get(user.id)
            c_time = comment_time_map.get(user.id)
            if r_time and c_time:
                last_interaction = max(r_time, c_time)
            elif r_time:
                last_interaction = r_time
            elif c_time:
                last_interaction = c_time

            i_info = InteractedStudentInfo(
                user_id=user.id,
                name=full_name,
                email=user.email,
                avatar_url=user.avatar_url,
                reactions=user_reactions,
                comment_count=user_comments,
                last_interacted_at=last_interaction,
            )
            if user_reactions or user_comments > 0:
                interacted_list.append(i_info)
            else:
                not_interacted_list.append(i_info)

            # Downloads metric
            user_downloads = download_map.get(user.id, [])
            last_download_time = download_time_map.get(user.id)
            d_info = DownloadedStudentInfo(
                user_id=user.id,
                name=full_name,
                email=user.email,
                avatar_url=user.avatar_url,
                downloaded_files=user_downloads,
                last_downloaded_at=last_download_time,
            )
            if user_downloads:
                downloaded_list.append(d_info)
            else:
                not_downloaded_list.append(d_info)

        # Sắp xếp
        viewers.sort(key=lambda x: x.viewed_at or datetime.min, reverse=True)
        non_viewers.sort(key=lambda x: x.name.lower())

        interacted_list.sort(key=lambda x: x.last_interacted_at or datetime.min, reverse=True)
        not_interacted_list.sort(key=lambda x: x.name.lower())

        downloaded_list.sort(key=lambda x: x.last_downloaded_at or datetime.min, reverse=True)
        not_downloaded_list.sort(key=lambda x: x.name.lower())

        total = len(seen_users)
        v_pct = round((len(viewers) / total) * 100) if total > 0 else 0
        i_pct = round((len(interacted_list) / total) * 100) if total > 0 else 0
        d_pct = round((len(downloaded_list) / total) * 100) if total > 0 else 0

        return PostEngagementSummaryResponse(
            post_id=post_id,
            total_students=total,
            views=ViewsMetrics(
                count=len(viewers),
                percentage=v_pct,
                viewers=viewers,
                non_viewers=non_viewers,
            ),
            interactions=InteractionsMetrics(
                count=len(interacted_list),
                percentage=i_pct,
                interacted=interacted_list,
                not_interacted=not_interacted_list,
            ),
            downloads=DownloadsMetrics(
                has_attachments=has_attachments,
                count=len(downloaded_list),
                percentage=d_pct,
                downloaded=downloaded_list,
                not_downloaded=not_downloaded_list,
            ),
            # Backward compatibility fields
            viewed_count=len(viewers),
            not_viewed_count=len(non_viewers),
            viewers=viewers,
            non_viewers=non_viewers,
        )


class_post_view_repo = ClassPostViewRepository(ClassPostView)
