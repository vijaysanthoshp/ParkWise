"""
Step 8 - Enforcement Schedule Generation
For each junction × day × time_period, computes incident density and
generates officer deployment recommendations.

This directly addresses the "targeted enforcement" gap in the PS:
  - No more reactive patrol - tells BTP exactly when and where to deploy.

Usage:
    python pipeline/08_enforcement_schedule.py

Input:  data/processed/proximity_scored.parquet
Output: data/outputs/enforcement_schedule.json
"""

import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

IN  = Path("data/processed/proximity_scored.parquet")
OUT = Path("data/outputs/enforcement_schedule.json")

DAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

PERIODS = {
    "Early morning (5–7 AM)":  [5, 6],
    "Morning peak (7–10 AM)":  [7, 8, 9],
    "Midday (10 AM–2 PM)":    [10, 11, 12, 13],
    "Afternoon (2–5 PM)":     [14, 15, 16],
    "Evening peak (5–8 PM)":  [17, 18, 19],
    "Night (8 PM–midnight)":  [20, 21, 22, 23],
}

TOP_N_JUNCTIONS = 15


def assign_period(hour: int) -> str:
    for period, hours in PERIODS.items():
        if hour in hours:
            return period
    return "Late night (0–5 AM)"


def recommend(incidents_per_week: float) -> str:
    if incidents_per_week >= 3.0:
        return "MANDATORY - deploy 2 officers"
    elif incidents_per_week >= 1.5:
        return "RECOMMENDED - deploy 1 officer"
    elif incidents_per_week >= 0.5:
        return "ADVISORY - include in patrol route"
    else:
        return "ROUTINE"


def compute_schedule(df: pd.DataFrame) -> dict:
    """
    Build a junction × day × time_period enforcement schedule
    based on historical incident frequency.
    """
    # Filter out Unknown/No Junction to ensure schedule target real junctions
    df_filtered = df[~df["junction"].isin(["Unknown", "No Junction"])].copy()
    
    df_filtered["start_datetime"] = pd.to_datetime(df_filtered["start_datetime"])
    parking = df_filtered[df_filtered["is_high_confidence_parking"] == 1].copy()

    if len(parking) == 0:
        print("  WARNING: No high-confidence parking incidents. "
              "Using all incidents.")
        parking = df_filtered.copy()

    parking["time_period"] = parking["hour_of_day"].apply(assign_period)
    parking["day_name"]    = parking["day_of_week"].map(
        {i: d for i, d in enumerate(DAYS)}
    )

    # Observed weeks for rate normalisation
    n_weeks = max(
        1,
        (df["start_datetime"].max() - df["start_datetime"].min()).days / 7,
    )

    schedule_df = (
        parking
        .groupby(["junction", "day_of_week", "day_name", "time_period"],
                 observed=True)
        .agg(
            incident_count      = ("id",                    "count"),
            avg_clearance       = ("clearance_minutes",     "mean"),
            road_closure_rate   = ("requires_road_closure", "mean"),
        )
        .reset_index()
    )
    schedule_df["incidents_per_week"] = (
        schedule_df["incident_count"] / n_weeks
    ).round(2)
    schedule_df["recommendation"] = schedule_df["incidents_per_week"].apply(recommend)

    # Select top junctions by total parking incidents
    top_junctions = (
        parking.groupby("junction", observed=True)["id"]
        .count()
        .sort_values(ascending=False)
        .head(TOP_N_JUNCTIONS)
        .index
        .tolist()
    )

    output = {}
    for jn in top_junctions:
        jn_sched = schedule_df[
            (schedule_df["junction"] == jn) &
            (schedule_df["recommendation"] != "ROUTINE")
        ].sort_values(["day_of_week", "time_period"])

        records = []
        for _, row in jn_sched.iterrows():
            records.append({
                "day_name":            row["day_name"],
                "day_of_week":         int(row["day_of_week"]),
                "time_period":         row["time_period"],
                "incidents_per_week":  round(float(row["incidents_per_week"]), 2),
                "avg_clearance_min":   round(float(row["avg_clearance"]), 1),
                "road_closure_rate":   round(float(row["road_closure_rate"]), 2),
                "recommendation":      row["recommendation"],
            })
        output[jn] = records

    print(f"  Enforcement schedule generated for {len(output):,} junctions")
    print(f"  Observed period: {n_weeks:.0f} weeks")

    # Print sample
    if output:
        first_jn = list(output.keys())[0]
        print(f"\n  Sample - {first_jn}:")
        for row in output[first_jn][:3]:
            print(f"    {row['day_name']:12s} {row['time_period']:28s} "
                  f"{row['incidents_per_week']:.1f}/wk -> {row['recommendation']}")

    return output


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print("Loading proximity-scored data ...")
    df = pd.read_parquet(IN)

    schedule = compute_schedule(df)

    with open(OUT, "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"\n  [OK] Enforcement schedule saved to {OUT}")
