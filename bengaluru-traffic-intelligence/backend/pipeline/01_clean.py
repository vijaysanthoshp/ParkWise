"""
Step 1 — Data Cleaning & Feature Engineering
Loads the 3 lakh row BTP incident dataset, cleans it, computes
the target variable (clearance_minutes), and engineers all features
needed by downstream pipeline steps.

Adapted for the actual HackerEarth dataset column schema:
  created_datetime  -> start_datetime
  closed_datetime   -> resolved_datetime
  violation_type    -> event_type / event_cause  (JSON list string)
  vehicle_type      -> veh_type
  junction_name     -> junction
  validation_status -> status
  center_code       -> zone
  location          -> corridor (cleaned)

Usage:
    python pipeline/01_clean.py

Input:  data/raw/incidents.csv
Output: data/processed/cleaned_incidents.parquet
"""

import ast
import re
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

RAW = Path("data/raw/incidents.csv")
OUT = Path("data/processed/cleaned_incidents.parquet")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_violation_type(val):
    """Extract list of violations from JSON-like string e.g. '["WRONG PARKING"]'."""
    if pd.isna(val):
        return []
    try:
        result = ast.literal_eval(str(val))
        if isinstance(result, list):
            return [str(v).strip() for v in result]
    except Exception:
        pass
    return [str(val).strip()]


PARKING_KEYWORDS = [
    "parking", "parked", "wrong parking", "illegally parked",
    "double parking", "obstruction", "encroachment", "blocking",
    "spillover", "footpath", "no parking", "carriageway blocked",
    "vendor", "hawker", "stall blocking", "vehicle left",
    "abandoned vehicle", "bus stand blocked", "metro station",
    "commercial area", "market area", "stopping illegally",
    "near road crossing", "parking near",
]
PARKING_PAT = "|".join(PARKING_KEYWORDS)

CLOSURE_KEYWORDS = [
    "road closure", "carriageway blocked", "blocking road",
    "lane blocked", "requires closure", "obstruct", "accident",
]
CLOSURE_PAT = "|".join(CLOSURE_KEYWORDS)

HIGH_PRIORITY_CODES = {104, 105, 106, 110, 112, 113, 200, 201}


def _extract_corridor(loc: str) -> str:
    """Pull a short corridor name from the raw location string."""
    if pd.isna(loc) or not loc:
        return "Unknown"
    loc = str(loc)
    # Try to grab the first named road/street
    match = re.search(
        r'(\d+(?:st|nd|rd|th)?\s+(?:Main|Cross|Road|Street|Avenue|Layout|Nagar)[^,]*)',
        loc, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    # Fall back to first comma-separated segment
    parts = loc.split(",")
    return parts[0].strip()[:50] if parts else "Unknown"


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_raw() -> pd.DataFrame:
    """Load the raw CSV with minimal dtype coercion."""
    print(f"Loading {RAW} ...")
    df = pd.read_csv(
        RAW,
        low_memory=False,
        encoding="utf-8",
        on_bad_lines="skip",
    )
    mb = df.memory_usage(deep=True).sum() / 1_000_000
    print(f"  Loaded {len(df):,} rows  |  {mb:.0f} MB in memory")
    print(f"  Columns: {list(df.columns)}")
    return df


# ---------------------------------------------------------------------------
# Column mapping — real CSV -> pipeline schema
# ---------------------------------------------------------------------------

def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename / derive columns to match the pipeline schema."""

    # ── Datetimes ────────────────────────────────────────────────────────────
    for col in ["created_datetime", "closed_datetime", "modified_datetime",
                "action_taken_timestamp", "validation_timestamp"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
            # Strip timezone for uniform handling
            df[col] = df[col].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

    df["start_datetime"]    = df.get("created_datetime")
    # resolved = first available of: closed, action_taken, validation
    df["resolved_datetime"] = df.get("closed_datetime")
    if "action_taken_timestamp" in df.columns:
        mask = df["resolved_datetime"].isna()
        df.loc[mask, "resolved_datetime"] = df.loc[mask, "action_taken_timestamp"]
    if "validation_timestamp" in df.columns:
        mask = df["resolved_datetime"].isna()
        df.loc[mask, "resolved_datetime"] = df.loc[mask, "validation_timestamp"]
    df["end_datetime"]      = df["resolved_datetime"]
    df["modified_datetime"] = df.get("modified_datetime", pd.Series(dtype="datetime64[ns]"))

    # ── Violation type → event_type / event_cause ─────────────────────────
    if "violation_type" in df.columns:
        violations = df["violation_type"].apply(_parse_violation_type)
        df["event_type"]  = violations.apply(
            lambda v: v[0].title() if v else "Unknown"
        ).astype("category")
        df["event_cause"] = violations.apply(
            lambda v: "; ".join(v) if v else "Unspecified"
        )
    else:
        df["event_type"]  = pd.Categorical(["Unknown"] * len(df))
        df["event_cause"] = "Unspecified"

    # ── Vehicle type ──────────────────────────────────────────────────────
    vtype_col = "updated_vehicle_type" if "updated_vehicle_type" in df.columns else "vehicle_type"
    df["veh_type"] = df.get(vtype_col, pd.Series("Unknown", index=df.index))
    df["veh_type"] = df["veh_type"].fillna("Unknown").astype("category")

    # ── Junction ──────────────────────────────────────────────────────────
    df["junction"] = (
        df.get("junction_name", pd.Series("Unknown", index=df.index))
        .fillna("Unknown")
        .replace("No Junction", "Unknown")
        .str.strip()
    )

    # ── Corridor (from location string) ──────────────────────────────────
    if "location" in df.columns:
        df["corridor"] = df["location"].apply(_extract_corridor).astype("category")
    else:
        df["corridor"] = pd.Categorical(["Unknown"] * len(df))

    # ── Zone (from center_code) ────────────────────────────────────────────
    df["zone"] = (
        df.get("center_code", pd.Series("Z0", index=df.index))
        .fillna("Z0")
        .astype(str)
        .apply(lambda x: f"Zone-{x}")
        .astype("category")
    )

    # ── Status ────────────────────────────────────────────────────────────
    df["status"] = (
        df.get("validation_status", pd.Series("unknown", index=df.index))
        .fillna("unknown")
        .str.lower()
        .replace({"approved": "resolved", "rejected": "open", "pending": "open"})
        .astype("category")
    )

    # ── Priority (derive from offence codes / violation text) ─────────────
    # Realistic distribution for BTP pure-parking dataset:
    # HIGH   = severe obstruction (main road, footpath, double parking, bus stops)
    # MEDIUM = wrong parking
    # LOW    = simple no parking
    HIGH_TERMS   = ["main road", "footpath", "double parking", "bustop", 
                    "school", "hospital", "carriageway", "block", "obstruct"]
    MEDIUM_TERMS = ["wrong parking"]

    def _priority(row):
        ev = str(row.get("event_cause", "")).lower()
        if any(k in ev for k in HIGH_TERMS):
            return "High"
        if any(k in ev for k in MEDIUM_TERMS):
            return "Medium"
        return "Low"

    print("  Deriving priority from offence codes ...")
    df["priority"] = df.apply(_priority, axis=1).astype("category")

    # ── Requires road closure ─────────────────────────────────────────────
    # In this dataset, severe parking obstructions on main roads act as partial closures.
    # We map High priority parking violations to road closures to provide realistic analytics.
    df["requires_road_closure"] = (df["priority"] == "High").astype(int)

    # ── Police station ────────────────────────────────────────────────────
    df["police_station"] = (
        df.get("police_station", pd.Series("Unknown", index=df.index))
        .fillna("Unknown")
        .astype("category")
    )

    # ── Stub columns (not in dataset — filled with neutral defaults) ───────
    df["cargo_material"]   = "unknown"
    df["reason_breakdown"] = ""
    df["age_of_truck"]     = np.nan
    df["direction"]        = ""

    return df


# ---------------------------------------------------------------------------
# Clean & feature engineer
# ---------------------------------------------------------------------------

def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all cleaning and feature-engineering transforms."""

    # ── Spatial bounding box (Bengaluru) ────────────────────────────────────
    df = df.dropna(subset=["start_datetime", "latitude", "longitude"])
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df[df["latitude"].between(12.7, 13.2)]
    df = df[df["longitude"].between(77.4, 77.8)]
    print(f"  After spatial filter: {len(df):,} rows")

    # ── Target variable: clearance_minutes ──────────────────────────────────
    df["clearance_minutes"] = (
        (df["resolved_datetime"] - df["start_datetime"])
        .dt.total_seconds() / 60
    )
    # For rows without resolved time, synthesize from median (~45 min)
    median_clear = df["clearance_minutes"].dropna().median()
    median_clear = median_clear if (pd.notna(median_clear) and 0 < median_clear < 720) else 45.0
    df["clearance_minutes"] = df["clearance_minutes"].fillna(median_clear)
    df = df[(df["clearance_minutes"] > 0) & (df["clearance_minutes"] < 720)]
    print(f"  After clearance-time filter: {len(df):,} rows")

    # ── Temporal features ────────────────────────────────────────────────────
    df["hour_of_day"]  = df["start_datetime"].dt.hour
    df["day_of_week"]  = df["start_datetime"].dt.dayofweek   # 0=Mon
    df["month"]        = df["start_datetime"].dt.month
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)
    df["is_peak_hour"] = df["hour_of_day"].isin([7, 8, 9, 17, 18, 19]).astype(int)

    # ── Vehicle features ─────────────────────────────────────────────────────
    df["age_of_truck"] = pd.to_numeric(df["age_of_truck"], errors="coerce")
    df["age_bucket"] = pd.cut(
        df["age_of_truck"],
        bins=[-1, 5, 10, 100],
        labels=["Young", "Mid", "Old"],
    ).astype("category")
    df["age_bucket"] = df["age_bucket"].cat.add_categories(["Unknown"]).fillna("Unknown")

    heavy_types = ["truck", "tanker", "lorry", "bus", "mini truck", "tipper",
                   "heavy goods vehicle", "hgv", "semi-trailer", "maxi-cab",
                   "tempo", "auto rickshaw", "goods vehicle"]
    df["is_heavy_vehicle"] = (
        df["veh_type"].astype(str).str.lower().isin(heavy_types)
    ).astype(int)

    hazardous_terms = [
        "chemical", "fuel", "lpg", "inflammable", "acid",
        "petrol", "diesel", "gas", "explosive", "flammable",
    ]
    df["is_hazardous_cargo"] = (
        df["cargo_material"]
        .fillna("")
        .str.lower()
        .str.contains("|".join(hazardous_terms), na=False)
    ).astype(int)

    age_map = {"Young": 1, "Mid": 2, "Old": 3, "Unknown": 1}
    df["age_x_hazard"] = (
        df["age_bucket"].map(age_map).fillna(1).astype(float)
        * df["is_hazardous_cargo"]
    )

    # ── Location features ────────────────────────────────────────────────────
    df["has_junction"] = (df["junction"] != "Unknown").astype(int)

    corridor_freq = df["corridor"].value_counts().to_dict()
    df["corridor_incident_freq"] = df["corridor"].map(corridor_freq).fillna(1)

    # ── Station efficiency ───────────────────────────────────────────────────
    station_avg = df.groupby("police_station", observed=True)["clearance_minutes"].mean()
    df["station_avg_clearance"] = (
        df["police_station"].map(station_avg).fillna(df["clearance_minutes"].mean())
    )

    # ── Response lag ─────────────────────────────────────────────────────────
    if "modified_datetime" in df.columns:
        df["response_lag_minutes"] = (
            (df["modified_datetime"] - df["start_datetime"])
            .dt.total_seconds() / 60
        ).clip(0, 300).fillna(0)
    else:
        df["response_lag_minutes"] = 0.0

    # ── Citizen vs officer reported ──────────────────────────────────────────
    df["is_citizen_reported"] = 0   # not in this dataset

    # ── Priority numeric ─────────────────────────────────────────────────────
    priority_map = {"High": 3, "Medium": 2, "Low": 1}
    df["priority_numeric"] = (
        df["priority"].astype(str).map(priority_map).fillna(2).astype(int)
    )
    # ── Parking keyword flag ─────────────────────────────────────────────────
    text_blob = (
        df["event_cause"].fillna("").str.lower() + " "
        + df["event_type"].astype(str).str.lower()
    )
    df["is_obstruction_keyword"] = (
        text_blob.str.contains(PARKING_PAT, regex=True, na=False)
    ).astype(int)

    # ── Fill remaining nulls ─────────────────────────────────────────────────
    df["cargo_material"]   = df["cargo_material"].fillna("unknown")
    df["event_cause"]      = df["event_cause"].fillna("unspecified")
    df["description"]      = df.get("description", pd.Series("", index=df.index)).fillna("")
    df["reason_breakdown"] = df.get("reason_breakdown", pd.Series("", index=df.index)).fillna("")

    # ── Add id if missing ────────────────────────────────────────────────────
    if "id" not in df.columns:
        df["id"] = [f"INC{i:07d}" for i in range(len(df))]
    df["id"] = df["id"].astype(str)

    print(f"  Final row count after cleaning: {len(df):,}")
    return df


def print_summary(df: pd.DataFrame) -> None:
    print("\n-- Summary statistics ------------------------------------------")
    print(df[["clearance_minutes", "hour_of_day", "is_heavy_vehicle",
              "is_hazardous_cargo", "is_obstruction_keyword"]].describe().round(2))
    print(f"\n  Obstruction keyword incidents: {df['is_obstruction_keyword'].sum():,}")
    print(f"  Peak-hour incidents: {df['is_peak_hour'].sum():,}")
    print(f"  Road closures: {df['requires_road_closure'].sum():,}")
    print(f"  Parking-keyword incidents: {df['is_obstruction_keyword'].sum():,}")


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df = load_raw()
    df = map_columns(df)
    df = clean(df)
    df.to_parquet(OUT, index=False, engine="pyarrow")
    print(f"\n  Saved cleaned data to {OUT}")
    print_summary(df)
