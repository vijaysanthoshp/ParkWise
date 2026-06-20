"""
Step 2 — AI Parking Incident Classifier
This dataset is a pure parking-violation dataset from BTP (all incidents ARE
parking-related). Instead of a binary classifier, we assign a nuanced
parking_probability score based on:
  - Violation type severity (e.g. road-blocking vs minor parking)
  - Number of concurrent violations
  - Location type (junction vs non-junction)
  - Vehicle type (heavy vehicle parked = higher risk)

This mimics what the downstream pipeline expects:
  parking_probability        float  0-1
  is_parking_induced         int    0/1
  is_high_confidence_parking int    0/1
  parking_confidence         category  Low/Medium/High

Usage:
    python pipeline/02_parking_classifier.py

Input:  data/processed/cleaned_incidents.parquet
Output: data/processed/parking_classified.parquet
        models/parking_classifier.pkl  (score model metadata)
"""

import ast
import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

warnings.filterwarnings("ignore")

IN  = Path("data/processed/cleaned_incidents.parquet")
OUT = Path("data/processed/parking_classified.parquet")
MDL = Path("models/parking_classifier.pkl")

# ── Violation severity weights ────────────────────────────────────────────────
# Higher weight = more severe parking violation = higher probability score
HIGH_SEVERITY = [
    "wrong parking", "parking near road crossing", "parking on footpath",
    "double parking", "carriageway blocked", "road block",
    "parking near junction", "no parking zone", "blocking",
    "obstruct", "encroach", "abandoned vehicle",
]
MEDIUM_SEVERITY = [
    "parking", "parked", "stopping illegally", "vehicle left",
    "bus stand blocked", "metro station", "market area",
    "commercial area", "vendor", "hawker",
]


def score_violation(violation_list: list) -> float:
    """
    Compute a parking severity probability from the list of violations.
    Returns a float in [0.40, 1.00].
    """
    if not violation_list:
        return 0.50

    score = 0.40   # base: all incidents are parking-related
    joined = " ".join(violation_list).lower()

    # Each HIGH violation adds 0.20 (capped)
    for term in HIGH_SEVERITY:
        if term in joined:
            score += 0.20
            break

    # Each MEDIUM violation adds 0.10
    for term in MEDIUM_SEVERITY:
        if term in joined:
            score += 0.10
            break

    # Multiple concurrent violations → riskier
    n = len(violation_list)
    if n >= 3:
        score += 0.15
    elif n == 2:
        score += 0.08

    return min(score, 1.00)


def parse_violations(val) -> list:
    """Parse JSON-like violation_type column."""
    if pd.isna(val):
        return []
    try:
        result = ast.literal_eval(str(val))
        if isinstance(result, list):
            return [str(v).strip() for v in result]
    except Exception:
        pass
    return [str(val).strip()]


def compute_parking_probability(df: pd.DataFrame) -> pd.DataFrame:
    """Assign parking_probability to every row."""
    print("  Computing parking probability scores ...")

    # Base scores from violation type
    if "violation_type" in df.columns:
        violations = df["violation_type"].apply(parse_violations)
    else:
        # Fall back to event_cause column
        violations = df["event_cause"].apply(lambda x: [str(x)] if pd.notna(x) else [])

    df["parking_probability"] = violations.apply(score_violation)

    # Boost for heavy vehicles (parked illegally = higher risk)
    heavy_mask = df.get("is_heavy_vehicle", pd.Series(0, index=df.index)) == 1
    df.loc[heavy_mask, "parking_probability"] = (
        df.loc[heavy_mask, "parking_probability"] + 0.10
    ).clip(upper=1.0)

    # Boost for junction incidents
    junction_mask = df.get("has_junction", pd.Series(0, index=df.index)) == 1
    df.loc[junction_mask, "parking_probability"] = (
        df.loc[junction_mask, "parking_probability"] + 0.08
    ).clip(upper=1.0)

    # All incidents are parking-induced (this is a parking violation dataset)
    df["is_parking_induced"]         = 1
    df["is_high_confidence_parking"] = (df["parking_probability"] >= 0.65).astype(int)

    df["parking_confidence"] = pd.cut(
        df["parking_probability"],
        bins=[0, 0.55, 0.75, 1.0],
        labels=["Low", "Medium", "High"],
    ).astype("category")

    return df


if __name__ == "__main__":
    MDL.parent.mkdir(parents=True, exist_ok=True)

    print("Loading cleaned data ...")
    df = pd.read_parquet(IN)

    # Load raw violations if available for richer scoring
    raw_path = Path("data/raw/incidents.csv")
    if raw_path.exists():
        print("  Loading violation_type from raw CSV for scoring ...")
        raw = pd.read_csv(
            raw_path,
            usecols=["id", "violation_type"],
            low_memory=False,
            encoding="utf-8",
            on_bad_lines="skip",
        )
        df = df.merge(raw, on="id", how="left", suffixes=("", "_raw"))
        if "violation_type_raw" in df.columns:
            df["violation_type"] = df["violation_type_raw"].fillna(df.get("violation_type", ""))
            df.drop(columns=["violation_type_raw"], inplace=True)

    print("\nAssigning parking probability scores ...")
    df = compute_parking_probability(df)

    # Save a lightweight metadata object so downstream scripts find the model file
    meta = {
        "type": "rule_based_scorer",
        "note": "All incidents are parking violations; probabilities scored by severity.",
        "high_severity": HIGH_SEVERITY,
        "medium_severity": MEDIUM_SEVERITY,
    }
    joblib.dump(meta, MDL)
    print(f"  Scorer metadata saved to {MDL}")

    df.to_parquet(OUT, index=False)
    print(f"  Classified data saved to {OUT}")

    print("\n-- Parking probability distribution --------------------------------")
    print(df["parking_probability"].describe().round(3))
    print("\n-- Confidence distribution ------------------------------------------")
    print(df["parking_confidence"].value_counts())
    hc = df["is_high_confidence_parking"].sum()
    print(f"\n  High-confidence parking incidents: {hc:,} ({100*hc/len(df):.1f}%)")
    print(f"  Total incidents processed: {len(df):,}")
