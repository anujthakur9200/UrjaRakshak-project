'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { api, ghiApi, GHIDashboard } from '@/lib/api'

const GHI_COLORS: Record<string, string> = {
  HEALTHY:  'var(--green)',
  STABLE:   'var(--cyan)',
  DEGRADED: 'var(--amber)',
  CRITICAL: '#FF6B35',
  SEVERE:   'var(--red)',
}

export default function GHIPage() {
  const [data, setData]     = useState<GHIDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)
  const [authRequired, setAuthRequired] = useState(false)

  // Auth state (for endpoints that require login)
  const [authEmail, setAuthEmail]     = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError]     = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const d = await ghiApi.getDashboard()
      setData(d)
      setError(null)
    } catch (e: any) {
      const msg: string = e.message || 'Failed to load GHI data'
      if (msg.includes('401') || msg.includes('Authentication') || msg.includes('Not authenticated') || msg.includes('403')) {
        setAuthRequired(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 90000)
    return () => clearInterval(id)
  }, [fetchData])

  const handleLogin = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const res = await api.login(authEmail, authPassword)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setAuthRequired(false)
      fetchData()
    } catch (e: any) {
      setAuthError(e.message || 'Login failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleRegister = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      await api.register(authEmail, authPassword, 'analyst')
      const res = await api.login(authEmail, authPassword)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setAuthRequired(false)
      fetchData()
    } catch (e: any) {
      setAuthError(e.message || 'Registration failed')
    } finally {
      setAuthLoading(false)
    }
  }

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 'calc(100vh - 120px)' }}>
      <div className="spinner spinner-lg" />
      <span>Loading GHI data…</span>
    </div>
  )

  return (
    <div className="page">
      <div className="page-header fade-in">
        <div className="page-eyebrow">Grid Health Index</div>
        <h1 className="page-title">GHI Analytics</h1>
        <p className="page-desc">
          Composite score (0–100) combining physics balance (PBS), anomaly signals (ASS),
          confidence (CS), temporal stability (TSS), and drift indicators (DIS).
        </p>
      </div>

      {/* Auth gate */}
      {authRequired && (
        <div className="panel fade-in" style={{ marginBottom: 24, maxWidth: 440 }}>
          <div className="sec-label accent">Authentication Required</div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 1.6 }}>
            Log in to view GHI analytics. Register instantly for free.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <input className="input" type="email" placeholder="Email address"
              value={authEmail} onChange={e => setAuthEmail(e.target.value)} autoComplete="email" />
            <input className="input" type="password" placeholder="Password (min 8 chars)"
              value={authPassword} onChange={e => setAuthPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()} autoComplete="current-password" />
          </div>
          {authError && <div className="alert alert-err" style={{ marginBottom: 14 }}>{authError}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleLogin} disabled={authLoading || !authEmail || !authPassword}
              className="btn btn-primary" style={{ flex: 1 }}>
              {authLoading ? 'Logging in…' : 'Login'}
            </button>
            <button onClick={handleRegister} disabled={authLoading || !authEmail || !authPassword}
              className="btn btn-secondary" style={{ flex: 1 }}>
              Register
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-err fade-in" style={{ marginBottom: 20 }}>
          Backend error: {error}
        </div>
      )}

      {!authRequired && !data?.has_data ? (
        <div className="panel fade-in">
          <div className="empty-state">
            <div className="empty-icon">🏥</div>
            <div className="empty-title">No GHI data yet</div>
            <div className="empty-desc">
              GHI snapshots are computed automatically each time you upload meter data and run an analysis.
              Upload a CSV file to generate your first GHI score.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
              <Link href="/upload" className="btn btn-primary">Upload Meter Data →</Link>
              <Link href="/analysis" className="btn btn-secondary">View Analyses →</Link>
            </div>
          </div>
        </div>
      ) : !authRequired && (
        <>
          {/* Top KPIs */}
          <div className="grid-4 fade-in stagger-1" style={{ marginBottom: 16 }}>
            <div className="metric-card">
              <div className="metric-label">Avg GHI (all time)</div>
              <div className="metric-value" style={{
                color: data?.avg_ghi_all_time != null
                  ? data.avg_ghi_all_time >= 70 ? 'var(--green)'
                    : data.avg_ghi_all_time >= 50 ? 'var(--amber)' : 'var(--red)'
                  : 'var(--text-dim)'
              }}>
                {data?.avg_ghi_all_time ?? '—'}
              </div>
              <div className="metric-sub">fleet average</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">GHI Snapshots</div>
              <div className="metric-value">{data?.total_ghi_snapshots}</div>
              <div className="metric-sub">computed</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Open Inspections</div>
              <div className="metric-value" style={{ color: (data?.open_inspections ?? 0) > 0 ? 'var(--amber)' : 'var(--green)' }}>
                {data?.open_inspections}
              </div>
              <div className="metric-sub">{data?.critical_open} critical</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">AI Interpretations</div>
              <div className="metric-value">{data?.total_ai_interpretations}</div>
              <div className="metric-sub">{data?.live_ai_interpretations} live LLM</div>
            </div>
          </div>

          {/* Classification breakdown + recent snapshots */}
          <div className="grid-2 fade-in stagger-2" style={{ marginBottom: 16 }}>
            {/* Classification breakdown */}
            <div className="panel">
              <div className="sec-label accent">Classification Breakdown</div>
              {Object.entries(data?.by_classification || {}).length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {Object.entries(data!.by_classification).map(([cls, cnt]) => {
                    const total = Object.values(data!.by_classification).reduce((a, b) => a + b, 0)
                    const pct = total > 0 ? ((cnt / total) * 100) : 0
                    return (
                      <div key={cls}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: GHI_COLORS[cls] || 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{cls}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>{cnt} ({pct.toFixed(0)}%)</span>
                        </div>
                        <div style={{ height: 4, borderRadius: 2, background: 'var(--border-subtle)', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${pct}%`, background: GHI_COLORS[cls] || 'var(--text-dim)', borderRadius: 2, transition: 'width 0.6s ease' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No classification data yet</div>
              )}
            </div>

            {/* Recent snapshots */}
            <div className="panel panel-flush">
              <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="sec-label" style={{ marginBottom: 0 }}>Recent Snapshots</div>
              </div>
              {data?.substations && data.substations.length > 0 ? (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Substation</th>
                        <th>GHI</th>
                        <th className="hide-mobile">Class</th>
                        <th className="hide-mobile">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.substations?.slice(0, 10).map((s: any, i: number) => (
                        <tr key={i}>
                          <td style={{ color: 'var(--cyan)' }}>{s.substation_id}</td>
                          <td style={{ color: GHI_COLORS[s.classification] || 'var(--cyan)', fontWeight: 500 }}>{s.ghi_score}</td>
                          <td className="hide-mobile">
                            <span style={{ color: GHI_COLORS[s.classification], fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                              {s.classification}
                            </span>
                          </td>
                          <td className="hide-mobile" style={{ color: 'var(--text-dim)' }}>{s.updated_at?.slice(0, 10)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: '24px' }}>
                  <div className="empty-desc">No snapshots yet</div>
                </div>
              )}
            </div>
          </div>

          {/* GHI component explanation */}
          <div className="panel fade-in stagger-3">
            <div className="sec-label">GHI Formula Components</div>
            <div className="grid-auto">
              {[
                { code: 'PBS', name: 'Physics Balance Score', weight: '35%', desc: 'Piecewise linear on residual %. ≤1% → 1.0, >7% → 0.' },
                { code: 'ASS', name: 'Anomaly Stability Score', weight: '20%', desc: 'Exponential decay: exp(−10 × anomaly_rate).' },
                { code: 'CS', name: 'Confidence Score', weight: '15%', desc: 'Measurement quality from physics engine [0,1].' },
                { code: 'TSS', name: 'Temporal Stability', weight: '15%', desc: 'Rolling volatility of residual history.' },
                { code: 'DIS', name: 'Data Integrity Score', weight: '15%', desc: 'Penalises missing and invalid readings.' },
              ].map(c => (
                <div key={c.code} style={{ padding: '14px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', border: '1px solid var(--border-ghost)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--cyan)', fontWeight: 500 }}>{c.code}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)' }}>{c.weight}</span>
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)', marginBottom: 4 }}>{c.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5 }}>{c.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div style={{ marginTop: 16, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button onClick={fetchData} className="btn btn-secondary btn-sm">↻ Refresh</button>
        <Link href="/analysis" className="btn btn-secondary btn-sm">Run AI Analysis →</Link>
        <Link href="/inspections" className="btn btn-secondary btn-sm">View Inspections →</Link>
      </div>
    </div>
  )
}

