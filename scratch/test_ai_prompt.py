import sys
import os
import json
import asyncio

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.schemas.ai_schedule import AIAnalyzeRequest
from app.services.schedule.ai_service import ai_schedule_service

class MockSession:
    def close(self):
        pass

# Fake context data to bypass DB query
FAKE_CONTEXT = [
    {
        "class_id": "c1111111-1111-1111-1111-111111111111",
        "class_name": "Lớp IELTS 4.0",
        "students": [
            {"student_id": "s1111", "name": "Nguyễn Văn An"},
            {"student_id": "s1112", "name": "Trần Thị Cúc"}
        ]
    },
    {
        "class_id": "c2222222-2222-2222-2222-222222222222",
        "class_name": "Lớp Giao tiếp cơ bản",
        "students": [
            {"student_id": "s2221", "name": "Lê Hải Bình"},
            {"student_id": "s2222", "name": "Phạm Tùng"}
        ]
    },
    {
        "class_id": "c3333333-3333-3333-3333-333333333333",
        "class_name": "Lớp TOEIC Cấp tốc",
        "students": []
    }
]

async def run_test_async():
    print("========== BẮT ĐẦU TEST AI PROMPT (ASYNC) ==========")
    
    # 1. Mock the _get_context_data method so it doesn't query the real DB
    original_get_context = ai_schedule_service._get_context_data
    ai_schedule_service._get_context_data = lambda db, text: FAKE_CONTEXT

    try:
        # Define the test prompt
        test_text = "Ghép An và Bình học cùng buổi. Xếp lớp TOEIC học buổi sáng. Quan trọng nhất là tuyệt đối không để dạy liên tiếp quá nhiều."
        print(f"\n[USER INPUT]:\n{test_text}\n")
        
        request = AIAnalyzeRequest(natural_language_text=test_text)
        
        # 2. Call the AI service asynchronously
        response = await ai_schedule_service.analyze_schedule_constraints(db=MockSession(), request=request)
        
        # 3. Print the result nicely
        print("[AI TRẢ VỀ THÀNH CÔNG]:")
        print(f"- Ghép cặp (paired_class_ids): {response.paired_class_ids}")
        print(f"- Ca học (class_preferences): {response.class_preferences}")
        print(f"- Điểm phạt (penalties_override): {response.penalties_override}")
        print(f"- Lời giải thích (ai_explanation): {response.ai_explanation}")
        print(f"- Cảnh báo (warnings): {response.warnings}")
        
        print("\n[ĐÁNH GIÁ KẾT QUẢ ĐÚNG NẾU]:")
        print("1. paired_class_ids có chứa uuid của lớp IELTS 4.0 và Giao tiếp cơ bản.")
        print("2. class_preferences gán lớp TOEIC vào 'morning'.")
        print("3. penalties_override có penalty_consecutive_limit được set điểm cao (vd: 30-50).")
        
    except Exception as e:
        print(f"Lỗi: {e}")
    finally:
        # Restore original method
        ai_schedule_service._get_context_data = original_get_context

def run_test():
    asyncio.run(run_test_async())

if __name__ == "__main__":
    run_test()
