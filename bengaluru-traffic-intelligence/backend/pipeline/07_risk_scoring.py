"""
Step 7 - Junction Risk Scoring
Ranks every junction by structural parking-induced congestion risk
using a transparent weighted formula (no black-box ML).

Formula (weights sum to 1.0):
    risk_score = 0.40 × norm_incident_frequency
               + 0.25 × norm_recurrence_rate   (avg daily violations, normalised)
               + 0.20 × road_closure_rate
               + 0.15 × enforcement_gap_rate

Usage:
    python pipeline/07_risk_scoring.py

Input:  data/processed/proximity_scored.parquet
        data/outputs/cascade_scores.json
Output: data/outputs/risk_scores.json
"""

import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

IN_DATA    = Path("data/processed/proximity_scored.parquet")
IN_CASCADE = Path("data/outputs/cascade_scores.json")
OUT        = Path("data/outputs/risk_scores.json")

# Weight configuration (must sum to 1.0)
WEIGHTS = {
    "norm_freq":       0.40,
    "norm_recurrence": 0.25,
    "norm_closure":    0.20,
    "norm_enf_gap":    0.15,
}


def norm(series: pd.Series) -> pd.Series:
    """Min-max normalise a Series to [0, 1]."""
    mn, mx = series.min(), series.max()
    return (series - mn) / (mx - mn + 1e-6)


def compute_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Compute risk score for each junction."""
    # Filter out Unknown/No Junction to ensure only real junctions are scored
    df_filtered = df[~df["junction"].isin(["Unknown", "No Junction"])].copy()
    parking = df_filtered[df_filtered["is_high_confidence_parking"] == 1].copy()

    if len(parking) == 0:
        print("  WARNING: No high-confidence parking incidents found.")
        parking = df_filtered.copy()   # fallback: use filtered all

    junction_stats = (
        parking.groupby("junction", observed=True)
        .agg(
            incident_count      = ("id",                    "count"),
            avg_clearance       = ("clearance_minutes",     "mean"),
            road_closure_rate   = ("requires_road_closure", "mean"),
            recurrence_rate     = ("is_peak_hour",          "mean"),
            lat                 = ("latitude",              "mean"),
            lon                 = ("longitude",             "mean"),
            avg_parking_score   = ("composite_parking_score","mean"),
        )
        .reset_index()
    )

    # Enforcement gap: fraction of incidents outside typical patrol hours (6–22h)
    def enf_gap(hours):
        return ((hours < 6) | (hours >= 22)).mean()

    enf_gap_series = (
        parking.groupby("junction", observed=True)["hour_of_day"]
        .apply(enf_gap)
        .reset_index(name="enforcement_gap_rate")
    )
    junction_stats = junction_stats.merge(enf_gap_series, on="junction", how="left")
    junction_stats["enforcement_gap_rate"] = (
        junction_stats["enforcement_gap_rate"].fillna(0)
    )

    # Top cause and top vehicle type per junction
    def mode_or_unknown(x):
        m = x.mode()
        return m.iloc[0] if len(m) > 0 else "unknown"

    top_cause = (
        parking.groupby("junction", observed=True)["event_cause"]
        .apply(mode_or_unknown)
        .reset_index(name="top_cause")
    )
    top_veh = (
        parking.groupby("junction", observed=True)["veh_type"]
        .apply(lambda x: x.astype(str).mode().iloc[0] if len(x) > 0 else "unknown")
        .reset_index(name="top_veh_type")
    )
    junction_stats = junction_stats.merge(top_cause, on="junction", how="left")
    junction_stats = junction_stats.merge(top_veh,   on="junction", how="left")

    # Load recurrence data (replaces old cascade_score)
    recurrence_map = {}
    if IN_CASCADE.exists():
        with open(IN_CASCADE) as f:
            cascade_data = json.load(f)
        recurrence_map = {
            r["junction"]: r.get("avg_daily_violations", 0.0)
            for r in cascade_data.get("junction_cascade", [])
        }
    junction_stats["avg_daily_violations"] = (
        junction_stats["junction"].map(recurrence_map).fillna(0)
    )
    junction_stats["cascade_score"] = junction_stats["avg_daily_violations"]  # kept for API compat

    # Normalise components
    junction_stats["norm_freq"]       = norm(junction_stats["incident_count"])
    junction_stats["norm_recurrence"] = norm(junction_stats["avg_daily_violations"])
    junction_stats["norm_closure"]    = junction_stats["road_closure_rate"]
    junction_stats["norm_enf_gap"]    = junction_stats["enforcement_gap_rate"]

    # Weighted risk score (0–100)
    junction_stats["risk_score"] = (
        WEIGHTS["norm_freq"]       * junction_stats["norm_freq"]       +
        WEIGHTS["norm_recurrence"] * junction_stats["norm_recurrence"] +
        WEIGHTS["norm_closure"]    * junction_stats["norm_closure"]    +
        WEIGHTS["norm_enf_gap"]    * junction_stats["norm_enf_gap"]
    ) * 100

    junction_stats["risk_score"] = junction_stats["risk_score"].round(1)
    junction_stats = junction_stats.sort_values(
        "risk_score", ascending=False
    ).reset_index(drop=True)

    print(f"  Scored {len(junction_stats):,} junctions")
    print("\n  Top 5 risk junctions:")
    cols = ["junction", "risk_score", "incident_count", "avg_clearance", "top_cause"]
    print(junction_stats[cols].head().to_string(index=False))

    return junction_stats.head(20)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print("Loading proximity-scored data ...")
    df = pd.read_parquet(IN_DATA)

    top20 = compute_risk(df)

    # Serialise - clean numpy types
    records = top20.to_dict("records")
    for rec in records:
        for k, v in list(rec.items()):
            if isinstance(v, (np.integer, np.int64)):    rec[k] = int(v)
            elif isinstance(v, (np.floating, np.float64)): rec[k] = round(float(v), 2)
            elif pd.isna(v):                             rec[k] = None

    with open(OUT, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\n  [OK] Risk scores saved to {OUT}")
