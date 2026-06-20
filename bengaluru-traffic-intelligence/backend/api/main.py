"""
FastAPI Backend — BTP Parking Intelligence Module API
======================================================
Serves all pre-computed pipeline outputs and live LightGBM
Enforcement Demand Forecast predictions.

Start with:
    uvicorn api.main:app --reload --port 8000
    (run from the backend/ directory)

API docs: http://localhost:8000/docs
"""

import json
import warnings
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

warnings.filterwarnings("ignore")

# -- Optional imports ---------------------------------------------------------
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

# -- App setup ----------------------------------------------------------------
app = FastAPI(
    title="BTP Parking Intelligence API",
    description=(
        "AI-driven parking enforcement intelligence for "
        "Bengaluru Traffic Police — Flipkart Grid PS1"
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- File paths ---------------------------------------------------------------
BASE        = Path(__file__).parent.parent
DATA_DIR    = BASE / "data"
MODELS_DIR  = BASE / "models"
OUTPUTS_DIR = DATA_DIR / "outputs"

BTP_PEAK_HOURS = {19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5}

# -- Global state -------------------------------------------------------------
df            = None        # proximity_scored.parquet
DEMAND_SURF   = None        # demand_surface.parquet
h3_surface    = None
HEXES         = {"type": "FeatureCollection", "features": []}
CASCADE       = {"event_type_cascade": [], "junction_cascade": []}
RISK_SCORES   = []
VALIDATION    = {}
ENFORCEMENT   = {}
model_bundle  = None        # {"model", "encoders", "features", ...}
shap_explainer = None


# -- Helpers ------------------------------------------------------------------

def safe_load_parquet(path: Path, label: str):
    if path.exists():
        print(f"  Loading {label}...")
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


# -- Startup ------------------------------------------------------------------

@app.on_event("startup")
def load_all():
    global df, DEMAND_SURF, h3_surface, HEXES, CASCADE
    global RISK_SCORES, VALIDATION, ENFORCEMENT
    global model_bundle, shap_explainer

    print("\n-- Loading pre-computed outputs ------------------------")

    df = safe_load_parquet(
        DATA_DIR / "processed" / "proximity_scored.parquet", "incident data"
    )
    if not df.empty:
        df["start_datetime"] = pd.to_datetime(df["start_datetime"])

    DEMAND_SURF = safe_load_parquet(
        OUTPUTS_DIR / "demand_surface.parquet", "demand surface"
    )

    h3_surface  = safe_load_parquet(OUTPUTS_DIR / "h3_surface.parquet",       "H3 surface")
    HEXES       = safe_load_json(OUTPUTS_DIR / "hotspot_hexes.geojson",       "hotspot hexes",      HEXES)
    CASCADE     = safe_load_json(OUTPUTS_DIR / "cascade_scores.json",         "recurrence scores",  CASCADE)
    RISK_SCORES = safe_load_json(OUTPUTS_DIR / "risk_scores.json",            "risk scores",        [])
    VALIDATION  = safe_load_json(OUTPUTS_DIR / "validation_results.json",     "validation results", {})
    ENFORCEMENT = safe_load_json(OUTPUTS_DIR / "enforcement_schedule.json",   "enforcement schedule", {})

    # Load model bundle
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


# -- ENDPOINT: GET /incidents -------------------------------------------------

@app.get("/incidents", summary="Filtered violation list (live simulation)")
def get_incidents(
    zone:         Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    priority:     Optional[str] = Query(None),
    parking_only: bool          = Query(False),
    day:          Optional[int] = Query(None, ge=0, le=6),
    limit:        int           = Query(200, le=2000),
):
    if df is None or df.empty:
        raise HTTPException(503, "Incident data not loaded. Run pipeline first.")

    result = df.copy()
    if zone:         result = result[result.get("zone",       pd.Series()) == zone]
    if event_type:   result = result[result.get("event_type", pd.Series()) == event_type]
    if priority:     result = result[result.get("priority",   pd.Series()) == priority]
    if day is not None: result = result[result.get("day_of_week", pd.Series()) == day]
    if parking_only:
        result = result[
            result.get("is_high_confidence_parking",
                       pd.Series(0, index=result.index)) == 1
        ]

    COLS = [
        "id", "latitude", "longitude", "event_type", "event_cause",
        "corridor", "junction", "zone", "priority", "status",
        "requires_road_closure", "start_datetime",
        "veh_type", "is_parking_induced",
        "parking_probability", "composite_parking_score",
        "nearest_zone_type", "within_parking_zone",
    ]
    available = [c for c in COLS if c in result.columns]
    result    = result[available].tail(limit)
    records   = [clean_record(r) for r in result.to_dict("records")]
    return {"count": len(records), "incidents": records}


# -- ENDPOINT: GET /hotspots --------------------------------------------------

@app.get("/hotspots", summary="H3 hex hotspot GeoJSON for time slider")
def get_hotspots(
    hour: int = Query(8, ge=0, le=23),
    day:  int = Query(0, ge=0, le=6),
):
    if h3_surface is None or h3_surface.empty:
        return HEXES

    slot = h3_surface[
        (h3_surface["hour_of_day"] == hour) &
        (h3_surface["day_of_week"] == day)
    ][["h3_index", "incident_count", "weekly_rate", "avg_clearance"]].to_dict("records")

    slot_map = {r["h3_index"]: r for r in slot}
    features = []
    for f in HEXES.get("features", []):
        idx       = f["properties"].get("h3_index", "")
        slot_data = slot_map.get(idx, {})
        features.append({
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {
                **f["properties"],
                "slot_count":  slot_data.get("incident_count", 0),
                "weekly_rate": slot_data.get("weekly_rate", 0),
            },
        })
    return {"type": "FeatureCollection", "features": features}


# -- ENDPOINT: POST /predict --------------------------------------------------

DEMAND_LEVELS = {
    "HIGH":    {"label": "HIGH DEMAND",    "color": "#EF4444", "officers": "3+ officers — MANDATORY"},
    "MEDIUM":  {"label": "MEDIUM DEMAND",  "color": "#F59E0B", "officers": "2 officers — RECOMMENDED"},
    "LOW":     {"label": "LOW DEMAND",     "color": "#22C55E", "officers": "1 officer — ADVISORY"},
    "MINIMAL": {"label": "MINIMAL DEMAND", "color": "#94a3b8", "officers": "Patrol optional"},
}

@app.post("/predict", summary="Enforcement demand forecast + SHAP for a junction-time slot")
def predict_demand(payload: dict):
    """
    Input:  { junction_name, hour_of_day, day_of_week,
              [optional: zone, nearest_zone_type, avg_parking_score, ...] }
    Output: { expected_violations, demand_level, officer_recommendation,
              shap_values, base_value }
    """
    if model_bundle is None:
        raise HTTPException(503, "Model not loaded. Run pipeline step 05 first.")

    model    = model_bundle.get("model")
    encoders = model_bundle.get("encoders", {})
    features = model_bundle.get("features", [])

    # Encode the junction
    junction_name = str(payload.get("junction_name", "Unknown"))
    le_jn = encoders.get("junction")
    if le_jn is not None and junction_name in le_jn.classes_:
        junction_enc = int(le_jn.transform([junction_name])[0])
    else:
        # Unseen junction — use median encoding
        junction_enc = int(len(le_jn.classes_) // 2) if le_jn else 0

    hour       = int(payload.get("hour_of_day", 20))
    day        = int(payload.get("day_of_week", 4))
    is_peak    = 1 if hour in BTP_PEAK_HOURS else 0
    is_weekend = 1 if day >= 5 else 0

    # Zone encoding
    le_zone = encoders.get("zone")
    zone_str = str(payload.get("zone", "Unknown"))
    if le_zone is not None and zone_str in le_zone.classes_:
        zone_enc = int(le_zone.transform([zone_str])[0])
    else:
        zone_enc = 0

    # Vehicle type encoding
    le_veh  = encoders.get("veh_type")
    veh_str = str(payload.get("dominant_veh_type", "Unknown"))
    if le_veh is not None and veh_str in le_veh.classes_:
        veh_enc = int(le_veh.transform([veh_str])[0])
    else:
        veh_enc = 0

    # Nearest zone type encoding
    le_nzt  = encoders.get("nearest_zone_type")
    nzt_str = str(payload.get("nearest_zone_type", "none"))
    if le_nzt is not None and nzt_str in le_nzt.classes_:
        nzt_enc = int(le_nzt.transform([nzt_str])[0])
    else:
        nzt_enc = 0

    row = pd.DataFrame([{
        "junction_encoded":      junction_enc,
        "hour_of_day":           hour,
        "day_of_week":           day,
        "is_peak_hour":          is_peak,
        "is_weekend":            is_weekend,
        "zone_encoded":          zone_enc,
        "dominant_veh_encoded":  veh_enc,
        "nearest_zone_encoded":  nzt_enc,
        "avg_parking_score":     float(payload.get("avg_parking_score", 0.5)),
        "parking_prob_mean":     float(payload.get("parking_prob_mean", 0.5)),
        "has_junction":          int(payload.get("has_junction", 1)),
    }])

    # Ensure correct feature order
    for f in features:
        if f not in row.columns:
            row[f] = 0
    row = row[features]

    try:
        pred_raw     = float(model.predict(row)[0])
        pred_count   = max(0.0, round(pred_raw, 1))
    except Exception as e:
        raise HTTPException(500, f"Prediction error: {e}")

    thresholds = model_bundle.get("demand_thresholds", {"HIGH": 16, "MEDIUM": 6, "LOW": 1})
    if pred_count >= thresholds["HIGH"]:
        level = "HIGH"
    elif pred_count >= thresholds["MEDIUM"]:
        level = "MEDIUM"
    elif pred_count >= thresholds["LOW"]:
        level = "LOW"
    else:
        level = "MINIMAL"

    level_info = DEMAND_LEVELS[level]

    # Calculate Congestion Severity
    junction_risk = next((r for r in RISK_SCORES if r.get("junction") == junction_name), {})
    base_risk = float(junction_risk.get("risk_score", 5.0))
    narrowness_index = round(min(5.0, max(1.0, 1.0 + (base_risk / 2.5))), 1)
    congestion_severity = round(pred_count * narrowness_index, 1)

    if congestion_severity >= 40:
        impact_level = "SEVERE CHOKEPOINT"
    elif congestion_severity >= 15:
        impact_level = "MODERATE CONGESTION"
    elif congestion_severity > 0:
        impact_level = "LOW IMPACT"
    else:
        impact_level = "NO IMPACT"

    # SHAP
    shap_dict  = {}
    base_value = 0.0
    if SHAP_AVAILABLE and shap_explainer is not None:
        try:
            sv = shap_explainer.shap_values(row)
            shap_dict = {
                feat: round(float(sv[0][i]), 2)
                for i, feat in enumerate(features)
            }
            shap_dict  = dict(sorted(shap_dict.items(), key=lambda x: abs(x[1]), reverse=True)[:10])
            base_value = round(float(shap_explainer.expected_value), 1)
        except Exception:
            pass

    return {
        "expected_violations":    pred_count,
        "demand_level":           level,
        "demand_label":           level_info["label"],
        "officer_recommendation": level_info["officers"],
        "shap_values":            shap_dict,
        "base_value":             base_value,
        "junction_name":          junction_name,
        "hour_of_day":            hour,
        "day_of_week":            day,
        "road_narrowness":        narrowness_index,
        "congestion_severity":    congestion_severity,
        "impact_level":           impact_level,
    }


# -- ENDPOINT: GET /junctions -------------------------------------------------

@app.get("/junctions", summary="List of all junctions with their basic stats")
def get_junctions(top_n: int = Query(100, le=300)):
    """Returns junctions from risk scores + recurrence data for frontend dropdowns."""
    junctions = []

    # Merge risk scores with recurrence
    risk_map = {r["junction"]: r for r in RISK_SCORES}
    rec_map  = {r["junction"]: r for r in CASCADE.get("junction_cascade", [])}

    all_jns = set(list(risk_map.keys()) + list(rec_map.keys()))
    for jn in all_jns:
        if jn in ("Unknown", "No Junction"):
            continue
        r = risk_map.get(jn, {})
        c = rec_map.get(jn, {})
        junctions.append({
            "junction":            jn,
            "risk_score":          r.get("risk_score", 0),
            "incident_count":      r.get("incident_count", c.get("total_violations", 0)),
            "avg_daily_violations": c.get("avg_daily_violations", 0),
            "top_cause":           r.get("top_cause", c.get("top_cause", "")),
            "zone":                r.get("zone", ""),
            "lat":                 r.get("lat"),
            "lon":                 r.get("lon"),
        })

    junctions.sort(key=lambda x: x["incident_count"], reverse=True)
    return {"junctions": junctions[:top_n]}


# -- ENDPOINT: GET /risk-scores -----------------------------------------------

@app.get("/risk-scores", summary="Top junctions by parking risk score")
def get_risk_scores(top_n: int = Query(20, le=50)):
    return {"junctions": RISK_SCORES[:top_n]}


# -- ENDPOINT: GET /cascade ---------------------------------------------------

@app.get("/cascade", summary="Recurrence analysis by junction / event type")
def get_cascade(junction: Optional[str] = Query(None)):
    """
    Returns recurrence stats (avg_daily_violations, active_days, recurrence_rate).
    Field avg_downstream = avg_daily_violations for frontend chart compatibility.
    """
    if junction:
        result = [
            r for r in CASCADE.get("junction_cascade", [])
            if r.get("junction") == junction
        ]
        return {"data": result}
    return CASCADE


# -- ENDPOINT: GET /enforcement-schedule --------------------------------------

@app.get("/enforcement-schedule", summary="Officer deployment schedule by junction")
def get_enforcement_schedule(junction: Optional[str] = Query(None)):
    if junction:
        if junction in ENFORCEMENT:
            return {"junction": junction, "schedule": ENFORCEMENT[junction]}
        raise HTTPException(404, f"Junction '{junction}' not in schedule.")
    return {"schedule": ENFORCEMENT}


# -- ENDPOINT: GET /validation ------------------------------------------------

@app.get("/validation", summary="Model validation metrics and SHAP feature importance")
def get_validation():
    if not VALIDATION:
        raise HTTPException(503, "Validation results not available. Run pipeline step 05.")
    return VALIDATION


# -- ENDPOINT: GET /summary ---------------------------------------------------

@app.get("/summary", summary="High-level KPI cards for dashboard")
def get_summary():
    if df is None or df.empty:
        raise HTTPException(503, "Data not loaded.")

    parking = df[
        df.get("is_high_confidence_parking",
               pd.Series(0, index=df.index)) == 1
    ] if "is_high_confidence_parking" in df.columns else df.head(0)

    total = len(df)
    return {
        "total_incidents":       int(total),
        "parking_incidents":     int(len(parking)),
        "parking_pct":           round(100 * len(parking) / max(1, total), 1),
        "avg_clearance_minutes": 0,           # not applicable — field kept for compat
        "parking_avg_clearance": 0,
        "road_closure_rate":     round(float(df["requires_road_closure"].mean()), 3)
                                 if "requires_road_closure" in df.columns else 0,
        "top_corridor":          str(df["corridor"].value_counts().index[0])
                                 if "corridor" in df.columns else "Unknown",
        "open_incidents":        int((df.get("status", pd.Series()) != "resolved").sum()),
        "date_range_start":      str(df["start_datetime"].min()),
        "date_range_end":        str(df["start_datetime"].max()),
        "top_junction":          (
            str(
                df[df["junction"].notna() & ~df["junction"].isin(["Unknown", "No Junction", ""])]["junction"]
                .value_counts().index[0]
            )
            if "junction" in df.columns and df["junction"].notna().any() else "Unknown"
        ),
        "top_violation":         str(df["event_type"].astype(str).value_counts().index[0])
                                 if "event_type" in df.columns else "Unknown",
    }


# -- ENDPOINT: GET /policy-recommendations ------------------------------------

@app.get("/policy-recommendations",
         summary="Groq / Llama-3 enforcement recommendations")
def get_policy_recs():
    """
    Passes top-3 junction recurrence stats to Groq (Llama-3.3-70b-versatile).
    Returns plain-English enforcement recommendations for BTP.
    Requires GROQ_API_KEY env var (free at console.groq.com).
    """
    if not GROQ_AVAILABLE:
        return {
            "recommendations": (
                "Groq SDK not installed. "
                "Run: pip install groq  "
                "then set GROQ_API_KEY in backend/.env (free at console.groq.com)."
            ),
            "generated_from": "unavailable",
        }

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {
            "recommendations": (
                "GROQ_API_KEY not set.\n"
                "1. Get a free key at https://console.groq.com/keys\n"
                "2. Add to backend/.env as: GROQ_API_KEY=gsk_...\n"
                "3. Restart the API server."
            ),
            "generated_from": "unavailable",
        }

    top3_risk = RISK_SCORES[:3]
    top3_rec  = CASCADE.get("junction_cascade", [])[:3]
    if not top3_risk and not top3_rec:
        return {"recommendations": "No risk/recurrence data. Run pipeline first.",
                "generated_from": "none"}

    context_lines = []
    for i, (j, rec) in enumerate(zip(top3_risk, top3_rec), 1):
        sched     = ENFORCEMENT.get(j.get("junction", ""), [])
        peak_slot = sched[0] if sched else {}
        context_lines.append(
            f"Junction {i}: {j.get('junction', 'Unknown')}\n"
            f"- Total violations: {j.get('incident_count', 'N/A')}\n"
            f"- Avg daily violations: {rec.get('avg_daily_violations', 'N/A')}\n"
            f"- Active violation days: {rec.get('active_days', 'N/A')}\n"
            f"- Top violation: {j.get('top_cause', 'N/A')}\n"
            f"- Risk score: {j.get('risk_score', 0)}\n"
            f"- Enforcement gap rate: {round(j.get('enforcement_gap_rate', 0)*100)}%\n"
            f"- Peak window: {peak_slot.get('day_name','N/A')} {peak_slot.get('time_period','N/A')}"
        )

    system_prompt = (
        "You are a traffic enforcement analyst advising Bengaluru Traffic Police (BTP). "
        "Be concise, specific, and actionable. Write plain English. "
        "Use a numbered list. Each recommendation must name the junction, "
        "the specific action, and cite one number from the data. "
        "Max 2 sentences per junction. No bullet symbols."
    )
    user_message = (
        "Here are the top 3 high-risk parking violation junctions "
        "from BTP enforcement data (Bengaluru):\n\n"
        + "\n\n".join(context_lines)
        + "\n\nGenerate 3 targeted patrol deployment recommendations for BTP, "
          "one per junction."
    )

    try:
        client   = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=500,
            temperature=0.4,
        )
        recs       = response.choices[0].message.content
        model_used = response.model
    except Exception as e:
        recs       = f"Groq API error: {e}"
        model_used = "groq-error"

    return {
        "recommendations": recs,
        "generated_from":  f"Groq / {model_used}",
        "data_source":     "BTP violation database",
    }


# -- ENDPOINT: GET /health ----------------------------------------------------

@app.get("/health")
def health():
    groq_key_set = bool(os.getenv("GROQ_API_KEY", ""))
    return {
        "status":          "ok",
        "data_loaded":     df is not None and not df.empty,
        "model_loaded":    model_bundle is not None,
        "shap_available":  SHAP_AVAILABLE,
        "groq_available":  GROQ_AVAILABLE and groq_key_set,
        "incident_count":  int(len(df)) if df is not None else 0,
        "model_type":      "Enforcement Demand Forecast (LightGBM)",
    }
