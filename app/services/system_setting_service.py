from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting


class SystemSettingService:
    """
    Service quản lý cấu hình hệ thống dạng key-value.
    Dùng chung cho mọi module.
    """

    def get_setting(self, db: Session, key: str, default: str = None) -> Optional[str]:
        """Lấy giá trị setting theo key."""
        record = db.query(SystemSetting).filter(
            SystemSetting.setting_key == key
        ).first()
        return record.setting_value if record else default

    def get_setting_int(self, db: Session, key: str, default: int = 0) -> int:
        """Lấy giá trị setting dạng int."""
        val = self.get_setting(db, key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_setting_float(self, db: Session, key: str, default: float = 0.0) -> float:
        """Lấy giá trị setting dạng float."""
        val = self.get_setting(db, key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def set_setting(
        self, db: Session, key: str, value: str, description: str = None
    ) -> SystemSetting:
        """Tạo hoặc cập nhật setting."""
        record = db.query(SystemSetting).filter(
            SystemSetting.setting_key == key
        ).first()

        if record:
            record.setting_value = value
            if description is not None:
                record.description = description
        else:
            record = SystemSetting(
                setting_key=key,
                setting_value=value,
                description=description,
            )
            db.add(record)

        db.commit()
        db.refresh(record)
        return record

    def get_all_by_prefix(self, db: Session, prefix: str) -> List[SystemSetting]:
        """Lấy tất cả settings có key bắt đầu bằng prefix."""
        return (
            db.query(SystemSetting)
            .filter(SystemSetting.setting_key.like(f"{prefix}%"))
            .order_by(SystemSetting.setting_key)
            .all()
        )


system_setting_service = SystemSettingService()
