from sqlalchemy import Column, Integer, String

from app.models.base import Base


class SystemSetting(Base):
    """
    Bảng cấu hình hệ thống dạng key-value.
    Dùng chung cho mọi module (KPI, Attendance, v.v.)

    Convention cho setting_key:
      - attendance.min_rate_percent
      - attendance.grace_period_min
      - kpi.some_setting
    """
    __tablename__ = "system_settings"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    setting_key   = Column(String(50), unique=True, nullable=False)
    setting_value = Column(String(255), nullable=False)
    description   = Column(String(255), nullable=True)
