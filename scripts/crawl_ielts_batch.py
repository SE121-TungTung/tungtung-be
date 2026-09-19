import urllib.request
from bs4 import BeautifulSoup
import json
import os
import time
import re

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crawled_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def crawl_mini_ielts_reading_batch(max_pages=15):
    print(f"--- Bat dau cao hang loat bai Reading tu Mini-IELTS (Toi da {max_pages} bai) ---")
    index_url = "https://mini-ielts.com/reading"
    req = urllib.request.Request(index_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    passage_links = []
    try:
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/reading/' in href and not href.startswith('/view-solution'):
                    full_url = f"https://mini-ielts.com{href}" if href.startswith('/') else href
                    if full_url not in passage_links:
                        passage_links.append(full_url)
    except Exception as e:
        print(f"[ERROR] Loi lay danh sach de Reading: {e}")
        return

    passage_links = passage_links[:max_pages]
    print(f"[INFO] Da tim thay {len(passage_links)} bai Reading. Dang tien hanh cao du lieu chi tiet...")

    results = []
    for idx, url in enumerate(passage_links, start=1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode('utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                
                title_node = soup.find('h1') or soup.find('h2')
                title = title_node.get_text(strip=True) if title_node else f"Reading Passage {idx}"
                
                passage_node = soup.find('div', class_=lambda c: c and 'readingPassage' in c)
                passage_text = passage_node.get_text('\n\n', strip=True) if passage_node else ""
                
                sections = soup.find_all('div', class_='exam-section')
                question_groups = []
                for s_idx, sec in enumerate(sections, start=1):
                    sec_text = sec.get_text('\n', strip=True)
                    question_groups.append({
                        "order": s_idx,
                        "raw_content": sec_text
                    })

                results.append({
                    "id": idx,
                    "url": url,
                    "title": title,
                    "skill": "reading",
                    "passage_text": passage_text,
                    "question_groups": question_groups
                })
                print(f"  [Reading {idx}/{len(passage_links)}] SUCCESS: {title[:30]}... ({len(passage_text)} chars)")
                time.sleep(0.3)
        except Exception as e:
            print(f"  [Reading {idx}] ERROR: {e}")

    file_path = os.path.join(OUTPUT_DIR, "ielts_reading_crawled.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[COMPLETE] Da luu {len(results)} bai Reading vao: {file_path}")

def crawl_writing_prompts():
    print("\n--- Dang tao bo de thi Writing Task 1 & Task 2 ---")
    writing_data = [
        {
            "id": 1,
            "skill": "writing",
            "task_type": "writing_task_1",
            "title": "Task 1: Process of Recycling Plastic Bottles",
            "prompt": "The diagram below shows the process of recycling plastic bottles. Summarise the information by selecting and reporting the main features, and make comparisons where relevant.",
            "image_url": "https://images.unsplash.com/photo-1532996122724-e3c354a0b15b?w=800",
            "min_words": 150
        },
        {
            "id": 2,
            "skill": "writing",
            "task_type": "writing_task_2",
            "title": "Task 2: Impact of Artificial Intelligence on Future Employment",
            "prompt": "Some people believe that Artificial Intelligence (AI) will create more job opportunities, while others argue that it will cause widespread unemployment. Discuss both views and give your opinion.",
            "min_words": 250
        },
        {
            "id": 3,
            "skill": "writing",
            "task_type": "writing_task_1",
            "title": "Task 1: Coffee Consumption Bar Chart",
            "prompt": "The bar chart below shows the average daily coffee consumption per person in five European countries in 2024. Summarise the main trends and compare where relevant.",
            "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=800",
            "min_words": 150
        },
        {
            "id": 4,
            "skill": "writing",
            "task_type": "writing_task_2",
            "title": "Task 2: Remote Work vs Office Work",
            "prompt": "Working from home has become increasingly common. Do the advantages of remote working outweigh the disadvantages for both employers and employees?",
            "min_words": 250
        }
    ]
    file_path = os.path.join(OUTPUT_DIR, "ielts_writing_crawled.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(writing_data, f, ensure_ascii=False, indent=2)
    print(f"[COMPLETE] Da luu {len(writing_data)} bo de Writing vao: {file_path}")

def crawl_speaking_topics():
    print("\n--- Dang tao bo de thi Speaking Parts 1, 2, 3 ---")
    speaking_data = [
        {
            "id": 1,
            "skill": "speaking",
            "title": "Speaking Test: Work, Education & Technology",
            "part1": [
                "Do you work or are you a student?",
                "What subject are you studying or what is your job responsibilities?",
                "Do you prefer using a smartphone or a laptop for your daily tasks?"
            ],
            "part2_cue_card": {
                "topic": "Describe a time when you used an AI tool to solve a problem.",
                "cues": [
                    "What the AI tool was",
                    "When and why you used it",
                    "How it helped you solve the problem",
                    "And explain how you felt after using it"
                ]
            },
            "part3": [
                "In what ways do you think AI will change higher education in the next decade?",
                "Do you think students rely too much on technology nowadays?",
                "How can teachers ensure students maintain critical thinking skills when AI tools are available?"
            ]
        },
        {
            "id": 2,
            "skill": "speaking",
            "title": "Speaking Test: Travel, Hobbies & Environment",
            "part1": [
                "Do you enjoy traveling during holidays?",
                "What is your favorite type of destination?",
                "How often do you go outdoors?"
            ],
            "part2_cue_card": {
                "topic": "Describe a memorable journey you took with friends or family.",
                "cues": [
                    "Where you went",
                    "Who you went with",
                    "What activities you did there",
                    "And explain why this journey was so memorable"
                ]
            },
            "part3": [
                "Why do people like visiting tourist destinations in their free time?",
                "What impact does mass tourism have on local cultures and ecosystems?",
                "Should governments restrict the number of visitors to natural reserves?"
            ]
        }
    ]
    file_path = os.path.join(OUTPUT_DIR, "ielts_speaking_crawled.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(speaking_data, f, ensure_ascii=False, indent=2)
    print(f"[COMPLETE] Da luu {len(speaking_data)} bo de Speaking vao: {file_path}")

if __name__ == "__main__":
    crawl_mini_ielts_reading_batch(max_pages=15)
    crawl_writing_prompts()
    crawl_speaking_topics()
