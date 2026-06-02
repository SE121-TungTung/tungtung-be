"""
End-to-end test script for the Lotus KPI system.
Tests the full flow: login → templates → period → metrics → calculate → submit → approve
"""

import requests
import json

BASE = "http://localhost:8000/api/v1"

def log(step, response):
    status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = response.text
    success = body.get("success", False) if isinstance(body, dict) else False
    indicator = "[OK]" if success else "[FAIL]"
    print(f"\n{indicator} Step: {step} (HTTP {status})")
    if not success:
        print(f"   Response: {json.dumps(body, indent=2, default=str)[:500]}")
    return body


# ===== 1. LOGIN AS ADMIN =====
print("=" * 60)
print("LOTUS KPI END-TO-END TEST")
print("=" * 60)

r = requests.post(f"{BASE}/auth/login-json", json={
    "email": "admin@lotus.edu.vn",
    "password": "admin123"
})
body = log("Login as Admin", r)
TOKEN = body["data"]["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# ===== 2. LIST TEMPLATES =====
r = requests.get(f"{BASE}/kpi/templates", headers=HEADERS)
body = log("List KPI Templates", r)
templates = body["data"]
print(f"   Found {len(templates)} templates")

gv_template_id = None
ta_template_id = None
for t in templates:
    print(f"   - {t['name']} (contract: {t['contract_type']}, bonus: {t['max_bonus_amount']}, type: {t['bonus_type']})")
    if t["contract_type"] == "FULL_TIME":
        gv_template_id = t["id"]
    else:
        ta_template_id = t["id"]

# ===== 3. GET TEMPLATE DETAIL WITH METRICS =====
r = requests.get(f"{BASE}/kpi/templates/{gv_template_id}", headers=HEADERS)
body = log("Get GV Template Detail", r)
metrics = body["data"]["metrics"]
print(f"   GV template has {len(metrics)} metrics")
for m in metrics:
    if m["is_group_header"]:
        print(f"   [{m['metric_code']}] {m['metric_name']} (group weight: {m.get('group_weight')})")
    else:
        print(f"     {m['metric_code']}: {m['metric_name']} | min={m.get('target_min')} max={m.get('target_max')} weight={m.get('weight')}")

# ===== 4. CREATE A KPI PERIOD =====
r = requests.post(f"{BASE}/kpi/periods", headers=HEADERS, json={
    "name": "Ky 1 - 2025",
    "period_type": "SEMESTER",
    "start_date": "2025-01-01",
    "end_date": "2025-06-30"
})
body = log("Create KPI Period", r)
period_data = body["data"]
period_id = period_data["period"]["id"]
print(f"   Period ID: {period_id}")
print(f"   Records created: {period_data['records_created']}")
if period_data.get("skipped"):
    print(f"   Skipped: {period_data['skipped']}")

# ===== 5. GET PERIOD DETAIL =====
r = requests.get(f"{BASE}/kpi/periods/{period_id}", headers=HEADERS)
body = log("Get Period Detail", r)
print(f"   Total records: {body['data']['total_records']}")
print(f"   Draft: {body['data']['draft_count']}, Submitted: {body['data']['submitted_count']}, Approved: {body['data']['approved_count']}")

# ===== 6. LIST RECORDS =====
r = requests.get(f"{BASE}/kpi/records", headers=HEADERS, params={"period_id": period_id})
body = log("List KPI Records", r)
records = body["data"]
print(f"   Found {len(records)} records")
for rec in records:
    print(f"   - {rec['staff_name']} ({rec.get('staff_contract','N/A')}) | status: {rec['approval_status']}")

if not records:
    print("\n[STOP] No records found. Exiting.")
    exit(1)

record_id = records[0]["id"]
staff_name = records[0]["staff_name"]
print(f"\n   Testing with record: {record_id} ({staff_name})")

# ===== 7. GET RECORD DETAIL =====
r = requests.get(f"{BASE}/kpi/records/{record_id}", headers=HEADERS)
body = log("Get Record Detail (before input)", r)
detail = body["data"]
print(f"   Metrics count: {len(detail['metrics'])}")
print(f"   Total score: {detail['total_score']}")
print(f"   Status: {detail['approval_status']}")

# ===== 8. ENTER METRIC VALUES (Excel sample data) =====
sample_data = [
    {"metric_code": "A1", "actual_value": 0.31},   # Below min -> 0
    {"metric_code": "A2", "actual_value": 0.06},   # Linear interpolation
    {"metric_code": "A3", "actual_value": 1.0},    # Full
    {"metric_code": "A4", "actual_value": 1.0},    # Full
    {"metric_code": "A5", "actual_value": 1.0},    # Full
    {"metric_code": "A6", "actual_value": 2.0},    # Full (student)
    {"metric_code": "B1", "actual_value": 1.0},    # Full
    {"metric_code": "B2", "actual_value": 1.0},    # Full
    {"metric_code": "C1", "actual_value": 1.0},    # Full
    {"metric_code": "D1", "actual_value": 2.0},    # Full (count)
    {"metric_code": "D2", "actual_value": 1.0},    # Full
    {"metric_code": "D3", "actual_value": 5.0},    # Full (count)
]

r = requests.put(
    f"{BASE}/kpi/records/{record_id}/metrics",
    headers=HEADERS,
    json={"metrics": sample_data}
)
body = log("Enter Metric Values (Excel sample)", r)
detail = body["data"]
print(f"   Total score: {detail['total_score']}")
print(f"   Bonus amount: {detail['bonus_amount']}")
print(f"   Teaching hours: {detail['teaching_hours']}")

# Print metric breakdown
for m in detail["metrics"]:
    if m["is_group_header"]:
        print(f"   [{m['metric_code']}] {m['metric_name']}: {m.get('converted_score', 'N/A')}")
    elif m.get("actual_value") is not None:
        print(f"     {m['metric_code']}: actual={m['actual_value']} -> score={m.get('converted_score', 'N/A')} {m.get('note', '')}")

# ===== 9. SUPPORT CALCULATOR (pure calculation) =====
r = requests.post(f"{BASE}/kpi/support/score-calculator", headers=HEADERS, json={
    "class_size": 32,
    "max_score": 9,
    "avg_threshold": 4.5,
    "above_avg_count": 10,
    "high_threshold": 7.0,
    "above_high_count": 2
})
body = log("Support Calculator (pure)", r)
print(f"   Rate above avg (A1): {body['data']['rate_above_avg']}")
print(f"   Rate above high (A2): {body['data']['rate_above_high']}")
print(f"   Breakdown: {body['data']['breakdown']}")

# ===== 10. SUBMIT RECORD =====
r = requests.post(f"{BASE}/kpi/records/{record_id}/submit", headers=HEADERS)
body = log("Submit Record for Approval", r)
print(f"   New status: {body['data']['approval_status']}")

# ===== 11. GET APPROVAL LOG =====
r = requests.get(f"{BASE}/kpi/records/{record_id}/approval-log", headers=HEADERS)
body = log("Get Approval Log", r)
print(f"   Log entries: {len(body['data'])}")
for entry in body["data"]:
    print(f"   - {entry['action']} at {entry['created_at']}: {entry.get('comment', '')}")

# ===== 12. APPROVE RECORD =====
r = requests.post(f"{BASE}/kpi/records/{record_id}/approve", headers=HEADERS)
body = log("Approve Record", r)
print(f"   New status: {body['data']['approval_status']}")
print(f"   Approved at: {body['data']['approved_at']}")

# ===== 13. DASHBOARD =====
r = requests.get(f"{BASE}/kpi/dashboard", headers=HEADERS, params={"period_id": period_id})
body = log("Get Dashboard", r)
dash = body["data"]
print(f"   Total staff: {dash['total_staff']}")
print(f"   Teachers: {dash['total_teachers']}, TAs: {dash['total_ta']}")
print(f"   Avg score: {dash['avg_score']}")
print(f"   Total bonus: {dash['total_bonus_amount']}")
print(f"   Approved: {dash['approved_count']}, Draft: {dash['draft_count']}")

# ===== 14. RANKING =====
r = requests.get(f"{BASE}/kpi/reports/period/{period_id}/ranking", headers=HEADERS)
body = log("Get Ranking", r)
for item in body["data"]:
    print(f"   #{item['rank']} {item['staff_name']} | score={item['total_score']} | bonus={item['bonus_amount']}")

# ===== 15. VERIFY: TRY TO EDIT APPROVED RECORD (should fail) =====
r = requests.put(
    f"{BASE}/kpi/records/{record_id}/metrics",
    headers=HEADERS,
    json={"metrics": [{"metric_code": "A1", "actual_value": 0.5}]}
)
body = log("Try Edit Approved Record (expect 400)", r)

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
