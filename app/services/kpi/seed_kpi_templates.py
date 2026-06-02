"""
Seed default KPI templates for GV (Teacher / FULL_TIME) and TA (PART_TIME).
Run this script to populate the database with the Lotus KPI metric definitions.

Usage:
    python -m app.services.kpi.seed_kpi_templates
"""

from app.core.database import SessionLocal
from app.models.kpi import (
    KPITemplate, KPITemplateMetric, ContractType, BonusType, MetricUnit,
)


def seed_teacher_template(db):
    """Seed GV (Teacher) KPI Template — max bonus 15,000,000 VND/kỳ."""
    template = KPITemplate(
        name="KPI cho Giáo viên (GV)",
        contract_type=ContractType.FULL_TIME,
        max_bonus_amount=15_000_000,
        bonus_type=BonusType.FIXED_PER_PERIOD,
        version=1,
        is_active=True,
        description="Bộ KPI tiêu chuẩn dành cho Giáo viên chính - Trung tâm Anh ngữ Lotus",
    )
    db.add(template)
    db.flush()

    metrics = [
        # Group A — CHẤT LƯỢNG VÀ KHỐI LƯỢNG GIẢNG DẠY (weight: 0.4)
        {"code": "A", "name": "CHẤT LƯỢNG VÀ KHỐI LƯỢNG GIẢNG DẠY", "is_group": True, "gw": 0.4, "order": 0},
        {"code": "A1", "name": "Tỷ lệ HS đạt điểm trung bình trở lên trong các kỳ kiểm tra",
         "unit": MetricUnit.PERCENT, "min": 0.4, "max": 1.0, "w": 0.12, "order": 1},
        {"code": "A2", "name": "Tỷ lệ HS đạt điểm cao trở lên trong các kỳ kiểm tra",
         "unit": MetricUnit.PERCENT, "min": 0.0, "max": 0.1, "w": 0.02, "order": 2},
        {"code": "A3", "name": "Tỷ lệ hoàn thành soạn giảng (nộp giáo án trước 1 tuần)",
         "unit": MetricUnit.PERCENT, "min": 0.9, "max": 1.0, "w": 0.08, "order": 3},
        {"code": "A4", "name": "Tỷ lệ dạy đủ các buổi theo lịch phân công",
         "unit": MetricUnit.PERCENT, "min": 0.8, "max": 1.0, "w": 0.08, "order": 4},
        {"code": "A5", "name": "Tỷ lệ hoàn thành và đúng tiến độ kế hoạch giảng dạy",
         "unit": MetricUnit.PERCENT, "min": 0.9, "max": 1.0, "w": 0.08, "order": 5},
        {"code": "A6", "name": "Có HS đạt giải cao trong các kỳ thi Tiếng Anh quan trọng",
         "unit": MetricUnit.STUDENT, "min": 0.0, "max": 2.0, "w": 0.02, "order": 6},

        # Group B — NỀ NẾP VÀ KỶ LUẬT (weight: 0.3)
        {"code": "B", "name": "NỀ NẾP VÀ KỶ LUẬT", "is_group": True, "gw": 0.3, "order": 7},
        {"code": "B1", "name": "Tỷ lệ lên lớp đúng giờ",
         "unit": MetricUnit.PERCENT, "min": 0.5, "max": 1.0, "w": 0.15, "order": 8},
        {"code": "B2", "name": "Tỷ lệ thực hiện tác phong sư phạm (trang phục, cử chỉ...)",
         "unit": MetricUnit.PERCENT, "min": 0.5, "max": 1.0, "w": 0.15, "order": 9},

        # Group C — SỰ THAM GIA CỦA HỌC SINH (weight: 0.2)
        {"code": "C", "name": "SỰ THAM GIA CỦA HỌC SINH", "is_group": True, "gw": 0.2, "order": 10},
        {"code": "C1", "name": "Tỷ lệ HS tiếp tục học vào khóa tiếp theo (retention/renewal)",
         "unit": MetricUnit.PERCENT, "min": 0.7, "max": 1.0, "w": 0.20, "order": 11},

        # Group D — ĐÓNG GÓP SÁNG KIẾN VÀ NGHIÊN CỨU (weight: 0.1)
        {"code": "D", "name": "ĐÓNG GÓP SÁNG KIẾN VÀ NGHIÊN CỨU", "is_group": True, "gw": 0.1, "order": 12},
        {"code": "D1", "name": "Số lượng đóng góp nâng cao phát triển giảng dạy",
         "unit": MetricUnit.COUNT, "min": 0.0, "max": 2.0, "w": 0.025, "order": 13},
        {"code": "D2", "name": "Tỷ lệ tham gia các phong trào của trung tâm",
         "unit": MetricUnit.PERCENT, "min": 0.7, "max": 1.0, "w": 0.05, "order": 14},
        {"code": "D3", "name": "Tham gia tương tác/chia sẻ bài đăng trên mạng xã hội",
         "unit": MetricUnit.COUNT, "min": 0.0, "max": 5.0, "w": 0.025, "order": 15},
    ]

    for m in metrics:
        metric = KPITemplateMetric(
            template_id=template.id,
            metric_code=m["code"],
            metric_name=m["name"],
            is_group_header=m.get("is_group", False),
            unit=m.get("unit"),
            target_min=m.get("min"),
            target_max=m.get("max"),
            weight=m.get("w"),
            group_weight=m.get("gw"),
            sort_order=m["order"],
        )
        db.add(metric)

    return template


def seed_ta_template(db):
    """Seed TA (Teaching Assistant) KPI Template — max bonus 15,000 VND/giờ."""
    template = KPITemplate(
        name="KPI cho TA (Teaching Assistant)",
        contract_type=ContractType.PART_TIME,
        max_bonus_amount=15_000,
        bonus_type=BonusType.PER_HOUR,
        version=1,
        is_active=True,
        description="Bộ KPI tiêu chuẩn dành cho Teaching Assistant - Trung tâm Anh ngữ Lotus",
    )
    db.add(template)
    db.flush()

    metrics = [
        # Group A — CHẤT LƯỢNG VÀ KHỐI LƯỢNG GIẢNG DẠY (weight: 0.4)
        {"code": "A", "name": "CHẤT LƯỢNG VÀ KHỐI LƯỢNG GIẢNG DẠY", "is_group": True, "gw": 0.4, "order": 0},
        {"code": "A1", "name": "Tỷ lệ HS đạt điểm trung bình trở lên trong các kỳ kiểm tra",
         "unit": MetricUnit.PERCENT, "min": 0.3, "max": 1.0, "w": 0.12, "order": 1},
        {"code": "A2", "name": "Tỷ lệ HS đạt điểm cao trở lên trong các kỳ kiểm tra",
         "unit": MetricUnit.PERCENT, "min": 0.0, "max": 0.1, "w": 0.02, "order": 2},
        {"code": "A3", "name": "Điểm số đánh giá từ GV",
         "unit": MetricUnit.SCORE, "min": 5.0, "max": 10.0, "w": 0.08, "order": 3},
        {"code": "A4", "name": "Tỷ lệ dạy đủ các buổi theo lịch phân công",
         "unit": MetricUnit.PERCENT, "min": 0.8, "max": 1.0, "w": 0.08, "order": 4},
        {"code": "A5", "name": "Tỷ lệ hoàn thành và đúng tiến độ kế hoạch giảng dạy",
         "unit": MetricUnit.PERCENT, "min": 0.8, "max": 1.0, "w": 0.08, "order": 5},
        {"code": "A6", "name": "Có HS đạt giải cao trong các kỳ thi Tiếng Anh quan trọng",
         "unit": MetricUnit.STUDENT, "min": 0.0, "max": 2.0, "w": 0.02, "order": 6},

        # Group B — NỀ NẾP VÀ KỶ LUẬT (weight: 0.3)
        {"code": "B", "name": "NỀ NẾP VÀ KỶ LUẬT", "is_group": True, "gw": 0.3, "order": 7},
        {"code": "B1", "name": "Tỷ lệ lên lớp đúng giờ",
         "unit": MetricUnit.PERCENT, "min": 0.9, "max": 1.0, "w": 0.15, "order": 8},
        {"code": "B2", "name": "Tỷ lệ thực hiện tác phong sư phạm (trang phục, cử chỉ...)",
         "unit": MetricUnit.PERCENT, "min": 0.8, "max": 1.0, "w": 0.15, "order": 9},

        # Group C — SỰ THAM GIA CỦA HỌC SINH (weight: 0.2)
        {"code": "C", "name": "SỰ THAM GIA CỦA HỌC SINH", "is_group": True, "gw": 0.2, "order": 10},
        {"code": "C1", "name": "Tỷ lệ HS tiếp tục học vào khóa tiếp theo (retention/renewal)",
         "unit": MetricUnit.PERCENT, "min": 0.6, "max": 1.0, "w": 0.20, "order": 11},

        # Group D — ĐÓNG GÓP SÁNG KIẾN VÀ NGHIÊN CỨU (weight: 0.1)
        {"code": "D", "name": "ĐÓNG GÓP SÁNG KIẾN VÀ NGHIÊN CỨU", "is_group": True, "gw": 0.1, "order": 12},
        {"code": "D1", "name": "Số lượng đóng góp nâng cao phát triển giảng dạy",
         "unit": MetricUnit.COUNT, "min": 0.0, "max": 2.0, "w": 0.025, "order": 13},
        {"code": "D2", "name": "Tỷ lệ tham gia các phong trào của trung tâm",
         "unit": MetricUnit.PERCENT, "min": 0.5, "max": 1.0, "w": 0.05, "order": 14},
        {"code": "D3", "name": "Tham gia tương tác/chia sẻ bài đăng trên mạng xã hội",
         "unit": MetricUnit.COUNT, "min": 0.0, "max": 5.0, "w": 0.025, "order": 15},
    ]

    for m in metrics:
        metric = KPITemplateMetric(
            template_id=template.id,
            metric_code=m["code"],
            metric_name=m["name"],
            is_group_header=m.get("is_group", False),
            unit=m.get("unit"),
            target_min=m.get("min"),
            target_max=m.get("max"),
            weight=m.get("w"),
            group_weight=m.get("gw"),
            sort_order=m["order"],
        )
        db.add(metric)

    return template


def seed_all():
    """Seed both GV and TA templates."""
    db = SessionLocal()
    try:
        # Check if templates already exist
        existing = db.query(KPITemplate).count()
        if existing > 0:
            print(f"[WARN] {existing} template(s) already exist. Skipping seed.")
            return

        gv = seed_teacher_template(db)
        ta = seed_ta_template(db)
        db.commit()

        print(f"[OK] Seeded GV template: {gv.name} (ID: {gv.id})")
        print(f"[OK] Seeded TA template: {ta.name} (ID: {ta.id})")

        # Verify weight sums
        for t in [gv, ta]:
            metrics = [m for m in t.metrics if not m.is_group_header]
            total_weight = sum(float(m.weight or 0) for m in metrics)
            print(f"   {t.name}: {len(metrics)} metrics, total weight = {total_weight}")

    except Exception as e:
        db.rollback()
        print(f"[ERR] Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
