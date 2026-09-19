# Báo cáo Kiểm thử Phân quyền (RBAC Testing)

Dưới đây là kết quả kiểm tra khả năng truy cập (Read/GET và Execute/POST) của từng role đối với các module chính.

## Module: User Management (CRUD)
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:422 |
| CENTER_ADMIN | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| OFFICE_ADMIN | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| TEACHER | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |
| STUDENT | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |
| GUEST | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |

## Module: Course Catalog
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| CENTER_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| OFFICE_ADMIN | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| TEACHER | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| STUDENT | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| GUEST | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |

## Module: Room Management
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| CENTER_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| OFFICE_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| TEACHER | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |
| STUDENT | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |
| GUEST | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |

## Module: Class Lifecycle
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| CENTER_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| OFFICE_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:400 |
| TEACHER | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| STUDENT | ✅ ALLOWED | ❌ FORBIDDEN | GET:200, POST:403 |
| GUEST | ❌ FORBIDDEN | ❌ FORBIDDEN | GET:403, POST:403 |

## Module: Enrollment
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |
| CENTER_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |
| OFFICE_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |
| TEACHER | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |
| STUDENT | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |
| GUEST | ✅ ALLOWED | ✅ ALLOWED | GET:404, POST:404 |

## Module: Audit Logs
| Role | GET (Read) | POST (Execute) | Status Codes |
|---|---|---|---|
| SYSTEM_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:405 |
| CENTER_ADMIN | ✅ ALLOWED | ✅ ALLOWED | GET:200, POST:405 |
| OFFICE_ADMIN | ❌ FORBIDDEN | ✅ ALLOWED | GET:403, POST:405 |
| TEACHER | ❌ FORBIDDEN | ✅ ALLOWED | GET:403, POST:405 |
| STUDENT | ❌ FORBIDDEN | ✅ ALLOWED | GET:403, POST:405 |
| GUEST | ❌ FORBIDDEN | ✅ ALLOWED | GET:403, POST:405 |

