import { useState, useEffect } from 'react'
import Tab1_SmartMap       from './components/Tab1_SmartMap'
import Tab2_Predictions    from './components/Tab2_Predictions'
import Tab3_RiskScorecard  from './components/Tab3_RiskScorecard'
import ChatbotWidget       from './components/ChatbotWidget'
import './index.css'

const API = 'http://localhost:8000'

const TABS = [
  { id: 'map',     label: 'Smart Incident Map',         icon: '📍', desc: 'Heatmap & clustering' },
  { id: 'predict', label: 'Enforcement Demand Forecast', icon: '🚔', desc: 'Patrol deployment AI' },
  { id: 'risk',    label: 'Risk Scorecard',              icon: '⚠',  desc: 'Junction risk & enforcement' },
]

/* ── Utility bar ───────────────────────────────────── */
function UtilBar({ health }) {
  const ok = health?.status === 'ok'
  return (
    <div className="util-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <span>🏛 Flipkart Grid 6.0 — Problem Statement 1</span>
        <span style={{ color: 'rgba(255,255,255,0.35)' }}>|</span>
        <span>Karnataka State Police</span>
      </div>
      <div className="util-right">
        <span>
          <span className="status-dot" style={{ background: ok ? '#4ade80' : '#f87171' }} />
          API {ok ? 'Connected' : 'Offline'}
        </span>
        {ok && health.incident_count
          ? <span>{health.incident_count?.toLocaleString()} records</span>
          : null}
        <span style={{ color: 'rgba(255,255,255,0.35)' }}>|</span>
        <span>English | ಕನ್ನಡ</span>
      </div>
    </div>
  )
}

/* ── Branding Header ───────────────────────────────── */
function BrandHeader({ health }) {
  return (
    <div className="btp-header">
      {/* Karnataka State Emblem */}
      <div className="emblem">
        {/* Emblem SVG — Ganda Bherunda simplified */}
        <svg width="52" height="52" viewBox="0 0 52 52" fill="none">
          <circle cx="26" cy="26" r="25" fill="#fff" stroke="#1a3f6f" strokeWidth="1.5"/>
          <circle cx="26" cy="26" r="22" fill="#fff3cd"/>
          <text x="26" y="34" textAnchor="middle" fontSize="22" fill="#1a3f6f">🦅</text>
        </svg>
        <div>
          <div style={{ fontSize: 9, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5 }}>ಕರ್ನಾಟಕ ಸರ್ಕಾರ</div>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#0e2a4d' }}>Government of Karnataka</div>
        </div>
      </div>

      <div className="header-divider" />

      {/* BTP Logo */}
      <div className="emblem-circle">🚦</div>

      {/* Brand text */}
      <div className="header-brand">
        <div className="org">Bengaluru Traffic Police · ASTraM Plugin</div>
        <div className="title">Parking Intelligence Module</div>
        <div className="subtitle">AI-Driven Enforcement Prioritisation System · Flipkart Grid PS-1</div>
      </div>

      {/* Status chips */}
      <div className="header-chips">
        <span className="chip chip-live">● Live</span>
        {health?.model_loaded && <span className="chip" style={{ background:'#e8f0fe', color:'#1a3f6f', border:'1px solid #93c5fd', fontSize:10, fontWeight:700, padding:'4px 10px', borderRadius:3 }}>ML Active</span>}
        {health?.groq_available && <span className="chip" style={{ background:'#f3e8ff', color:'#6b21a8', border:'1px solid #c4b5fd', fontSize:10, fontWeight:700, padding:'4px 10px', borderRadius:3 }}>Groq/LLM</span>}
      </div>

      {/* Right logo */}
      <div className="header-divider" />
      <div style={{ textAlign: 'center', flexShrink: 0 }}>
        <div style={{
          width: 52, height: 52, borderRadius: '50%',
          background: 'linear-gradient(135deg,#1a3f6f,#2155a3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 24, border: '2px solid #c8922a',
        }}>🚓</div>
        <div style={{ fontSize: 8, color: '#666', marginTop: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.3 }}>BTP</div>
      </div>
    </div>
  )
}

/* ── KPI Bar ───────────────────────────────────────── */
function KpiBar({ summary }) {
  if (!summary) return null
  const fmt = n => n == null ? '—' : typeof n === 'number' ? n.toLocaleString() : n
  return (
    <div className="kpi-bar">
      <div className="kpi-item">
        <div className="kpi-label">Total Violations</div>
        <div className="kpi-value">{fmt(summary.total_incidents)}</div>
        <div className="kpi-sub">All records</div>
      </div>
      <div className="kpi-item accent-green">
        <div className="kpi-label">Parking Violations</div>
        <div className="kpi-value">{fmt(summary.parking_incidents)}</div>
        <div className="kpi-sub">{summary.parking_pct}% of total</div>
      </div>
      <div className="kpi-item accent-yellow">
        <div className="kpi-label">Road Closure Rate</div>
        <div className="kpi-value">{summary.road_closure_rate != null ? (summary.road_closure_rate * 100).toFixed(1) + '%' : '—'}</div>
        <div className="kpi-sub">Carriageway blocked</div>
      </div>
      <div className="kpi-item accent-cyan">
        <div className="kpi-label">Top Junction</div>
        <div className="kpi-value" style={{ fontSize: 12 }}>{summary.top_junction?.replace(/^BTP\d+ - /, '') || '—'}</div>
        <div className="kpi-sub">Highest violation density</div>
      </div>
      <div className="kpi-item accent-red">
        <div className="kpi-label">Top Violation</div>
        <div className="kpi-value" style={{ fontSize: 11 }}>{summary.top_violation?.slice(0,20) || '—'}</div>
        <div className="kpi-sub">Most frequent type</div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">Data Range</div>
        <div className="kpi-value" style={{ fontSize: 12 }}>{summary.date_range_start ? new Date(summary.date_range_start).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : '—'}</div>
        <div className="kpi-sub">To {summary.date_range_end ? new Date(summary.date_range_end).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : '—'}</div>
      </div>
    </div>
  )
}

/* ── Footer status bar ─────────────────────────────── */
function FooterBar({ health }) {
  if (!health) return null
  return (
    <div style={{
      background: '#0e2a4d',
      borderTop: '1px solid rgba(255,255,255,0.1)',
      padding: '5px 24px',
      display: 'flex',
      gap: 24,
      fontSize: 10,
      color: 'rgba(255,255,255,0.55)',
      flexShrink: 0,
    }}>
      <span>Model: LightGBM Enforcement Demand Forecast</span>
      <span>·</span>
      <span>SHAP: {health.shap_available ? '✓ Enabled' : '✗ Disabled'}</span>
      <span>·</span>
      <span>Groq LLM: {health.groq_available ? '✓ Connected' : '✗ Not configured'}</span>
      <span style={{ marginLeft: 'auto' }}>
        Bengaluru Traffic Police · ASTraM Intelligence Module v2.0 · Flipkart Grid 6.0
      </span>
    </div>
  )
}

/* ── Root App ──────────────────────────────────────── */
export default function App() {
  const [tab,     setTab]     = useState('map')
  const [health,  setHealth]  = useState(null)
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    const load = () => {
      fetch(`${API}/health`)
        .then(r => r.ok ? r.json() : null)
        .then(d => d && setHealth(d))
        .catch(() => setHealth({ status: 'error' }))
      fetch(`${API}/summary`)
        .then(r => r.ok ? r.json() : null)
        .then(d => d && setSummary(d))
        .catch(() => {})
    }
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  const activeTab = TABS.find(t => t.id === tab) || TABS[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <UtilBar health={health} />
      <BrandHeader health={health} />

      {/* Tab nav */}
      <div className="tab-nav">
        {TABS.map(t => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
          >
            <span>{t.icon}</span>
            <span>{t.label}</span>
            <span style={{ fontSize: 9, opacity: 0.55, fontWeight: 400, marginLeft: 2 }}>— {t.desc}</span>
          </button>
        ))}

        {/* Right side metadata */}
        <div style={{
          marginLeft: 'auto',
          display: 'flex', alignItems: 'center', gap: 12,
          fontSize: 10, color: 'rgba(255,255,255,0.5)',
          paddingRight: 4,
        }}>
          <span>📅 {new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</span>
          <span style={{ color: 'rgba(255,255,255,0.25)' }}>|</span>
          <span>🕐 {new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      </div>

      {/* KPI bar */}
      <KpiBar summary={summary} />

      {/* Main content */}
      <div className="content-area fade-in" key={tab}>
        {/* Breadcrumb */}
        <div style={{
          fontSize: 11, color: 'var(--text-3)',
          marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5,
        }}>
          <span style={{ color: 'var(--navy)', fontWeight: 600 }}>ASTraM</span>
          <span>›</span>
          <span style={{ color: 'var(--navy)', fontWeight: 600 }}>Parking Intelligence</span>
          <span>›</span>
          <span>{activeTab.label}</span>
        </div>

        {tab === 'map'     && <Tab1_SmartMap       api={API} />}
        {tab === 'predict' && <Tab2_Predictions    api={API} />}
        {tab === 'risk'    && <Tab3_RiskScorecard  api={API} />}
      </div>

      <ChatbotWidget api={API} />
      <FooterBar health={health} />
    </div>
  )
}
