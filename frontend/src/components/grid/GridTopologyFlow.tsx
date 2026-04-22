'use client'

import { useCallback, useState, useEffect } from 'react'
import ReactFlow, {
  Node, Edge, Background, Controls, MiniMap,
  BackgroundVariant, NodeTypes,
  useNodesState, useEdgesState, addEdge,
  MarkerType, Connection,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { motion, AnimatePresence } from 'framer-motion'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

/* ──────────────────────────── Custom Node ──────────────────────────── */

interface SubstationData {
  label: string
  load: number
  health: 'healthy' | 'warning' | 'critical'
  region: string
}

const HEALTH_COLOR = {
  healthy:  { border: '#00E096', bg: 'rgba(0,224,150,0.10)', text: '#00E096' },
  warning:  { border: '#FFB020', bg: 'rgba(255,176,32,0.10)', text: '#FFB020' },
  critical: { border: '#FF4455', bg: 'rgba(255,68,85,0.10)',  text: '#FF4455' },
}

function SubstationNode({ data, selected }: { data: SubstationData; selected: boolean }) {
  const clr = HEALTH_COLOR[data.health]
  return (
    <div
      style={{
        background: selected ? clr.bg : 'rgba(10,16,32,0.9)',
        border: `1.5px solid ${selected ? clr.border : 'rgba(100,180,255,0.15)'}`,
        borderRadius: 10,
        padding: '8px 12px',
        minWidth: 110,
        backdropFilter: 'blur(8px)',
        boxShadow: selected ? `0 0 16px ${clr.border}44` : '0 2px 8px rgba(0,0,0,0.4)',
        transition: 'all 0.2s ease',
        cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: clr.border,
          boxShadow: `0 0 6px ${clr.border}`,
          flexShrink: 0,
          animation: data.health === 'critical' ? 'pulse-dot 1s ease-in-out infinite' : undefined,
        }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-primary)', fontWeight: 600, whiteSpace: 'nowrap' }}>
          {data.label}
        </span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: clr.text, fontWeight: 300 }}>
        {data.load} <span style={{ fontSize: 8, color: 'var(--text-dim)' }}>MW</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>
        {data.region} · {data.health}
      </div>
    </div>
  )
}

const nodeTypes: NodeTypes = {
  substation: SubstationNode as any,
}

/* ──────────────────────────── Default data ──────────────────────────── */

const INITIAL_NODES: Node<SubstationData>[] = [
  { id: 'NR-DEL', type: 'substation', position: { x: 340, y: 60  }, data: { label: 'Delhi',       load: 512, health: 'healthy',  region: 'North' } },
  { id: 'NR-CHD', type: 'substation', position: { x: 200, y: 0   }, data: { label: 'Chandigarh',  load: 199, health: 'warning',  region: 'North' } },
  { id: 'NR-LKO', type: 'substation', position: { x: 480, y: 100 }, data: { label: 'Lucknow',     load: 345, health: 'healthy',  region: 'North' } },
  { id: 'NR-JAI', type: 'substation', position: { x: 220, y: 130 }, data: { label: 'Jaipur',      load: 279, health: 'healthy',  region: 'North' } },
  { id: 'WR-MUM', type: 'substation', position: { x: 120, y: 300 }, data: { label: 'Mumbai',      load: 724, health: 'critical', region: 'West'  } },
  { id: 'WR-PUN', type: 'substation', position: { x: 200, y: 240 }, data: { label: 'Pune',        load: 389, health: 'warning',  region: 'West'  } },
  { id: 'WR-AHM', type: 'substation', position: { x: 100, y: 180 }, data: { label: 'Ahmedabad',   load: 303, health: 'healthy',  region: 'West'  } },
  { id: 'WR-NGP', type: 'substation', position: { x: 320, y: 240 }, data: { label: 'Nagpur',      load: 216, health: 'healthy',  region: 'West'  } },
  { id: 'SR-BLR', type: 'substation', position: { x: 320, y: 400 }, data: { label: 'Bengaluru',   load: 567, health: 'healthy',  region: 'South' } },
  { id: 'SR-CHN', type: 'substation', position: { x: 460, y: 420 }, data: { label: 'Chennai',     load: 494, health: 'healthy',  region: 'South' } },
  { id: 'SR-HYD', type: 'substation', position: { x: 360, y: 320 }, data: { label: 'Hyderabad',   load: 442, health: 'warning',  region: 'South' } },
  { id: 'ER-KOL', type: 'substation', position: { x: 600, y: 200 }, data: { label: 'Kolkata',     load: 398, health: 'healthy',  region: 'East'  } },
  { id: 'ER-BHU', type: 'substation', position: { x: 560, y: 300 }, data: { label: 'Bhubaneswar', load: 187, health: 'healthy',  region: 'East'  } },
  { id: 'ER-PAT', type: 'substation', position: { x: 520, y: 140 }, data: { label: 'Patna',       load: 225, health: 'warning',  region: 'East'  } },
]

function makeEdge(id: string, source: string, target: string, flow: number, interRegional = false): Edge {
  return {
    id,
    source,
    target,
    label: `${flow} MW`,
    animated: true,
    style: {
      stroke: interRegional ? 'rgba(139,92,246,0.6)' : 'rgba(0,212,255,0.4)',
      strokeWidth: Math.max(1.5, flow / 100),
      strokeDasharray: interRegional ? '6 3' : undefined,
    },
    labelStyle: { fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'rgba(100,180,255,0.6)' },
    labelBgStyle: { fill: 'rgba(6,11,20,0.8)', fillOpacity: 0.9 },
    markerEnd: { type: MarkerType.ArrowClosed, color: interRegional ? 'rgba(139,92,246,0.6)' : 'rgba(0,212,255,0.4)', width: 12, height: 12 },
  }
}

const INITIAL_EDGES: Edge[] = [
  makeEdge('e1',  'NR-DEL', 'NR-CHD', 180),
  makeEdge('e2',  'NR-DEL', 'NR-LKO', 260),
  makeEdge('e3',  'NR-DEL', 'NR-JAI', 200),
  makeEdge('e4',  'NR-DEL', 'WR-AHM', 150, true),
  makeEdge('e5',  'WR-MUM', 'WR-PUN', 310),
  makeEdge('e6',  'WR-MUM', 'WR-AHM', 250),
  makeEdge('e7',  'WR-AHM', 'WR-NGP', 170),
  makeEdge('e8',  'WR-NGP', 'SR-HYD', 140, true),
  makeEdge('e9',  'SR-BLR', 'SR-CHN', 290),
  makeEdge('e10', 'SR-BLR', 'SR-HYD', 320),
  makeEdge('e11', 'SR-CHN', 'ER-BHU', 130, true),
  makeEdge('e12', 'ER-KOL', 'ER-BHU', 210),
  makeEdge('e13', 'ER-KOL', 'ER-PAT', 180),
  makeEdge('e14', 'ER-PAT', 'NR-LKO', 160, true),
]

/* ──────────────────────────── Component ──────────────────────────── */

export function GridTopologyFlow() {
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES)
  const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES)
  const [selected, setSelected] = useState<SubstationData | null>(null)
  const [dataSource, setDataSource] = useState<'live' | 'demo'>('demo')

  // Fetch real GHI dashboard data and build nodes/edges from it
  useEffect(() => {
    async function loadData() {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('urjarakshak_token') : null
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${BASE}/api/v1/ai/ghi/dashboard`, { headers })
        if (!res.ok) return
        const data = await res.json()
        const substations: Array<{
          substation_id: string
          ghi_score: number
          balance_status?: string
          total_energy_mwh?: number
        }> = data.substations || []
        if (substations.length < 2) return

        const n = substations.length
        const radius = Math.min(220, 40 + n * 14)
        const cx = 360
        const cy = 260

        const newNodes: Node<SubstationData>[] = substations.map((s, i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const bs = (s.balance_status || '').toLowerCase()
          const ghi = s.ghi_score ?? 50
          let health: SubstationData['health'] = 'healthy'
          if (bs === 'critical_imbalance' || ghi < 30) health = 'critical'
          else if (bs === 'significant_imbalance' || ghi < 60) health = 'warning'
          return {
            id: s.substation_id,
            type: 'substation',
            position: {
              x: cx + radius * Math.cos(angle),
              y: cy + radius * Math.sin(angle),
            },
            data: {
              label: s.substation_id,
              load: parseFloat(((s.total_energy_mwh ?? 0) * 1000 / 8760).toFixed(1)),
              health,
              region: 'Uploaded',
            },
          }
        })

        const newEdges: Edge[] = newNodes.map((nd, i) => {
          const next = newNodes[(i + 1) % newNodes.length]
          const flow = Math.round(nd.data.load * 0.6)
          return makeEdge(`eu${i}`, nd.id, next.id, flow, false)
        })

        setNodes(newNodes)
        setEdges(newEdges)
        setDataSource('live')
      } catch (_) { /* keep fallback */ }
    }
    loadData()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onConnect = useCallback(
    (params: Connection) => setEdges(eds => addEdge(params, eds)),
    [setEdges]
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node<SubstationData>) => {
    setSelected(prev => prev?.label === node.data.label ? null : node.data)
  }, [])

  const totalLoad     = nodes.reduce((s, n) => s + n.data.load, 0)
  const criticalCount = nodes.filter(n => n.data.health === 'critical').length
  const warningCount  = nodes.filter(n => n.data.health === 'warning').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Stats row */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <Stat label="Substations" value={nodes.length.toString()} color="var(--cyan)" />
        <Stat label="Total Load"  value={`${totalLoad.toFixed(0)} MW`}    color="var(--blue)" />
        <Stat label="Critical"    value={criticalCount.toString()}         color="var(--red)"  />
        <Stat label="Warnings"    value={warningCount.toString()}          color="var(--amber)" />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          {dataSource === 'demo' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--amber)', border: '1px solid rgba(255,186,48,0.3)', borderRadius: 4, padding: '2px 6px' }}>
              DEMO
            </span>
          )}
          {dataSource === 'live' && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--green)', border: '1px solid rgba(0,224,150,0.3)', borderRadius: 4, padding: '2px 6px' }}>
              LIVE DATA
            </span>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 24, height: 2, background: 'rgba(0,212,255,0.5)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>Intra-region</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ width: 24, height: 2, background: 'rgba(139,92,246,0.6)', borderTop: '2px dashed rgba(139,92,246,0.6)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>Inter-region</span>
          </div>
        </div>
      </div>

      {/* ReactFlow canvas */}
      <div
        className="panel-flush"
        style={{
          height: 480,
          background: 'var(--bg-panel)',
          borderRadius: 'var(--r-lg)',
          overflow: 'hidden',
          border: '1px solid var(--border-subtle)',
          position: 'relative',
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.4}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          style={{ background: 'transparent' }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1}
            color="rgba(0,212,255,0.06)"
          />
          <Controls
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 8,
            }}
          />
          <MiniMap
            nodeColor={n => HEALTH_COLOR[(n.data as SubstationData).health].border}
            style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 8,
            }}
          />
        </ReactFlow>

        {/* Selected node info overlay */}
        <AnimatePresence>
          {selected && (
            <motion.div
              key={selected.label}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              style={{
                position: 'absolute',
                top: 12, right: 12,
                background: 'var(--bg-elevated)',
                border: `1px solid ${HEALTH_COLOR[selected.health].border}`,
                borderRadius: 10,
                padding: '12px 16px',
                minWidth: 160,
                zIndex: 10,
                backdropFilter: 'blur(12px)',
                boxShadow: `0 0 24px ${HEALTH_COLOR[selected.health].border}44`,
              }}
            >
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', fontWeight: 600, marginBottom: 8 }}>
                📍 {selected.label}
              </p>
              <Row label="Region"  value={selected.region} />
              <Row label="Load"    value={`${selected.load} MW`} />
              <Row label="Status"  value={selected.health} color={HEALTH_COLOR[selected.health].text} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color, fontWeight: 300 }}>{value}</div>
    </div>
  )
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid var(--border-ghost)' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: color || 'var(--text-secondary)', textTransform: 'capitalize' }}>{value}</span>
    </div>
  )
}
