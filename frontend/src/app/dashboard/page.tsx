'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import { motion } from 'framer-motion'
import { api, DashboardData, ghiApi, GHIDashboard } from '@/lib/api'
import { AIAnalysisPanel } from '@/components/ui/AIAnalysisPanel'
import { FaultSimulator } from '@/components/ui/FaultSimulator'
import { LiveMetricsChart } from '@/components/charts/LiveMetricsChart'
import { TheftDetectionPanel } from '@/components/ui/TheftDetectionPanel'
import { SessionBanner } from '@/components/ui/SessionBanner'
import { useAppStore } from '@/store/useAppStore'

// Lazy-load heavy SVG component (SSR-safe)
const PowerFlowAnimation = dynamic(
  () => import('@/components/ui/PowerFlowAnimation').then(m => m.PowerFlowAnimation),
  { ssr: false, loading: () => <div className="panel" style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading power flow…</div> }
)

const TABS = [
  { key: 'overview',  label: '📊 Overview'     },
  { key: 'theft',     label: '🤖 Theft AI'     },
  { key: 'powerflow', label: '⚡ Power Flow'    },
  { key: 'ai',        label: '🧠 AI Analysis'   },
  { key: 'faults',    label: '🔌 Fault Sim'     },
] as const

type TabKey = typeof TABS[number]['key']

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [ghiData, setGhiData] = useState<GHIDashboard | null>(null)
  const [health, setHealth] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState('')
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [role, setRole] = useState<'admin' | 'inspector' | 'consumer'>('admin')
  const { selectedRegion } = useAppStore()

  const fetchData = useCallback(async () => {
    try {
      const [dashData, healthData, ghiDashData] = await Promise.all([
        api.getDashboard(),
        api.health().catch(() => null),
        ghiApi.getDashboard().catch(() => null),
      ])
      setData(dashData)
      setHealth(healthData)
      setGhiData(ghiDashData)
      setError(null)
      setLastFetched(new Date().toLocaleTimeString())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 60000)
    return () => clearInterval(id)
  }, [fetchData])

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 'calc(100vh - 120px)' }}>
      <div className="spinner spinner-lg" />
      <span>Loading dashboard…</span>
    </div>
  )

  const la         = data?.latest_analysis
  const agg        = data?.aggregates
  const components = health?.components || {}
  const uptimeRaw  = health?.uptime_seconds
  const uptime     = uptimeRaw
    ? uptimeRaw > 3600
      ? `${Math.floor(uptimeRaw / 3600)}h ${Math.floor((uptimeRaw % 3600) / 60)}m`
      : `${Math.floor(uptimeRaw / 60)}m`
    : null

  const residualColor = (pct: number | null | undefined) => {
    if (pct == null) return 'var(--cyan)'
    if (pct > 8) return 'var(--red)'
    if (pct > 3) return 'var(--amber)'
    return 'var(--green)'
  }

  return (
    <div className="page grid-bg">
      {/* Scan line decorative element */}
      <div className="scan-line" />

      {/* Header */}
      <motion.div
        className="page-header"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <div className="page-eyebrow">⚡ Live Control Room</div>
        <h1 className="page-title glow-text">Grid Intelligence Overview</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <p className="page-desc" style={{ margin: 0 }}>
            Real-time aggregates from all substations. Physics-validated energy balances,
            anomaly detection, and GHI scores.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
            {lastFetched && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: 5 }}>
                <span className="status-dot status-dot-green status-dot-pulse" />
                Updated {lastFetched}
              </span>
            )}
            <button onClick={fetchData} className="btn btn-secondary btn-sm">↻</button>
          </div>
        </div>
      </motion.div>

      {error && (
        <div className="alert alert-err fade-in" style={{ marginBottom: 20 }}>
          ⚠ Backend unreachable: {error}
          <span style={{ marginLeft: 12, opacity: 0.7 }}>Start: <code>cd backend && uvicorn app.main:app --reload</code></span>
        </div>
      )}

      <SessionBanner />

      {/* No data banner */}
      {!loading && data && !data.has_data && (
        <div className="panel fade-in glass" style={{ marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14, padding: '18px 24px' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>No meter data yet</div>
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Upload a CSV with timestamp, meter_id, energy_kwh to start seeing real analytics.</div>
          </div>
          <Link href="/upload" className="btn btn-primary">Upload CSV →</Link>
        </div>
      )}

      {/* Role selector */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.05 }}
        style={{ marginBottom: 20 }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>View as</span>
          {([
            { key: 'admin',     label: '🏛  DISCOM Admin',     desc: 'Grid view, all alerts' },
            { key: 'inspector', label: '🔍  Field Inspector',   desc: 'Alerts + dispatch' },
            { key: 'consumer',  label: '🏠  Consumer',          desc: 'Usage + bill' },
          ] as const).map(r => (
            <button
              key={r.key}
              onClick={() => setRole(r.key)}
              style={{
                padding: '8px 16px',
                borderRadius: 'var(--r-md)',
                border: `1px solid ${role === r.key ? 'var(--cyan)' : 'var(--border-subtle)'}`,
                background: role === r.key ? 'var(--cyan-dim)' : 'transparent',
                color: role === r.key ? 'var(--cyan)' : 'var(--text-tertiary)',
                fontFamily: 'var(--font-ui)',
                fontSize: 12,
                fontWeight: role === r.key ? 600 : 400,
                cursor: 'pointer',
                transition: 'all 0.18s',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: 2,
              }}
            >
              <span>{r.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: role === r.key ? 'var(--cyan)' : 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{r.desc}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Primary KPIs */}
      <motion.div
        className="grid-4"
        style={{ marginBottom: 16 }}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <GlassMetricCard
          label="Total Analyses"
          value={agg?.total_analyses?.toString() ?? (data?.has_data ? '—' : '0')}
          sub="physics-validated"
          icon="📊"
        />
        <GlassMetricCard
          label="Avg Residual"
          value={agg?.avg_residual_pct != null ? `${agg.avg_residual_pct}%` : '—'}
          sub="energy imbalance"
          color={residualColor(agg?.avg_residual_pct)}
          icon="📉"
        />
        <GlassMetricCard
          label="Anomalies"
          value={agg?.total_meter_anomalies?.toLocaleString() ?? '—'}
          sub={agg ? `${agg.meter_anomaly_rate_pct}% rate` : 'flagged readings'}
          color={agg && agg.meter_anomaly_rate_pct > 5 ? 'var(--amber)' : undefined}
          icon="⚠️"
        />
        <GlassMetricCard
          label="Open Inspections"
          value={ghiData?.open_inspections?.toString() ?? '—'}
          sub={ghiData?.critical_open ? `${ghiData.critical_open} critical` : 'tickets'}
          color={ghiData?.critical_open ? 'var(--red)' : undefined}
          icon="🔍"
        />
      </motion.div>

      {/* Navigation tabs */}
      <div className="tab-bar" style={{ marginBottom: 16 }}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`tab-btn${activeTab === tab.key ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Role-specific action banner */}
      {role === 'inspector' && (
        <motion.div
          key="inspector-banner"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel"
          style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, borderColor: 'rgba(255,176,32,0.35)', background: 'rgba(255,176,32,0.04)' }}
        >
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>🔍 Inspector View</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>
              {data?.high_risk_substations?.length
                ? `${data.high_risk_substations.length} high-risk substation${data.high_risk_substations.length > 1 ? 's' : ''} flagged: ${data.high_risk_substations.slice(0, 3).map(r => r.substation).join(', ')}.`
                : agg?.total_anomaly_checks
                  ? `${agg.anomalies_flagged ?? 0} anomalies flagged across ${agg.total_analyses ?? 0} analyses.`
                  : 'Upload meter data to see anomaly alerts for inspection.'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Link href="/anomaly" className="btn btn-secondary btn-sm" style={{ borderColor: 'var(--amber)', color: 'var(--amber)' }}>Anomaly Detection →</Link>
            <Link href="/analysis" className="btn btn-secondary btn-sm">Run Analysis →</Link>
          </div>
        </motion.div>
      )}
      {role === 'consumer' && (
        <motion.div
          key="consumer-banner"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel"
          style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, borderColor: 'rgba(0,224,150,0.35)', background: 'rgba(0,224,150,0.04)' }}
        >
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--green)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>🏠 Consumer View</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>
              {data?.latest_batch
                ? `Latest meter batch: ${data.latest_batch.filename}. Readings: ${data.latest_batch.row_count?.toLocaleString() ?? '—'}. Anomalies detected: ${data.latest_batch.anomalies_detected ?? 0}.`
                : 'No meter data uploaded yet. Upload a CSV to track your usage and billing estimates.'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Link href="/upload" className="btn btn-secondary btn-sm" style={{ borderColor: 'var(--green)', color: 'var(--green)' }}>Upload Meter Data →</Link>
            <Link href="/analysis" className="btn btn-secondary btn-sm">View Analysis →</Link>
          </div>
        </motion.div>
      )}
      {role === 'admin' && (
        <motion.div
          key="admin-banner"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel"
          style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, borderColor: 'rgba(0,212,255,0.35)', background: 'rgba(0,212,255,0.04)' }}
        >
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cyan)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>🏛 Admin View — DISCOM Control Room</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>
              {ghiData?.has_data
                ? `Fleet GHI: ${ghiData.avg_ghi_all_time ?? '—'}. ${ghiData.open_inspections ?? 0} open inspection${(ghiData.open_inspections ?? 0) !== 1 ? 's' : ''}${ghiData.critical_open ? `, ${ghiData.critical_open} critical` : ''}. ${agg?.anomalies_flagged ?? 0} anomalies flagged.`
                : `${agg?.total_analyses ?? 0} analyses run. ${agg?.anomalies_flagged ?? 0} anomalies flagged. Upload meter data to generate GHI scores.`}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab('theft')}>View Theft AI →</button>
            <Link href="/grid" className="btn btn-secondary btn-sm">Grid Map →</Link>
          </div>
        </motion.div>
      )}

      {/* ── OVERVIEW TAB ── */}
      {activeTab === 'overview' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          {/* Live metrics chart */}
          <LiveMetricsChart title="Real-time Grid Metrics" metric="load" />

          {/* Analysis + upload row */}
          <div className="grid-2-1">
            {/* Latest analysis */}
            <div className="panel panel-glow glass">
              <div className="sec-label accent">Latest Analysis</div>
              {la ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                    <div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)', marginBottom: 4 }}>
                        {la.substation_id}
                      </div>
                      <StatusChip status={la.balance_status} />
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 300, color: residualColor(la.residual_pct), letterSpacing: '-0.02em' }}>
                        {la.residual_pct?.toFixed(1) ?? '—'}%
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>residual loss</div>
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 12, marginBottom: 14 }}>
                    <KV label="Input"      value={`${la.input_energy_mwh?.toFixed(1)} MWh`}       />
                    <KV label="Output"     value={`${la.output_energy_mwh?.toFixed(1)} MWh`}      />
                    <KV label="Confidence" value={`${(la.confidence_score || 0).toFixed(0)}%`} />
                  </div>
                  <div style={{ height: 3, borderRadius: 2, background: 'var(--border-subtle)', overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(la.confidence_score || 0, 100)}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                      style={{ height: '100%', background: 'var(--cyan)', borderRadius: 2 }}
                    />
                  </div>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: '24px 0' }}>
                  <div className="empty-icon">📊</div>
                  <div className="empty-title">No analyses yet</div>
                  <div className="empty-desc">Run a physics analysis via the Upload or Analysis API</div>
                </div>
              )}
            </div>

            {/* Upload stats */}
            <div className="panel panel-glow glass">
              <div className="sec-label">Upload Activity</div>
              {data?.latest_batch ? (
                <>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', marginBottom: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {data.latest_batch.filename}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                    <KV label="Substation"    value={data.latest_batch.substation_id}                               />
                    <KV label="Readings"      value={data.latest_batch.row_count?.toLocaleString() ?? '—'}           />
                    <KV label="Anomalies"     value={data.latest_batch.anomalies_detected?.toString() ?? '0'}       />
                    <KV label="Batches total" value={agg?.total_batches_uploaded?.toString() ?? '—'}                />
                  </div>
                </>
              ) : (
                <div style={{ marginBottom: 16, fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                  No uploads yet. Upload a CSV file to begin analysis.
                </div>
              )}
              <Link href="/upload" className="btn btn-primary" style={{ width: '100%' }}>
                Upload Meter Data →
              </Link>
            </div>
          </div>

          {/* GHI + System Row */}
          <div className="grid-2">
            {/* GHI Overview */}
            <div className="panel panel-glow glass">
              <div className="sec-label accent">Grid Health Index</div>
              {ghiData?.has_data ? (
                <div>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
                    <div>
                      <motion.div
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.5 }}
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 52,
                          fontWeight: 300,
                          letterSpacing: '-0.03em',
                          lineHeight: 1,
                          color: ghiData.avg_ghi_all_time != null
                            ? ghiData.avg_ghi_all_time >= 70 ? 'var(--green)'
                              : ghiData.avg_ghi_all_time >= 50 ? 'var(--amber)' : 'var(--red)'
                            : 'var(--text-dim)',
                        }}
                      >
                        {ghiData.avg_ghi_all_time ?? '—'}
                      </motion.div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 4 }}>fleet avg GHI</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingBottom: 6 }}>
                      {Object.entries(ghiData.by_classification || {}).map(([cls, cnt]) => {
                        const colors: Record<string, string> = { HEALTHY: 'var(--green)', STABLE: 'var(--cyan)', DEGRADED: 'var(--amber)', CRITICAL: '#FF6B35', SEVERE: 'var(--red)' }
                        return (
                          <div key={cls} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: colors[cls] ?? 'var(--text-dim)', flexShrink: 0 }} />
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', width: 68, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{cls}</span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: colors[cls] ?? 'var(--text-secondary)' }}>{cnt}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Link href="/ghi" className="btn btn-secondary btn-sm">Full GHI →</Link>
                    <Link href="/inspections" className="btn btn-secondary btn-sm">Inspections →</Link>
                  </div>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: '24px 0' }}>
                  <div className="empty-icon">🏥</div>
                  <div className="empty-title">No GHI data</div>
                  <div className="empty-desc">GHI scores appear after running analysis with physics validation</div>
                </div>
              )}
            </div>

            {/* System status */}
            <div className="panel panel-glow glass">
              <div className="sec-label">System Health</div>
              <SystemRow label="Overall" status={health?.status || (error ? 'degraded' : 'unknown')} />
              {Object.entries(components).slice(0, 4).map(([key, val]: any) => (
                <SystemRow key={key} label={key.replace(/_/g, ' ')} status={val?.status ?? 'unknown'} />
              ))}
              {Object.keys(components).length === 0 && (
                <>
                  <SystemRow label="Database"       status={error ? 'unhealthy' : 'healthy'} />
                  <SystemRow label="Physics Engine"  status="active" />
                  <SystemRow label="Anomaly Engine"  status="active" />
                </>
              )}
              {uptime && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-ghost)' }}>
                  <KV label="Uptime" value={uptime} />
                </div>
              )}
            </div>
          </div>

          {/* Trend chart */}
          {data?.trend && data.trend.length > 0 && (
            <div className="grid-2-1">
              <div className="panel panel-glow glass">
                <div className="sec-label">Residual Loss Trend</div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 64 }}>
                  {data.trend?.map((t, i) => {
                    const maxR = Math.max(...(data.trend?.map(x => x.residual_pct) ?? [0.01]), 0.01)
                    const h = Math.max(4, (t.residual_pct / maxR) * 56)
                    const color = t.residual_pct > 8 ? 'var(--red)' : t.residual_pct > 3 ? 'var(--amber)' : 'var(--green)'
                    return (
                      <motion.div
                        key={i}
                        initial={{ scaleY: 0 }}
                        animate={{ scaleY: 1 }}
                        transition={{ duration: 0.5, delay: i * 0.02 }}
                        title={`${t.substation}: ${t.residual_pct.toFixed(1)}%`}
                        style={{ flex: 1, height: h, background: color, borderRadius: '2px 2px 0 0', opacity: 0.75, transformOrigin: 'bottom', cursor: 'default', minWidth: 3 }}
                      />
                    )
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>Oldest</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>Latest</span>
                </div>
              </div>

              {data.high_risk_substations?.length > 0 && (
                <div className="panel panel-glow glass">
                  <div className="sec-label">High Risk</div>
                  {data.high_risk_substations?.slice(0, 6).map(r => (
                    <div key={r.substation} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-ghost)' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{r.substation}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--red)', fontWeight: 500 }}>{r.avg_residual_pct}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Footer bar */}
          <div className="panel glass" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, padding: '14px 20px' }}>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              <KV label="Physics Engine"    value="PTE v2.1"    />
              <KV label="Anomaly Detection" value="IF + Z-Score" />
              <KV label="API"               value="v1"           />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Link href="/docs" className="btn btn-secondary btn-sm">API Docs</Link>
              <Link href="/grid" className="btn btn-secondary btn-sm">Grid Topology →</Link>
            </div>
          </div>
        </motion.div>
      )}

      {/* ── THEFT AI TAB ── */}
      {activeTab === 'theft' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          <div className="panel">
            <TheftDetectionPanel />
          </div>
        </motion.div>
      )}

      {/* ── POWER FLOW TAB ── */}
      {activeTab === 'powerflow' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          <PowerFlowAnimation />
          <LiveMetricsChart title="Grid Frequency & Voltage" metric="frequency" />
        </motion.div>
      )}

      {/* ── AI ANALYSIS TAB ── */}
      {activeTab === 'ai' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          <AIAnalysisPanel />
          <LiveMetricsChart title="Anomaly & Loss Tracking" metric="loss" />
        </motion.div>
      )}

      {/* ── FAULT SIMULATOR TAB ── */}
      {activeTab === 'faults' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          <FaultSimulator />
          <LiveMetricsChart title="Grid Stability Monitor" metric="voltage" />
        </motion.div>
      )}
    </div>
  )
}

/* ──────────────────────────── Sub-components ──────────────────────────── */

function GlassMetricCard({
  label, value, sub, color, icon,
}: {
  label: string; value: string; sub?: string; color?: string; icon?: string
}) {
  return (
    <motion.div
      className="metric-card glass panel-glow"
      whileHover={{ scale: 1.02, transition: { duration: 0.15 } }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div className="metric-label">{label}</div>
        {icon && <span style={{ fontSize: 16, opacity: 0.6 }}>{icon}</span>}
      </div>
      <div className="metric-value" style={{ color: color || 'var(--cyan)' }}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </motion.div>
  )
}

function MetricCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: color || 'var(--cyan)' }}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>{value}</div>
    </div>
  )
}

function SystemRow({ label, status }: { label: string; status: string }) {
  const isOk   = ['healthy', 'active', 'ok', 'running'].includes(status.toLowerCase())
  const isWarn = ['degraded', 'partial'].includes(status.toLowerCase())
  const cls    = isOk ? 'chip-ok' : isWarn ? 'chip-warn' : 'chip-err'
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-ghost)' }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{label}</span>
      <span className={`chip ${cls}`}>{status}</span>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    balanced:               'chip-ok',
    minor_imbalance:        'chip-info',
    significant_imbalance:  'chip-warn',
    critical_imbalance:     'chip-err',
    uncertain:              'chip-neutral',
    refused:                'chip-err',
  }
  return <span className={`chip ${map[status] || 'chip-neutral'}`}>{status?.replace(/_/g, ' ')}</span>
}

