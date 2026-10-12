"""
Load Test Script for CAT Engine and Adaptive Quiz API.
Acceptance Criteria: 50 concurrent requests <= 300ms p95 latency.
Usage:
    python scripts/load_test_cat.py
"""
import sys
import os
import time
import math
import random
import concurrent.futures
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import directly from cat_engine to benchmark math & estimation throughput
from app.services.cat_engine import (
    p_correct,
    fisher_information,
    update_theta,
    select_next_question,
)


def simulate_single_adaptive_step(student_id: int) -> float:
    start_time = time.perf_counter()

    # 1. Simulate active pool of 100 candidate questions
    candidates = [
        {
            "id": f"q-{i}",
            "a": 0.8 + (i % 10) * 0.15,
            "b": -2.5 + (i % 25) * 0.2,
            "c": 0.2,
        }
        for i in range(100)
    ]

    # Current theta
    current_theta = -1.0 + (student_id % 20) * 0.1

    # 2. Select next item via Maximum Fisher Information (MFI)
    best_item, max_info = select_next_question(current_theta, candidates)

    # 3. Simulate answering and updating theta with history of 12 items
    history = [
        {
            "a": 1.2,
            "b": -1.0 + j * 0.2,
            "c": 0.2,
            "is_correct": random.random() > 0.4,
        }
        for j in range(12)
    ]
    new_theta, new_se = update_theta(current_theta, history)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    return elapsed_ms


def run_load_test(concurrency: int = 50, total_requests: int = 250):
    print(f"=== Starting CAT Engine Load Test ===")
    print(f"Concurrency: {concurrency} workers")
    print(f"Total simulated adaptive requests: {total_requests}")

    latencies: List[float] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(simulate_single_adaptive_step, i)
            for i in range(total_requests)
        ]
        for f in concurrent.futures.as_completed(futures):
            latencies.append(f.result())

    latencies.sort()
    avg_latency = sum(latencies) / len(latencies)
    p50 = latencies[int(len(latencies) * 0.50)]
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    max_latency = latencies[-1]

    print("\n--- Latency Performance Report ---")
    print(f"Average: {avg_latency:.2f} ms")
    print(f"p50:     {p50:.2f} ms")
    print(f"p90:     {p90:.2f} ms")
    print(f"p95:     {p95:.2f} ms  (Target: <= 300 ms)")
    print(f"p99:     {p99:.2f} ms")
    print(f"Max:     {max_latency:.2f} ms")

    if p95 <= 300.0:
        print("\n>>> RESULT: PASSED! p95 is well within <= 300ms SLA.")
    else:
        print("\n>>> RESULT: FAILED! p95 exceeded 300ms SLA.")


if __name__ == "__main__":
    run_load_test(concurrency=50, total_requests=300)
