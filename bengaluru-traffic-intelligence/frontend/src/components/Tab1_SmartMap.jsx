import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { MAPPLS_API_KEY } from '../mapplsConfig.js'

// ─── Mappls SDK Loader ───────────────────────────────────────────────────────
let mapplsLoadPromise = null
function loadMappls() {
  if (mapplsLoadPromise) return mapplsLoadPromise
  mapplsLoadPromise = new Promise((resolve, reject) => {
    if (window.mappls) { resolve(window.mappls); return }
    const script = document.createElement('script')
    script.src = `https://apis.mappls.com/advancedmaps/api/${MAPPLS_API_KEY}/map_sdk?v=3.0&layer=vector`
    script.async = true
    let settled = false
    const timeout = setTimeout(() => { if (!settled) { settled = true; reject(new Error('timeout')) } }, 8000)
    script.onload = () => {
      const wait = () => {
        if (window.mappls) { clearTimeout(timeout); settled = true; resolve(window.mappls) }
        else setTimeout(wait, 100)
      }
      wait()
    }
    script.onerror = () => { clearTimeout(timeout); settled = true; reject(new Error('load_error')) }
    document.head.appendChild(script)
  })
  return mapplsLoadPromise
}

// ─── Leaflet (OSM) Fallback Loader ───────────────────────────────────────────
let leafletLoadPromise = null
function loadLeaflet() {
  if (leafletLoadPromise) return leafletLoadPromise
  leafletLoadPromise = new Promise((resolve, reject) => {
    if (window.L) { resolve(window.L); return }
    const link = document.createElement('link')
    link.rel  = 'stylesheet'
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
    document.head.appendChild(link)
    const script = document.createElement('script')
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
    script.onload  = () => resolve(window.L)
    script.onerror = reject
    document.head.appendChild(script)
  })
  return leafletLoadPromise
}

const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
const PRIORITY_COLORS = { High: '#EF4444', Medium: '#F59E0B', Low: '#22C55E' }

// ─── Unified Map Component (Mappls first → Leaflet fallback) ─────────────────
function MapplsMap({ incidents, hour, day }) {
  const containerRef = useRef(null)
  const mapRef       = useRef(null)   // Mappls or Leaflet map instance
  const layersRef    = useRef([])     // circles / markers
  const infoRef      = useRef(null)   // shared InfoWindow (Mappls) or Popup (Leaflet)
  const sdkRef       = useRef(null)   // 'mappls' | 'leaflet' | null
  const [ready, setReady]     = useState(false)
  const [usingOSM, setUsingOSM] = useState(false)

  // ── Initialise map (try Mappls, fall back to Leaflet) ────────────────────
  useEffect(() => {
    let destroyed = false

    const initMappls = (mappls) => {
      if (destroyed || !containerRef.current) return
      sdkRef.current = 'mappls'
      const map = new mappls.Map(containerRef.current, {
        center: { lat: 12.9716, lng: 77.5946 },
        zoom: 12,
        search: false,
      })
      mapRef.current  = map
      infoRef.current = new mappls.InfoWindow({ map })
      setReady(true)
    }

    const initLeaflet = (L) => {
      if (destroyed || !containerRef.current) return
      sdkRef.current = 'leaflet'
      const map = L.map(containerRef.current).setView([12.9716, 77.5946], 12)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map)
      mapRef.current = map
      setUsingOSM(true)
      setReady(true)
    }

    loadMappls()
      .then(initMappls)
      .catch(() => loadLeaflet().then(initLeaflet).catch(console.error))

    return () => {
      destroyed = true
      layersRef.current.forEach(l => { try {
        if (sdkRef.current === 'mappls') l.setMap(null)
        else l.remove()
      } catch (_) {} })
      layersRef.current = []
      if (mapRef.current) {
        try {
          if (sdkRef.current === 'mappls') mapRef.current.remove()
          else mapRef.current.remove()
        } catch (_) {}
        mapRef.current = null
      }
    }
  }, [])

  // ── Draw / redraw circles whenever incidents or ready-state changes ───────
  useEffect(() => {
    if (!ready || !mapRef.current) return
    const mode = sdkRef.current
    const map  = mapRef.current

    // Remove old layers
    layersRef.current.forEach(l => { try {
      if (mode === 'mappls') l.setMap(null)
      else l.remove()
    } catch (_) {} })
    layersRef.current = []

    incidents.forEach(inc => {
      if (!inc.latitude || !inc.longitude) return
      const lat = parseFloat(inc.latitude)
      const lng = parseFloat(inc.longitude)
      if (isNaN(lat) || isNaN(lng)) return

      const isPark = inc.is_parking_induced === 1
      const isHigh = inc.priority === 'High'
      const isMed  = inc.priority === 'Medium'
      const isLow  = inc.priority === 'Low'
      const prob   = inc.parking_probability || 0

      // Color by priority — all incidents are parking violations in this dataset
      let color, radiusM, fillOp, strokeCol, strokeW
      if (isHigh) {
        color     = '#EF4444'   // red → High priority parking
        radiusM   = 140 + prob * 110
        fillOp    = 0.88
        strokeCol = '#dc2626'
        strokeW   = 2.5
      } else if (isMed) {
        color     = '#F59E0B'   // amber → Medium priority parking
        radiusM   = 110 + prob * 80
        fillOp    = 0.80
        strokeCol = '#d97706'
        strokeW   = 2
      } else if (isLow) {
        color     = '#22C55E'   // green → Low priority parking
        radiusM   = 80 + prob * 50
        fillOp    = 0.70
        strokeCol = '#16a34a'
        strokeW   = 1.5
      } else {
        color     = '#6366F1'   // indigo → unknown priority
        radiusM   = 70
        fillOp    = 0.60
        strokeCol = '#4f46e5'
        strokeW   = 1
      }

      const popupHtml = `
        <div style="font-family:Inter,sans-serif;min-width:200px;padding:2px 0">
          <div style="font-weight:700;font-size:13px;margin-bottom:6px">
            ${inc.event_type || 'Incident'}
            ${isPark ? '<span style="background:#f3e8ff;color:#7C3AED;padding:1px 7px;border-radius:8px;font-size:10px;margin-left:6px">PARKING</span>' : ''}
          </div>
          <div style="font-size:11px;color:#374151;line-height:1.9">
            <b>Junction:</b> ${inc.junction || 'Unknown'}<br/>
            <b>Cause:</b> ${inc.event_cause || '—'}<br/>
            <b>Priority:</b> <span style="color:${PRIORITY_COLORS[inc.priority]||'#6B7280'};font-weight:700">${inc.priority||'—'}</span><br/>
            <b>Clearance:</b> ${inc.clearance_minutes ? Math.round(inc.clearance_minutes)+' min' : 'Open'}<br/>
            ${prob ? `<b>Parking prob:</b> ${(prob*100).toFixed(0)}%<br/>` : ''}
            <b>Zone:</b> ${inc.zone || '—'}
          </div>
        </div>`

      if (mode === 'mappls') {
        const mappls = window.mappls
        const circle = new mappls.Circle({
          map, center: { lat, lng }, radius: radiusM,
          fillColor: color, fillOpacity: fillOp,
          strokeColor: strokeCol,
          strokeWeight: strokeW, strokeOpacity: 0.9,
        })
        mappls.addListener(circle, 'click', () => {
          if (infoRef.current) {
            infoRef.current.setPosition({ lat, lng })
            infoRef.current.setContent(popupHtml)
            infoRef.current.open(map)
          }
        })
        layersRef.current.push(circle)
      } else {
        // Leaflet — convert metres radius to pixels approx
        const radiusPx = Math.max(6, Math.round(radiusM / 15))
        const circle = window.L.circleMarker([lat, lng], {
          radius: radiusPx,
          fillColor: color, fillOpacity: fillOp,
          color: strokeCol,
          weight: strokeW,
        }).addTo(map).bindPopup(popupHtml)
        layersRef.current.push(circle)
      }
    })
  }, [incidents, ready])

  return (
    <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ height: 460, width: '100%', borderRadius: 10 }} />

      {/* Legend */}
      <div style={{
        position: 'absolute', bottom: 28, left: 10, zIndex: 1000,
        background: 'rgba(17,24,39,0.88)', backdropFilter: 'blur(6px)',
        borderRadius: 8, padding: '8px 12px', fontSize: 11, color: '#e2e8f0',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      }}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: '#9FE1CB', fontSize: 10, letterSpacing: 0.5 }}>LEGEND — by Priority</div>
        {[
          { color: '#EF4444', border: '#dc2626', label: 'High priority',   glow: true },
          { color: '#F59E0B', border: '#d97706', label: 'Medium priority', glow: false },
          { color: '#22C55E', border: '#16a34a', label: 'Low priority',    glow: false },
          { color: '#6366F1', border: '#4f46e5', label: 'Unknown priority',glow: false },
        ].map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
            <div style={{
              width: 11, height: 11, borderRadius: '50%',
              background: item.color,
              border: `2px solid ${item.border}`,
              boxShadow: item.glow ? `0 0 5px ${item.color}99` : 'none',
              flexShrink: 0,
            }} />
            <span style={{ fontWeight: item.glow ? 700 : 400, color: item.glow ? '#fff' : '#e2e8f0' }}>{item.label}</span>
          </div>
        ))}
        <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid rgba(255,255,255,0.1)', color: '#64748b', fontSize: 10 }}>Click circle for details</div>
      </div>

      {/* Map branding chip */}
      <div style={{
        position: 'absolute', bottom: 8, right: 10, zIndex: 1000,
        background: 'rgba(12,35,64,0.80)', backdropFilter: 'blur(4px)',
        borderRadius: 6, padding: '3px 8px', color: '#9FE1CB', fontSize: 10, fontWeight: 600,
      }}>
        {usingOSM ? '🗺️ OpenStreetMap (fallback)' : '🇮🇳 Powered by MapMyIndia'}
      </div>

      {/* Time chip */}
      <div style={{
        position: 'absolute', top: 10, right: 10, zIndex: 1000,
        background: 'rgba(12,35,64,0.88)', backdropFilter: 'blur(6px)',
        borderRadius: 8, padding: '5px 12px',
        color: '#9FE1CB', fontSize: 11, fontWeight: 700,
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      }}>
        {DAYS[day].slice(0,3)}  {String(hour).padStart(2,'0')}:00
      </div>
    </div>
  )
}

// ─── Incident Sidebar Row ─────────────────────────────────────────────────────
function IncidentRow({ inc }) {
  const isPark = inc.is_parking_induced === 1
  const color  = PRIORITY_COLORS[inc.priority] || '#6B7280'
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '9px 0',
      borderBottom: '1px solid var(--border-2)',
    }}>
      <div style={{
        width: 9, height: 9, borderRadius: '50%', marginTop: 4, flexShrink: 0,
        background: isPark ? '#EF4444' : color,
        boxShadow: isPark ? '0 0 6px rgba(239,68,68,0.5)' : 'none',
      }} />
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
          display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap',
        }}>
          {inc.event_type || 'Incident'}
          {isPark && <span className="badge badge-purple">PARKING</span>}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
          {inc.junction || inc.corridor || 'Unknown location'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 2 }}>
          {inc.event_cause || '—'} ·{' '}
          {inc.clearance_minutes ? `${Math.round(inc.clearance_minutes)} min` : 'Open'} ·{' '}
          <span style={{ color }}>{inc.priority || '—'}</span>
        </div>
        {inc.parking_probability != null && (
          <div style={{ fontSize: 10, color: '#7C3AED', marginTop: 2, fontWeight: 600 }}>
            NLP: {(inc.parking_probability * 100).toFixed(0)}% parking prob
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Hourly Chart ─────────────────────────────────────────────────────────────
function HourlyChart({ data }) {
  const peak = data.reduce((m, d) => d.count > m.count ? d : m, { count: 0, hour: 0 })
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="section-title">
        📈 Incidents by Hour of Day
        <span className="sub">Peak: {peak.hour}:00 ({peak.count} incidents in sample)</span>
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="hour" tick={{ fontSize: 9 }} tickFormatter={h => `${h}h`} />
          <YAxis tick={{ fontSize: 9 }} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb' }}
            formatter={(v, n) => [v, n === 'count' ? 'Total' : 'Parking-induced']}
            labelFormatter={h => `Hour ${h}:00`}
          />
          <Bar dataKey="count"   name="count"   fill="#93C5FD" radius={[3,3,0,0]} />
          <Bar dataKey="parking" name="parking" fill="#EF4444" radius={[3,3,0,0]} />
        </BarChart>
      </ResponsiveContainer>
      <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 6, textAlign: 'center' }}>
        🔵 Total incidents · 🔴 Parking-induced incidents
      </div>
    </div>
  )
}

// ─── Main Tab ─────────────────────────────────────────────────────────────────
export default function Tab1_SmartMap({ api }) {
  const [incidents, setIncidents]     = useState([])
  const [parkingOnly, setParkingOnly] = useState(false)
  const [priority, setPriority]       = useState('')
  const [hour, setHour]               = useState(new Date().getHours())
  const [day, setDay]                 = useState(() => {
    const d = new Date().getDay(); return d === 0 ? 6 : d - 1
  })
  const [loading, setLoading]         = useState(true)
  const [hourlyData, setHourlyData]   = useState(
    Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0, parking: 0 }))
  )

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ limit: 2000 })
    if (parkingOnly) params.set('parking_only', 'true')
    if (priority)    params.set('priority', priority)
    params.set('day', day)

    fetch(`${api}/incidents?${params}`)
      .then(r => r.json())
      .then(d => {
        const incs = d.incidents || []
        setIncidents(incs)
        const counts = Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0, parking: 0 }))
        incs.forEach(inc => {
          const dt = new Date(inc.start_datetime)
          if (!isNaN(dt)) {
            counts[dt.getHours()].count++
            if (inc.is_parking_induced) counts[dt.getHours()].parking++
          }
        })
        setHourlyData(counts)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [parkingOnly, priority, day])

  const display      = useMemo(() =>
    incidents.filter(i => {
      if (parkingOnly && !i.is_parking_induced) return false
      const dt = new Date(i.start_datetime)
      if (isNaN(dt)) return false
      return dt.getHours() === hour
    }),
    [incidents, parkingOnly, hour]
  )
  const parkCount    = incidents.filter(i => i.is_parking_induced).length
  const highCount    = incidents.filter(i => i.priority === 'High').length
  const closureCount = incidents.filter(i => i.requires_road_closure).length

  return (
    <div className="fade-in">
      {/* Controls */}
      <div className="card" style={{ marginBottom: 14, padding: '12px 16px' }}>
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', flexWrap: 'wrap', gap: 10,
        }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              id="btn-parking-only"
              onClick={() => setParkingOnly(p => !p)}
              style={{
                padding: '7px 14px', borderRadius: 8, fontSize: 12,
                border: `1px solid ${parkingOnly ? 'var(--navy)' : 'var(--border)'}`,
                background: parkingOnly ? 'var(--navy)' : '#fff',
                color: parkingOnly ? '#fff' : 'var(--text-2)',
                fontWeight: parkingOnly ? 700 : 500,
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              🅿️ Parking-Induced Only
            </button>
            <select
              id="sel-priority"
              className="form-select"
              value={priority}
              onChange={e => setPriority(e.target.value)}
              style={{ width: 155, marginBottom: 0 }}
            >
              <option value="">All priorities</option>
              <option value="High">🔴 High</option>
              <option value="Medium">🟡 Medium</option>
              <option value="Low">🟢 Low</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 12, flexWrap: 'wrap' }}>
            <span style={{ color: 'var(--navy-light)', fontWeight: 600 }}>🅿️ {parkCount} parking</span>
            <span style={{ color: '#EF4444', fontWeight: 600 }}>🔴 {highCount} high priority</span>
            <span style={{ color: '#F59E0B', fontWeight: 600 }}>🚧 {closureCount} closures</span>
            <span style={{ color: 'var(--text-4)' }}>Total: {display.length} shown</span>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 290px', gap: 16 }}>
        {/* Map column */}
        <div>
          <div className="card" style={{ padding: 14 }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8,
            }}>
              <div className="section-title" style={{ marginBottom: 0 }}>
                🗺️ Live Incident Map — Bengaluru
                <span className="sub">MapMyIndia (Mappls) · click circle for details</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                {DAYS[day]}, {String(hour).padStart(2,'0')}:00
              </div>
            </div>

            {/* Time controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{
                  fontSize: 10, fontWeight: 600, color: 'var(--text-3)',
                  textTransform: 'uppercase', letterSpacing: 0.5,
                  display: 'flex', justifyContent: 'space-between',
                }}>
                  <span>Hour of Day</span>
                  <span style={{ color: 'var(--navy-light)', fontWeight: 700 }}>{String(hour).padStart(2,'0')}:00</span>
                </label>
                <input
                  id="slider-hour"
                  type="range" min={0} max={23} value={hour}
                  onChange={e => setHour(+e.target.value)}
                  style={{ width: '100%', marginTop: 4, accentColor: 'var(--navy)' }}
                />
              </div>

              {/* Day chips */}
              <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                {DAYS.map((d, i) => (
                  <button
                    key={i}
                    id={`btn-day-${i}`}
                    onClick={() => setDay(i)}
                    style={{
                      padding: '4px 8px', borderRadius: 6, fontSize: 10,
                      border: `1px solid ${day === i ? 'var(--navy)' : 'var(--border)'}`,
                      background: day === i ? 'var(--navy)' : '#fff',
                      color: day === i ? '#fff' : 'var(--text-2)',
                      fontWeight: day === i ? 700 : 400,
                      cursor: 'pointer', transition: 'all 0.12s',
                    }}
                  >
                    {d.slice(0,3)}
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div style={{
                height: 460, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                background: '#f9fafb', borderRadius: 10,
                color: 'var(--text-4)', gap: 10,
              }}>
                <div style={{ fontSize: 28 }}>🔄</div>
                <div style={{ fontSize: 13 }}>Loading incident data…</div>
                <div style={{ fontSize: 11 }}>Make sure the FastAPI backend is running on port 8000</div>
              </div>
            ) : (
              <MapplsMap incidents={display} hour={hour} day={day} />
            )}
          </div>

          <HourlyChart data={hourlyData} />
        </div>

        {/* Right sidebar */}
        <div>
          <div className="card scroll-y" style={{ maxHeight: 680, padding: 14 }}>
            <div className="section-title">
              Recent Incidents
              <span className="sub">({Math.min(display.length, 60)} of {display.length})</span>
            </div>
            {display.length === 0 ? (
              <div className="empty-state">
                <div className="icon">📋</div>
                <div>No incidents to display</div>
                <div style={{ fontSize: 11 }}>
                  {loading ? 'Loading…' : 'Check API or adjust filters'}
                </div>
              </div>
            ) : (
              [...display].reverse().slice(0, 60).map((inc, i) => (
                <IncidentRow key={i} inc={inc} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
