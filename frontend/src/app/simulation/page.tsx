'use client'

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

// ── Zone model ──────────────────────────────────────────────────────────────

interface Zone {
  id: string
  name: string
  sector: string
  type: 'residential' | 'commercial' | 'industrial' | 'substation'
  status: 'normal' | 'warning' | 'theft' | 'investigating' | 'resolved'
  consumption: number
  expected: number
  theftProb: number
  row: number
  col: number
}

// ── Fallback zones when no data is uploaded ──────────────────────────────────

const FALLBACK_ZONES: Zone[] = [
  { id: 'Z01', name: 'Substation Alpha', sector: 'Central',  type: 'substation',  status: 'normal',  consumption: 2840, expected: 2900, theftProb:  4, row: 0, col: 1 },
  { id: 'Z02', name: 'Sector 12 — Res',  sector: 'North',    type: 'residential', status: 'theft',   consumption:  148, expected:  312, theftProb: 94, row: 0, col: 2 },
  { id: 'Z03', name: 'Market Complex',   sector: 'East',     type: 'commercial',  status: 'normal',  consumption: 1102, expected: 1140, theftProb:  8, row: 0, col: 3 },
  { id: 'Z04', name: 'Factory Zone A',   sector: 'North',    type: 'industrial',  status: 'normal',  consumption: 4200, expected: 4350, theftProb: 12, row: 1, col: 0 },
  { id: 'Z05', name: 'Residential Block',sector: 'West',     type: 'residential', status: 'warning', consumption:  390, expected:  520, theftProb: 38, row: 1, col: 1 },
  { id: 'Z06', name: 'Substation Beta',  sector: 'Central',  type: 'substation',  status: 'normal',  consumption: 3100, expected: 3150, theftProb:  6, row: 1, col: 2 },
  { id: 'Z07', name: 'Sector 8 — Comm',  sector: 'East',     type: 'commercial',  status: 'theft',   consumption:  890, expected: 1340, theftProb: 78, row: 1, col: 3 },
  { id: 'Z08', name: 'Apartment Block',  sector: 'South',    type: 'residential', status: 'normal',  consumption:  625, expected:  640, theftProb:  9, row: 2, col: 0 },
  { id: 'Z09', name: 'Industrial Park',  sector: 'South',    type: 'industrial',  status: 'warning', consumption: 3800, expected: 4900, theftProb: 45, row: 2, col: 1 },
  { id: 'Z10', name: 'Sector 21 — Ind',  sector: 'South',    type: 'industrial',  status: 'normal',  consumption: 4200, expected: 5800, theftProb: 61, row: 2, col: 2 },
  { id: 'Z11', name: 'Housing Estate',   sector: 'West',     type: 'residential', status: 'normal',  consumption:  480, expected:  490, theftProb:  3, row: 2, col: 3 },
  { id: 'Z12', name: 'Grid Control',     sector: 'Central',  type: 'substation',  status: 'normal',  consumption: 1800, expected: 1850, theftProb:  2, row: 3, col: 1 },
]

// ── Build zones from GHI dashboard API data ───────────────────────────────────

interface GhiSubstation {
  substation_id: string
  ghi_score: number
  balance_status?: string
  residual_pct?: number
  total_energy_mwh?: number
  last_updated?: string
}

function ghiToZone(s: GhiSubstation, idx: number): Zone {
  const row = Math.floor(idx / 4)
  const col = idx % 4
  const ghi = s.ghi_score ?? 50
  const residual = s.residual_pct ?? 0
  // Derive theft probability from residual loss and GHI
  const theftProb = Math.round(Math.min(99, Math.max(0, residual * 4 + (100 - ghi) * 0.5)))
  const totalMwh = (s.total_energy_mwh ?? 1) * 1000   // convert to kWh
  const consumption = Math.round(totalMwh * (1 - residual / 100))
  const expected = Math.round(totalMwh)

  let status: Zone['status'] = 'normal'
  const bs = (s.balance_status || '').toLowerCase()
  if (bs === 'critical_imbalance') status = 'theft'
  else if (bs === 'significant_imbalance') status = 'warning'
  else if (ghi < 40) status = 'warning'

  return {
    id: s.substation_id,
    name: s.substation_id,
    sector: s.substation_id.split('-')[0] || 'Grid',
    type: 'substation',
    status,
    consumption,
    expected,
    theftProb,
    row,
    col,
  }
}

// ── Type icons / colors ─────────────────────────────────────────────────────

const TYPE_ICON: Record<Zone['type'], string> = {
  substation:  '🔌',
  residential: '🏘',
  commercial:  '🏢',
  industrial:  '🏭',
}

const TYPE_COLOR: Record<Zone['type'], string> = {
  substation:  '#00D4FF',
  residential: '#00E096',
  commercial:  '#8B5CF6',
  industrial:  '#FFB020',
}

const STATUS_CONFIG: Record<Zone['status'], { border: string; bg: string; label: string; chipClass: string }> = {
  normal:       { border: 'var(--border-subtle)',      bg: 'var(--bg-panel)',       label: 'Normal',      chipClass: 'chip-ok'   },
  warning:      { border: 'rgba(255,186,48,0.45)',     bg: 'rgba(255,176,32,0.06)', label: 'Warning',     chipClass: 'chip-warn' },
  theft:        { border: 'rgba(255,68,85,0.7)',       bg: 'rgba(255,68,85,0.1)',   label: 'THEFT',       chipClass: 'chip-err'  },
  investigating:{ border: 'rgba(0,212,255,0.5)',       bg: 'rgba(0,212,255,0.06)',  label: 'Under Review',chipClass: 'chip-cyan' },
  resolved:     { border: 'rgba(5,232,154,0.4)',       bg: 'rgba(5,232,154,0.05)',  label: 'Resolved',    chipClass: 'chip-ok'   },
}

// ── Event log ───────────────────────────────────────────────────────────────

interface EventLog {
  id: number
  ts: string
  zoneId: string
  zoneName: string
  message: string
  severity: 'info' | 'warning' | 'critical'
}

let _eventId = 1

function nowStr() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

// ── Zone card ───────────────────────────────────────────────────────────────

function ZoneCard({
  zone,
  selected,
  onClick,
}: {
  zone: Zone
  selected: boolean
  onClick: () => void
}) {
  const cfg = STATUS_CONFIG[zone.status]
  const typeColor = TYPE_COLOR[zone.type]
  const deviation = zone.expected > 0 ? ((zone.consumption - zone.expected) / zone.expected) * 100 : 0

  return (
    <motion.div
      layout
      onClick={onClick}
      animate={
        zone.status === 'theft'
          ? { boxShadow: ['0 0 0 rgba(255,68,85,0)', '0 0 24px rgba(255,68,85,0.7)', '0 0 0 rgba(255,68,85,0)'] }
          : { boxShadow: '0 0 0 rgba(0,0,0,0)' }
      }
      transition={zone.status === 'theft' ? { duration: 1.4, repeat: Infinity, ease: 'easeInOut' } : {}}
      style={{
        padding: '14px 16px',
        borderRadius: 'var(--r-lg)',
        border: `1px solid ${selected ? typeColor : cfg.border}`,
        background: selected ? `${typeColor}0d` : cfg.bg,
        cursor: 'pointer',
        transition: 'border-color 0.2s, background 0.2s',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Theft blinking overlay */}
      {zone.status === 'theft' && (
        <motion.div
          style={{ position: 'absolute', inset: 0, background: 'rgba(255,68,85,0.08)', borderRadius: 'inherit', pointerEvents: 'none' }}
          animate={{ opacity: [0.4, 0, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity }}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 16 }}>{TYPE_ICON[zone.type]}</span>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.2 }}>{zone.name}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{zone.sector}</div>
          </div>
        </div>
        <span className={`chip ${cfg.chipClass}`} style={{ fontSize: 9, flexShrink: 0 }}>{cfg.label}</span>
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 300, color: zone.status === 'theft' ? 'var(--red)' : 'var(--text-primary)', lineHeight: 1 }}>
            {zone.consumption.toLocaleString()}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>kWh</div>
        </div>
        {deviation !== 0 && (
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: deviation < -15 ? 'var(--red)' : deviation < -5 ? 'var(--amber)' : 'var(--green)',
            marginBottom: 2,
          }}>
            {deviation.toFixed(1)}%
          </div>
        )}
      </div>

      {/* Theft probability bar */}
      {zone.theftProb > 10 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Theft risk</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: zone.theftProb >= 70 ? 'var(--red)' : zone.theftProb >= 40 ? 'var(--amber)' : 'var(--cyan)' }}>{zone.theftProb}%</span>
          </div>
          <div style={{ height: 3, background: 'var(--border-ghost)', borderRadius: 2, overflow: 'hidden' }}>
            <motion.div
              style={{ height: '100%', background: zone.theftProb >= 70 ? 'var(--red)' : zone.theftProb >= 40 ? 'var(--amber)' : 'var(--cyan)', borderRadius: 2 }}
              initial={{ width: 0 }}
              animate={{ width: `${zone.theftProb}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
            />
          </div>
        </div>
      )}
    </motion.div>
  )
}

// ── Simulation constants ─────────────────────────────────────────────────────

const THEFT_MIN_RATIO   = 0.35   // minimum consumption ratio when theft injected
const THEFT_RATIO_RANGE = 0.25   // random range on top of min ratio
const THEFT_MIN_PROB    = 75     // minimum theft probability on injection
const THEFT_PROB_RANGE  = 24     // random range on top of min probability
const MAX_WARNING_PROB  = 60     // cap for auto-event warning probability
const WARNING_PROB_INC  = 15     // probability increment per auto-warning event
const AUTO_EVENT_CHANCE = 0.25   // probability an auto tick triggers a warning

// ── Main page ────────────────────────────────────────────────────────────────

export default function SimulationPage() {
  const [zones, setZones] = useState<Zone[]>([])
  const [baseZones, setBaseZones] = useState<Zone[]>([])   // for reset
  const [loading, setLoading] = useState(true)
  const [dataSource, setDataSource] = useState<'live' | 'fallback'>('fallback')
  const [eventLog, setEventLog] = useState<EventLog[]>([])
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null)
  const [autoRun, setAutoRun] = useState(true)
  const autoRef = useRef(autoRun)
  autoRef.current = autoRun
  const zonesRef = useRef(zones)
  zonesRef.current = zones

  // Fetch real data from backend
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
            const liveZones = substations.map((s, i) => ghiToZone(s, i))
            setZones(liveZones)
            setBaseZones(liveZones)
            setDataSource('live')
            setLoading(false)
            return
          }
        }
      } catch (_) { /* fall through */ }
      // Fallback to demo data
      setZones(FALLBACK_ZONES)
      setBaseZones(FALLBACK_ZONES)
      setDataSource('fallback')
      setLoading(false)
    }
    fetchData()
  }, [])

  function addEvent(zoneId: string, zoneName: string, message: string, severity: EventLog['severity']) {
    const entry: EventLog = { id: _eventId++, ts: nowStr(), zoneId, zoneName, message, severity }
    setEventLog(prev => [entry, ...prev].slice(0, 15))
  }

  function injectTheft(targetId?: string) {
    const currentZones = zonesRef.current
    const candidates = currentZones.filter(z => z.status === 'normal')
    const target = targetId
      ? currentZones.find(z => z.id === targetId)
      : candidates[Math.floor(Math.random() * candidates.length)]
    if (!target) return
    setZones(prev => prev.map(z =>
      z.id === target.id
        ? { ...z, status: 'theft', consumption: Math.round(z.expected * (THEFT_MIN_RATIO + Math.random() * THEFT_RATIO_RANGE)), theftProb: THEFT_MIN_PROB + Math.floor(Math.random() * THEFT_PROB_RANGE) }
        : z
    ))
    addEvent(target.id, target.name, `Theft detected — 52% consumption drop vs 30-day baseline. Isolation Forest score: 0.91`, 'critical')
  }

  function investigateZone(zoneId: string) {
    const zone = zonesRef.current.find(z => z.id === zoneId)
    setZones(prev => prev.map(z =>
      z.id === zoneId ? { ...z, status: 'investigating' } : z
    ))
    if (zone) addEvent(zone.id, zone.name, 'Inspector dispatched. Zone under investigation.', 'info')
  }

  function resolveZone(zoneId: string) {
    const zone = zonesRef.current.find(z => z.id === zoneId)
    setZones(prev => prev.map(z =>
      z.id === zoneId ? { ...z, status: 'resolved', consumption: z.expected, theftProb: Math.max(2, z.theftProb - 80) } : z
    ))
    if (zone) addEvent(zone.id, zone.name, 'Theft confirmed. Illegal bypass removed. Consumption normalised.', 'info')
    setSelectedZone(null)
  }

  function resetAll() {
    setZones(baseZones)
    setEventLog([])
    setSelectedZone(null)
  }

  // Auto-run: randomly trigger events every 8 seconds
  useEffect(() => {
    const id = setInterval(() => {
      if (!autoRef.current) return
      const r = Math.random()
      if (r < AUTO_EVENT_CHANCE) {
        const normalZones = zonesRef.current.filter(z => z.status === 'normal')
        const pick = normalZones[Math.floor(Math.random() * normalZones.length)]
        if (pick) {
          setZones(prev => prev.map(z =>
            z.id === pick.id ? { ...z, status: 'warning', theftProb: Math.min(MAX_WARNING_PROB, z.theftProb + WARNING_PROB_INC) } : z
          ))
          addEvent(pick.id, pick.name, 'Unusual load fluctuation. Monitoring…', 'warning')
        }
      }
    }, 8000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="page grid-bg" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
          <p style={{ color: 'var(--text-secondary)' }}>Loading simulation data…</p>
        </div>
      </div>
    )
  }

  const theftZones        = zones.filter(z => z.status === 'theft')
  const warningZones      = zones.filter(z => z.status === 'warning')
  const investigatingZones = zones.filter(z => z.status === 'investigating')
  const totalLoss         = theftZones.reduce((s, z) => s + (z.expected - z.consumption), 0)

  return (
    <div className="page grid-bg">
      <div className="scan-line" />

      {/* Header */}
      <motion.div className="page-header" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="page-eyebrow">⚡ Live Simulation</div>
        <h1 className="page-title glow-text">Grid Theft Detection Simulation</h1>
        <p className="page-desc">
          Interactive grid — inject theft events, investigate zones, and resolve incidents in real-time.
          {dataSource === 'live'
            ? ` Showing ${zones.length} substations from uploaded data.`
            : ' Showing demo data — upload meter readings to see your real grid.'}
        </p>
        {dataSource === 'fallback' && (
          <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 'var(--r-md)', background: 'rgba(255,186,48,0.07)', border: '1px solid rgba(255,186,48,0.2)', fontSize: 12, color: 'var(--amber)', display: 'inline-block' }}>
            ⚠ Demo mode — <a href="/upload" style={{ color: 'var(--cyan)' }}>upload meter data</a> to simulate your real grid
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn btn-danger" onClick={() => injectTheft()}>
            ⚡ Inject Theft Event
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => setAutoRun(v => !v)}
            style={autoRun ? { borderColor: 'var(--cyan)', color: 'var(--cyan)' } : {}}
          >
            {autoRun ? '⏸ Pause Auto-Events' : '▶ Resume Auto-Events'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={resetAll}>↺ Reset</button>
        </div>
      </motion.div>

      {/* KPIs */}
      <div className="grid-4" style={{ marginBottom: 20 }}>
        {[
          { label: 'Theft Events',         value: theftZones.length,        color: 'var(--red)',   sub: 'active now' },
          { label: 'Warning Zones',         value: warningZones.length,      color: 'var(--amber)', sub: 'monitoring' },
          { label: 'Under Investigation',   value: investigatingZones.length, color: 'var(--cyan)',  sub: 'in progress' },
          { label: 'Energy Loss',           value: `${totalLoss.toLocaleString()} kWh`, color: 'var(--red)', sub: 'estimated theft' },
        ].map(kpi => (
          <motion.div key={kpi.label} className="panel" layout>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>{kpi.label}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 300, color: kpi.color, lineHeight: 1, marginBottom: 4 }}>{kpi.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{kpi.sub}</div>
          </motion.div>
        ))}
      </div>

      {/* Main layout: zone grid + side panel */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16, marginBottom: 20 }} className="sim-layout">
        {/* Zone grid */}
        <div>
          <div className="sec-label" style={{ marginBottom: 12 }}>City Grid — {zones.length} Zones</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {zones.map(zone => (
              <ZoneCard
                key={zone.id}
                zone={zone}
                selected={selectedZone?.id === zone.id}
                onClick={() => setSelectedZone(prev => prev?.id === zone.id ? null : zone)}
              />
            ))}
          </div>
        </div>

        {/* Side panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Selected zone detail */}
          <AnimatePresence mode="wait">
            {selectedZone ? (
              <motion.div
                key={selectedZone.id}
                className="panel"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{selectedZone.name}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2 }}>
                      {selectedZone.sector} · {selectedZone.type}
                    </div>
                  </div>
                  <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', fontSize: 16 }} onClick={() => setSelectedZone(null)}>×</button>
                </div>
                <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
                  <span className={`chip ${STATUS_CONFIG[selectedZone.status].chipClass}`}>{STATUS_CONFIG[selectedZone.status].label}</span>
                </div>
                {[
                  { label: 'Consumption', value: `${selectedZone.consumption.toLocaleString()} kWh` },
                  { label: 'Expected',    value: `${selectedZone.expected.toLocaleString()} kWh` },
                  { label: 'Deviation',   value: `${(((selectedZone.consumption - selectedZone.expected) / selectedZone.expected) * 100).toFixed(1)}%` },
                  { label: 'Theft Risk',  value: `${selectedZone.theftProb}%` },
                ].map(row => (
                  <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid var(--border-ghost)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{row.label}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)' }}>{row.value}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
                  {(selectedZone.status === 'theft' || selectedZone.status === 'warning') && (
                    <button className="btn btn-secondary btn-sm" style={{ width: '100%' }} onClick={() => investigateZone(selectedZone.id)}>
                      🔍 Dispatch Inspector
                    </button>
                  )}
                  {selectedZone.status === 'investigating' && (
                    <button className="btn btn-primary btn-sm" style={{ width: '100%' }} onClick={() => resolveZone(selectedZone.id)}>
                      ✓ Mark Resolved
                    </button>
                  )}
                  {selectedZone.status === 'normal' && (
                    <button className="btn btn-danger btn-sm" style={{ width: '100%' }} onClick={() => injectTheft(selectedZone.id)}>
                      ⚡ Simulate Theft
                    </button>
                  )}
                </div>
              </motion.div>
            ) : (
              <motion.div className="panel panel-ghost" key="hint" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <p style={{ fontSize: 12, color: 'var(--text-tertiary)', textAlign: 'center', lineHeight: 1.65 }}>
                  👆 Click any zone card to inspect it and take action.
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Event log */}
          <div className="panel panel-flush" style={{ flex: 1 }}>
            <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Event Log</span>
              {eventLog.length > 0 && <span className="chip chip-cyan" style={{ fontSize: 9 }}>{eventLog.length}</span>}
            </div>
            <div style={{ maxHeight: 260, overflowY: 'auto', padding: '6px 0' }}>
              {eventLog.length === 0 ? (
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)', textAlign: 'center', padding: '16px 0' }}>No events yet.</p>
              ) : (
                <AnimatePresence>
                  {eventLog.map(ev => (
                    <motion.div key={ev.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-ghost)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
                        <span style={{ width: 5, height: 5, borderRadius: '50%', background: ev.severity === 'critical' ? 'var(--red)' : ev.severity === 'warning' ? 'var(--amber)' : 'var(--cyan)', flexShrink: 0 }} />
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)' }}>{ev.ts}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-secondary)', fontWeight: 600, marginLeft: 2 }}>{ev.zoneName}</span>
                      </div>
                      <p style={{ margin: 0, fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5, paddingLeft: 10 }}>{ev.message}</p>
                    </motion.div>
                  ))}
                </AnimatePresence>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="panel panel-ghost" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', padding: '10px 14px' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Status</span>
        {Object.entries(STATUS_CONFIG).map(([status, cfg]) => (
          <span key={status} className={`chip ${cfg.chipClass}`} style={{ fontSize: 9 }}>{cfg.label}</span>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {Object.entries(TYPE_ICON).map(([type, icon]) => (
            <span key={type} style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)' }}>{icon} {type}</span>
          ))}
        </div>
      </div>

      <style>{`
        @media (max-width: 900px) { .sim-layout { grid-template-columns: 1fr !important; } }
        @media (max-width: 560px) { .sim-layout > div:first-child > div { grid-template-columns: repeat(2, 1fr) !important; } }
      `}</style>
    </div>
  )
}
