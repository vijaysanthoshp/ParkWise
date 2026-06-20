import os
import pandas as pd
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

import api.data_store as ds

router = APIRouter()

DEMAND_LEVELS = {
    "HIGH":    {"label": "HIGH DEMAND",    "color": "#EF4444", "officers": "3+ officers — MANDATORY"},
    "MEDIUM":  {"label": "MEDIUM DEMAND",  "color": "#F59E0B", "officers": "2 officers — RECOMMENDED"},
    "LOW":     {"label": "LOW DEMAND",     "color": "#22C55E", "officers": "1 officer — ADVISORY"},
    "MINIMAL": {"label": "MINIMAL DEMAND", "color": "#94a3b8", "officers": "Patrol optional"},
}

@router.get("/incidents", summary="Filtered violation list (live simulation)")
def get_incidents(
    zone:         Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    priority:     Optional[str] = Query(None),
    parking_only: bool          = Query(False),
    day:          Optional[int] = Query(None, ge=0, le=6),
    limit:        int           = Query(200, le=2000),
):
    if not ds.INCIDENTS_PARQUET_PATH or not ds.INCIDENTS_PARQUET_PATH.exists():
        raise HTTPException(503, "Incident data not found. Run pipeline first.")

    import duckdb
    path_str = str(ds.INCIDENTS_PARQUET_PATH).replace('\\', '/')
    
    COLS = [
        "id", "latitude", "longitude", "event_type", "event_cause",
        "corridor", "junction", "zone", "priority", "status",
        "requires_road_closure", "start_datetime",
        "veh_type", "is_parking_induced",
        "parking_probability", "composite_parking_score",
        "nearest_zone_type", "within_parking_zone",
    ]
    col_str = ", ".join(COLS)
    
    query = f"SELECT {col_str} FROM '{path_str}'"
    filters = []
    if zone:         filters.append(f"zone = '{zone}'")
    if event_type:   filters.append(f"event_type = '{event_type}'")
    if priority:     filters.append(f"priority = '{priority}'")
    if day is not None: filters.append(f"day_of_week = {day}")
    if parking_only: filters.append("is_high_confidence_parking = 1")
    
    if filters:
        query += " WHERE " + " AND ".join(filters)
        
    query += f" ORDER BY start_datetime DESC LIMIT {limit}"
    
    try:
        with duckdb.connect() as con:
            result = con.query(query).df()
    except Exception as e:
        raise HTTPException(500, f"Query error: {e}")

    records = [ds.clean_record(r) for r in result.to_dict("records")]
    return {"count": len(records), "incidents": records}


@router.get("/hotspots", summary="H3 hex hotspot GeoJSON for time slider")
def get_hotspots(hour: int = Query(8, ge=0, le=23), day: int = Query(0, ge=0, le=6)):
    if ds.h3_surface is None or ds.h3_surface.empty:
        return ds.HEXES

    slot = ds.h3_surface[
        (ds.h3_surface["hour_of_day"] == hour) &
        (ds.h3_surface["day_of_week"] == day)
    ][["h3_index", "incident_count", "weekly_rate", "avg_clearance"]].to_dict("records")

    slot_map = {r["h3_index"]: r for r in slot}
    features = []
    for f in ds.HEXES.get("features", []):
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


@router.post("/predict", summary="Enforcement demand forecast + SHAP for a junction-time slot")
def predict_demand(payload: dict):
    if ds.model_bundle is None:
        raise HTTPException(503, "Model not loaded. Run pipeline step 05 first.")

    model    = ds.model_bundle.get("model")
    encoders = ds.model_bundle.get("encoders", {})
    features = ds.model_bundle.get("features", [])

    junction_name = str(payload.get("junction_name", "Unknown"))
    le_jn = encoders.get("junction")
    if le_jn is not None and junction_name in le_jn.classes_:
        junction_enc = int(le_jn.transform([junction_name])[0])
    else:
        junction_enc = int(len(le_jn.classes_) // 2) if le_jn else 0

    hour       = int(payload.get("hour_of_day", 20))
    day        = int(payload.get("day_of_week", 4))
    is_peak    = 1 if hour in ds.BTP_PEAK_HOURS else 0
    is_weekend = 1 if day >= 5 else 0

    le_zone = encoders.get("zone")
    zone_str = str(payload.get("zone", "Unknown"))
    zone_enc = int(le_zone.transform([zone_str])[0]) if le_zone is not None and zone_str in le_zone.classes_ else 0

    le_veh  = encoders.get("veh_type")
    veh_str = str(payload.get("dominant_veh_type", "Unknown"))
    veh_enc = int(le_veh.transform([veh_str])[0]) if le_veh is not None and veh_str in le_veh.classes_ else 0

    le_nzt  = encoders.get("nearest_zone_type")
    nzt_str = str(payload.get("nearest_zone_type", "none"))
    nzt_enc = int(le_nzt.transform([nzt_str])[0]) if le_nzt is not None and nzt_str in le_nzt.classes_ else 0

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

    for f in features:
        if f not in row.columns:
            row[f] = 0
    row = row[features]

    try:
        pred_raw     = float(model.predict(row)[0])
        pred_count   = max(0.0, round(pred_raw, 1))
    except Exception as e:
        raise HTTPException(500, f"Prediction error: {e}")

    thresholds = ds.model_bundle.get("demand_thresholds", {"HIGH": 16, "MEDIUM": 6, "LOW": 1})
    if pred_count >= thresholds["HIGH"]: level = "HIGH"
    elif pred_count >= thresholds["MEDIUM"]: level = "MEDIUM"
    elif pred_count >= thresholds["LOW"]: level = "LOW"
    else: level = "MINIMAL"

    level_info = DEMAND_LEVELS[level]

    junction_risk = next((r for r in ds.RISK_SCORES if r.get("junction") == junction_name), {})
    base_risk = float(junction_risk.get("risk_score", 5.0))
    narrowness_index = round(min(5.0, max(1.0, 1.0 + (base_risk / 2.5))), 1)
    congestion_severity = round(pred_count * narrowness_index, 1)

    if congestion_severity >= 40: impact_level = "SEVERE CHOKEPOINT"
    elif congestion_severity >= 15: impact_level = "MODERATE CONGESTION"
    elif congestion_severity > 0: impact_level = "LOW IMPACT"
    else: impact_level = "NO IMPACT"

    shap_dict  = {}
    base_value = 0.0
    if ds.SHAP_AVAILABLE and ds.shap_explainer is not None:
        try:
            sv = ds.shap_explainer.shap_values(row)
            shap_dict = {feat: round(float(sv[0][i]), 2) for i, feat in enumerate(features)}
            shap_dict = dict(sorted(shap_dict.items(), key=lambda x: abs(x[1]), reverse=True)[:10])
            base_value = round(float(ds.shap_explainer.expected_value), 1)
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


@router.get("/junctions", summary="List of all junctions with their basic stats")
def get_junctions(top_n: int = Query(100, le=300)):
    junctions = []
    risk_map = {r["junction"]: r for r in ds.RISK_SCORES}
    rec_map  = {r["junction"]: r for r in ds.CASCADE.get("junction_cascade", [])}

    all_jns = set(list(risk_map.keys()) + list(rec_map.keys()))
    for jn in all_jns:
        if jn in ("Unknown", "No Junction"): continue
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


@router.get("/risk-scores", summary="Top junctions by parking risk score")
def get_risk_scores(top_n: int = Query(20, le=50)):
    return {"junctions": ds.RISK_SCORES[:top_n]}


@router.get("/cascade", summary="Recurrence analysis by junction / event type")
def get_cascade(junction: Optional[str] = Query(None)):
    if junction:
        result = [r for r in ds.CASCADE.get("junction_cascade", []) if r.get("junction") == junction]
        return {"data": result}
    return ds.CASCADE


@router.get("/enforcement-schedule", summary="Officer deployment schedule by junction")
def get_enforcement_schedule(junction: Optional[str] = Query(None)):
    if junction:
        if junction in ds.ENFORCEMENT:
            return {"junction": junction, "schedule": ds.ENFORCEMENT[junction]}
        raise HTTPException(404, f"Junction '{junction}' not in schedule.")
    return {"schedule": ds.ENFORCEMENT}


@router.get("/validation", summary="Model validation metrics and SHAP feature importance")
def get_validation():
    if not ds.VALIDATION:
        raise HTTPException(503, "Validation results not available. Run pipeline step 05.")
    return ds.VALIDATION


@router.get("/summary", summary="High-level KPI cards for dashboard")
def get_summary():
    if not ds.INCIDENTS_PARQUET_PATH or not ds.INCIDENTS_PARQUET_PATH.exists():
        raise HTTPException(503, "Incident data not found.")

    import duckdb
    path = str(ds.INCIDENTS_PARQUET_PATH).replace('\\', '/')
    
    q = f"""
    SELECT 
        COUNT(*) as total_incidents,
        SUM(is_high_confidence_parking) as parking_incidents,
        AVG(requires_road_closure) as road_closure_rate,
        SUM(CASE WHEN status != 'resolved' THEN 1 ELSE 0 END) as open_incidents,
        MIN(start_datetime) as date_range_start,
        MAX(start_datetime) as date_range_end
    FROM '{path}'
    """
    
    try:
        with duckdb.connect() as con:
            res = con.query(q).df().iloc[0]
            top_corridor = con.query(f"SELECT corridor, COUNT(*) as c FROM '{path}' GROUP BY corridor ORDER BY c DESC LIMIT 1").df()['corridor'].iloc[0]
            top_violation = con.query(f"SELECT event_type, COUNT(*) as c FROM '{path}' GROUP BY event_type ORDER BY c DESC LIMIT 1").df()['event_type'].iloc[0]
            top_junction = con.query(f"SELECT junction, COUNT(*) as c FROM '{path}' WHERE junction NOT IN ('Unknown', 'No Junction', '') AND junction IS NOT NULL GROUP BY junction ORDER BY c DESC LIMIT 1").df()['junction'].iloc[0]
    except Exception as e:
        raise HTTPException(500, f"Query error: {e}")

    total = int(res['total_incidents'])
    parking = int(res['parking_incidents'])
    
    return {
        "total_incidents":       total,
        "parking_incidents":     parking,
        "parking_pct":           round(100 * parking / max(1, total), 1),
        "avg_clearance_minutes": 0,
        "parking_avg_clearance": 0,
        "road_closure_rate":     round(float(res['road_closure_rate'] or 0), 3),
        "top_corridor":          str(top_corridor),
        "open_incidents":        int(res['open_incidents'] or 0),
        "date_range_start":      str(res['date_range_start']),
        "date_range_end":        str(res['date_range_end']),
        "top_junction":          str(top_junction),
        "top_violation":         str(top_violation),
    }


@router.get("/policy-recommendations", summary="Groq / Llama-3 enforcement recommendations")
def get_policy_recs():
    if not ds.GROQ_AVAILABLE:
        return {"recommendations": "Groq SDK not installed.", "generated_from": "unavailable"}

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {"recommendations": "GROQ_API_KEY not set.", "generated_from": "unavailable"}

    top3_risk = ds.RISK_SCORES[:3]
    top3_rec  = ds.CASCADE.get("junction_cascade", [])[:3]
    if not top3_risk and not top3_rec:
        return {"recommendations": "No risk/recurrence data.", "generated_from": "none"}

    context_lines = []
    for i, (j, rec) in enumerate(zip(top3_risk, top3_rec), 1):
        sched     = ds.ENFORCEMENT.get(j.get("junction", ""), [])
        peak_slot = sched[0] if sched else {}
        context_lines.append(
            f"Junction {i}: {j.get('junction', 'Unknown')}\n"
            f"- Total violations: {j.get('incident_count', 'N/A')}\n"
            f"- Avg daily violations: {rec.get('avg_daily_violations', 'N/A')}\n"
            f"- Active violation days: {rec.get('active_days', 'N/A')}\n"
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
        "Here are the top 3 high-risk parking violation junctions:\n\n"
        + "\n\n".join(context_lines)
        + "\n\nGenerate 3 targeted patrol deployment recommendations for BTP."
    )

    try:
        from groq import Groq
        client   = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            max_tokens=500, temperature=0.4,
        )
        return {
            "recommendations": response.choices[0].message.content,
            "generated_from":  f"Groq / {response.model}",
            "data_source":     "BTP violation database",
        }
    except Exception as e:
        return {"recommendations": f"Groq API error: {e}", "generated_from": "error"}


class ChatMessage(BaseModel):
    message: str

@router.post("/chat", summary="Interactive Chatbot with RAG context")
def chat_with_astram(payload: ChatMessage):
    if not ds.GROQ_AVAILABLE:
        return {"reply": "Groq SDK not installed."}

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {"reply": "GROQ_API_KEY not set in backend/.env"}

    # Inject data context
    top5_risk = ds.RISK_SCORES[:5]
    context = "CURRENT TRAFFIC INTELLIGENCE CONTEXT (BENGALURU):\n\n"
    for j in top5_risk:
        context += f"Junction: {j.get('junction', 'Unknown')} | Risk Score: {j.get('risk_score', 0)} | Top Issue: {j.get('top_cause', '')}\n"

    system_prompt = (
        "You are ASTraM Copilot, an AI assistant for Bengaluru Traffic Police. "
        "You help commanders analyze parking violations and enforcement deployment. "
        "Keep your answers concise, highly professional, and direct. Use Markdown for emphasis. "
        "Use the provided context to answer questions about specific junctions if relevant. "
        f"\n\n{context}"
    )

    try:
        from groq import Groq
        client   = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload.message},
            ],
            max_tokens=500, temperature=0.5,
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        return {"reply": f"Groq API error: {e}"}

@router.get("/health")
def health():
    groq_key_set = bool(os.getenv("GROQ_API_KEY", ""))
    
    data_loaded = False
    incident_count = 0
    if ds.INCIDENTS_PARQUET_PATH and ds.INCIDENTS_PARQUET_PATH.exists():
        data_loaded = True
        try:
            import duckdb
            path = str(ds.INCIDENTS_PARQUET_PATH).replace('\\', '/')
            with duckdb.connect() as con:
                incident_count = int(con.query(f"SELECT COUNT(*) FROM '{path}'").fetchone()[0])
        except Exception:
            pass
            
    return {
        "status":          "ok",
        "data_loaded":     data_loaded,
        "model_loaded":    ds.model_bundle is not None,
        "shap_available":  ds.SHAP_AVAILABLE,
        "groq_available":  ds.GROQ_AVAILABLE and groq_key_set,
        "incident_count":  incident_count,
        "model_type":      "Enforcement Demand Forecast (LightGBM)",
    }
