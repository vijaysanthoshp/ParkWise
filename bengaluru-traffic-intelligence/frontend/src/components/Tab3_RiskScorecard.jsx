import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis, Legend,
} from 'recharts'

/* ── Risk Score Bar ──────────────────────────────────── */
function ScoreBar({ score, maxScore }) {
  const pct   = Math.min(100, (score / (maxScore || 100)) * 100)
  const color = score >= 60 ? '#c0392b' : score >= 35 ? '#d35400' : '#217a3c'
  const cls   = score >= 60 ? 'badge-red' : score >= 35 ? 'badge-orange' : 'badge-green'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1 }}>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${pct}%`, background: color }} />
        </div>
      </div>
      <span className={`badge ${cls}`} style={{ minWidth: 36, justifyContent: 'center', fontVariantNumeric: 'tabular-nums' }}>
        {score}
      </span>
    </div>
  )
}

/* ── Junction Radar ──────────────────────────────────── */
function JunctionRadar({ junction }) {
  if (!junction) return (
    <div className="empty-state">
      <div className="icon">📡</div>
      <div style={{ fontSize: 12 }}>Click a row in the table to see breakdown</div>
    </div>
  )

  const data = [
    { axis: 'Frequency',       jn: +((junction.norm_freq          || 0) * 100).toFixed(0), avg: 40 },
    { axis: 'Daily Volume',    jn: Math.min(100, +((junction.avg_daily_violations || 0) * 2).toFixed(0)), avg: 20 },
    { axis: 'Road Closures',   jn: +((junction.road_closure_rate  || 0) * 100).toFixed(0), avg: 25 },
    { axis: 'Recurrence',      jn: +((junction.norm_recurrence    || 0) * 100).toFixed(0), avg: 30 },
    { axis: 'Enf. Gap',        jn: +((junction.enforcement_gap_rate || 0) * 100).toFixed(0), avg: 15 },
  ]

  return (
    <div>
      <div className="section-title" style={{ marginBottom: 6 }}>
        {junction.junction?.replace(/^BTP\d+ - /, '') || junction.junction}
        <span className="sub">vs city average</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <RadarChart data={data}>
          <PolarGrid stroke="#d0dae8" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 9, fill: '#4a6080' }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 8 }} tickCount={4} />
          <Radar name="This junction" dataKey="jn"  stroke="#1a3f6f" fill="#1a3f6f" fillOpacity={0.3} />
          <Radar name="City avg"      dataKey="avg" stroke="#c8922a" fill="#c8922a" fillOpacity={0.12} strokeDasharray="4 2" />
          <Legend iconSize={9} wrapperStyle={{ fontSize: 10 }} />
        </RadarChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
        {[
          ['Incidents',       junction.incident_count],
          ['Avg daily',       junction.avg_daily_violations ? `${junction.avg_daily_violations.toFixed(1)}/day` : null],
          ['Closure rate',    junction.road_closure_rate != null ? `${Math.round(junction.road_closure_rate * 100)}%` : null],
          ['Top violation',   junction.top_cause],
          ['Vehicle type',    junction.top_veh_type],
        ].filter(([,v]) => v != null).map(([k, v]) => (
          <div key={k} style={{
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            borderRadius: 3, padding: '3px 8px', fontSize: 10,
          }}>
            <span style={{ color: 'var(--text-3)' }}>{k}: </span>
            <span style={{ fontWeight: 700, color: 'var(--text-1)' }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Enforcement Table ───────────────────────────────── */
function EnforcementTable({ schedule, junction }) {
  const rows = schedule?.[junction] || []
  if (!rows.length) return (
    <div className="empty-state">
      <div className="icon">📅</div>
      <div style={{ fontSize: 12 }}>{junction ? 'No actionable slots for this junction.' : 'Select a junction from the table above.'}</div>
    </div>
  )

  const badgeCls = rec => {
    if (rec.includes('MANDATORY'))   return 'badge-red'
    if (rec.includes('RECOMMENDED')) return 'badge-orange'
    if (rec.includes('ADVISORY'))    return 'badge-blue'
    return 'badge'
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            {['Day', 'Time Period', 'Violations/Wk', 'Closure %', 'Recommendation'].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ fontWeight: 700 }}>{r.day_name}</td>
              <td>{r.time_period}</td>
              <td style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--navy)' }}>
                {r.incidents_per_week}
              </td>
              <td>{(r.road_closure_rate * 100).toFixed(0)}%</td>
              <td><span className={`badge ${badgeCls(r.recommendation)}`}>{r.recommendation}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Recurrence Chart ────────────────────────────────── */
function RecurrenceChart({ cascade }) {
  const data = (cascade?.junction_cascade || [])
    .slice(0, 12)
    .map(r => ({
      junction: (r.junction || '').replace(/^BTP\d+ - /, '').slice(0, 22),
      avg:      +(r.avg_daily_violations?.toFixed(1) || 0),
    }))

  if (!data.length) return (
    <div className="empty-state">
      <div className="icon">📊</div>
      <div style={{ fontSize: 12 }}>No recurrence data. Run pipeline step 06.</div>
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 50, top: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8edf5" />
        <XAxis
          type="number"
          tick={{ fontSize: 9 }}
          label={{ value: 'Avg daily violations', position: 'insideBottom', offset: -2, fontSize: 10 }}
        />
        <YAxis type="category" dataKey="junction" tick={{ fontSize: 9 }} width={145} />
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 3, border: '1px solid #d0dae8' }}
          formatter={v => [`${v} violations/day`, 'Daily recurrence']}
        />
        <Bar dataKey="avg" radius={[0, 2, 2, 0]}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.avg > 30 ? '#c0392b' : d.avg > 15 ? '#d35400' : '#1a3f6f'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── Policy Card ─────────────────────────────────────── */
function PolicyCard({ api }) {
  const [policy,  setPolicy]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  const generate = () => {
    setLoading(true)
    setError('')
    fetch(`${api}/policy-recommendations`)
      .then(r => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then(d => { setPolicy(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }

  return (
    <div className="card-with-header" style={{ marginTop: 14 }}>
      <div className="card-header">
        <span>🤖 AI Enforcement Recommendations — Groq / Llama-3.3-70b</span>
        <span className="sub">Powered by real junction risk + recurrence data</span>
      </div>
      <div className="card-body">
        {policy ? (
          <div>
            <div style={{
              fontSize: 13, lineHeight: 1.85, color: 'var(--text-1)',
              whiteSpace: 'pre-line', background: 'var(--surface-2)',
              border: '1px solid var(--border)', borderRadius: 3,
              padding: '14px 16px',
            }}>
              {policy.recommendations}
            </div>
            <div style={{
              marginTop: 10, display: 'flex', alignItems: 'center',
              justifyContent: 'space-between', fontSize: 10, color: 'var(--text-3)',
            }}>
              <span>Generated by <strong>{policy.generated_from}</strong> · Source: {policy.data_source}</span>
              <button className="btn-secondary" style={{ padding: '4px 12px', fontSize: 10 }} onClick={() => setPolicy(null)}>
                ↩ Regenerate
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <div style={{ flex: 1 }}>
              <p style={{ color: 'var(--text-2)', fontSize: 12, lineHeight: 1.6, marginBottom: 10 }}>
                Generate plain-English patrol deployment recommendations based on top junction risk scores and daily recurrence rates.
                Requires <code>GROQ_API_KEY</code> in <code>backend/.env</code> (free at{' '}
                <a href="https://console.groq.com/keys" style={{ color: 'var(--navy-light)' }} target="_blank">console.groq.com</a>).
              </p>
              {error && (
                <div className="badge badge-red" style={{ fontSize: 10, padding: '4px 10px', display: 'inline-flex', marginBottom: 8 }}>
                  ⚠ {error}
                </div>
              )}
              <button
                id="btn-generate-policy"
                className="btn-primary"
                onClick={generate}
                disabled={loading}
              >
                {loading ? '⏳ Generating...' : '✦ Generate Recommendations'}
              </button>
            </div>
            <div style={{
              textAlign: 'center', padding: '14px 20px',
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 3,
            }}>
              <div style={{ fontSize: 28, marginBottom: 6 }}>🤖</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4 }}>Groq LLM</div>
              <div style={{ fontSize: 9, color: 'var(--text-4)' }}>Llama-3.3-70b</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Main Tab ─────────────────────────────────────────── */
export default function Tab3_RiskScorecard({ api }) {
  const [riskScores, setRiskScores] = useState([])
  const [cascade,    setCascade]    = useState(null)
  const [schedule,   setSchedule]   = useState({})
  const [selected,   setSelected]   = useState(null)
  const [loading,    setLoading]    = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${api}/risk-scores`).then(r => r.json()).catch(() => ({ junctions: [] })),
      fetch(`${api}/cascade`).then(r => r.json()).catch(() => ({})),
      fetch(`${api}/enforcement-schedule`).then(r => r.json()).catch(() => ({ schedule: {} })),
    ]).then(([risk, casc, sched]) => {
      setRiskScores(risk.junctions || [])
      setCascade(casc)
      setSchedule(sched.schedule || {})
      if (risk.junctions?.length) setSelected(risk.junctions[0])
      setLoading(false)
    })
  }, [api])

  const maxScore = riskScores[0]?.risk_score || 100

  if (loading) return (
    <div className="empty-state" style={{ padding: 80 }}>
      <div className="icon">⏳</div>
      <div>Loading risk intelligence...</div>
    </div>
  )

  return (
    <div className="fade-in">

      {/* Row 1: Risk table + radar */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 12 }}>

        {/* Risk scorecard table */}
        <div className="card-with-header">
          <div className="card-header">
            <span>⚠ Junction Risk Scorecard — Top 20 by Parking Risk</span>
            <span className="sub">click a row to inspect</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            {riskScores.length === 0 ? (
              <div className="empty-state">
                <div className="icon">📊</div>
                <div style={{ fontSize: 12 }}>No data. Run pipeline steps 06 &amp; 07.</div>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    {['#', 'Junction', 'Risk Score', 'Incidents', 'Avg/Day', 'Closure %', 'Enf. Gap', 'Top Violation'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {riskScores.map((r, i) => (
                    <tr
                      key={i}
                      id={`risk-row-${i}`}
                      className={selected?.junction === r.junction ? 'selected' : ''}
                      onClick={() => setSelected(r)}
                    >
                      <td style={{ color: 'var(--text-4)', width: 26, fontWeight: 500 }}>{i + 1}</td>
                      <td style={{ fontWeight: 600, maxWidth: 180, fontSize: 11 }}>{r.junction}</td>
                      <td style={{ minWidth: 120 }}>
                        <ScoreBar score={r.risk_score} maxScore={maxScore} />
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.incident_count?.toLocaleString()}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: 'var(--navy)' }}>
                        {r.avg_daily_violations ? `${r.avg_daily_violations.toFixed(1)}/day` : '—'}
                      </td>
                      <td>{r.road_closure_rate != null ? `${Math.round(r.road_closure_rate * 100)}%` : '—'}</td>
                      <td>{r.enforcement_gap_rate != null ? `${Math.round(r.enforcement_gap_rate * 100)}%` : '—'}</td>
                      <td style={{ maxWidth: 160, fontSize: 10, color: 'var(--text-3)' }}>
                        {(r.top_cause || '—').slice(0, 40)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Radar */}
        <div className="card-with-header">
          <div className="card-header">📡 Junction Profile</div>
          <div className="card-body">
            <JunctionRadar junction={selected} />
          </div>
        </div>
      </div>

      {/* Row 2: Recurrence chart + enforcement schedule */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>

        <div className="card-with-header">
          <div className="card-header">
            <span>🔁 Chronic Violation Recurrence — Top Junctions</span>
            <span className="sub">avg daily violations (real metric)</span>
          </div>
          <div className="card-body">
            <RecurrenceChart cascade={cascade} />
            <div style={{ fontSize: 10, color: 'var(--text-4)', textAlign: 'center', marginTop: 6 }}>
              High recurrence = chronic enforcement blind spot = prolonged carriageway blockage
            </div>
          </div>
        </div>

        <div className="card-with-header">
          <div className="card-header">
            <span>📅 Patrol Deployment Schedule</span>
            {selected && <span className="sub">— {selected.junction?.replace(/^BTP\d+ - /, '')}</span>}
          </div>
          <div className="card-body">
            <EnforcementTable schedule={schedule} junction={selected?.junction} />
          </div>
        </div>
      </div>

      {/* Row 3: AI Policy */}
      <PolicyCard api={api} />

      {/* Row 4: Recurrence by event type */}
      {cascade?.event_type_cascade?.length > 0 && (
        <div className="card-with-header" style={{ marginTop: 12 }}>
          <div className="card-header">📋 Violation Type Recurrence — Top (Junction, Cause) Pairs</div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['Junction', 'Violation Cause', 'Total Incidents', 'Active Days', 'Avg/Day', 'Peak Count'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cascade.event_type_cascade.slice(0, 10).map((r, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, fontSize: 11 }}>{r.junction?.replace(/^BTP\d+ - /, '')}</td>
                    <td style={{ fontSize: 11 }}>{r.event_cause}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.trigger_count?.toLocaleString()}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.active_days}</td>
                    <td style={{
                      fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                      color: r.avg_downstream > 20 ? '#c0392b' : r.avg_downstream > 10 ? '#d35400' : 'var(--text-1)',
                    }}>
                      {r.avg_downstream?.toFixed(1)}
                    </td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{r.max_downstream}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
