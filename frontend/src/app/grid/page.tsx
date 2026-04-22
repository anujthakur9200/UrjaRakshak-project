'use client'

import { useState, useMemo, useEffect } from 'react'
import dynamic from 'next/dynamic'
import type { GridNode, GridEdge } from '@/components/grid/AnimatedGridMap'
import { MetricCard } from '@/components/ui/MetricCard'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

const AnimatedGridMap = dynamic(
  () => import('@/components/grid/AnimatedGridMap').then((m) => m.AnimatedGridMap),
  { ssr: false, loading: () => <div style={{ height: 400, background: 'var(--bg-panel)', borderRadius: 'var(--r-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Initialising grid topology…</div> }
)

const GridTopologyFlow = dynamic(
  () => import('@/components/grid/GridTopologyFlow').then((m) => m.GridTopologyFlow),
  { ssr: false, loading: () => <div style={{ height: 500, background: 'var(--bg-panel)', borderRadius: 'var(--r-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Loading ReactFlow topology…</div> }
)

// ── Fallback mock data used only when no data has been uploaded ────────────

const FALLBACK_NODES: GridNode[] = [
  { id: 'NR-DEL', label: 'Delhi',       health: 'healthy',  load: 512.4 },
  { id: 'NR-CHD', label: 'Chandigarh',  health: 'warning',  load: 198.7 },
  { id: 'NR-LKO', label: 'Lucknow',     health: 'healthy',  load: 345.2 },
  { id: 'NR-JAI', label: 'Jaipur',      health: 'healthy',  load: 278.9 },
  { id: 'WR-MUM', label: 'Mumbai',      health: 'critical', load: 724.3 },
  { id: 'WR-PUN', label: 'Pune',        health: 'warning',  load: 389.1 },
  { id: 'WR-AHM', label: 'Ahmedabad',   health: 'healthy',  load: 302.5 },
  { id: 'WR-NGP', label: 'Nagpur',      health: 'healthy',  load: 215.8 },
  { id: 'SR-BLR', label: 'Bengaluru',   health: 'healthy',  load: 567.2 },
  { id: 'SR-CHN', label: 'Chennai',     health: 'healthy',  load: 493.6 },
  { id: 'SR-HYD', label: 'Hyderabad',   health: 'warning',  load: 441.9 },
  { id: 'ER-KOL', label: 'Kolkata',     health: 'healthy',  load: 398.4 },
  { id: 'ER-BHU', label: 'Bhubaneswar', health: 'healthy',  load: 187.3 },
  { id: 'ER-PAT', label: 'Patna',       health: 'warning',  load: 224.6 },
]

const FALLBACK_EDGES: GridEdge[] = [
  { source: 'NR-DEL', target: 'NR-CHD', flow: 180 },
  { source: 'NR-DEL', target: 'NR-LKO', flow: 260 },
  { source: 'NR-DEL', target: 'NR-JAI', flow: 200 },
  { source: 'NR-DEL', target: 'WR-AHM', flow: 150 },
  { source: 'WR-MUM', target: 'WR-PUN', flow: 310 },
  { source: 'WR-MUM', target: 'WR-AHM', flow: 250 },
  { source: 'WR-AHM', target: 'WR-NGP', flow: 170 },
  { source: 'WR-NGP', target: 'SR-HYD', flow: 140 },
  { source: 'SR-BLR', target: 'SR-CHN', flow: 290 },
  { source: 'SR-BLR', target: 'SR-HYD', flow: 320 },
  { source: 'SR-CHN', target: 'ER-BHU', flow: 130 },
  { source: 'ER-KOL', target: 'ER-BHU', flow: 210 },
  { source: 'ER-KOL', target: 'ER-PAT', flow: 180 },
  { source: 'ER-PAT', target: 'NR-LKO', flow: 160 },
]

// ── Build GridNode from GHI dashboard data ─────────────────────────────────

interface GhiSubstation {
  substation_id: string
  ghi_score: number
  balance_status?: string
  residual_pct?: number
  total_energy_mwh?: number
}

function ghiToNode(s: GhiSubstation): GridNode {
  const ghi = s.ghi_score ?? 50
  let health: GridNode['health'] = 'healthy'
  const bs = (s.balance_status || '').toLowerCase()
  if (bs === 'critical_imbalance' || ghi < 30) health = 'critical'
  else if (bs === 'significant_imbalance' || ghi < 60) health = 'warning'
  return {
    id: s.substation_id,
    label: s.substation_id,
    health,
    load: parseFloat(((s.total_energy_mwh ?? 0) * 1000 / 8760).toFixed(1)), // avg kW → MW
  }
}

/** Connect uploaded substations in a simple ring topology for visualisation */
function buildEdgesFromNodes(nodes: GridNode[]): GridEdge[] {
  if (nodes.length < 2) return []
  return nodes.map((n, i) => ({
    source: n.id,
    target: nodes[(i + 1) % nodes.length].id,
    flow: Math.round(n.load * 0.6),
  }))
}

interface RegionSummary {
  name: string
  color: string
  nodes: string[]
  nodeIds: string[]
  totalLoad: number
  alerts: number
}

function buildRegions(nodes: GridNode[]): RegionSummary[] {
  // For uploaded data (no NR-/WR- prefix) group all under "Uploaded"
  const hasPrefix = nodes.some((n) => /^[A-Z]{2}-/.test(n.id))
  if (!hasPrefix) {
    return [{
      name: 'Uploaded Substations',
      color: '#00D4FF',
      nodes: nodes.map((n) => n.label),
      nodeIds: nodes.map((n) => n.id),
      totalLoad: nodes.reduce((s, n) => s + n.load, 0),
      alerts: nodes.filter((n) => n.health !== 'healthy').length,
    }]
  }
  const regions: { name: string; color: string; prefix: string }[] = [
    { name: 'North', color: '#00D4FF', prefix: 'NR-' },
    { name: 'West',  color: '#8B5CF6', prefix: 'WR-' },
    { name: 'South', color: '#00E096', prefix: 'SR-' },
    { name: 'East',  color: '#FFB020', prefix: 'ER-' },
  ]
  return regions.map((r) => {
    const regionNodes = nodes.filter((n) => n.id.startsWith(r.prefix))
    return {
      name: r.name,
      color: r.color,
      nodes: regionNodes.map((n) => n.label),
      nodeIds: regionNodes.map((n) => n.id),
      totalLoad: regionNodes.reduce((s, n) => s + n.load, 0),
      alerts: regionNodes.filter((n) => n.health !== 'healthy').length,
    }
  }).filter((r) => r.nodes.length > 0)
}

export default function GridPage() {
  const [allNodes, setAllNodes] = useState<GridNode[]>([])
  const [allEdges, setAllEdges] = useState<GridEdge[]>([])
  const [dataSource, setDataSource] = useState<'live' | 'fallback'>('fallback')
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'force' | 'flow'>('flow')

  // Fetch real substation data from GHI dashboard
  useEffect(() => {
    async function fetchData() {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('urjarakshak_token') : null
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${BASE}/api/v1/ai/ghi/dashboard`, { headers })
        if (res.ok) {
          const data = await res.json()
          const substations: GhiSubstation[] = data.substations || []
          if (substations.length > 0) {
            const nodes = substations.map(ghiToNode)
            const edges = buildEdgesFromNodes(nodes)
            setAllNodes(nodes)
            setAllEdges(edges)
            setDataSource('live')
            return
          }
        }
      } catch (_) { /* fall through */ }
      setAllNodes(FALLBACK_NODES)
      setAllEdges(FALLBACK_EDGES)
      setDataSource('fallback')
    }
    fetchData()
  }, [])

  const regions = useMemo(() => buildRegions(allNodes), [allNodes])

  const displayNodes = useMemo(() => {
    if (!selectedRegion) return allNodes
    const region = regions.find((r) => r.name === selectedRegion)
    if (region) {
      const ids = new Set(region.nodeIds)
      return allNodes.filter((n) => ids.has(n.id))
    }
    return allNodes
  }, [selectedRegion, allNodes, regions])

  const displayEdges = useMemo(() => {
    const ids = new Set(displayNodes.map((n) => n.id))
    return allEdges.filter((e) => ids.has(e.source) && ids.has(e.target))
  }, [displayNodes, allEdges])

  const totalLoad    = allNodes.reduce((s, n) => s + n.load, 0)
  const activeAlerts = allNodes.filter((n) => n.health !== 'healthy').length
  const criticalCount = allNodes.filter((n) => n.health === 'critical').length

  return (
    <main className="page grid-bg">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">⚡ Grid Visualization</div>
          <h1 className="page-title">Grid Topology</h1>
          <p className="page-desc">
            {dataSource === 'live'
              ? `Showing ${allNodes.length} substations from uploaded data. Health and load derived from GHI analysis.`
              : 'Real-time visualisation of substation nodes, transmission lines, and power flow. Upload meter data to see your real grid.'}
          </p>
          {dataSource === 'fallback' && (
            <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 'var(--r-md)', background: 'rgba(255,186,48,0.07)', border: '1px solid rgba(255,186,48,0.2)', fontSize: 12, color: 'var(--amber)', display: 'inline-block' }}>
              ⚠ Demo data — <a href="/upload" style={{ color: 'var(--cyan)' }}>upload meter readings</a> to visualise your real grid
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
          {/* View mode toggle */}
          <div style={{ display: 'flex', gap: 4, background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 4 }}>
            <button
              className={`btn btn-sm${viewMode === 'flow' ? ' btn-primary' : ' btn-secondary'}`}
              style={{ border: 'none', padding: '4px 10px' }}
              onClick={() => setViewMode('flow')}
            >
              Flow Diagram
            </button>
            <button
              className={`btn btn-sm${viewMode === 'force' ? ' btn-primary' : ' btn-secondary'}`}
              style={{ border: 'none', padding: '4px 10px' }}
              onClick={() => setViewMode('force')}
            >
              Force Graph
            </button>
          </div>
          {viewMode === 'force' && (
            <>
              <button
                className={`btn ${selectedRegion === null ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setSelectedRegion(null)}
              >
                All Regions
              </button>
              {regions.map((r) => (
                <button
                  key={r.name}
                  className={`btn ${selectedRegion === r.name ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSelectedRegion(selectedRegion === r.name ? null : r.name)}
                  style={selectedRegion === r.name ? { borderColor: r.color, color: r.color } : {}}
                >
                  {r.name}
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Summary metrics */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <MetricCard label="Total Substations"  value={allNodes.length}  unit=""     color="var(--cyan)"  />
        <MetricCard label="Total Load"         value={totalLoad}        unit=" MW"  color="var(--blue)"  />
        <MetricCard label="Active Alerts"      value={activeAlerts}     unit=""     color="var(--amber)" />
        <MetricCard label="Critical Nodes"     value={criticalCount}    unit=""     color="var(--red)"   />
      </div>

      {/* ReactFlow topology */}
      {viewMode === 'flow' && (
        <div style={{ marginBottom: 24 }}>
          <GridTopologyFlow />
        </div>
      )}

      {/* Force-directed map */}
      {viewMode === 'force' && (
        <div className="panel glass" style={{ marginBottom: 24, padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--border)' }}>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', margin: 0 }}>
              Showing {displayNodes.length} substations · {displayEdges.length} transmission links
              {selectedRegion ? ` · ${selectedRegion} Region` : ' · National Grid'}
            </p>
          </div>
          <AnimatedGridMap nodes={displayNodes} edges={displayEdges} />
        </div>
      )}

      {/* Region cards */}
      <h2 style={{ fontFamily: 'var(--font-ui)', fontSize: 15, color: 'var(--text-secondary)', marginBottom: 14, fontWeight: 500, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Regional Breakdown
      </h2>
      <div className="grid-4">
        {regions.map((r) => (
          <div
            key={r.name}
            className="panel-elevated glass"
            style={{
              cursor: 'pointer',
              borderLeft: `3px solid ${r.color}`,
              transition: 'box-shadow 0.2s',
              boxShadow: selectedRegion === r.name ? `0 0 20px ${r.color}33` : undefined,
            }}
            onClick={() => setSelectedRegion(selectedRegion === r.name ? null : r.name)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ fontFamily: 'var(--font-ui)', fontWeight: 600, color: r.color }}>
                {r.name} Region
              </span>
              {r.alerts > 0 && (
                <span className="chip chip-warn" style={{ fontSize: 10 }}>
                  {r.alerts} alert{r.alerts > 1 ? 's' : ''}
                </span>
              )}
            </div>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color: 'var(--text-primary)', margin: '4px 0' }}>
              {r.totalLoad.toFixed(0)} <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>MW</span>
            </p>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', margin: 0 }}>
              {r.nodes.join(' · ')}
            </p>
          </div>
        ))}
      </div>
    </main>
  )
}
