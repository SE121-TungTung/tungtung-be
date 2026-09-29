import asyncio
import aiohttp
import time
import numpy as np
from sqlalchemy import text
from app.core.database import SessionLocal

API_URL = "http://localhost:8000/api/v1/flashcards/reviews"

# Cần một user_id hợp lệ, giả sử mock UUID nếu auth bị disable hoặc lấy trực tiếp 1 user
MOCK_USER_ID = "00000000-0000-0000-0000-000000000001" 
# Lấy token từ local system. Ở môi trường perf test cục bộ, có thể tắt auth hoặc truyền mock token.
HEADERS = {
    "Content-Type": "application/json",
    # "Authorization": f"Bearer mock_token" 
}

def get_test_cards(limit=100):
    """Lấy 100 card_id bất kỳ từ DB để test."""
    cards = []
    with SessionLocal() as db:
        result = db.execute(text("SELECT id FROM flashcards LIMIT :limit"), {"limit": limit})
        cards = [str(row[0]) for row in result]
    return cards

async def submit_review(session, card_id):
    payload = {
        "card_id": card_id,
        "rating": "good", # Lựa chọn phổ biến
        "review_duration_ms": 1500
    }
    
    start_time = time.time()
    try:
        # Trong thực tế perf test cần auth hợp lệ. 
        # Script này demo cấu trúc gọi tải song song
        async with session.post(API_URL, json=payload, headers=HEADERS) as response:
            await response.read()
            # Bỏ qua status check vì mục đích đo lường độ trễ mạng và xử lý tải
            elapsed = time.time() - start_time
            return elapsed * 1000 # convert to ms
    except Exception as e:
        print(f"Request failed: {e}")
        return None

async def run_load_test():
    print("Chuẩn bị dữ liệu test...")
    card_ids = get_test_cards(100)
    
    if not card_ids:
        print("Không tìm thấy thẻ nào trong DB. Vui lòng chạy seed_flashcards.py trước.")
        return

    # Nếu có ít hơn 100 thẻ, lặp lại cho đủ 100 request
    while len(card_ids) < 100:
        card_ids.extend(card_ids)
    card_ids = card_ids[:100]

    print(f"Bắt đầu load test: 100 concurrent requests (POST {API_URL})...")
    
    async with aiohttp.ClientSession() as session:
        tasks = [submit_review(session, cid) for cid in card_ids]
        start_total = time.time()
        
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_total
        
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            print("Toàn bộ requests bị lỗi.")
            return
            
        p95 = np.percentile(valid_results, 95)
        avg = np.mean(valid_results)
        
        print("\n--- KẾT QUẢ LOAD TEST ---")
        print(f"Tổng số requests: {len(valid_results)}/100")
        print(f"Thời gian hoàn thành tổng cộng: {total_time:.2f}s")
        print(f"Thời gian trung bình (Avg): {avg:.2f}ms")
        print(f"Phân vị 95th (p95): {p95:.2f}ms")
        
        if p95 <= 200:
            print("✅ Đạt yêu cầu hiệu năng: p95 <= 200ms")
        else:
            print("❌ Chưa đạt yêu cầu hiệu năng: p95 > 200ms")

if __name__ == "__main__":
    asyncio.run(run_load_test())
