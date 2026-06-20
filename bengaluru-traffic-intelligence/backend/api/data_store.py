import json
import warnings
import os
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

BASE        = Path(__file__).parent.parent
DATA_DIR    = BASE / "data"
MODELS_DIR  = BASE / "models"
OUTPUTS_DIR = DATA_DIR / "outputs"

BTP_PEAK_HOURS = {19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5}

# Global State
df            = None
INCIDENTS_PARQUET_PATH = None
DEMAND_SURF   = None
h3_surface    = None
HEXES         = {"type": "FeatureCollection", "features": []}
CASCADE       = {"event_type_cascade": [], "junction_cascade": []}
RISK_SCORES   = []
VALIDATION    = {}
ENFORCEMENT   = {}
model_bundle  = None
shap_explainer = None


def safe_load_parquet(path: Path, label: str):
    if path.exists():
        print(f"  Loading {label}...")
        # For DuckDB, we don't load the massive dataframe into Pandas anymore.
        if "proximity_scored" in path.name:
            return None
        return pd.read_parquet(path)
    print(f"  WARN: {label} not found at {path}. Run pipeline first.")
    return pd.DataFrame()


def safe_load_json(path: Path, label: str, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    print(f"  WARN: {label} not found at {path}. Run pipeline first.")
    return default


def clean_record(rec: dict) -> dict:
    """Remove NaN, convert numpy types for JSON serialisation."""
    out = {}
    for k, v in rec.items():
        if isinstance(v, float) and np.isnan(v):    out[k] = None
        elif isinstance(v, pd.Timestamp):            out[k] = str(v)
        elif isinstance(v, (np.integer,)):           out[k] = int(v)
        elif isinstance(v, (np.floating,)):          out[k] = round(float(v), 4)
        elif not isinstance(v, (list, dict, str)) and pd.isna(v):
            out[k] = None
        else:                                        out[k] = v
    return out


def load_all_data():
    global df, INCIDENTS_PARQUET_PATH, DEMAND_SURF, h3_surface, HEXES, CASCADE
    global RISK_SCORES, VALIDATION, ENFORCEMENT
    global model_bundle, shap_explainer

    print("\n-- Loading pre-computed outputs ------------------------")

    INCIDENTS_PARQUET_PATH = DATA_DIR / "processed" / "proximity_scored.parquet"
    df = safe_load_parquet(INCIDENTS_PARQUET_PATH, "incident data")

    DEMAND_SURF = safe_load_parquet(OUTPUTS_DIR / "demand_surface.parquet", "demand surface")
    h3_surface  = safe_load_parquet(OUTPUTS_DIR / "h3_surface.parquet",       "H3 surface")
    HEXES       = safe_load_json(OUTPUTS_DIR / "hotspot_hexes.geojson",       "hotspot hexes",      HEXES)
    CASCADE     = safe_load_json(OUTPUTS_DIR / "cascade_scores.json",         "recurrence scores",  CASCADE)
    RISK_SCORES = safe_load_json(OUTPUTS_DIR / "risk_scores.json",            "risk scores",        [])
    VALIDATION  = safe_load_json(OUTPUTS_DIR / "validation_results.json",     "validation results", {})
    ENFORCEMENT = safe_load_json(OUTPUTS_DIR / "enforcement_schedule.json",   "enforcement schedule", {})

    lgbm_path = MODELS_DIR / "lgbm_model.pkl"
    if lgbm_path.exists():
        print("  Loading model bundle...")
        model_bundle = joblib.load(lgbm_path)
        if SHAP_AVAILABLE and model_bundle.get("model") is not None:
            try:
                shap_explainer = shap.TreeExplainer(model_bundle["model"])
            except Exception as e:
                print(f"  WARN: SHAP explainer failed: {e}")
    else:
        print(f"  WARN: lgbm_model.pkl not found. Run pipeline step 05.")

    print("-- All outputs loaded. API ready. ----------------------\n")
