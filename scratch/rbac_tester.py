import json
from fastapi.testclient import TestClient
from app.main import app

def run_rbac_test():
    client = TestClient(app)
    
    roles = [
        "system_admin", "center_admin", "office_admin",
        "teacher", "student", "guest"
    ]
    
    # Mappings of roles to email to login
    users = {role: f"{role}@test.com" for role in roles}
    password = "Password@123"
    
    tokens = {}
    print("Logging in users...")
    for role, email in users.items():
        resp = client.post("/api/v1/auth/login-json", json={"email": email, "password": password})
        if resp.status_code == 200:
            tokens[role] = resp.json().get("data", {}).get("access_token")
            print(f"[{role}] Login successful.")
        else:
            print(f"[{role}] Login failed! {resp.status_code}")
            tokens[role] = None

    # Endpoints to test and expected behavior
    # We will test GET and POST to see if they are forbidden (403) or allowed (2xx, 404, 422).
    # Allowed means it passed RBAC.
    
    endpoints = [
        {"path": "/api/v1/users", "name": "User Management (CRUD)"},
        {"path": "/api/v1/courses", "name": "Course Catalog"},
        {"path": "/api/v1/rooms", "name": "Room Management"},
        {"path": "/api/v1/classes", "name": "Class Lifecycle"},
        {"path": "/api/v1/enrollments", "name": "Enrollment"},
        {"path": "/api/v1/audit-logs", "name": "Audit Logs"}
    ]
    
    results = {}
    
    dummy_uuid = "00000000-0000-0000-0000-000000000000"
    
    print("\nRunning RBAC tests...")
    for endpoint in endpoints:
        path = endpoint["path"]
        name = endpoint["name"]
        results[name] = {}
        
        for role in roles:
            token = tokens.get(role)
            if not token:
                continue
            
            headers = {"Authorization": f"Bearer {token}"}
            
            # Test GET (Read)
            get_code = 500
            get_allowed = False
            try:
                get_resp = client.get(path, headers=headers)
                get_code = get_resp.status_code
                get_allowed = get_code not in (401, 403)
            except Exception as e:
                print(f"Exception on GET {path}: {e}")
                
            # Test POST (Execute/Create)
            post_code = 500
            post_allowed = False
            try:
                post_resp = client.post(path, json={}, headers=headers)
                post_code = post_resp.status_code
                post_allowed = post_code not in (401, 403)
            except Exception as e:
                print(f"Exception on POST {path}: {e}")
            
            results[name][role] = {
                "GET": "ALLOWED" if get_allowed else "FORBIDDEN",
                "POST": "ALLOWED" if post_allowed else "FORBIDDEN",
                "GET_CODE": get_code,
                "POST_CODE": post_code
            }
            
    # Generate Report
    print("\nWriting report...")
    with open("scratch/rbac_report.md", "w", encoding="utf-8") as f:
        f.write("# Báo cáo Kiểm thử Phân quyền (RBAC Testing)\n\n")
        f.write("Dưới đây là kết quả kiểm tra khả năng truy cập (Read/GET và Execute/POST) của từng role đối với các module chính.\n\n")
        
        for name, role_data in results.items():
            f.write(f"## Module: {name}\n")
            f.write("| Role | GET (Read) | POST (Execute) | Status Codes |\n")
            f.write("|---|---|---|---|\n")
            for role in roles:
                data = role_data.get(role)
                if data:
                    g_icon = "✅" if data["GET"] == "ALLOWED" else "❌"
                    p_icon = "✅" if data["POST"] == "ALLOWED" else "❌"
                    f.write(f"| {role.upper()} | {g_icon} {data['GET']} | {p_icon} {data['POST']} | GET:{data['GET_CODE']}, POST:{data['POST_CODE']} |\n")
            f.write("\n")
            
    print("Test completed! Report saved to scratch/rbac_report.md")

if __name__ == "__main__":
    run_rbac_test()
