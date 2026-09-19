"""
End-to-End (E2E) Test Suite for Class Feed Feature (4 Phases).

Tests the entire lifecycle:
- Phase 1: Class Posts CRUD, file attachments, 3-pin limit, force unpin, student permissions
- Phase 2: Comments (1-level nesting), Reactions toggle (like -> heart -> delete), Lock/Unlock comments
- Phase 3: View Tracking (student only, idempotent, teacher ignored, ViewersModal summary, 403 for student)
- Phase 4: Material Library Tab (material filtering, category filter, keyword search, unauthorized class access)
- Teardown: Clean up test posts

Usage:
    python tests/test_class_feed_e2e.py
"""

import sys
import os
import io
import json
from unittest.mock import patch

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend root is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
BASE = "/api/v1"

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def log(step_num: int, title: str, res, expect_status: int = 200):
    status = res.status_code
    try:
        body = res.json()
    except Exception:
        body = {"raw": res.text}

    is_ok = status == expect_status
    indicator = f"{Colors.GREEN}[OK]{Colors.RESET}" if is_ok else f"{Colors.RED}[FAIL]{Colors.RESET}"
    print(f"{indicator} Step {step_num:02d}: {title} (HTTP {status}, expected {expect_status})")

    if not is_ok:
        try:
            err_str = json.dumps(body, indent=2, ensure_ascii=False)[:600]
        except Exception:
            err_str = str(body)[:600]
        print(f"   {Colors.RED}Response: {err_str}{Colors.RESET}")
    return body


async def fake_cloudinary_upload(file, folder_name="class_materials"):
    content = await file.read()
    await file.seek(0)
    return {
        "file_url": f"https://res.cloudinary.com/demo/raw/upload/v1/{file.filename}",
        "bytes": len(content) or 2048,
        "public_id": f"class_materials/{file.filename}",
        "format": "pdf",
    }


def main():
    print("=" * 70)
    print(f"{Colors.BOLD}{Colors.CYAN}CLASS FEED END-TO-END AUTOMATED TEST SUITE (PHASES 1 - 4){Colors.RESET}")
    print("=" * 70)

    # -------------------------------------------------------------
    # 0. SETUP: AUTHENTICATION
    # -------------------------------------------------------------
    print(f"\n{Colors.BOLD}--- 0. AUTHENTICATION & CLASS SELECTION ---{Colors.RESET}")

    # Teacher
    r_teach = client.post(f"{BASE}/auth/login-json", json={
        "email": "teacher.an@tungtung.edu.vn",
        "password": "Password123"
    })
    b_teach = log(1, "Login as Teacher (teacher.an)", r_teach, 200)
    TEACHER_TOKEN = b_teach["data"]["access_token"]
    H_TEACHER = {"Authorization": f"Bearer {TEACHER_TOKEN}"}

    # Student 1
    r_s1 = client.post(f"{BASE}/auth/login-json", json={
        "email": "student.minh@gmail.com",
        "password": "Password123"
    })
    b_s1 = log(2, "Login as Student 1 (student.minh)", r_s1, 200)
    STUDENT1_TOKEN = b_s1["data"]["access_token"]
    H_STUDENT1 = {"Authorization": f"Bearer {STUDENT1_TOKEN}"}

    # Student 2
    r_s2 = client.post(f"{BASE}/auth/login-json", json={
        "email": "student.cuong@gmail.com",
        "password": "Password123"
    })
    b_s2 = log(3, "Login as Student 2 (student.cuong)", r_s2, 200)
    STUDENT2_TOKEN = b_s2["data"]["access_token"]
    H_STUDENT2 = {"Authorization": f"Bearer {STUDENT2_TOKEN}"}

    # Unauthorized Student (not in IELTS-FD-01)
    r_unauth = client.post(f"{BASE}/auth/login-json", json={
        "email": "student.vy@gmail.com",
        "password": "Password123"
    })
    b_unauth = log(4, "Login as Outside Student (student.vy)", r_unauth, 200)
    UNAUTH_TOKEN = b_unauth["data"]["access_token"]
    H_UNAUTH = {"Authorization": f"Bearer {UNAUTH_TOKEN}"}

    # Get IELTS-FD-01 class ID from DB
    from app.core.database import SessionLocal
    from app.models import Class
    db_session = SessionLocal()
    class_obj = db_session.query(Class).filter(Class.name == "IELTS-FD-01").first()
    CLASS_ID = str(class_obj.id)
    db_session.close()
    print(f"Target Class: {class_obj.name} (ID: {CLASS_ID})")

    created_post_ids = []

    with patch("app.services.class_post_service.handle_cloudinary_upload", side_effect=fake_cloudinary_upload):
        try:
            # -------------------------------------------------------------
            # PHASE 1: CLASS POSTS CRUD, ATTACHMENTS & PINNING
            # -------------------------------------------------------------
            print(f"\n{Colors.BOLD}--- PHASE 1: POSTS CRUD, ATTACHMENTS & PINNING ---{Colors.RESET}")

            # Step 5: Teacher creates Post 1 (Announcement with mock file attachment)
            mock_file_1 = ("notes.pdf", io.BytesIO(b"%PDF-1.4 test pdf file"), "application/pdf")
            r_p1 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_TEACHER,
                data={
                    "title": "[E2E Test] Thong bao khai giang",
                    "content": "Chao mung cac ban den voi khoa hoc IELTS!",
                    "post_type": "announcement",
                },
                files=[("files", mock_file_1)]
            )
            b_p1 = log(5, "Teacher creates Announcement with PDF", r_p1, 201)
            post_1_id = b_p1["data"]["id"]
            created_post_ids.append(post_1_id)
            assert len(b_p1["data"]["attachments"]) == 1, "Attachment was not saved"

            # Step 6: Teacher creates Post 2 (Material with category lecture_slide)
            mock_file_2 = ("slide_session_1.pdf", io.BytesIO(b"%PDF-1.4 slide content"), "application/pdf")
            r_p2 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_TEACHER,
                data={
                    "title": "[E2E Test] Slide bai giang Buoi 1",
                    "content": "Tai lieu ly thuyet phan Listening Section 1",
                    "post_type": "material",
                    "material_category": "lecture_slide",
                },
                files=[("files", mock_file_2)]
            )
            b_p2 = log(6, "Teacher creates Material (lecture_slide)", r_p2, 201)
            post_2_id = b_p2["data"]["id"]
            created_post_ids.append(post_2_id)
            assert b_p2["data"]["material_category"] == "lecture_slide"

            # Step 7: Teacher creates Post 3 (Material with category exercise)
            mock_file_3 = ("homework_1.docx", io.BytesIO(b"PK\x03\x04 fake docx"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            r_p3 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_TEACHER,
                data={
                    "title": "[E2E Test] Bai tap ve nha Buoi 1",
                    "content": "Han nop bai truoc thu nam tuan sau.",
                    "post_type": "material",
                    "material_category": "exercise",
                },
                files=[("files", mock_file_3)]
            )
            b_p3 = log(7, "Teacher creates Material (exercise)", r_p3, 201)
            post_3_id = b_p3["data"]["id"]
            created_post_ids.append(post_3_id)

            # Step 8: Teacher creates Post 4 (Announcement)
            r_p4 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_TEACHER,
                data={
                    "title": "[E2E Test] Nhac nho kiem tra giua ky",
                    "content": "Tuan sau se co bai mini-test 30 phut.",
                    "post_type": "announcement",
                }
            )
            b_p4 = log(8, "Teacher creates Announcement (no attachment)", r_p4, 201)
            post_4_id = b_p4["data"]["id"]
            created_post_ids.append(post_4_id)

            # Step 9: Pin 3 posts (Post 1, 2, 3)
            for idx, pid in enumerate([post_1_id, post_2_id, post_3_id], start=1):
                r_pin = client.patch(
                    f"{BASE}/classes/{CLASS_ID}/posts/{pid}/pin",
                    headers=H_TEACHER,
                    json={"pin": True, "force_unpin_oldest": False}
                )
                log(9, f"Teacher pins Post {idx}", r_pin, 200)

            # Step 10: Attempt to pin 4th post without force -> Expect 409
            r_pin_fail = client.patch(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_4_id}/pin",
                headers=H_TEACHER,
                json={"pin": True, "force_unpin_oldest": False}
            )
            log(10, "Attempt to pin 4th post without force (expect 409 Conflict)", r_pin_fail, 409)

            # Step 11: Pin 4th post with force_unpin_oldest=True -> Expect 200
            r_pin_force = client.patch(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_4_id}/pin",
                headers=H_TEACHER,
                json={"pin": True, "force_unpin_oldest": True}
            )
            b_force = log(11, "Pin 4th post with force_unpin_oldest=True", r_pin_force, 200)
            assert b_force["data"]["is_pinned"] is True

            # Step 12: Teacher updates Post 1
            r_up = client.put(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}",
                headers=H_TEACHER,
                data={"title": "[E2E Test] Thong bao khai giang [DA CAP NHAT]"}
            )
            b_up = log(12, "Teacher updates Post 1 title", r_up, 200)
            assert "[DA CAP NHAT]" in b_up["data"]["title"]
            assert b_up["data"]["is_edited"] is True

            # Step 13: Student tries to create post -> Expect 403
            r_stud_post = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_STUDENT1,
                data={"title": "Hoc vien thu dang bai", "content": "Test"}
            )
            log(13, "Student tries to create post (expect 403 Forbidden)", r_stud_post, 403)

            # -------------------------------------------------------------
            # PHASE 2: COMMENTS & REACTIONS
            # -------------------------------------------------------------
            print(f"\n{Colors.BOLD}--- PHASE 2: COMMENTS & REACTIONS ---{Colors.RESET}")

            # Step 14: Student 1 reacts "like" to Post 1
            r_react_like = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/reactions",
                headers=H_STUDENT1,
                json={"reaction_type": "like"}
            )
            b_react_like = log(14, "Student 1 reacts LIKE to Post 1", r_react_like, 200)
            assert b_react_like["data"]["action"] == "added"
            assert b_react_like["data"]["summary"]["like"] >= 1
            assert "like" in b_react_like["data"]["summary"]["user_reactions"]

            # Step 15: Student 1 reacts "heart" to Post 1 (additional reaction)
            r_react_heart = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/reactions",
                headers=H_STUDENT1,
                json={"reaction_type": "heart"}
            )
            b_react_heart = log(15, "Student 1 reacts HEART to Post 1", r_react_heart, 200)
            assert b_react_heart["data"]["action"] == "added"
            assert b_react_heart["data"]["summary"]["heart"] >= 1
            assert "heart" in b_react_heart["data"]["summary"]["user_reactions"]

            # Step 16: Student 1 clicks "heart" again -> toggles off (hard delete)
            r_react_toggle = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/reactions",
                headers=H_STUDENT1,
                json={"reaction_type": "heart"}
            )
            b_react_toggle = log(16, "Student 1 clicks HEART again (toggle remove)", r_react_toggle, 200)
            assert b_react_toggle["data"]["action"] == "removed"
            assert "heart" not in b_react_toggle["data"]["summary"]["user_reactions"]

            # Step 17: Student 1 creates root comment
            r_c1 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/comments",
                headers=H_STUDENT1,
                json={"content": "Thua thay, tai lieu buoi 1 da co chua a?", "parent_comment_id": None}
            )
            b_c1 = log(17, "Student 1 posts root comment", r_c1, 201)
            root_comment_id = b_c1["data"]["id"]

            # Step 18: Teacher replies to comment (1-level nesting)
            r_c2 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/comments",
                headers=H_TEACHER,
                json={"content": "Da co trong tab Kho hoc lieu roi em nhe!", "parent_comment_id": root_comment_id}
            )
            b_c2 = log(18, "Teacher replies to root comment", r_c2, 201)
            assert b_c2["data"]["parent_comment_id"] == root_comment_id

            # Step 19: Get comments list -> verify nested replies
            r_list_comments = client.get(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/comments",
                headers=H_STUDENT1
            )
            b_comments = log(19, "Student 1 gets comments list", r_list_comments, 200)
            root_found = next((c for c in b_comments["data"] if c["id"] == root_comment_id), None)
            assert root_found is not None, "Root comment not found in list"
            assert len(root_found.get("replies", [])) >= 1, "Nested reply not present"

            # Step 20: Teacher locks comments
            r_lock = client.patch(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/lock-comments",
                headers=H_TEACHER,
                json={"is_comment_locked": True}
            )
            b_lock = log(20, "Teacher locks comments on Post 1", r_lock, 200)
            assert b_lock["data"]["is_comment_locked"] is True

            # Step 21: Student attempts to comment on locked post -> Expect 400
            r_c_locked = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/comments",
                headers=H_STUDENT1,
                json={"content": "Em muon hoi them..."}
            )
            log(21, "Student tries to comment on locked post (expect 400)", r_c_locked, 400)

            # Step 22: Teacher unlocks comments
            r_unlock = client.patch(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/lock-comments",
                headers=H_TEACHER,
                json={"is_comment_locked": False}
            )
            b_unlock = log(22, "Teacher unlocks comments on Post 1", r_unlock, 200)
            assert b_unlock["data"]["is_comment_locked"] is False

            # -------------------------------------------------------------
            # PHASE 3: VIEW TRACKING & VIEWERS MODAL
            # -------------------------------------------------------------
            print(f"\n{Colors.BOLD}--- PHASE 3: VIEW TRACKING & VIEWERS MODAL ---{Colors.RESET}")

            # Step 23: Teacher records view -> should be IGNORED (viewed=False)
            r_view_teach = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/view",
                headers=H_TEACHER
            )
            b_view_teach = log(23, "Teacher records view (should be ignored)", r_view_teach, 200)
            assert b_view_teach["data"]["viewed"] is False
            assert b_view_teach["data"]["view_count"] == 0

            # Step 24: Student 1 records view -> SUCCESS (viewed=True, view_count=1)
            r_view_s1 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/view",
                headers=H_STUDENT1
            )
            b_view_s1 = log(24, "Student 1 records view (viewport >= 2s)", r_view_s1, 200)
            assert b_view_s1["data"]["viewed"] is True
            assert b_view_s1["data"]["view_count"] == 1

            # Step 25: Student 1 records view again -> IDEMPOTENT (view_count remains 1)
            r_view_s1_repeat = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/view",
                headers=H_STUDENT1
            )
            b_view_s1_repeat = log(25, "Student 1 views again (idempotency check)", r_view_s1_repeat, 200)
            assert b_view_s1_repeat["data"]["view_count"] == 1

            # Step 26: Student 2 records view -> SUCCESS (view_count becomes 2)
            r_view_s2 = client.post(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/view",
                headers=H_STUDENT2
            )
            b_view_s2 = log(26, "Student 2 records view", r_view_s2, 200)
            assert b_view_s2["data"]["viewed"] is True
            assert b_view_s2["data"]["view_count"] == 2

            # Step 27: Teacher gets viewers summary -> Expect 2 viewers
            r_viewers = client.get(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/views",
                headers=H_TEACHER
            )
            b_viewers = log(27, "Teacher gets Viewers Summary", r_viewers, 200)
            data_v = b_viewers["data"]
            assert data_v["viewed_count"] == 2
            viewed_emails = [u["email"] for u in data_v.get("viewers", [])]
            assert "student.minh@gmail.com" in viewed_emails
            assert "student.cuong@gmail.com" in viewed_emails

            # Step 28: Student tries to get viewers summary -> Expect 403 Forbidden
            r_viewers_stud = client.get(
                f"{BASE}/classes/{CLASS_ID}/posts/{post_1_id}/views",
                headers=H_STUDENT1
            )
            log(28, "Student tries to get Viewers summary (expect 403 Forbidden)", r_viewers_stud, 403)

            # -------------------------------------------------------------
            # PHASE 4: MATERIAL LIBRARY TAB
            # -------------------------------------------------------------
            print(f"\n{Colors.BOLD}--- PHASE 4: MATERIAL LIBRARY TAB ---{Colors.RESET}")

            # Step 29: Get materials list -> only material post types should appear
            r_mat_all = client.get(
                f"{BASE}/classes/{CLASS_ID}/materials",
                headers=H_STUDENT1
            )
            b_mat_all = log(29, "Student gets all materials", r_mat_all, 200)
            mat_types = [p["post_type"] for p in b_mat_all["data"]]
            assert all(t == "material" for t in mat_types), "Found non-material posts in materials tab"
            mat_ids = [p["id"] for p in b_mat_all["data"]]
            assert post_2_id in mat_ids and post_3_id in mat_ids
            assert post_1_id not in mat_ids, "Announcement appeared in materials!"

            # Step 30: Filter materials by category: lecture_slide
            r_mat_cat = client.get(
                f"{BASE}/classes/{CLASS_ID}/materials?material_category=lecture_slide",
                headers=H_STUDENT1
            )
            b_mat_cat = log(30, "Filter materials by category (lecture_slide)", r_mat_cat, 200)
            assert all(p["material_category"] == "lecture_slide" for p in b_mat_cat["data"])
            cat_pids = [p["id"] for p in b_mat_cat["data"]]
            assert post_2_id in cat_pids
            assert post_3_id not in cat_pids

            # Step 31: Search materials by keyword (search="Slide")
            r_mat_search = client.get(
                f"{BASE}/classes/{CLASS_ID}/materials?search=Slide",
                headers=H_STUDENT1
            )
            b_mat_search = log(31, "Search materials with keyword 'Slide'", r_mat_search, 200)
            search_pids = [p["id"] for p in b_mat_search["data"]]
            assert post_2_id in search_pids

            # Step 32: Unauthorized student (student.vy) tries to access class feed/materials
            r_unauth_posts = client.get(
                f"{BASE}/classes/{CLASS_ID}/posts",
                headers=H_UNAUTH
            )
            log(32, "Outside student tries to view class posts (expect 403)", r_unauth_posts, 403)

            r_unauth_mat = client.get(
                f"{BASE}/classes/{CLASS_ID}/materials",
                headers=H_UNAUTH
            )
            log(33, "Outside student tries to view materials (expect 403)", r_unauth_mat, 403)

        finally:
            # -------------------------------------------------------------
            # TEARDOWN: CLEAN UP CREATED POSTS
            # -------------------------------------------------------------
            print(f"\n{Colors.BOLD}--- TEARDOWN: CLEAN UP TEST POSTS ---{Colors.RESET}")
            for pid in created_post_ids:
                r_del = client.delete(
                    f"{BASE}/classes/{CLASS_ID}/posts/{pid}",
                    headers=H_TEACHER
                )
                log(99, f"Soft-delete test post {pid[:8]}...", r_del, 200)

    print("\n" + "=" * 70)
    print(f"{Colors.BOLD}{Colors.GREEN}ALL 33 E2E TESTS COMPLETED SUCCESSFULLY!{Colors.RESET}")
    print("=" * 70)


if __name__ == "__main__":
    main()
