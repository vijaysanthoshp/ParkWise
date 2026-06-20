"""
Run All — Pipeline Orchestrator
Executes all 8 pipeline steps in sequence from the backend/ directory.

Expected runtime on 3 lakh rows: 8–15 minutes
(most time is step 05 — LightGBM training)

Usage (from backend/ directory):
    python pipeline/run_all.py

Or to skip a specific step:
    python pipeline/run_all.py --skip 05
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path

STEPS = [
    ("01_clean.py",               "Data cleaning & feature engineering"),
    ("02_parking_classifier.py",  "NLP parking incident classifier"),
    ("03_proximity_scoring.py",   "Spatial proximity scoring"),
    ("04_hotspot_analysis.py",    "H3 hotspot analysis + DBSCAN clustering"),
    ("05_lgbm_model.py",          "LightGBM + XGBoost model training"),
    ("06_cascade_analysis.py",    "Cascade impact analysis"),
    ("07_risk_scoring.py",        "Junction risk scoring"),
    ("08_enforcement_schedule.py","Enforcement schedule generation"),
]

WIDTH = 60


def banner(text: str) -> None:
    print(f"\n{'='*WIDTH}")
    print(f"  {text}")
    print(f"{'='*WIDTH}")


def run_step(script: str, description: str) -> bool:
    """Run a single pipeline step. Returns True on success."""
    banner(description)
    t0 = time.time()

    result = subprocess.run(
        [sys.executable, f"pipeline/{script}"],
        # Stream output in real time:
        stdout=None,
        stderr=None,
    )
    elapsed = time.time() - t0

    if result.returncode == 0:
        print(f"\n  [OK] Completed in {elapsed:.0f}s")
        return True
    else:
        print(f"\n  [FAILED] exit code {result.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run the BTP intelligence pipeline"
    )
    parser.add_argument(
        "--skip", nargs="*", default=[],
        help="Step prefixes to skip, e.g. --skip 05 06"
    )
    parser.add_argument(
        "--only", nargs="*", default=[],
        help="Run only these step prefixes, e.g. --only 01 02"
    )
    args = parser.parse_args()

    total_start = time.time()
    failed      = []

    for script, description in STEPS:
        step_num = script[:2]

        if args.only and step_num not in args.only:
            print(f"  Skipping {script} (--only filter)")
            continue
        if step_num in args.skip:
            print(f"  Skipping {script} (--skip flag)")
            continue

        success = run_step(script, description)
        if not success:
            failed.append(script)
            print(f"\n  ERROR: {script} failed. Stopping pipeline.")
            sys.exit(1)

    total = time.time() - total_start
    banner(f"Pipeline complete in {total:.0f}s")

    if failed:
        print(f"  Failed steps: {failed}")
        sys.exit(1)
    else:
        print("  All steps succeeded.")
        print("\n  ── Next steps ────────────────────────────────────")
        print("  Start API:     uvicorn api.main:app --reload --port 8000")
        print("  API docs:      http://localhost:8000/docs")
        print("  Frontend:      cd ../frontend && npm install && npm run dev")
        print("  Dashboard:     http://localhost:5173")


if __name__ == "__main__":
    main()
