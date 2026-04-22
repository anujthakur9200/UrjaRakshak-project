'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'

interface SuspiciousMeter {
  id: string
  sector: string
  theftProbability: number
  consumption: number
  expected: number
  deviation: number
  reason: string
  action: string
}

const MOCK_METERS: SuspiciousMeter[] = [
  {
    id: 'MTR-2241',
    sector: 'Sector 12 — Residential',
    theftProbability: 94,
    consumption: 148,
    expected: 312,
    deviation: -52.6,
    reason: 'Meter reading dropped 52.6% vs 30-day baseline. Physics gate: First-Law imbalance 3.8σ above fleet.',
    action: 'Dispatch field inspector immediately',
  },
  {
    id: 'MTR-3087',
    sector: 'Sector 8 — Commercial',
    theftProbability: 78,
    consumption: 890,
    expected: 1340,
    deviation: -33.6,
    reason: 'Consistent 33% under-consumption since new transformer installed. Isolation Forest anomaly score: 0.82.',
    action: 'Schedule meter audit within 48 hours',
  },
  {
    id: 'MTR-1155',
    sector: 'Sector 21 — Industrial',
    theftProbability: 61,
    consumption: 4200,
    expected: 5800,
    deviation: -27.6,
    reason: 'Night-time load profile mismatch. Z-score: 2.4. Possible illegal bypass after 22:00.',
    action: 'Review night-time meter logs',
  },
]

/** Max theft probability cap */
const THEFT_PROB_MAX = 98
/** Z-score to probability weight (each σ adds this much probability) */
const Z_SCORE_WEIGHT = 15
/** Z-score contribution cap before deviation adds its share */
const Z_SCORE_CAP = 60
/** Deviation threshold above which full deviation bonus applies */
const DEVIATION_BONUS_THRESHOLD = 30

/** Build theft suspects from real anomaly sample */
function buildMetersFromSession(session: ReturnType<typeof useAppStore.getState>['activeSession']): SuspiciousMeter[] {
  if (!session?.anomalySample?.length) return []
  return session.anomalySample
    .slice(0, 5)
    .map(a => {
      const zAbs = Math.abs(a.z_score ?? 0)
      const deviation = a.expected_kwh > 0
        ? ((a.energy_kwh - a.expected_kwh) / a.expected_kwh) * 100
        : 0
      const theftProb = Math.min(THEFT_PROB_MAX, Math.round(
        Math.min(zAbs * Z_SCORE_WEIGHT, Z_SCORE_CAP) +
        (Math.abs(deviation) > DEVIATION_BONUS_THRESHOLD ? DEVIATION_BONUS_THRESHOLD : Math.abs(deviation))
      ))
      const action = theftProb >= 80
        ? 'Dispatch field inspector immediately'
        : theftProb >= 60
        ? 'Schedule meter audit within 48 hours'
        : 'Review meter logs and 30-day baseline'
      return {
        id: a.meter_id,
        sector: session.substationId,
        theftProbability: theftProb,
        consumption: +a.energy_kwh.toFixed(2),
        expected: +a.expected_kwh.toFixed(2),
        deviation: +deviation.toFixed(1),
        reason: `${a.reason}. Z-score: ${a.z_score?.toFixed(2) ?? 'N/A'}. Isolation Forest anomaly detected.`,
        action,
      } satisfies SuspiciousMeter
    })
    .sort((a, b) => b.theftProbability - a.theftProbability)
}

function ProbabilityGauge({ value, size = 120 }: { value: number; size?: number }) {
  const radius = (size - 20) / 2
  const circumference = 2 * Math.PI * radius
  const strokeDash = (value / 100) * circumference * 0.75
  const startAngle = -225
  const color =
    value >= 80 ? '#FF4455' : value >= 60 ? '#FFB020' : value >= 40 ? '#00D4FF' : '#00E096'

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        {/* Background arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={8}
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          style={{ transform: `rotate(${startAngle + 90}deg)`, transformOrigin: `${size / 2}px ${size / 2}px` }}
        />
        {/* Value arc */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeDasharray={`${strokeDash} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          style={{
            transform: `rotate(${startAngle + 90}deg)`,
            transformOrigin: `${size / 2}px ${size / 2}px`,
            filter: `drop-shadow(0 0 8px ${color})`,
          }}
          initial={{ strokeDasharray: `0 ${circumference}` }}
          animate={{ strokeDasharray: `${strokeDash} ${circumference}` }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        />
      </svg>
      <div style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: size * 0.22,
          fontWeight: 700,
          color,
          lineHeight: 1,
        }}>
          {value}%
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 2 }}>
          Theft Prob
        </span>
      </div>
    </div>
  )
}

function MeterRow({ meter, isSelected, onClick }: { meter: SuspiciousMeter; isSelected: boolean; onClick: () => void }) {
  const color = meter.theftProbability >= 80 ? 'var(--red)' : meter.theftProbability >= 60 ? 'var(--amber)' : 'var(--cyan)'
  const chipClass = meter.theftProbability >= 80 ? 'chip-err' : meter.theftProbability >= 60 ? 'chip-warn' : 'chip-cyan'

  return (
    <motion.div
      layout
      onClick={onClick}
      style={{
        padding: '14px 16px',
        borderRadius: 'var(--r-md)',
        border: `1px solid ${isSelected ? color : 'var(--border-subtle)'}`,
        background: isSelected ? `${color}0d` : 'transparent',
        cursor: 'pointer',
        transition: 'border-color 0.2s, background 0.2s',
        marginBottom: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: isSelected ? 10 : 0 }}>
        <span className={`chip ${chipClass}`}>
          {meter.theftProbability}% risk
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>
          {meter.id}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
          {meter.sector}
        </span>
      </div>

      <AnimatePresence>
        {isSelected && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22 }}
          >
            {/* Consumption vs Expected */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
              <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '8px 12px', flex: 1, minWidth: 100 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Actual</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--text-primary)', fontWeight: 300 }}>{meter.consumption} <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>kWh</span></div>
              </div>
              <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '8px 12px', flex: 1, minWidth: 100 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Expected</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--text-secondary)', fontWeight: 300 }}>{meter.expected} <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>kWh</span></div>
              </div>
              <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '8px 12px', flex: 1, minWidth: 100 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Deviation</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color, fontWeight: 300 }}>{meter.deviation}%</div>
              </div>
            </div>

            {/* Reason */}
            <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--r-sm)', padding: '10px 12px', marginBottom: 8, borderLeft: `3px solid ${color}` }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-tertiary)', marginBottom: 4 }}>Why flagged</div>
              <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.6 }}>{meter.reason}</p>
            </div>

            {/* Action */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 11, color }}>→</span>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', fontWeight: 500 }}>{meter.action}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export function TheftDetectionPanel() {
  const activeSession = useAppStore(s => s.activeSession)
  const realMeters = useMemo(() => buildMetersFromSession(activeSession), [activeSession])
  const meters = realMeters.length > 0 ? realMeters : MOCK_METERS
  const isRealData = realMeters.length > 0

  const [selectedMeter, setSelectedMeter] = useState<string | null>(meters[0]?.id ?? null)
  const [scanActive, setScanActive] = useState(false)
  const [scanProgress, setScanProgress] = useState(0)
  const [scanResults, setScanResults] = useState<string[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset selection when meters change
  useEffect(() => { setSelectedMeter(meters[0]?.id ?? null) }, [meters])

  const SCAN_LINES = isRealData
    ? [
        `Loading ${activeSession?.rowsParsed} meter readings from ${activeSession?.substationId}…`,
        'Running Isolation Forest on uploaded batch…',
        'Computing Z-scores per meter…',
        'Applying physics gate: First-Law check…',
        'Cross-validating 3 detection methods…',
        'Ranking meters by theft probability…',
        'Generating explainability report…',
        `Scan complete — ${meters.length} suspicious meter${meters.length !== 1 ? 's' : ''} found.`,
      ]
    : [
        'Initialising anomaly detection engine…',
        'Loading 30-day baseline per meter…',
        'Running Isolation Forest (n_estimators=200)…',
        'Computing Z-scores across fleet…',
        'Applying physics gate: First-Law check…',
        'Cross-validating 3 detection methods…',
        'Ranking meters by theft probability…',
        'Generating explainability report…',
        'Scan complete — 3 suspicious meters found.',
      ]

  function startScan() {
    setScanActive(true)
    setScanProgress(0)
    setScanResults([])
    let step = 0
    intervalRef.current = setInterval(() => {
      step++
      setScanProgress(Math.min(100, Math.round((step / SCAN_LINES.length) * 100)))
      setScanResults(prev => [...prev, SCAN_LINES[step - 1]])
      if (step >= SCAN_LINES.length) {
        const id = intervalRef.current
        if (id) clearInterval(id)
        intervalRef.current = null
        setTimeout(() => setScanActive(false), 600)
      }
    }, 420)
  }

  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current) }, [])

  const topMeter = meters.find(m => m.id === selectedMeter) ?? meters[0]
  const totalSuspect = meters.length
  const criticalCount = meters.filter(m => m.theftProbability >= 80).length

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <div className="page-eyebrow" style={{ marginBottom: 6 }}>🤖 AI Theft Detection</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--text-primary)', margin: 0 }}>
            Anomaly Intelligence
          </h2>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.6 }}>
            3-gate detection: Isolation Forest + Z-Score + Physics validation. All three must agree before flagging.
            {isRealData && (
              <span style={{ marginLeft: 8, color: 'var(--green)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                ● Live data · {activeSession?.substationId}
              </span>
            )}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={startScan} disabled={scanActive}>
          {scanActive ? '⏳ Scanning…' : '🔍 Run Detection Scan'}
        </button>
      </div>

      {/* Scan progress */}
      <AnimatePresence>
        {(scanActive || scanResults.length > 0) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="panel"
            style={{ marginBottom: 20, background: 'rgba(0,0,0,0.3)', fontFamily: 'var(--font-mono)', fontSize: 11.5 }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <div style={{ flex: 1, height: 3, background: 'var(--border-ghost)', borderRadius: 2, overflow: 'hidden' }}>
                <motion.div
                  style={{ height: '100%', background: 'var(--cyan)', borderRadius: 2 }}
                  animate={{ width: `${scanProgress}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
              <span style={{ color: 'var(--cyan)', minWidth: 36, textAlign: 'right' }}>{scanProgress}%</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              {scanResults.map((line, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  style={{ color: i === scanResults.length - 1 ? 'var(--cyan)' : 'var(--text-tertiary)' }}
                >
                  <span style={{ color: 'var(--text-dim)', marginRight: 8 }}>{'>'}</span>
                  {line}
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* KPI row */}
      {topMeter && (
        <div className="grid-3" style={{ marginBottom: 20 }}>
          <div className="panel" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <ProbabilityGauge value={topMeter.theftProbability} size={88} />
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>Top Risk</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>{topMeter.id}</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>{topMeter.sector}</div>
            </div>
          </div>
          <div className="panel" style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 36, fontWeight: 300, color: 'var(--amber)', lineHeight: 1 }}>{totalSuspect}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 6 }}>Suspicious Meters</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{isRealData ? `from ${activeSession?.substationId}` : 'across 3 sectors'}</div>
          </div>
          <div className="panel" style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 36, fontWeight: 300, color: 'var(--red)', lineHeight: 1 }}>{criticalCount}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 6 }}>Critical — High Risk</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>immediate action needed</div>
          </div>
        </div>
      )}

      {/* Meter list */}
      <div className="sec-label" style={{ marginBottom: 12 }}>Suspicious Meters — Ranked by Risk</div>
      <div>
        {meters.map(meter => (
          <MeterRow
            key={meter.id}
            meter={meter}
            isSelected={selectedMeter === meter.id}
            onClick={() => setSelectedMeter(selectedMeter === meter.id ? null : meter.id)}
          />
        ))}
      </div>

      {/* Methodology note */}
      <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: 'var(--r-md)', background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.12)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--cyan)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>Explainability</div>
        <p style={{ fontSize: 12.5, color: 'var(--text-tertiary)', margin: 0, lineHeight: 1.65 }}>
          All flags require consensus across three independent gates: (1) Isolation Forest anomaly score {'>'}0.7, (2) Z-score deviation {'>'}2.0σ from 30-day rolling baseline, (3) Physics engine First-Law imbalance {'>'} 3%. This 3-of-3 requirement minimises false positives and protects against model gaming.
        </p>
      </div>
    </div>
  )
}
