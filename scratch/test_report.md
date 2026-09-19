# Tóm tắt kết quả Test Hệ Thống (GET Endpoints)

## Module: Untagged
- **Working:** 2 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET / -> 200`
- `GET /health -> 200`

## Module: Users
- **Working:** 5 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/users/me -> 200`
- `GET /api/v1/users -> 200`
- `GET /api/v1/users/overview -> 200`
- `GET /api/v1/users/{user_id} -> 404`
- `GET /api/v1/users/me/classes -> 200`

## Module: Rooms
- **Working:** 3 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/rooms -> 200`
- `GET /api/v1/rooms/{id} -> 404`
- `GET /api/v1/available -> 200`

## Module: Courses
- **Working:** 4 endpoints
- **Failing:** 1 endpoints

### Working Details
- `GET /api/v1/courses -> 200`
- `GET /api/v1/courses/{id} -> 404`
- `GET /api/v1/active -> 200`
- `GET /api/v1/search -> 422`

### Failing Details
- `GET /api/v1/by-level/{level} -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Classes
- **Working:** 2 endpoints
- **Failing:** 1 endpoints

### Working Details
- `GET /api/v1/classes/{class_id} -> 404`
- `GET /api/v1/teacher/classes -> 403`

### Failing Details
- `GET /api/v1/classes -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Class Enrollment
- **Working:** 2 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/classenrollments -> 200`
- `GET /api/v1/classenrollments/{enrollment_id} -> 404`

## Module: Class Session
- **Working:** 1 endpoints
- **Failing:** 1 endpoints

### Working Details
- `GET /api/v1/classsessions/{id} -> 404`

### Failing Details
- `GET /api/v1/classsessions -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Attendance
- **Working:** 4 endpoints
- **Failing:** 2 endpoints

### Working Details
- `GET /api/v1/sessions/{session_id}/attendance -> 404`
- `GET /api/v1/classes/{class_id}/attendance/stats -> 404`
- `GET /api/v1/attendance/config -> 200`
- `GET /api/v1/enrollments/{enrollment_id}/certificate-eligibility -> 404`

### Failing Details
- `GET /api/v1/classes/{class_id}/attendance/students -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`
- `GET /api/v1/attendance/alerts -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Schedule Management
- **Working:** 1 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/schedule/weekly -> 200`

## Module: GA Schedule Optimizer
- **Working:** 3 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/schedule/ga/runs -> 200`
- `GET /api/v1/schedule/ga/runs/{run_id} -> 404`
- `GET /api/v1/schedule/ga/teacher-unavailability -> 200`

## Module: Messaging
- **Working:** 5 endpoints
- **Failing:** 1 endpoints

### Working Details
- `GET /api/v1/messaging/rooms/{room_id}/history -> 404`
- `GET /api/v1/messaging/conversations/all -> 200`
- `GET /api/v1/messaging/groups/{room_id} -> 404`
- `GET /api/v1/messaging/search-messages -> 422`
- `GET /api/v1/messaging/unread-count -> 200`

### Failing Details
- `GET /api/v1/messaging/conversations/direct/{other_user_id} -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Tests
- **Working:** 7 endpoints
- **Failing:** 2 endpoints

### Working Details
- `GET /api/v1/tests/speaking/random-part1 -> 200`
- `GET /api/v1/tests/{test_id} -> 404`
- `GET /api/v1/tests/{test_id}/dictation-segments -> 404`
- `GET /api/v1/tests/admin/{test_id} -> 404`
- `GET /api/v1/tests/{test_id}/attempts -> 404`
- `GET /api/v1/tests/attempts/{attempt_id} -> 404`
- `GET /api/v1/tests/attempts/{attempt_id}/teacher -> 403`

### Failing Details
- `GET /api/v1/tests -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`
- `GET /api/v1/tests/student -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Notifications
- **Working:** 2 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/notifications -> 200`
- `GET /api/v1/notifications/unread-count -> 200`

## Module: KPI & Payroll
- **Working:** 22 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/kpi/templates -> 200`
- `GET /api/v1/kpi/templates/{template_id} -> 404`
- `GET /api/v1/kpi/templates/{template_id}/metrics -> 404`
- `GET /api/v1/kpi/periods -> 200`
- `GET /api/v1/kpi/periods/{period_id} -> 404`
- `GET /api/v1/kpi/records -> 200`
- `GET /api/v1/kpi/records/me -> 422`
- `GET /api/v1/kpi/records/{record_id} -> 404`
- `GET /api/v1/kpi/records/{record_id}/approval-log -> 404`
- `GET /api/v1/kpi/records/{record_id}/support-calcs -> 200`
- `GET /api/v1/kpi/dashboard -> 422`
- `GET /api/v1/kpi/reports/period/{period_id}/ranking -> 200`
- `GET /api/v1/kpi/reports/staff/{staff_id}/history -> 200`
- `GET /api/v1/teachers/me/kpi -> 422`
- `GET /api/v1/teachers/{teacher_id}/kpi-history -> 200`
- `GET /api/v1/teachers/{teacher_id}/payroll-config -> 404`
- `GET /api/v1/teachers/me/salary-history -> 200`
- `GET /api/v1/teachers/{teacher_id}/salary-history -> 200`
- `GET /api/v1/payroll-runs -> 200`
- `GET /api/v1/payroll-runs/{run_id} -> 404`
- `GET /api/v1/salaries -> 200`
- `GET /api/v1/salaries/{salary_id} -> 404`

## Module: Invoices
- **Working:** 3 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/invoices -> 200`
- `GET /api/v1/invoices/me -> 200`
- `GET /api/v1/invoices/{invoice_id} -> 404`

## Module: Payments
- **Working:** 2 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/payments -> 200`
- `GET /api/v1/payments/{payment_id}/receipt -> 404`

## Module: Reports
- **Working:** 4 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/reports/revenue -> 200`
- `GET /api/v1/reports/expenses -> 200`
- `GET /api/v1/reports/profit -> 200`
- `GET /api/v1/reports/debts -> 200`

## Module: Refunds
- **Working:** 1 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/refunds/calculate -> 422`

## Module: Audit Logs
- **Working:** 0 endpoints
- **Failing:** 1 endpoints

### Failing Details
- `GET /api/v1/audit-logs -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Recommendations
- **Working:** 2 endpoints
- **Failing:** 1 endpoints

### Working Details
- `GET /api/v1/recommendations/today -> 200`
- `GET /api/v1/recommendations/learning-path -> 200`

### Failing Details
- `GET /api/v1/recommendations/history -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Substitutions
- **Working:** 0 endpoints
- **Failing:** 1 endpoints

### Failing Details
- `GET /api/v1/substitutions -> 500 {"success":false,"error":{"code":"INTERNAL_SERVER_ERROR","message":"Unexpected server error","detail`

## Module: Certificates
- **Working:** 1 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/certificates/students/{student_id} -> 200`

## Module: Vocabulary
- **Working:** 1 endpoints
- **Failing:** 0 endpoints

### Working Details
- `GET /api/v1/vocabulary/my-words -> 200`

