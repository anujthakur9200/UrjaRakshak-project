'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { streamApi, LiveEvent, SubstationStability } from '@/lib/api'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

function getToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('urjarakshak_token')
}

const stabilityColor = (score: number | null) => {
  if (score === null) return 'var(--text-dim)'
  if (score >= 0.8) return 'var(--green)'
  if (score >= 0.6) return 'var(--cyan)'
  if (score >= 0.4) return 'var(--amber)'
  return 'var(--red)'
}

/** Animated load-flow SVG diagram.
 *  Nodes = substations / meters arranged in a ring.
 *  Edges = animated dashed lines showing power flow direction.
 */
function LoadFlowDiagram({ meters, substation }: { meters: any[]; substation: string }) {
  const W = 320, H = 240, CX = 160, CY = 120
  const nodes = meters.length > 0 ? meters.slice(0, 8) : [
    { meter_id: substation, stability_score: 0.9 },
    { meter_id: 'M-A', stability_score: 0.75 },
    { meter_id: 'M-B', stability_score: 0.55 },
    { meter_id: 'M-C', stability_score: 0.85 },
    { meter_id: 'M-D', stability_score: 0.3 },
  ]
  const n = nodes.length
  const MAX_RADIUS = 80
  const NODE_SPACING_FACTOR = 28
  const R = Math.min(MAX_RADIUS, NODE_SPACING_FACTOR * n / 2)

  const pos = nodes.map((_, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    return {
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
    }
  })

  // Build ring edges: each node connects to next
  const edges = nodes.map((_, i) => ({
    from: i,
    to: (i + 1) % n,
    reverse: nodes[i].stability_score < 0.5,
  }))

  return (
    <div>
      <div className="sec-label" style={{ marginBottom: 10 }}>Load Flow Diagram</div>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <svg width={W} height={H} style={{ overflow: 'visible' }}>
          {/* Flow edges */}
          {edges.map((e, i) => {
            const p1 = pos[e.from], p2 = pos[e.to]
            return (
              <line
                key={i}
                x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
                stroke="var(--border-dim)"
                strokeWidth={2}
                strokeDasharray="8 4"
                className={e.reverse ? 'flow-line-rev' : 'flow-line'}
              />
            )
          })}
          {/* Arrow heads in middle of each edge */}
          {edges.map((e, i) => {
            const p1 = pos[e.from], p2 = pos[e.to]
            const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2
            const dx = p2.x - p1.x, dy = p2.y - p1.y
            const len = Math.sqrt(dx * dx + dy * dy)
            const ux = dx / len, uy = dy / len
            const side = e.reverse ? -1 : 1
            return (
              <polygon
                key={`a${i}`}
                points={`0,-4 6,0 0,4`}
                fill="var(--cyan)"
                opacity={0.6}
                transform={`translate(${mx},${my}) rotate(${Math.atan2(side * uy, side * ux) * 180 / Math.PI})`}
              />
            )
          })}
          {/* Nodes */}
          {nodes.map((m, i) => {
            const { x, y } = pos[i]
            const color = stabilityColor(m.stability_score ?? null)
            const isHub = i === 0
            return (
              <g key={i}>
                <circle cx={x} cy={y} r={isHub ? 14 : 10} fill="var(--bg-elevated)" stroke={color} strokeWidth={isHub ? 2.5 : 1.5} />
                {isHub && <circle cx={x} cy={y} r={18} fill="none" stroke={color} strokeWidth={1} opacity={0.3} />}
                <text x={x} y={y + 3} textAnchor="middle" fill={color} fontSize={isHub ? 7 : 6} fontFamily="monospace">
                  {String(m.meter_id).slice(-4)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <div style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
        {[['≥80%', 'var(--green)', 'Stable'], ['60–79%', 'var(--cyan)', 'Good'], ['40–59%', 'var(--amber)', 'Watch'], ['<40%', 'var(--red)', 'Alert']].map(([rng, c, lbl]) => (
          <div key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase' }}>{lbl} {rng}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function StreamPage() {
  const [substation, setSubstation] = useState('SS001')
  const [inputVal, setInputVal] = useState('SS001')
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [stability, setStability] = useState<SubstationStability | null>(null)
  const [anomalyCount, setAnomalyCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)
  const [sseError, setSseError] = useState<string | null>(null)
  const [isAuthed, setIsAuthed] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setIsAuthed(!!getToken())
  }, [])

  const loadStability = useCallback(async (sub: string) => {
    try {
      const s = await streamApi.getSubstationStability(sub)
      setStability(s)
    } catch {}
  }, [])

  const loadRecent = useCallback(async (sub: string) => {
    try {
      const r = await streamApi.getRecent(sub, 30)
      setEvents(r.events?.slice().reverse() ?? [])
      setTotalCount(r.count)
      setAnomalyCount(r.events?.filter((e: LiveEvent) => e.is_anomaly).length)
    } catch {}
  }, [])

  const connectSSE = useCallback((sub: string) => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setSseError(null)
    const token = getToken()
    if (!token) { setSseError('Login required — authenticate via the Upload page first.'); return }

    const url = `${BASE}/api/v1/stream/live/${encodeURIComponent(sub)}?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onerror = () => {
      setConnected(false)
      es.close()
    }
    es.onmessage = (e) => {
      try {
        const ev: LiveEvent = JSON.parse(e.data)
        if (ev.type === 'ping') return
        setEvents(prev => [ev, ...prev].slice(0, 100))
        setTotalCount(c => c + 1)
        if (ev.is_anomaly) setAnomalyCount(c => c + 1)
        if (logRef.current) logRef.current.scrollTop = 0
      } catch {}
    }
  }, [])

  const disconnect = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setConnected(false)
  }, [])

  useEffect(() => {
    loadStability(substation)
    loadRecent(substation)
    return () => { esRef.current?.close() }
  }, [substation, loadStability, loadRecent])

  const applySubstation = () => {
    const val = inputVal.trim().toUpperCase()
    if (!val) return
    setSubstation(val)
    setEvents([])
    setTotalCount(0)
    setAnomalyCount(0)
    setStability(null)
    disconnect()
  }

  const anomalyRate = totalCount > 0 ? ((anomalyCount / totalCount) * 100).toFixed(1) : '0.0'

  return (
    <div className="page">
      <div className="page-header fade-in">
        <div className="page-eyebrow">Real-Time Monitoring</div>
        <h1 className="page-title">Live Stream</h1>
        <p className="page-desc">
          Server-Sent Events stream from SCADA/AMI. Per-meter physics z-scores computed
          in real-time. No message broker required.
        </p>
      </div>

      {!isAuthed && (
        <div className="alert alert-warn fade-in" style={{ marginBottom: 20 }}>
          ⚠ Not authenticated — <a href="/upload" style={{ color: 'inherit', textDecoration: 'underline' }}>log in via the Upload page</a> to connect the live stream.
        </div>
      )}

      {sseError && (
        <div className="alert alert-err fade-in" style={{ marginBottom: 20 }}>{sseError}</div>
      )}

      {/* Controls */}
      <div className="panel fade-in stagger-1" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            className="input"
            value={inputVal}
            onChange={e => setInputVal(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && applySubstation()}
            placeholder="Substation ID (e.g. SS001)"
            style={{ maxWidth: 220 }}
          />
          <button onClick={applySubstation} className="btn btn-secondary btn-sm">Set</button>
          <div className="nav-divider" style={{ height: 20 }} />
          {connected ? (
            <button onClick={disconnect} className="btn btn-danger btn-sm">■ Disconnect</button>
          ) : (
            <button onClick={() => connectSSE(substation)} disabled={!isAuthed} className="btn btn-primary btn-sm">
              ▶ Connect SSE
            </button>
          )}
          <button
            onClick={() => { loadStability(substation); loadRecent(substation) }}
            className="btn btn-secondary btn-sm"
          >
            ↻ Refresh
          </button>
          <div className={`live-pill ${connected ? 'online' : 'offline'}`}>
            <span className="live-dot" />
            {connected ? `${substation} live` : 'Disconnected'}
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid-4 fade-in stagger-2" style={{ marginBottom: 16 }}>
        <div className="metric-card">
          <div className="metric-label">Events</div>
          <div className="metric-value">{totalCount.toLocaleString()}</div>
          <div className="metric-sub">total received</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Anomalies</div>
          <div className="metric-value" style={{ color: anomalyCount > 0 ? 'var(--amber)' : 'var(--cyan)' }}>{anomalyCount}</div>
          <div className="metric-sub">{anomalyRate}% rate</div>
        </div>
        {stability && (
          <>
            <div className="metric-card">
              <div className="metric-label">Meters Tracked</div>
              <div className="metric-value">{stability.meters?.length ?? 0}</div>
              <div className="metric-sub">active meters</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Avg Stability</div>
              <div className="metric-value" style={{ color: stabilityColor(stability.avg_stability_score ?? null) }}>
                {stability.avg_stability_score != null ? `${(stability.avg_stability_score * 100).toFixed(0)}%` : '—'}
              </div>
              <div className="metric-sub">fleet avg</div>
            </div>
          </>
        )}
        {!stability && (
          <>
            <div className="metric-card">
              <div className="metric-label">Meters</div>
              <div className="metric-value" style={{ color: 'var(--text-dim)' }}>—</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Stability</div>
              <div className="metric-value" style={{ color: 'var(--text-dim)' }}>—</div>
            </div>
          </>
        )}
      </div>

      {/* Meter stability table */}
      {stability?.meters && stability.meters.length > 0 && (
        <div className="panel panel-flush fade-in stagger-3" style={{ marginBottom: 16 }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div className="sec-label" style={{ marginBottom: 0 }}>Meter Stability Scores</div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Meter ID</th>
                  <th>Stability</th>
                  <th className="hide-mobile">Anomaly Rate</th>
                  <th className="hide-mobile">Last Reading</th>
                  <th className="hide-mobile">Trend</th>
                </tr>
              </thead>
              <tbody>
                {stability.meters?.slice(0, 15).map((m: any) => (
                  <tr key={m.meter_id}>
                    <td style={{ color: 'var(--cyan)' }}>{m.meter_id}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 48, height: 4, borderRadius: 2, background: 'var(--border-subtle)', overflow: 'hidden', flexShrink: 0 }}>
                          <div style={{ height: '100%', width: `${(m.stability_score ?? 0) * 100}%`, background: stabilityColor(m.stability_score), borderRadius: 2 }} />
                        </div>
                        <span style={{ color: stabilityColor(m.stability_score) }}>
                          {m.stability_score != null ? `${(m.stability_score * 100).toFixed(0)}%` : '—'}
                        </span>
                      </div>
                    </td>
                    <td className="hide-mobile">{m.anomaly_rate_30d != null ? `${(m.anomaly_rate_30d * 100).toFixed(1)}%` : '—'}</td>
                    <td className="hide-mobile">{m.last_reading_kwh != null ? `${m.last_reading_kwh.toFixed(2)} kWh` : '—'}</td>
                    <td className="hide-mobile" style={{ color: m.trend_direction === 'UP' ? 'var(--amber)' : m.trend_direction === 'DOWN' ? 'var(--green)' : 'var(--text-dim)' }}>
                      {m.trend_direction === 'UP' ? '↑' : m.trend_direction === 'DOWN' ? '↓' : '→'} {m.trend_direction || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Load flow diagram */}
      <div className="panel fade-in stagger-4" style={{ marginBottom: 16 }}>
        <LoadFlowDiagram meters={stability?.meters ?? []} substation={substation} />
      </div>

      {/* Event log */}
      <div className="panel panel-flush fade-in stagger-5">
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="sec-label" style={{ marginBottom: 0 }}>Event Log</div>
          <button onClick={() => { setEvents([]); setTotalCount(0); setAnomalyCount(0) }} className="btn btn-secondary btn-sm">Clear</button>
        </div>
        <div ref={logRef} style={{ maxHeight: 400, overflowY: 'auto' }}>
          {events.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📡</div>
              <div className="empty-title">No events yet</div>
              <div className="empty-desc">
                Connect the SSE stream to see live meter events, or use POST /api/v1/stream/ingest to push events.
              </div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Meter</th>
                  <th>Energy kWh</th>
                  <th className="hide-mobile">Z-Score</th>
                  <th>Status</th>
                  <th className="hide-mobile">Time</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, i) => (
                  <tr key={i} style={{ background: ev.is_anomaly ? 'rgba(255,176,32,0.04)' : undefined }}>
                    <td style={{ color: 'var(--cyan)' }}>{ev.meter_id}</td>
                    <td>{ev.energy_kwh?.toFixed(2)}</td>
                    <td className="hide-mobile" style={{ color: Math.abs(ev.z_score ?? 0) > 3 ? 'var(--red)' : Math.abs(ev.z_score ?? 0) > 2 ? 'var(--amber)' : 'var(--text-tertiary)' }}>
                      {ev.z_score != null ? `${ev.z_score > 0 ? '+' : ''}${ev.z_score.toFixed(2)}σ` : '—'}
                    </td>
                    <td>
                      {ev.is_anomaly
                        ? <span className="chip chip-warn">Anomaly</span>
                        : <span className="chip chip-ok">Normal</span>
                      }
                    </td>
                    <td className="hide-mobile" style={{ color: 'var(--text-dim)' }}>
                      {ev.event_ts ? new Date(ev.event_ts).toLocaleTimeString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
