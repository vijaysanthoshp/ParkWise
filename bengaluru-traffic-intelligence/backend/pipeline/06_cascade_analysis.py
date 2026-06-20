"""
Step 6 — Recurrence & Chronic Hotspot Analysis
================================================
Replaces the time-window cascade self-join with a recurrence analysis.

"Recurrence" is the right concept for this dataset:
    A junction where violations happen on 20+ different days = a CHRONIC
    enforcement blind spot, not a one-off event.  This is far more
    actionable for BTP than a theoretical downstream cascade.

Output fields (kept compatible with downstream API structure):
    junction_cascade  — per-junction recurrence stats
    event_type_cascade — per-violation-type breakdown at top junctions

Usage:
    python pipeline/06_cascade_analysis.py

Input:  data/processed/proximity_scored.parquet
Output: data/outputs/cascade_scores.json
"""

import json
import warnings
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

IN  = Path("data/processed/proximity_scored.parquet")
OUT = Path("data/outputs/cascade_scores.json")


def compute_recurrence(df: pd.DataFrame) -> dict:
    """
    Compute recurrence stats per junction and per (junction, event_type).

    Returns a dict matching the existing API schema:
      {
        "junction_cascade":    [...],   # one entry per junction
        "event_type_cascade":  [...],   # one entry per (junction, cause)
      }
    """
    df["start_datetime"] = pd.to_datetime(df["start_datetime"], errors="coerce")
    df["date"] = df["start_datetime"].dt.date

    # Total dataset span
    date_min  = df["start_datetime"].min()
    date_max  = df["start_datetime"].max()
    span_days = max(1, (date_max - date_min).days + 1)

    # ── Per-junction recurrence ─────────────────────────────────────────────
    jn_groups = df.groupby("junction", observed=True)

    jn_stats = []
    for junction, grp in jn_groups:
        if junction in ("Unknown", "No Junction"):
            continue
        active_days      = grp["date"].nunique()
        total_violations = len(grp)
        recurrence_rate  = round(active_days / span_days, 4)   # 0–1
        avg_daily        = round(total_violations / max(1, active_days), 2)

        # Dominant cause
        if "event_cause" in grp.columns:
            top_cause = grp["event_cause"].mode()[0] if len(grp) > 0 else "Unknown"
        else:
            top_cause = "Unknown"

        jn_stats.append({
            "junction":        junction,
            "active_days":     int(active_days),
            "total_violations": int(total_violations),
            "recurrence_rate": recurrence_rate,
            "avg_daily_violations": avg_daily,
            # Keep field name for API/frontend compatibility:
            "avg_downstream":  avg_daily,         # repurposed → avg daily violations
            "top_cause":       str(top_cause)[:80],
        })

    # Sort by avg_daily desc (most active junctions first)
    jn_stats.sort(key=lambda x: x["avg_daily_violations"], reverse=True)
    print(f"  Junction recurrence computed for {len(jn_stats)} junctions")

    # ── Per-(junction, event_cause) breakdown ───────────────────────────────
    if "event_cause" not in df.columns:
        df["event_cause"] = "Unknown"

    type_groups = (
        df[df["junction"] != "Unknown"]
        .groupby(["junction", "event_cause"], observed=True)
    )

    type_stats = []
    for (junction, cause), grp in type_groups:
        active_days      = grp["date"].nunique()
        total_violations = len(grp)
        avg_daily        = round(total_violations / max(1, active_days), 2)

        type_stats.append({
            "junction":        junction,
            "event_cause":     str(cause)[:80],
            "trigger_count":   int(total_violations),
            "active_days":     int(active_days),
            "avg_downstream":  avg_daily,       # avg daily violations for this cause
            "max_downstream":  int(grp.groupby("date").size().max()),
            "avg_clearance":   0.0,             # not applicable — kept for schema compat
        })

    # Top 30 by avg daily violations
    type_stats.sort(key=lambda x: x["avg_downstream"], reverse=True)
    type_stats = type_stats[:30]
    print(f"  Event-type recurrence computed for {len(type_stats)} (junction, cause) pairs")

    return {
        "junction_cascade":   jn_stats,
        "event_type_cascade": type_stats,
        "metadata": {
            "analysis_type":  "recurrence",
            "dataset_span_days": int(span_days),
            "description": (
                "avg_downstream = avg daily violations at this junction. "
                "High recurrence_rate = chronic enforcement blind spot."
            ),
        },
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("Loading proximity-scored data ...")
    df = pd.read_parquet(IN)
    print(f"  {len(df):,} records loaded")

    print("\n-- Computing recurrence analysis ----------------------")
    result = compute_recurrence(df)

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  [OK] Recurrence scores saved to {OUT}")
    print(f"  Top 5 chronic junctions:")
    for j in result["junction_cascade"][:5]:
        print(f"    {j['junction'][:50]}: "
              f"{j['avg_daily_violations']} avg violations/day "
              f"({j['active_days']} active days)")
