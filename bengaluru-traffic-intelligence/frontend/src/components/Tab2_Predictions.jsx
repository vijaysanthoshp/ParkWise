import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell,
  LineChart, Line,
} from 'recharts'

const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

const DEMAND_CONFIG = {
  HIGH:    { bg: '#fef2f2', border: '#EF4444', badge: '#EF4444', label: 'HIGH DEMAND',    icon: '🔴' },
  MEDIUM:  { bg: '#fffbeb', border: '#F59E0B', badge: '#F59E0B', label: 'MEDIUM DEMAND',  icon: '🟡' },
  LOW:     { bg: '#f0fdf4', border: '#22C55E', badge: '#22C55E', label: 'LOW DEMAND',     icon: '🟢' },
  MINIMAL: { bg: '#f8fafc', border: '#94a3b8', badge: '#94a3b8', label: 'MINIMAL DEMAND', icon: '⚪' },
}

/* ── SHAP Waterfall ─────────────────────────────────── */
function ShapChart({ shapValues, baseValue }) {
  if (!shapValues || Object.keys(shapValues).length === 0) return null

  const labelMap = {
    junction_encoded:     'Junction identity',
    hour_of_day:          'Hour of day',
    day_of_week:          'Day of week',
    is_peak_hour:         'Peak patrol hour',
    is_weekend:           'Weekend',
    zone_encoded:         'Zone / area',
    dominant_veh_encoded: 'Dominant vehicle type',
    nearest_zone_encoded: 'Nearby zone type',
    avg_parking_score:    'Parking density score',
    parking_prob_mean:    'NLP parking probability',
    has_junction:         'Has junction marker',
  }

  const data = Object.entries(shapValues)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 10)
    .map(([feat, val]) => ({
      feat: labelMap[feat] || feat.replace(/_/g, ' '),
      val:  +val.toFixed(2),
    }))

  return (
    <div>
      <div className="section-title" style={{ marginTop: 16 }}>
        🧠 What Drives This Forecast (SHAP)
        <span className="sub">Base rate: {baseValue} violations/slot</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 55, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis
            type="number"
            tick={{ fontSize: 10 }}
            label={{ value: 'Violations impact', position: 'insideBottom', offset: -2, fontSize: 10 }}
          />
          <YAxis type="category" dataKey="feat" tick={{ fontSize: 10 }} width={155} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb' }}
            formatter={v => [`${v > 0 ? '+' : ''}${v} violations`, 'Feature impact']}
          />
          <ReferenceLine x={0} stroke="#374151" strokeWidth={1.5} />
          <Bar dataKey="val" radius={[0, 4, 4, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.val > 0 ? '#EF4444' : '#22C55E'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{ fontSize: 10, color: 'var(--text-4)', textAlign: 'center', marginTop: 4 }}>
        🔴 Increases expected violations · 🟢 Decreases expected violations
      </div>
    </div>
  )
}

/* ── CV Chart ───────────────────────────────────────── */
function ValidationChart({ validation }) {
  if (!validation?.cv_folds) return null

  const data = validation.cv_folds.map(f => ({
    fold: `Fold ${f.fold}`,
    mae:  f.mae_violations ?? f.mae_minutes ?? 0,
  }))
  data.push({ fold: 'Final', mae: validation.final_mae_violations ?? validation.final_mae_minutes ?? 0 })

  const naive = validation.naive_baseline_mae ?? 0
  const imp   = validation.improvement_pct ?? 0

  return (
    <div className="card">
      <div className="section-title">
        📊 Model Accuracy — Cross-Validation
        <span className="sub">
          MAE {validation.final_mae_violations ?? validation.final_mae_minutes} violations/slot
          · Baseline {naive} · {imp}% better than naive mean
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ left: -10, right: 16, top: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="fold" tick={{ fontSize: 10 }} />
          <YAxis
            tick={{ fontSize: 10 }}
            label={{ value: 'MAE (violations)', angle: -90, position: 'insideLeft', fontSize: 10 }}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8 }}
            formatter={v => [`${v} violations/slot`, 'Mean Absolute Error']}
          />
          <ReferenceLine
            y={naive}
            stroke="#EF4444"
            strokeDasharray="5 5"
            label={{ value: 'Naive baseline', fill: '#EF4444', fontSize: 10 }}
          />
          <Line
            type="monotone"
            dataKey="mae"
            stroke="#6366F1"
            strokeWidth={2.5}
            dot={{ r: 5, fill: '#6366F1', strokeWidth: 0 }}
            activeDot={{ r: 7 }}
          />
        </LineChart>
      </ResponsiveContainer>

      {validation.feature_importance && (
        <div style={{ marginTop: 16 }}>
          <div className="section-title">🎯 Top Predictors (Global SHAP Importance)</div>
          {Object.entries(validation.feature_importance).slice(0, 8).map(([feat, val], i) => {
            const maxVal = Object.values(validation.feature_importance)[0]
            const pct    = (val / maxVal) * 100
            const labelMap = {
              junction_encoded: 'Junction identity',
              hour_of_day:      'Hour of day',
              parking_prob_mean:'NLP parking probability',
              has_junction:     'Has junction marker',
              avg_parking_score:'Parking density score',
              zone_encoded:     'Zone / area',
              is_peak_hour:     'Peak patrol hour',
              is_weekend:       'Weekend',
              dominant_veh_encoded: 'Dominant vehicle type',
              nearest_zone_encoded: 'Nearby zone type',
            }
            return (
              <div key={i} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                  <span style={{ color: 'var(--text-2)' }}>{labelMap[feat] || feat.replace(/_/g, ' ')}</span>
                  <span style={{ color: 'var(--text-4)', fontVariantNumeric: 'tabular-nums' }}>{val}</span>
                </div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${pct}%`, background: 'linear-gradient(90deg,#6366F1,#8B5CF6)' }} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {validation.demand_distribution && (
        <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(validation.demand_distribution).map(([level, count]) => {
            const cfg = DEMAND_CONFIG[level] || DEMAND_CONFIG.MINIMAL
            return (
              <div key={level} style={{
                background: cfg.bg, border: `1px solid ${cfg.border}`,
                borderRadius: 8, padding: '6px 12px', fontSize: 11,
              }}>
                {cfg.icon} <strong>{level}</strong>: {count} slots
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ── Result Box ─────────────────────────────────────── */
function ResultBox({ result }) {
  const cfg = DEMAND_CONFIG[result.demand_level] || DEMAND_CONFIG.MINIMAL
  return (
    <div style={{
      background: cfg.bg,
      border: `2px solid ${cfg.border}`,
      borderRadius: 14,
      padding: '22px 20px',
      textAlign: 'center',
      marginBottom: 14,
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 6 }}>
        Expected Violations at <strong>{result.junction_name}</strong>
      </div>
      <div style={{
        fontSize: 60, fontWeight: 900, color: 'var(--text-1)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1.05,
      }}>
        {result.expected_violations}
        <span style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-3)', marginLeft: 6 }}>
          violations
        </span>
      </div>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        background: cfg.badge, color: '#fff',
        padding: '5px 16px', borderRadius: 20,
        fontSize: 13, fontWeight: 700, marginTop: 10,
      }}>
        {cfg.icon} {cfg.label}
      </div>
      <div style={{
        marginTop: 14, padding: '10px 16px',
        background: 'rgba(0,0,0,0.04)', borderRadius: 8,
        fontSize: 12, fontWeight: 600, color: 'var(--text-2)',
      }}>
        👮 {result.officer_recommendation}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 8 }}>
        {DAYS[result.day_of_week] || 'Day'} at {String(result.hour_of_day).padStart(2,'0')}:00
      </div>
    </div>
  )
}

/* ── Main Tab ────────────────────────────────────────── */
export default function Tab2_Predictions({ api }) {
  const [junctions, setJunctions]     = useState([])
  const [junction,  setJunction]      = useState('')
  const [hour,      setHour]          = useState(21)
  const [day,       setDay]           = useState(4)  // Friday
  const [result,    setResult]        = useState(null)
  const [validation,setValidation]    = useState(null)
  const [loading,   setLoading]       = useState(false)
  const [error,     setError]         = useState('')

  // Load junctions list
  useEffect(() => {
    fetch(`${api}/junctions?top_n=100`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.junctions?.length) {
          const jns = d.junctions.filter(j => j.junction !== 'Unknown')
          setJunctions(jns)
          setJunction(jns[0]?.junction || '')
        }
      })
      .catch(() => {})
  }, [api])

  // Load validation
  useEffect(() => {
    fetch(`${api}/validation`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setValidation(d))
      .catch(() => {})
  }, [api])

  const predict = () => {
    if (!junction) return
    setLoading(true)
    setError('')
    const payload = { junction_name: junction, hour_of_day: hour, day_of_week: day }
    fetch(`${api}/predict`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { setResult(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }

  return (
    <div className="fade-in">
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>

        {/* Left — Input form */}
        <div className="card" style={{ padding: 18 }}>
          <div className="section-title">📍 Patrol Scenario</div>
          <p style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.6 }}>
            Select a junction, day, and hour to forecast how many parking
            violations BTP can expect to encounter — and how many officers to deploy.
          </p>

          {/* Junction */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', marginBottom: 4 }}>
              Junction
            </label>
            <select
              id="sel-junction"
              className="form-select"
              value={junction}
              onChange={e => setJunction(e.target.value)}
              style={{ marginBottom: 0 }}
            >
              {junctions.length === 0 && <option>Loading...</option>}
              {junctions.map(j => (
                <option key={j.junction} value={j.junction}>
                  {j.junction} ({j.incident_count?.toLocaleString()} violations)
                </option>
              ))}
            </select>
          </div>

          {/* Day */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', marginBottom: 6 }}>
              Day of Week
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {DAYS.map((d, i) => (
                <button
                  key={i}
                  id={`day-btn-${i}`}
                  onClick={() => setDay(i)}
                  style={{
                    padding: '5px 9px', borderRadius: 6, fontSize: 10, cursor: 'pointer',
                    border: `1px solid ${day === i ? 'var(--navy)' : 'var(--border)'}`,
                    background: day === i ? 'var(--navy)' : '#fff',
                    color: day === i ? '#fff' : 'var(--text-2)',
                    fontWeight: day === i ? 700 : 400,
                    transition: 'all 0.12s',
                  }}
                >
                  {d.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>

          {/* Hour */}
          <div style={{ marginBottom: 16 }}>
            <label style={{
              fontSize: 10, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase',
              letterSpacing: 0.5, display: 'flex', justifyContent: 'space-between', marginBottom: 4,
            }}>
              <span>Hour of Day</span>
              <span style={{ color: 'var(--navy-light)', fontWeight: 700 }}>
                {String(hour).padStart(2,'0')}:00
              </span>
            </label>
            <input
              id="slider-hour-pred"
              type="range" min={0} max={23} value={hour}
              onChange={e => setHour(+e.target.value)}
              style={{ width: '100%', accentColor: 'var(--navy)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-4)', marginTop: 2 }}>
              <span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>11 PM</span>
            </div>
            {(hour >= 19 || hour <= 5) && (
              <div style={{ fontSize: 10, color: 'var(--gold)', fontWeight: 700, marginTop: 4 }}>
                🌙 BTP peak patrol hour
              </div>
            )}
          </div>

          <button
            id="btn-forecast"
            onClick={predict}
            disabled={loading || !junction}
            style={{
              width: '100%', padding: '12px 0', borderRadius: 10, border: 'none',
              background: (loading || !junction) ? '#94a3b8' : 'linear-gradient(135deg,var(--navy),var(--navy-light))',
              color: '#fff', fontSize: 14, fontWeight: 700,
              cursor: (loading || !junction) ? 'not-allowed' : 'pointer',
              boxShadow: (loading || !junction) ? 'none' : '0 4px 12px rgba(12,35,64,0.3)',
              transition: 'opacity 0.15s',
            }}
          >
            {loading ? '⏳ Forecasting...' : '▶ Forecast Violations'}
          </button>

          {error && (
            <div style={{
              color: '#EF4444', fontSize: 12, marginTop: 8,
              background: '#fef2f2', border: '1px solid #fecaca',
              borderRadius: 6, padding: '8px 10px',
            }}>
              ⚠ {error}
            </div>
          )}

          <div style={{ marginTop: 16, padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Officer Thresholds
            </div>
            {[
              { level: 'HIGH',    color: '#EF4444', text: '16+ violations → 3+ officers' },
              { level: 'MEDIUM',  color: '#F59E0B', text: '6–15 violations → 2 officers' },
              { level: 'LOW',     color: '#22C55E', text: '1–5 violations → 1 officer' },
              { level: 'MINIMAL', color: '#94a3b8', text: '0 violations → optional patrol' },
            ].map(r => (
              <div key={r.level} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 10 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
                <span style={{ color: 'var(--text-2)' }}>{r.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right — Results */}
        <div>
          {result ? (
            <div className="fade-in">
              <ResultBox result={result} />
              <div className="card">
                <ShapChart shapValues={result.shap_values} baseValue={result.base_value} />
              </div>
            </div>
          ) : (
            <div className="card" style={{
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              minHeight: 340, textAlign: 'center', color: 'var(--text-4)',
            }}>
              <div style={{ fontSize: 52, marginBottom: 12 }}>🚔</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>
                Enforcement Demand Forecast
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.6, maxWidth: 340 }}>
                Select a junction, day, and hour on the left and click{' '}
                <strong>Forecast Violations</strong>. The LightGBM model predicts
                expected violation volume and recommends officer deployment.
              </div>
              <div style={{
                marginTop: 20, padding: '10px 16px',
                background: 'var(--surface-2)', borderRadius: 8,
                fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6,
              }}>
                Trained on 136K real violations · 7,081 junction-time slots ·<br/>
                74% improvement over naive mean · SHAP explainability
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Validation section */}
      <div style={{ marginTop: 16 }}>
        {validation
          ? <ValidationChart validation={validation} />
          : (
            <div className="card" style={{ textAlign: 'center', color: 'var(--text-4)', padding: 24 }}>
              Validation metrics unavailable. Run <code>python pipeline/run_all.py --only 05</code> first.
            </div>
          )
        }
      </div>
    </div>
  )
}
