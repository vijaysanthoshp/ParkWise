"""
Step 3 - Spatial Proximity Scoring
Assigns each incident a proximity_risk_score based on distance to
known parking-prone zones (commercial areas, metro stations, hospitals,
event venues). Combines with NLP probability into composite_parking_score.

Research basis:
  - Annals of GIS 2019: POI categories (retail, accommodation, food)
    are positively associated with parking violation density.
    Random Forest with POI features achieves highest classification
    accuracy across all spatial analysis scales.

Usage:
    python pipeline/03_proximity_scoring.py

Input:  data/processed/parking_classified.parquet
Output: data/processed/proximity_scored.parquet
"""

import warnings
import numpy as np
import pandas as pd
from math import radians, cos
from pathlib import Path

warnings.filterwarnings("ignore")

IN  = Path("data/processed/parking_classified.parquet")
OUT = Path("data/processed/proximity_scored.parquet")

# -- Known parking-prone zones in Bengaluru ----------------------------------
# Format: (lat, lon, zone_type, risk_weight)
# In production: fetch from MapMyIndia POI API.
# For hackathon: hardcoded major known zones.
KNOWN_ZONES = [
    # -- Commercial / market areas ------------------------------------------
    (12.9716, 77.5946, "commercial", 1.0),   # MG Road
    (12.9698, 77.6099, "commercial", 0.9),   # Brigade Road
    (12.9352, 77.6245, "market",     1.0),   # Koramangala market
    (12.9766, 77.5713, "commercial", 0.8),   # Rajajinagar market
    (12.9889, 77.5697, "market",     0.9),   # Malleswaram market
    (12.9784, 77.6408, "commercial", 0.8),   # Indiranagar 100ft road
    (12.9120, 77.6446, "commercial", 0.7),   # BTM commercial area
    (12.9261, 77.6768, "commercial", 0.7),   # Whitefield commercial
    (13.0100, 77.5560, "commercial", 0.8),   # Yeshwanthpur market
    (12.9279, 77.6271, "market",     0.9),   # HSR Layout market
    (12.9592, 77.6974, "commercial", 0.7),   # Marathahalli market
    (12.9850, 77.7093, "commercial", 0.6),   # KR Puram commercial
    (13.0600, 77.5900, "commercial", 0.7),   # Hebbal market
    (13.0358, 77.5970, "commercial", 0.6),   # Nagawara market
    # -- Metro stations ----------------------------------------------------
    (12.9716, 77.5946, "metro",      0.8),   # MG Road metro
    (12.9891, 77.5618, "metro",      0.8),   # Rajajinagar metro
    (12.9549, 77.6205, "metro",      0.7),   # Indiranagar metro
    (12.9248, 77.6741, "metro",      0.7),   # Whitefield metro
    (12.9772, 77.5714, "metro",      0.7),   # Rajajinagar/Majestic metro
    (12.9767, 77.5713, "metro",      0.8),   # Majestic metro interchange
    (13.0100, 77.5525, "metro",      0.7),   # Yeshwanthpur metro
    (12.9144, 77.6010, "metro",      0.7),   # Jayanagar metro
    (12.9584, 77.5507, "metro",      0.6),   # Vijayanagar metro
    # -- Hospitals ---------------------------------------------------------
    (12.9352, 77.6082, "hospital",   0.6),   # Manipal Hospital, HAL
    (12.9719, 77.5937, "hospital",   0.6),   # St Martha's Hospital
    (12.9584, 77.6487, "hospital",   0.5),   # Manipal Indiranagar
    (12.9369, 77.5975, "hospital",   0.5),   # Apollo Hospitals
    (12.9716, 77.5660, "hospital",   0.5),   # Victoria Hospital
    # -- Event venues ------------------------------------------------------
    (12.9604, 77.5996, "event_venue", 0.7),  # NIMHANS Convention Centre
    (13.0100, 77.5560, "event_venue", 0.6),  # Kanteerava Stadium
    (12.9714, 77.5961, "event_venue", 0.5),  # Town Hall
    (12.9985, 77.5520, "event_venue", 0.5),  # Palace Grounds
]

BUFFER_METERS = 200   # incidents within 200m get a proximity score


def compute_proximity_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Vectorised Haversine distance from each incident to every known zone.
    Assigns proximity_risk_score (0–1) and nearest_zone_type.
    """
    print(f"  Computing proximity scores for {len(df):,} incidents ...")

    lats = df["latitude"].values
    lons = df["longitude"].values
    n    = len(df)

    min_dist       = np.full(n, np.inf)
    zone_type_arr  = np.full(n, "none", dtype=object)
    prox_score_arr = np.zeros(n)
    within_buf_arr = np.zeros(n, dtype=int)

    R = 6_371_000.0  # Earth radius in metres

    for z_lat, z_lon, z_type, z_weight in KNOWN_ZONES:
        # Vectorised Haversine
        phi1  = np.radians(lats)
        phi2  = radians(z_lat)
        dphi  = np.radians(z_lat - lats)
        dlam  = np.radians(z_lon - lons)
        a     = np.sin(dphi / 2) ** 2 + np.cos(phi1) * cos(phi2) * np.sin(dlam / 2) ** 2
        dist  = 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

        # Update nearest zone
        closer = dist < min_dist
        min_dist[closer]  = dist[closer]
        zone_type_arr[closer] = z_type

        # Proximity score: linear decay from z_weight -> 0 over BUFFER_METERS
        score = np.where(
            dist <= BUFFER_METERS,
            z_weight * (1.0 - dist / BUFFER_METERS),
            0.0,
        )
        prox_score_arr = np.maximum(prox_score_arr, score)
        within_buf_arr |= (dist <= BUFFER_METERS).astype(int)

    df["nearest_zone_meters"]  = min_dist.astype(int)
    df["nearest_zone_type"]    = zone_type_arr
    df["proximity_risk_score"] = np.round(prox_score_arr, 3)
    df["within_parking_zone"]  = within_buf_arr

    # -- Composite score: NLP probability + spatial proximity ----------------
    df["composite_parking_score"] = (
        0.6 * df["parking_probability"] + 0.4 * df["proximity_risk_score"]
    ).round(3)

    # -- High-confidence parking flag ----------------------------------------
    df["is_high_confidence_parking"] = (
        (df["composite_parking_score"] >= 0.5) |
        (df["parking_probability"] >= 0.65)
    ).astype(int)

    n_hcp = df["is_high_confidence_parking"].sum()
    print(f"  High-confidence parking incidents: {n_hcp:,} "
          f"({100 * n_hcp / len(df):.1f}%)")
    return df


if __name__ == "__main__":
    print("Loading classified data ...")
    df = pd.read_parquet(IN)

    df = compute_proximity_score(df)

    df.to_parquet(OUT, index=False)
    print(f"\n  [OK] Saved to {OUT}")

    print("\n-- Nearest zone type distribution ----------------------")
    print(df["nearest_zone_type"].value_counts())
    print("\n-- Proximity score stats --------------------------------")
    print(df[["proximity_risk_score", "composite_parking_score"]].describe().round(3))
