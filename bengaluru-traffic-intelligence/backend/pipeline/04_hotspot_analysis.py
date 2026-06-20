"""
Step 4 - Temporal Hotspot Analysis
Builds an H3 hexagonal probability surface (incidents per hex per time slot)
and runs DBSCAN to find named parking incident clusters.

Research basis:
  - DBSCAN validated for road-network-constrained spatial clustering
    where KDE's smooth surface assumption fails on irregular urban grids.
  - H3 hexagonal grids: equal-area cells with 6-neighbour adjacency,
    proven in production at Swiggy/Zomato for Bengaluru delivery zones.

Usage:
    python pipeline/04_hotspot_analysis.py

Input:  data/processed/proximity_scored.parquet
Output: data/outputs/hotspot_hexes.geojson
        data/outputs/h3_surface.parquet
        data/outputs/dbscan_clusters.json
"""

import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.cluster import DBSCAN

warnings.filterwarnings("ignore")

try:
    import h3
    H3_AVAILABLE = True
    # -- h3 v3 / v4 compatibility shim ------------------------------
    # v4 renamed: geo_to_h3 -> latlng_to_cell
    #             h3_to_geo_boundary -> cell_to_boundary
    if not hasattr(h3, 'geo_to_h3'):
        h3.geo_to_h3 = lambda lat, lng, res: h3.latlng_to_cell(lat, lng, res)
    if not hasattr(h3, 'h3_to_geo_boundary'):
        def _boundary_v4(cell, geo_json=False):
            coords = h3.cell_to_boundary(cell)   # returns list of (lat, lng)
            if geo_json:
                return [[lng, lat] for lat, lng in coords]   # GeoJSON is [lng, lat]
            return coords
        h3.h3_to_geo_boundary = _boundary_v4
except ImportError:
    H3_AVAILABLE = False
    print("  WARNING: h3 library not installed. "
          "Install with: pip install h3")

IN           = Path("data/processed/proximity_scored.parquet")
OUT_HEXES    = Path("data/outputs/hotspot_hexes.geojson")
OUT_SURFACE  = Path("data/outputs/h3_surface.parquet")
OUT_CLUSTERS = Path("data/outputs/dbscan_clusters.json")

H3_RESOLUTION    = 7      # ~1.2 km² per hex - junction-level granularity
DBSCAN_EPS_KM    = 0.3    # 300m radius
DBSCAN_MIN_SAMPS = 5


# -- H3 Surface ---------------------------------------------------------------

def assign_h3(df: pd.DataFrame) -> pd.DataFrame:
    """Assign H3 hex index to every incident."""
    if not H3_AVAILABLE:
        df["h3_index"] = "h3_unavailable"
        return df
    print("  Assigning H3 indices ...")
    df["h3_index"] = [
        h3.geo_to_h3(lat, lon, H3_RESOLUTION)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]
    return df


def build_h3_surface(df: pd.DataFrame):
    """
    Build a 7-day × 24-hour probability surface per H3 hex.
    Uses high-confidence parking incidents only.
    """
    parking = df[df["is_high_confidence_parking"] == 1].copy()
    print(f"  Building H3 surface from {len(parking):,} parking incidents ...")

    n_weeks = max(
        1,
        (df["start_datetime"].max() - df["start_datetime"].min()).days / 7,
    )

    surface = (
        parking
        .groupby(["h3_index", "day_of_week", "hour_of_day"], observed=True)
        .agg(
            incident_count    = ("id",                   "count"),
            avg_clearance     = ("clearance_minutes",    "mean"),
            road_closure_rate = ("requires_road_closure","mean"),
            cascade_risk_avg  = ("composite_parking_score", "mean"),
        )
        .reset_index()
    )
    surface["weekly_rate"] = (surface["incident_count"] / n_weeks).round(2)

    hex_summary = (
        parking
        .groupby("h3_index", observed=True)
        .agg(
            total_incidents   = ("id",                    "count"),
            avg_clearance     = ("clearance_minutes",     "mean"),
            road_closure_rate = ("requires_road_closure", "mean"),
            avg_parking_score = ("composite_parking_score","mean"),
        )
        .reset_index()
    )
    print(f"  H3 surface built: {len(hex_summary):,} unique hexes")
    return surface, hex_summary


def build_geojson(hex_summary: pd.DataFrame,
                  surface: pd.DataFrame) -> dict:
    """Convert H3 hex summary to GeoJSON for MapMyIndia overlay."""
    if not H3_AVAILABLE:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for _, row in hex_summary.iterrows():
        try:
            boundary = h3.h3_to_geo_boundary(row["h3_index"], geo_json=True)
            hex_surface = surface[surface["h3_index"] == row["h3_index"]]
            if not hex_surface.empty:
                peak_row  = hex_surface.loc[hex_surface["weekly_rate"].idxmax()]
                peak_hour = int(peak_row["hour_of_day"])
                peak_day  = int(peak_row["day_of_week"])
            else:
                peak_hour, peak_day = 8, 0

            feature = {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [boundary]},
                "properties": {
                    "h3_index":          row["h3_index"],
                    "total_incidents":   int(row["total_incidents"]),
                    "avg_clearance_min": round(float(row["avg_clearance"]), 1),
                    "road_closure_rate": round(float(row["road_closure_rate"]), 2),
                    "avg_parking_score": round(float(row["avg_parking_score"]), 2),
                    "peak_hour":         peak_hour,
                    "peak_day":          peak_day,
                    "risk_level": (
                        "HIGH"   if row["total_incidents"] > 20 else
                        "MEDIUM" if row["total_incidents"] > 8  else "LOW"
                    ),
                },
            }
            features.append(feature)
        except Exception:
            continue

    print(f"  Built GeoJSON with {len(features):,} hex features")
    return {"type": "FeatureCollection", "features": features}


# -- DBSCAN Clustering --------------------------------------------------------

def run_dbscan(df: pd.DataFrame) -> list:
    """Run DBSCAN on parking incidents to find named spatial clusters."""
    parking = (
        df[df["is_high_confidence_parking"] == 1][["latitude", "longitude", "id"]]
        .dropna()
    )
    print(f"\n  Running DBSCAN on {len(parking):,} parking incidents ...")

    coords  = np.radians(parking[["latitude", "longitude"]].values)
    eps_rad = DBSCAN_EPS_KM / 6371.0

    db = DBSCAN(
        eps=eps_rad,
        min_samples=DBSCAN_MIN_SAMPS,
        algorithm="ball_tree",
        metric="haversine",
    ).fit(coords)

    parking = parking.copy()
    parking["cluster_id"] = db.labels_

    n_clusters = len(set(db.labels_)) - (1 if -1 in db.labels_ else 0)
    noise_pct  = 100 * (db.labels_ == -1).sum() / len(parking)
    print(f"  DBSCAN: {n_clusters} clusters, {noise_pct:.1f}% noise points")

    cluster_summary = (
        parking[parking["cluster_id"] >= 0]
        .groupby("cluster_id")
        .agg(
            size        = ("id",        "count"),
            lat_center  = ("latitude",  "mean"),
            lon_center  = ("longitude", "mean"),
        )
        .sort_values("size", ascending=False)
        .reset_index()
    )

    records = cluster_summary.head(30).to_dict("records")
    for r in records:
        r["cluster_id"]  = int(r["cluster_id"])
        r["size"]        = int(r["size"])
        r["lat_center"]  = round(float(r["lat_center"]), 5)
        r["lon_center"]  = round(float(r["lon_center"]), 5)

    print(f"\n  Top 5 DBSCAN clusters:")
    for r in records[:5]:
        print(f"    Cluster {r['cluster_id']:2d}: {r['size']:4d} incidents  "
              f"@ ({r['lat_center']:.4f}, {r['lon_center']:.4f})")
    return records


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    OUT_HEXES.parent.mkdir(parents=True, exist_ok=True)

    print("Loading proximity-scored data ...")
    df = pd.read_parquet(IN)
    df["start_datetime"] = pd.to_datetime(df["start_datetime"])

    df = assign_h3(df)

    surface, hex_summary = build_h3_surface(df)
    surface.to_parquet(OUT_SURFACE, index=False)
    print(f"  [OK] H3 surface saved to {OUT_SURFACE}")

    geojson = build_geojson(hex_summary, surface)
    with open(OUT_HEXES, "w") as f:
        json.dump(geojson, f)
    print(f"  [OK] Hotspot GeoJSON saved to {OUT_HEXES}")

    cluster_records = run_dbscan(df)
    with open(OUT_CLUSTERS, "w") as f:
        json.dump(cluster_records, f, indent=2)
    print(f"  [OK] DBSCAN clusters saved to {OUT_CLUSTERS}")
