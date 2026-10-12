"""
Offline IRT Calibration CLI script.
Runs Joint Maximum Likelihood / EM calibration for active test questions.
Usage:
    python scripts/run_irt_calibration.py [--skill reading|listening] [--min-responses 30] [--learning-rate 0.05]
"""
import sys
import os
import argparse
import asyncio

# Ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import AsyncSessionLocal
from app.services.irt_calibration_service import irt_calibration_service


async def main():
    parser = argparse.ArgumentParser(description="Run IRT calibration on question bank.")
    parser.add_argument("--skill", choices=["reading", "listening"], default=None, help="Filter by skill area")
    parser.add_argument("--min-responses", type=int, default=30, help="Minimum responses required to calibrate an item")
    parser.add_argument("--learning-rate", type=float, default=0.05, help="Learning rate for gradient updates")
    parser.add_argument("--epochs", type=int, default=10, help="Number of calibration epochs")
    args = parser.parse_args()

    print(f"=== Starting IRT Question Calibration ===")
    print(f"Skill: {args.skill or 'ALL'}")
    print(f"Min responses: {args.min_responses}")
    print(f"Learning rate: {args.learning_rate}")
    print(f"Epochs: {args.epochs}")

    async with AsyncSessionLocal() as db:
        result = await irt_calibration_service.run_batch_calibration(
            db=db,
            skill_area=args.skill,
            min_responses=args.min_responses,
            learning_rate=args.learning_rate,
            epochs=args.epochs,
        )

        print("\n--- Calibration Results ---")
        print(f"Total questions processed: {result.get('total_items_processed', 0)}")
        print(f"Successfully calibrated:    {result.get('calibrated_count', 0)}")
        print(f"Skipped (< min responses): {result.get('skipped_count', 0)}")
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
