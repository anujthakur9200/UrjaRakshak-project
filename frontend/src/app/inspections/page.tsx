'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, inspectionApi, Inspection, InspectionStats } from '@/lib/api'

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: 'var(--red)',
  HIGH:     '#FF6B35',
  MEDIUM:   'var(--amber)',
  LOW:      'var(--cyan)',
  INFORMATIONAL: 'var(--text-dim)',
}
const STATUS_CHIP: Record<string, string> = {
  OPEN:        'chip-err',
  IN_PROGRESS: 'chip-warn',
  RESOLVED:    'chip-ok',
  DISMISSED:   'chip-neutral',
}
const STATUS_COLORS: Record<string, string> = {
  OPEN:        'var(--red)',
  IN_PROGRESS: 'var(--amber)',
  RESOLVED:    'var(--green)',
  DISMISSED:   'var(--text-dim)',
}
const RESOLUTIONS = ['TECHNICAL_LOSS_NORMAL','EQUIPMENT_FAULT','METER_ISSUE','DATA_QUALITY','OTHER']

/** Animated bar chart for inspection stats */
function StatsBarChart({ data, colorMap, label }: {
  data: Record<string, number>
  colorMap: Record<string, string>
  label: string
}) {
  const entries = Object.entries(data).filter(([, v]) => v > 0)
  if (entries.length === 0) return null
  const max = Math.max(...entries.map(([, v]) => v), 1)
  return (
    <div>
      <div className="sec-label" style={{ marginBottom: 10 }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {entries.map(([key, val]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.07em', color: colorMap[key] || 'var(--text-dim)', minWidth: 90 }}>
              {key.replace(/_/g, ' ')}
            </span>
            <div style={{ flex: 1, height: 8, background: 'var(--border-ghost)', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${(val / max) * 100}%`,
                background: colorMap[key] || 'var(--cyan)',
                borderRadius: 4,
                transition: 'width 0.7s ease',
                animation: 'growRight 0.7s ease forwards',
              }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', minWidth: 24, textAlign: 'right' }}>{val}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Mini animated sparkline from an array of numbers */
function Sparkline({ values, color = 'var(--cyan)' }: { values: number[]; color?: string }) {
  if (values.length === 0) return null
  const max = Math.max(...values, 1)
  return (
    <div className="sparkline" style={{ height: 28 }}>
      {values.map((v, i) => (
        <div
          key={i}
          className="sparkline-bar"
          style={{
            height: `${Math.max(4, (v / max) * 28)}px`,
            background: color,
            animationDelay: `${i * 0.03}s`,
          }}
        />
      ))}
    </div>
  )
}

export default function InspectionsPage() {
  const [items, setItems] = useState<Inspection[]>([])
  const [stats, setStats] = useState<InspectionStats | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [selected, setSelected] = useState<Inspection | null>(null)
  const [saving, setSaving] = useState(false)
  const [findings, setFindings] = useState('')
  const [resolution, setResolution] = useState('')
  const [newStatus, setNewStatus] = useState('')
  const [updateMsg, setUpdateMsg] = useState('')
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const [listRes, statsRes] = await Promise.all([
        inspectionApi.list({ status: statusFilter || undefined, priority: priorityFilter || undefined, limit: 50 }),
        inspectionApi.getStats(),
      ])
      setItems(listRes.items)
      setTotal(listRes.total)
      setStats(statsRes)
    } catch (e: any) {
      const msg = e.message || 'Failed to load inspections'
      if (msg.includes('401') || msg.includes('Authentication') || msg.includes('Not authenticated')) {
        setFetchError('auth_required')
      } else if (msg.includes('403') || msg.includes('forbidden') || msg.includes('Forbidden')) {
        setFetchError('auth_required')
      } else {
        setFetchError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [statusFilter, priorityFilter])

  useEffect(() => { fetchAll() }, [fetchAll])

  const openDetail = (item: Inspection) => {
    setSelected(item)
    setFindings(item.findings || '')
    setResolution(item.resolution_notes || item.resolution || '')
    setNewStatus(item.status)
    setUpdateMsg('')
  }

  const handleUpdate = async () => {
    if (!selected) return
    setSaving(true)
    setUpdateMsg('')
    try {
      await inspectionApi.update(selected.id, { findings, resolution_notes: resolution, status: newStatus })
      setUpdateMsg('✓ Saved')
      fetchAll()
      setTimeout(() => setSelected(null), 800)
    } catch (e: any) {
      setUpdateMsg(`Error: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleLogin = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const res = await api.login(authEmail, authPassword)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setFetchError(null)
      fetchAll()
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
      setFetchError(null)
      fetchAll()
    } catch (e: any) {
      setAuthError(e.message || 'Registration failed')
    } finally {
      setAuthLoading(false)
    }
  }

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 'calc(100vh - 120px)' }}>
      <div className="spinner spinner-lg" />
      <span>Loading inspections…</span>
    </div>
  )

  return (
    <div className="page">
      <div className="page-header fade-in">
        <div className="page-eyebrow">Inspection Workflow</div>
        <h1 className="page-title">Field Inspections</h1>
        <p className="page-desc">
          Tickets auto-created when physics analysis flags significant residual loss or GHI drops below threshold.
          Update status after field investigation.
        </p>
      </div>

      {fetchError && fetchError !== 'auth_required' && (
        <div className="alert alert-err fade-in" style={{ marginBottom: 20 }}>
          {fetchError}
        </div>
      )}

      {fetchError === 'auth_required' && (
        <div className="panel fade-in" style={{ marginBottom: 24, maxWidth: 440 }}>
          <div className="sec-label accent">Authentication Required</div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 1.6 }}>
            Viewing inspections requires an analyst account.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <input
              className="input"
              type="email"
              placeholder="Email address"
              value={authEmail}
              onChange={e => setAuthEmail(e.target.value)}
              autoComplete="email"
            />
            <input
              className="input"
              type="password"
              placeholder="Password"
              value={authPassword}
              onChange={e => setAuthPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
            />
          </div>
          {authError && <div className="alert alert-err" style={{ marginBottom: 14 }}>{authError}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleLogin} disabled={authLoading || !authEmail || !authPassword} className="btn btn-primary" style={{ flex: 1 }}>
              {authLoading ? 'Logging in…' : 'Login'}
            </button>
            <button onClick={handleRegister} disabled={authLoading || !authEmail || !authPassword} className="btn btn-secondary" style={{ flex: 1 }}>
              Register
            </button>
          </div>
        </div>
      )}

      {/* Stats row */}
      {stats && !fetchError && (
        <div className="grid-4 fade-in stagger-1" style={{ marginBottom: 20 }}>
          <div className="metric-card">
            <div className="metric-label">Open</div>
            <div className="metric-value" style={{ color: (stats.by_status?.OPEN ?? 0) > 0 ? 'var(--amber)' : 'var(--green)' }}>
              {stats.by_status?.OPEN ?? 0}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Critical / High</div>
            <div className="metric-value" style={{ color: stats.critical_open > 0 ? 'var(--red)' : 'var(--cyan)' }}>
              {stats.critical_open}
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">In Progress</div>
            <div className="metric-value">{stats.by_status?.IN_PROGRESS ?? 0}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Resolved</div>
            <div className="metric-value" style={{ color: 'var(--green)' }}>{stats.by_status?.RESOLVED ?? 0}</div>
          </div>
        </div>
      )}

      {/* Animated breakdown charts */}
      {stats && !fetchError && stats.total > 0 && (
        <div className="grid-2 fade-in stagger-2" style={{ marginBottom: 20 }}>
          <div className="panel">
            <StatsBarChart data={stats.by_status ?? {}} colorMap={STATUS_COLORS} label="By Status" />
          </div>
          <div className="panel">
            <StatsBarChart data={stats.by_priority ?? {}} colorMap={PRIORITY_COLORS} label="By Priority" />
          </div>
        </div>
      )}

      {/* Filters */}
      {!fetchError && (
      <div className="fade-in stagger-3" style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <select className="input" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All Statuses</option>
          <option value="OPEN">Open</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="RESOLVED">Resolved</option>
          <option value="DISMISSED">Dismissed</option>
        </select>
        <select className="input" value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All Priorities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <button onClick={fetchAll} className="btn btn-secondary btn-sm">↻ Refresh</button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', alignSelf: 'center', marginLeft: 4 }}>
          {total} ticket{total !== 1 ? 's' : ''}
        </span>
      </div>
      )}

      {/* Table / List */}
      {!fetchError && (items.length === 0 ? (
        <div className="panel fade-in">
          <div className="empty-state">
            <div className="empty-icon">🔍</div>
            <div className="empty-title">No inspections found</div>
            <div className="empty-desc">
              Tickets are auto-created when an analysis exceeds the risk threshold. Run a physics analysis to generate your first ticket.
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Mobile: card list */}
          <div className="hide-tablet fade-in stagger-4" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map(item => (
              <div
                key={item.id}
                className="panel panel-sm"
                onClick={() => openDetail(item)}
                style={{ cursor: 'pointer', borderLeft: `3px solid ${PRIORITY_COLORS[item.priority] || 'var(--border-dim)'}` }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 8 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--cyan)' }}>{item.substation_id}</div>
                  <span className={`chip ${STATUS_CHIP[item.status] || 'chip-neutral'}`}>{item.status}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, lineHeight: 1.5 }}>{item.description?.slice(0, 100)}{item.description?.length > 100 ? '…' : ''}</div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: PRIORITY_COLORS[item.priority], textTransform: 'uppercase', letterSpacing: '0.06em' }}>{item.priority}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>{item.created_at?.slice(0, 10)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop: table */}
          <div className="panel panel-flush fade-in stagger-4 hide-mobile" style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Substation</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Urgency</th>
                  <th>Description</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} style={{ cursor: 'pointer' }} onClick={() => openDetail(item)}>
                    <td style={{ color: 'var(--cyan)' }}>{item.substation_id}</td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: PRIORITY_COLORS[item.priority], textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {item.priority}
                      </span>
                    </td>
                    <td><span className={`chip ${STATUS_CHIP[item.status] || 'chip-neutral'}`}>{item.status}</span></td>
                    <td style={{ color: 'var(--text-tertiary)' }}>{item.urgency || '—'}</td>
                    <td style={{ color: 'var(--text-secondary)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.description?.slice(0, 80)}{item.description?.length > 80 ? '…' : ''}
                    </td>
                    <td style={{ color: 'var(--text-dim)' }}>{item.created_at?.slice(0, 10)}</td>
                    <td>
                      <button className="btn btn-secondary btn-sm" onClick={e => { e.stopPropagation(); openDetail(item) }}>
                        Update
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ))}

      {/* Detail modal */}
      {selected && (
        <div
          onClick={() => setSelected(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
        >
          <div
            onClick={e => e.stopPropagation()}
            className="panel panel-elevated fade-in"
            style={{ width: '100%', maxWidth: 560, maxHeight: '90vh', overflowY: 'auto' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div>
                <div className="page-eyebrow" style={{ marginBottom: 4 }}>Inspection Detail</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)' }}>{selected.substation_id}</div>
              </div>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>✕</button>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              <span className={`chip ${STATUS_CHIP[selected.status] || 'chip-neutral'}`}>{selected.status}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: PRIORITY_COLORS[selected.priority], textTransform: 'uppercase', letterSpacing: '0.06em' }}>{selected.priority}</span>
              {selected.urgency && <span className="chip chip-neutral">{selected.urgency}</span>}
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65, marginBottom: 20 }}>{selected.description}</p>

            {selected.ai_recommendation && (
              <div className="alert alert-info" style={{ marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, opacity: 0.7 }}>AI Recommendation</div>
                {selected.ai_recommendation}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', display: 'block', marginBottom: 6 }}>
                  Update Status
                </label>
                <select className="input" value={newStatus} onChange={e => setNewStatus(e.target.value)}>
                  <option value="OPEN">Open</option>
                  <option value="IN_PROGRESS">In Progress</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="DISMISSED">Dismissed</option>
                </select>
              </div>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', display: 'block', marginBottom: 6 }}>
                  Resolution Code
                </label>
                <select className="input" value={resolution} onChange={e => setResolution(e.target.value)}>
                  <option value="">— Select —</option>
                  {RESOLUTIONS.map(r => <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', display: 'block', marginBottom: 6 }}>
                  Field Findings
                </label>
                <textarea
                  className="input"
                  value={findings}
                  onChange={e => setFindings(e.target.value)}
                  rows={4}
                  placeholder="Describe what was found during inspection…"
                  style={{ resize: 'vertical' }}
                />
              </div>
            </div>

            {updateMsg && (
              <div className={`alert ${updateMsg.startsWith('✓') ? 'alert-ok' : 'alert-err'}`} style={{ marginTop: 12 }}>
                {updateMsg}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <button onClick={handleUpdate} disabled={saving} className="btn btn-primary" style={{ flex: 1 }}>
                {saving ? 'Saving…' : 'Save Update'}
              </button>
              <button onClick={() => setSelected(null)} className="btn btn-secondary">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
