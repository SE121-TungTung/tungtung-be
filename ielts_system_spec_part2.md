# IELTS PRACTICE PLATFORM — ĐẶC TẢ HỆ THỐNG CHI TIẾT
## Phần 2: Yêu cầu Chức năng & Lộ trình Phát triển

> Xem thêm [Phần 1: Tình trạng Hiện tại](file:///C:/Users/Admin/.gemini/antigravity/brain/015f2b22-f01c-481b-9ad6-23ccdda7cdbe/ielts_system_spec_part1.md)

---

## 3. ĐẶC TẢ YÊU CẦU CHỨC NĂNG CHI TIẾT

### 3.1 PHÂN HỆ LISTENING

#### 3.1.1 Chế độ Practice từng Part

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Mô tả** | Học viên chọn 1 Part (1-4) để luyện riêng |
| **Cấu trúc data** | 1 `Test` → 1 `TestSection(skill=listening)` → 1 `TestSectionPart(audio_url=mp3)` → N `QuestionGroup` |
| **Thời gian** | Tùy Part: Part 1-2 (~5 phút), Part 3-4 (~8 phút) |
| **UI** | Split-screen: Trái = Audio Player + Transcript (ẩn), Phải = Câu hỏi |
| **Dạng câu hỏi** | `multiple_choice`, `sentence_completion`, `note_completion`, `matching_features`, `short_answer` |
| **Chấm điểm** | Auto-grade (so khớp đáp án) |

#### 3.1.2 Chế độ Full Test 30 phút

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Cấu trúc** | 1 `Test` → 1 `TestSection(listening)` → 4 `TestSectionPart` (Part 1→4, mỗi Part có `audio_url` riêng) |
| **Thời gian** | 30 phút + 2 phút transfer (tổng 32 phút countdown) |
| **Audio** | Phát liên tục 4 Part, mỗi Part có intro + pause giữa sections |
| **Tổng câu hỏi** | 40 câu chuẩn IELTS |
| **Band Score** | Tự động tính từ raw score (VD: 30/40 → Band 7.0) theo bảng quy đổi Cambridge |

#### 3.1.3 Tính năng Dictation (Chép chính tả)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Mục đích** | Luyện nghe chi tiết từng câu để nâng Band Listening |
| **Luồng** | 1) Audio phát 1 câu → 2) Pause tự động → 3) Học viên gõ lại → 4) Bấm "Check" → 5) Diff highlight |
| **Diff Engine** | So khớp word-by-word: ✅ xanh (đúng), ❌ đỏ gạch ngang (sai/thiếu), 🟡 vàng (thừa) |
| **Data cần** | `ContentPassage` với `text_content` = transcript phân đoạn theo câu (JSON array of sentences) |
| **API mới** | `GET /tests/{id}/dictation-segments` — trả về danh sách câu + timestamp |
| **Điểm** | Tính % từ đúng / tổng từ của transcript |

#### 3.1.4 Yêu cầu dữ liệu Listening

| Hạng mục | Yêu cầu tối thiểu | Hiện có | Thiếu |
|----------|-------------------|--------|-------|
| Đề Full Test (4 Parts, 40 câu) | 10 bộ | 0 | 10 |
| Đề Practice từng Part | 20 bài (5/Part) | 0 | 20 |
| File Audio .mp3 | 30 file | 0 | 30 |
| Transcript text | 30 bài | 0 | 30 |

**Nguồn dữ liệu Listening:**
- [IELTS Online Tests](https://ieltsonlinetests.com/) — có audio .mp3 public
- [Cambridge IELTS Practice](https://cambridgeielts.pro/) — transcript kèm audio
- YouTube IELTS Official channels — extract audio bằng `yt-dlp`

---

### 3.2 PHÂN HỆ READING

#### 3.2.1 Chế độ Practice từng Passage (20 phút)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Cấu trúc** | 1 `Test` → 1 `TestSection(reading)` → 1 `TestSectionPart` → N `QuestionGroup` |
| **UI** | Split-screen chuẩn: Trái = Passage (scroll), Phải = Câu hỏi + Answer sheet |
| **Passage** | `ContentPassage.text_content` hiển thị paragraphs (A, B, C...) |
| **Dạng câu hỏi** | Tất cả 11 dạng Reading: T/F/NG, Y/N/NG, MC, Matching Headings/Information/Features, Sentence/Summary/Note Completion, Short Answer, Diagram Labeling |
| **Tổng câu hỏi** | 13-14 câu / passage |

#### 3.2.2 Chế độ Full Test 60 phút

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Cấu trúc** | 1 `Test` → 1 `TestSection(reading)` → 3 `TestSectionPart` (Passage 1, 2, 3) |
| **Tổng câu hỏi** | 40 câu (13+13+14) |
| **Navigation** | Tab chuyển Passage 1/2/3, thanh Answer Sheet hiển thị trạng thái đã trả lời |
| **Band Score** | Raw score → Band theo bảng Cambridge (VD: 30/40 → Band 7.0) |

#### 3.2.3 Tính năng Vocabulary & Collocation Notebook

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Highlight** | Bôi đen từ/cụm từ trên passage → Popup tooltip |
| **Popup** | Hiển thị: Từ gốc, phiên âm IPA, nghĩa Việt, ví dụ câu, loại từ |
| **Lưu từ** | Nút "Save to Notebook" → lưu vào bảng `user_vocabulary` (cần tạo mới) |
| **Ôn tập** | Trang riêng `/vocabulary` hiển thị dạng Flashcard hoặc Quiz |
| **API nguồn** | Free Dictionary API (`dictionaryapi.dev`) hoặc Google Translate API |
| **DB mới** | Bảng `user_vocabulary(user_id, word, ipa, meaning_vi, source_passage_id, created_at)` |

#### 3.2.4 Yêu cầu dữ liệu Reading

| Hạng mục | Yêu cầu | Hiện có | Thiếu |
|----------|---------|--------|-------|
| Passage đơn lẻ | 30+ | 14 | 16 |
| Full Test 3 Passage | 10 bộ | 0 (chưa ghép) | 10 |

---

### 3.3 PHÂN HỆ WRITING

#### 3.3.1 Chế độ luyện tập

| Chế độ | Cấu trúc data | Thời gian |
|--------|---------------|-----------|
| **Task 1 Only** | 1 Test → 1 Section(writing) → 1 Part → 1 QuestionGroup(`writing_task_1`) | 20 phút |
| **Task 2 Only** | 1 Test → 1 Section(writing) → 1 Part → 1 QuestionGroup(`writing_task_2`) | 40 phút |
| **Combo Task 1+2** | 1 Test → 1 Section(writing) → 2 Parts (Part 1 + Part 2) | 60 phút |

#### 3.3.2 Hệ thống Bộ lọc (Filter System)

**Task 1 — Filter theo dạng biểu đồ:**

| Dạng bài | Tag value | Mô tả |
|----------|----------|-------|
| Bar Chart | `bar_chart` | Biểu đồ cột |
| Line Graph | `line_graph` | Biểu đồ đường |
| Pie Chart | `pie_chart` | Biểu đồ tròn |
| Table | `table` | Bảng số liệu |
| Process / Diagram | `process` | Sơ đồ quy trình |
| Map | `map` | Bản đồ so sánh |
| Mixed / Combined | `mixed` | Kết hợp nhiều loại |

**Task 2 — Filter theo dạng bài luận:**

| Dạng bài | Tag value |
|----------|----------|
| Agree or Disagree | `agree_disagree` |
| Discuss Both Views | `discussion` |
| Advantages vs Disadvantages | `adv_disadv` |
| Problem & Solution | `problem_solution` |
| Two-part Question | `two_part` |
| Direct Question | `direct_question` |

**Task 2 — Filter theo chủ đề:**

`environment`, `technology`, `education`, `health`, `society`, `economy`, `crime`, `media`, `culture`, `transport`, `government`, `globalization`

**Cách lưu filter:** Sử dụng trường `QuestionBank.tags` (JSONB):
```json
{
  "task_type": "writing_task_1",
  "chart_type": "bar_chart",
  "topics": ["economy", "environment"]
}
```

**API cần bổ sung:**
```
GET /tests/student?skill=writing&tags.task_type=writing_task_1&tags.chart_type=bar_chart
```

#### 3.3.3 AI Writing Grader — Đầu ra chi tiết

| Tiêu chí IELTS | Field trong `ai_rubric_scores` | Thang điểm |
|----------------|-------------------------------|-----------|
| Task Achievement / Task Response | `task_achievement` | 0 - 9 |
| Coherence & Cohesion | `coherence_cohesion` | 0 - 9 |
| Lexical Resource | `lexical_resource` | 0 - 9 |
| Grammatical Range & Accuracy | `grammar_accuracy` | 0 - 9 |
| **Overall Band** | `ai_band_score` | 0 - 9 (step 0.5) |

**Feedback format (trong `ai_feedback` TEXT):**
```json
{
  "overall_comment": "Your essay demonstrates...",
  "sentence_corrections": [
    {
      "original": "The graph show that...",
      "corrected": "The graph shows that...",
      "error_type": "grammar",
      "explanation": "Subject-verb agreement..."
    }
  ],
  "vocabulary_suggestions": ["utilize → use", "big → significant"],
  "band_justification": {
    "task_achievement": "You addressed all parts of the task..."
  }
}
```

#### 3.3.4 Yêu cầu dữ liệu Writing

| Hạng mục | Yêu cầu | Hiện có | Thiếu |
|----------|---------|--------|-------|
| Task 1 (đủ 7 dạng) | 21+ (3/dạng) | 2 | 19 |
| Task 2 (đủ 6 dạng × 12 chủ đề) | 36+ (6 dạng × 6 đề) | 2 | 34 |
| Hình ảnh biểu đồ cho Task 1 | 21+ | 2 | 19 |

---

### 3.4 PHÂN HỆ SPEAKING

#### 3.4.1 Chế độ Practice từng Part

| Part | Cấu trúc | Thời gian | Đặc biệt |
|------|----------|-----------|----------|
| Part 1 | 2-3 chủ đề × 3-4 câu = 8-12 câu | 4-5 phút | Random từ Topic Bank |
| Part 2 | 1 Cue Card + 4 bullet points | 1 phút prep + 2 phút nói | Timer chuẩn bị + ghi âm liên tục |
| Part 3 | 4-6 câu hỏi thảo luận | 4-5 phút | Liên quan đến chủ đề Part 2 |

#### 3.4.2 Topic Bank & Cơ chế Random Part 1

**Kho chủ đề Part 1 (tối thiểu 20 topics):**

| # | Topic | Tag | Câu hỏi mẫu |
|---|-------|-----|-------------|
| 1 | Hometown | `hometown` | Where is your hometown? |
| 2 | Work/Study | `work_study` | Do you work or study? |
| 3 | Accommodation | `accommodation` | Do you live in a house or flat? |
| 4 | Daily Routine | `daily_routine` | What do you usually do in the morning? |
| 5 | Hobbies | `hobbies` | What do you like to do in your free time? |
| 6 | Technology | `technology` | How often do you use your phone? |
| 7 | Social Media | `social_media` | Do you use social media often? |
| 8 | Weather | `weather` | What kind of weather do you like? |
| 9 | Food & Cooking | `food` | Do you like cooking? |
| 10 | Travel | `travel` | Do you like traveling? |
| 11 | Sports | `sports` | What sports do you play? |
| 12 | Music | `music` | What kind of music do you listen to? |
| 13 | Reading | `reading_habit` | Do you enjoy reading books? |
| 14 | Shopping | `shopping` | Do you prefer shopping online or in stores? |
| 15 | Festivals | `festivals` | What is the most important festival in your country? |
| 16 | Friends | `friends` | Do you prefer having many friends or a few close friends? |
| 17 | Transportation | `transportation` | How do you usually get to school/work? |
| 18 | Sleep | `sleep` | How many hours do you sleep? |
| 19 | Colors | `colors` | What is your favorite color? |
| 20 | Animals | `animals` | Do you like animals? |

**Cơ chế Random:**
```
API: GET /tests/speaking/random-part1?num_topics=3

Logic backend:
1. Query QuestionBank WHERE skill_area='speaking' AND question_type='speaking_part_1'
2. GROUP BY tags->>'topic'
3. Random chọn 3 topics khác nhau
4. Từ mỗi topic, lấy 3-4 câu hỏi
5. Trả về Test tạm (in-memory) hoặc tạo Test mới trong DB
```

#### 3.4.3 AI Virtual Examiner Room (Phòng thi thật)

**Luồng tương tác chi tiết:**

```
┌─────────────────────────────────────────────────────────────┐
│                  AI VIRTUAL EXAMINER ROOM                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: AI Examiner (TTS) hỏi: "Good morning. Can you     │
│          tell me your full name?"                             │
│                          ↓                                   │
│  Step 2: Student (Microphone STT): "My name is..."          │
│                          ↓                                   │
│  Step 3: AI phân tích response → Chọn câu tiếp theo         │
│          (Có thể follow-up hoặc chuyển topic)                │
│                          ↓                                   │
│  Step 4: Lặp lại Step 1-3 cho đến hết Part                  │
│                          ↓                                   │
│  Step 5: AI tổng hợp → Band Score + Feedback chi tiết       │
│                                                              │
│  Công nghệ:                                                  │
│  • TTS: Azure TTS hoặc Web Speech API (miễn phí)            │
│  • STT: Whisper API hoặc Web Speech Recognition API          │
│  • Logic: GPT-4o-mini với system prompt "IELTS Examiner"     │
│  • Pronunciation: Azure Speech Pronunciation Assessment      │
└─────────────────────────────────────────────────────────────┘
```

**AI Scoring Output cho Speaking:**
```json
{
  "ai_rubric_scores": {
    "fluency_coherence": 6.5,
    "lexical_resource": 7.0,
    "grammar_accuracy": 6.0,
    "pronunciation": 6.5
  },
  "ai_band_score": 6.5,
  "pronunciation_details": [
    {"word": "environment", "score": 0.85, "phonemes_wrong": ["vaɪ"]},
    {"word": "technology", "score": 0.72, "phonemes_wrong": ["nɒl"]}
  ],
  "fluency_metrics": {
    "words_per_minute": 120,
    "pause_count": 5,
    "filler_words": ["um", "uh"],
    "self_corrections": 2
  }
}
```

#### 3.4.4 Yêu cầu dữ liệu Speaking

| Hạng mục | Yêu cầu | Hiện có | Thiếu |
|----------|---------|--------|-------|
| Topics Part 1 (mỗi topic 3-4 câu) | 20 topics × 4 câu = 80 câu | 6 câu (2 topics) | 74 |
| Cue Cards Part 2 | 20+ | 2 | 18 |
| Câu hỏi Part 3 (3-5 câu / Cue Card) | 80+ | 6 | 74 |

---

### 3.5 PHÂN HỆ FULL MOCK TEST (4 KỸ NĂNG)

#### 3.5.1 Đề do Giáo viên Thiết lập

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Cấu trúc** | 1 `Test(test_type=ielts_full)` → 4 `TestSection` (L → R → W → S) |
| **Thời gian tổng** | ~2h45m (Listening 30m → Reading 60m → Writing 60m → Speaking 15m) |
| **UI flow** | Stepper/Wizard: chuyển Section theo thứ tự, không cho quay lại Section trước |
| **Tính điểm** | Overall Band = Trung bình 4 Band Scores (làm tròn đến 0.5) |

#### 3.5.2 AI Suggest đề theo tiến độ học viên

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Input** | Lịch sử `TestAttempt` + `TestResponse` của student |
| **Logic phân tích** | 1) Tính band trung bình mỗi skill → 2) Xác định skill yếu nhất → 3) Trong skill yếu, xác định question_type yếu nhất |
| **Output** | Danh sách đề gợi ý tập trung vào điểm yếu |
| **API** | `GET /tests/recommendations?student_id=...` (gọi tới `tungtung-recommendation`) |

---

## 4. YÊU CẦU BỔ SUNG CẦN PHÁT TRIỂN

### 4.1 Role Guest (1-Click Login)

| Hạng mục | Chi tiết |
|----------|---------|
| **Backend** | Thêm `GUEST = "guest"` vào `UserRole` enum |
| **API** | `POST /auth/guest-login` → Tạo user tạm (email=`guest_xxx@temp`, password random) → trả JWT |
| **Frontend** | Nút "Trải nghiệm ngay — Không cần đăng ký" trên trang Login |
| **Quyền** | Guest chỉ được: Xem đề public, Làm bài, Xem kết quả. Không được: Tham gia lớp, Chat GV |
| **Data retention** | Guest data giữ 30 ngày, sau đó tự xóa bằng cron job |

### 4.2 Bảng DB mới cần tạo

| Bảng | Mục đích | Cột chính |
|------|---------|----------|
| `user_vocabulary` | Sổ tay từ vựng cá nhân | `user_id, word, ipa, meaning_vi, example, source_passage_id, mastery_level` |
| `dictation_attempts` | Lưu kết quả Dictation | `user_id, passage_id, segment_index, user_text, correct_text, accuracy_pct` |
| `speaking_topic_bank` | Kho chủ đề Speaking Part 1 | `topic_name, tag, questions(JSONB), difficulty, usage_count` |

### 4.3 API endpoints cần bổ sung

| # | Method | Endpoint | Chức năng |
|---|--------|----------|-----------|
| 1 | POST | `/auth/guest-login` | Đăng nhập Guest 1-click |
| 2 | GET | `/tests/student?skill=X&tags=Y` | Lọc đề theo kỹ năng + tags |
| 3 | GET | `/tests/speaking/random-part1` | Bốc random 3 topics Part 1 |
| 4 | GET | `/tests/{id}/dictation-segments` | Lấy segments cho Dictation |
| 5 | POST | `/vocabulary/save` | Lưu từ vào sổ tay |
| 6 | GET | `/vocabulary/my-words` | Danh sách từ đã lưu |
| 7 | GET | `/tests/recommendations` | AI gợi ý đề theo tiến độ |
| 8 | POST | `/speaking/examiner/interact` | AI Examiner real-time |

---

## 5. LỘ TRÌNH PHÁT TRIỂN 6 TUẦN (ROADMAP)

### Tuần 1-2: Dữ liệu & Guest Login
- [ ] Crawl thêm 16 bài Reading, 30 đề Writing (Task 1 + Task 2), 18 Cue Cards Speaking
- [ ] Tạo 80 câu hỏi Speaking Part 1 (20 topics × 4 câu) với `tags`
- [ ] Thêm `GUEST` role + API `/auth/guest-login`
- [ ] Bổ sung filter `?skill=&tags=` cho API `/tests/student`
- [ ] Ghép 3 passage thành 10 bộ Full Reading Test

### Tuần 3-4: Listening + AI Pipeline
- [ ] Crawl 10-15 bài Listening có audio .mp3 + transcript
- [ ] Triển khai Dictation Mode (FE + API segments)
- [ ] Migrate Pronunciation Assessment → Azure Speech API
- [ ] Deploy VPS DigitalOcean + Cloudflare HTTPS
- [ ] Tạo bảng `user_vocabulary` + API save/list

### Tuần 5-6: Marketing & Kiểm thử
- [ ] Triển khai AI Virtual Examiner (MVP: Part 1 only)
- [ ] Vocabulary Highlighter trên Reading passage
- [ ] Đăng bài marketing thu hút 100+ users
- [ ] Thu thập SUS Score + MAE metrics
- [ ] Tổng hợp báo cáo KLTN

---

## 6. THỐNG KÊ TỔNG HỢP

| Metric | Hiện tại | Mục tiêu |
|--------|---------|---------|
| Tổng đề thi | 20 | 200+ |
| Listening data | 0 | 30+ bài có audio |
| Speaking topics | 2 | 20+ |
| Roles | 6 | 7 (thêm Guest) |
| API endpoints (Test) | 16 | 24 |
| Users thực tế | 0 | 100+ |
| Deploy | localhost | VPS + HTTPS |
