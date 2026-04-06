import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from uuid import uuid4
import math

from app.main import app

# Create a TestClient instance
client = TestClient(app, base_url="http://testserver/api/v1")

from app.models.user import UserStatus, UserRole
# Fake Users for Role Based Auth
def create_mock_user(role=UserRole.SYSTEM_ADMIN):
    user = MagicMock()
    user.id = uuid4()
    user.role = role.value
    user.status = UserStatus.ACTIVE
    return user

system_admin = create_mock_user(UserRole.SYSTEM_ADMIN)
center_admin = create_mock_user(UserRole.CENTER_ADMIN)
teacher = create_mock_user(UserRole.TEACHER)

def override_get_current_user_sysadmin():
    return system_admin

def override_get_current_user_centeradmin():
    return center_admin

def override_get_current_user_teacher():
    return teacher

# Patch dependencies in tests using dependency overrides
# We mock get_current_user and we also mock Kpi*Services.

@pytest.fixture
def override_sysadmin():
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user_sysadmin
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def override_centeradmin():
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user_centeradmin
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def override_teacher():
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user_teacher
    yield
    app.dependency_overrides.clear()

# =============================================================================
# Nhóm 1: Cấu hình hệ thống (KPI Tiers & Payroll Config)
# =============================================================================

@patch('app.routers.kpi.KpiSettingsService')
def test_tc01_update_kpi_tiers_sysadmin(mock_service_class, override_sysadmin):
    """TC-01: Cập nhật KPI Tiers - Trả về list tiers mới"""
    mock_service_inst = mock_service_class.return_value
    mock_service_inst.bulk_update_tiers.return_value = [
        {"id": 1, "tier_name": "S", "min_score": 95, "max_score": 100, "reward_percentage": 20, "reward_per_lesson": 0, "status": "ACTIVE"}
    ]

    payload = [
        {"id": 1, "tier_name": "S", "min_score": 95, "max_score": 100, "reward_percentage": 20, "reward_per_lesson": 0}
    ]
    response = client.put("/settings/kpi-tiers", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["data"][0]["tier_name"] == "S"

@patch('app.routers.kpi.KpiSettingsService')
def test_tc01_update_kpi_tiers_invalid_payload(mock_service_class, override_sysadmin):
    """TC-01_Error: % thưởng âm hoặc tổng không logic"""
    # Test validation payload
    payload = [
        {"id": 1, "tier_name": "S", "min_score": 95, "max_score": 100, "reward_percentage": -10, "reward_per_lesson": 0}
    ]
    response = client.put("/settings/kpi-tiers", json=payload)
    # Pydantic validation error expected for negative percentage
    assert response.status_code == 422 

@patch('app.routers.kpi.KpiSettingsService')
def test_tc01_update_kpi_tiers_center_admin_forbidden(mock_service_class, override_centeradmin):
    """TC-01_Error: Role center_admin cố tình update"""
    # Assuming role middleware throws 403. Our mock is simple so let's just make sure it fails if role isn't system_admin.
    # Note: In FastAPI require_role depends might just throw an HTTPException.
    # Since we apply override_centeradmin, require_role("system_admin") should raise 403
    payload = [
        {"id": 1, "tier_name": "S", "min_score": 95, "max_score": 100, "reward_percentage": 20, "reward_per_lesson": 0}
    ]
    response = client.put("/settings/kpi-tiers", json=payload)
    # Actually require_role receives the current_user, so if current user is center_admin but require_role expects system_admin it throws 403
    assert response.status_code in [403, 401] # Depends on exact implementation in dependencies.py

@patch('app.routers.kpi.TeacherPayrollConfigService')
def test_tc02_update_payroll_config(mock_service_class, override_centeradmin):
    """TC-02: Cấu hình lương GV"""
    mock_service_inst = mock_service_class.return_value
    teacher_id = str(uuid4())
    mock_service_inst.update_config.return_value = {
        "teacher_id": teacher_id, "contract_type": "FULL_TIME", 
        "base_salary": 10000000, "lesson_rate": 0, "max_kpi_bonus": 2000000, "fixed_allowance": 500000, "updated_at": "2024-03-01T00:00:00Z"
    }
    
    payload = {
        "contract_type": "FULL_TIME",
        "base_salary": 10000000,
        "lesson_rate": 0,
        "max_kpi_bonus": 2000000,
        "fixed_allowance": 500000
    }
    response = client.put(f"/teachers/{teacher_id}/payroll-config", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert response.json()["data"]["base_salary"] == 10000000

@patch('app.routers.kpi.TeacherPayrollConfigService')
def test_tc02_update_payroll_config_invalid_type(mock_service_class, override_centeradmin):
    """TC-02_Error: Nhập chữ vào field số"""
    teacher_id = str(uuid4())
    payload = {
        "contract_type": "FULL_TIME",
        "base_salary": "Mười triệu", # Invalid
        "lesson_rate": 0,
        "max_kpi_bonus": 2000000,
        "fixed_allowance": 500000
    }
    response = client.put(f"/teachers/{teacher_id}/payroll-config", json=payload)
    assert response.status_code == 422


# =============================================================================
# Nhóm 2: Xử lý dữ liệu & Tính toán (Metrics & Jobs)
# =============================================================================

@patch('app.routers.kpi.KpiMetricService')
def test_tc03_sync_raw_metrics(mock_service_class, override_sysadmin):
    """TC-03: Sync Raw Metrics - Trả về thành công"""
    mock_service_inst = mock_service_class.return_value
    mock_service_inst.sync_metrics.return_value = "Thành công"
    
    payload = {
        "teacher_id": str(uuid4()),
        "period": "2024-03",
        "source_module": "ATTENDANCE",
        "metric_data": {"lessons_taught": 25, "late_count": 0}
    }
    response = client.post("/kpi/metrics/sync", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] == True

@patch('app.routers.kpi.KpiCalculationService')
def test_tc04_trigger_kpi_job(mock_service_class, override_centeradmin):
    """TC-04: Trigger KPI Job - status pending"""
    mock_service_inst = mock_service_class.return_value
    job_id = str(uuid4())
    mock_service_inst.trigger_calculation_job.return_value = {
        "job_id": job_id, "period": "2024-03", "status": "PENDING",
        "total_teachers": 0, "processed_count": 0, "started_at": "2024-03-01T00:00:00Z"
    }

    payload = {"period": "2024-03", "teacher_ids": []}
    response = client.post("/kpi/calculation-jobs", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == job_id
    assert response.json()["data"]["status"] == "PENDING"

@patch('app.routers.kpi.KpiCalculationService')
def test_tc05_check_job_progress(mock_service_class, override_centeradmin):
    """TC-05: Kiểm tra tiến độ job"""
    mock_service_inst = mock_service_class.return_value
    job_id = str(uuid4())
    mock_service_inst.get_job.return_value = {
        "job_id": job_id, "period": "2024-03", "status": "COMPLETED", 
        "total_teachers": 10, "processed_count": 10, "started_at": "2024-03-01T00:00:00Z"
    }

    response = client.get(f"/kpi/calculation-jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "COMPLETED"


# =============================================================================
# Nhóm 3: Kiểm soát lương & Phê duyệt (Salaries)
# =============================================================================

@patch('app.routers.kpi.SalaryService')
def test_tc06_salary_adjustment(mock_service_class, override_centeradmin):
    """TC-06: Điều chỉnh lương"""
    mock_service_inst = mock_service_class.return_value
    adj_id = str(uuid4())
    mock_service_inst.add_adjustment.return_value = {
        "id": adj_id, "salary_id": str(uuid4()), "adjustment_type": "ALLOWANCE", "amount": 500000, "reason": "Thưởng nóng", "created_at": "2024-03-01T00:00:00Z"
    }

    payload = {
        "adjustment_type": "ALLOWANCE",
        "amount": 500000,
        "reason": "Thưởng nóng"
    }
    salary_id = str(uuid4())
    response = client.patch(f"/salaries/{salary_id}/adjustments", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["amount"] == 500000

@patch('app.routers.kpi.SalaryService')
def test_tc07_approve_salary(mock_service_class, override_centeradmin):
    """TC-07: Phê duyệt lương"""
    mock_service_inst = mock_service_class.return_value
    salary_id = str(uuid4())
    mock_service_inst.approve.return_value = {
        "id": salary_id, 
        "teacher_id": str(uuid4()),
        "period": "2024-03",
        "contract_type": "FULL_TIME",
        "lesson_count": 0,
        "base_salary_calc": 10000000,
        "kpi_bonus_calc": 5000000,
        "fixed_allowance": 0,
        "total_adjustments": 0,
        "status": "APPROVED", 
        "net_salary": 15000000
    }

    response = client.post(f"/salaries/{salary_id}/approve")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPROVED"

@patch('app.routers.kpi.SalaryService')
def test_tc08_view_salary_history_teacher(mock_service_class, override_teacher):
    """TC-08: Xem lịch sử lương (Teacher Me)"""
    mock_service_inst = mock_service_class.return_value
    mock_service_inst.get_history.return_value = ([
        {
            "id": str(uuid4()), 
            "teacher_id": str(uuid4()),
            "period": "2024-02", 
            "contract_type": "FULL_TIME",
            "lesson_count": 0,
            "base_salary_calc": 10000000,
            "kpi_bonus_calc": 4000000,
            "fixed_allowance": 0,
            "total_adjustments": 0,
            "net_salary": 14000000, 
            "status": "APPROVED"
        }
    ], 1)

    response = client.get("/teachers/me/salary-history?period=2024-02")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["period"] == "2024-02"


# =============================================================================
# Nhóm 4: Khiếu nại (KPI Dispute)
# =============================================================================

@patch('app.routers.kpi.KpiDisputeService')
def test_tc09_submit_dispute(mock_service_class, override_teacher):
    """TC-09: Gửi khiếu nại - Status Open/Pending"""
    mock_service_inst = mock_service_class.return_value
    mock_service_inst.create_dispute.return_value = {
        "id": str(uuid4()), "kpi_id": str(uuid4()), "teacher_id": str(uuid4()), "status": "PENDING", "reason": "Thiếu điểm chuyên cần", "created_at": "2024-03-01T00:00:00Z"
    }

    payload = {
        "kpi_id": str(uuid4()),
        "reason": "Thiếu điểm chuyên cần"
    }
    response = client.post("/kpi/dispute", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING"

@patch('app.routers.kpi.KpiDisputeService')
def test_tc10_resolve_dispute(mock_service_class, override_centeradmin):
    """TC-10: Giải quyết khiếu nại - Status Resolved"""
    mock_service_inst = mock_service_class.return_value
    dispute_id = str(uuid4())
    mock_service_inst.resolve_dispute.return_value = {
        "id": dispute_id, 
        "kpi_id": str(uuid4()),
        "teacher_id": str(uuid4()),
        "reason": "Thiếu điểm chuyên cần",
        "status": "RESOLVED", 
        "resolution_note": "Đã cộng lại điểm",
        "created_at": "2024-03-01T00:00:00Z"
    }

    payload = {
        "status": "RESOLVED",
        "resolution_note": "Đã cộng lại điểm"
    }
    response = client.put(f"/kpi/dispute/{dispute_id}/resolve", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RESOLVED"
    
