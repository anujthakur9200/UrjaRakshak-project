'use client'

import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '@/store/useAppStore'

interface AIInsight {
  id: string
  type: 'anomaly' | 'forecast' | 'recommendation' | 'alert'
  title: string
  detail: string
  confidence: number
  substation?: string
  timestamp: string
  severity?: 'low' | 'medium' | 'high'
}

const MOCK_INSIGHTS: AIInsight[] = [
  {
    id: '1',
    type: 'anomaly',
    title: 'Residual loss spike detected',
    detail: 'MUM-WR substation shows 11.4% residual loss — 3.2σ above fleet baseline. Possible meter calibration drift or unauthorized tap-off.',
    confidence: 92,
    substation: 'WR-MUM',
    timestamp: '18:01:34',
    severity: 'high',
  },
  {
    id: '2',
    type: 'forecast',
    title: 'Peak demand forecast: +12%',
    detail: 'Load model predicts 842 MW peak tonight (21:00–23:00 IST). Current transformer headroom: 97 MW. Recommend dispatch alert at 19:30.',
    confidence: 87,
    timestamp: '18:00:15',
    severity: 'medium',
  },
  {
    id: '3',
    type: 'recommendation',
    title: 'Dispatch inspection — CHD-NR',
    detail: 'Persistent minor imbalance (2.1–2.8%) over 14 days. Physics engine flags possible distribution transformer ageing (IEC 60076-7 thermal model: 94% consumed life).',
    confidence: 78,
    substation: 'NR-CHD',
    timestamp: '17:58:44',
    severity: 'medium',
  },
  {
    id: '4',
    type: 'alert',
    title: 'Frequency excursion — 49.87 Hz',
    detail: 'Grid frequency dropped below 49.9 Hz for 3.2 s at 17:55 IST. Automatic UFLS relay blocked load shedding. Investigate generation shortfall.',
    confidence: 99,
    timestamp: '17:55:12',
    severity: 'high',
  },
  {
    id: '5',
    type: 'recommendation',
    title: 'GHI improvement opportunity',
    detail: 'Fleet average GHI can be raised from 72 → 81 by resolving 3 critical substations. Estimated annual energy savings: 1.4 GWh.',
    confidence: 65,
    timestamp: '17:50:00',
    severity: 'low',
  },
]

const TYPE_CFG = {
  anomaly:        { icon: '🔍', label: 'Anomaly',       color: '#FF4455' },
  forecast:       { icon: '📈', label: 'Forecast',      color: '#8B5CF6' },
  recommendation: { icon: '💡', label: 'Insight',       color: '#00D4FF' },
  alert:          { icon: '🚨', label: 'Alert',         color: '#FFB020' },
}

const SEVERITY_COLOR = {
  low:    'var(--cyan)',
  medium: 'var(--amber)',
  high:   'var(--red)',
}

interface TypingTextProps {
  text: string
  speed?: number
}

function TypingText({ text, speed = 18 }: TypingTextProps) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    setDisplayed('')
    setDone(false)
    let i = 0
    const id = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) { clearInterval(id); setDone(true) }
    }, speed)
    return () => clearInterval(id)
  }, [text, speed])

  return (
    <span>
      {displayed}
      {!done && <span className="typewriter-cursor" />}
    </span>
  )
}

/** Max confidence score reported */
const CONFIDENCE_MAX = 99
/** Weight of z-score in confidence calculation */
const Z_SCORE_CONFIDENCE_WEIGHT = 15
/** Base confidence before z-score contribution */
const CONFIDENCE_BASE = 40
/** Z-score threshold for 'high' severity classification */
const HIGH_SEVERITY_Z = 3

/** Build real AI insights from a live analysis session */
function buildInsightsFromSession(session: ReturnType<typeof useAppStore.getState>['activeSession']): AIInsight[] {
  if (!session) return []
  const insights: AIInsight[] = []
  const ts = new Date(session.createdAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const substation = session.substationId

  // Residual loss insight
  const residual = session.stats.residual_pct
  if (residual > 8) {
    insights.push({
      id: 'r1',
      type: 'alert',
      title: `High residual loss: ${residual.toFixed(1)}%`,
      detail: `${substation} shows ${residual.toFixed(1)}% residual loss — significantly above the 3% safe threshold. ${session.stats.anomalies_detected} anomalous readings detected. Possible cause: meter bypass, transformer fault, or cable losses.`,
      confidence: Math.round(session.stats.confidence_score),
      substation,
      timestamp: ts,
      severity: 'high',
    })
  } else if (residual > 3) {
    insights.push({
      id: 'r1',
      type: 'anomaly',
      title: `Moderate residual loss: ${residual.toFixed(1)}%`,
      detail: `${substation} shows ${residual.toFixed(1)}% residual loss — above the 3% monitoring threshold. Recommend scheduling an inspection to rule out meter drift or minor tapping.`,
      confidence: Math.round(session.stats.confidence_score),
      substation,
      timestamp: ts,
      severity: 'medium',
    })
  } else {
    insights.push({
      id: 'r1',
      type: 'forecast',
      title: `Healthy residual: ${residual.toFixed(1)}%`,
      detail: `${substation} is operating within safe parameters. Residual loss ${residual.toFixed(1)}% is below the 3% threshold. Physics engine confidence: ${session.stats.confidence_score.toFixed(0)}%.`,
      confidence: Math.round(session.stats.confidence_score),
      substation,
      timestamp: ts,
      severity: 'low',
    })
  }

  // Anomaly rate insight
  const anomalyRate = session.stats.anomaly_rate_pct
  if (anomalyRate > 5) {
    insights.push({
      id: 'a1',
      type: 'anomaly',
      title: `Anomaly rate: ${anomalyRate.toFixed(1)}%`,
      detail: `${session.stats.anomalies_detected} anomalous meter readings out of ${session.rowsParsed} parsed — a ${anomalyRate.toFixed(1)}% anomaly rate. Isolation Forest + Z-score detected unusual consumption spikes.`,
      confidence: Math.min(95, Math.round(anomalyRate * 4 + 60)),
      substation,
      timestamp: ts,
      severity: anomalyRate > 15 ? 'high' : 'medium',
    })
  }

  // Energy balance insight
  insights.push({
    id: 'e1',
    type: 'recommendation',
    title: `Energy throughput: ${session.stats.total_energy_kwh.toLocaleString(undefined, { maximumFractionDigits: 0 })} kWh`,
    detail: `Total energy recorded: ${session.stats.total_energy_kwh.toFixed(0)} kWh across ${session.rowsParsed} meter readings at ${substation}. Physics engine validated this batch with ${session.stats.confidence_score.toFixed(0)}% confidence.`,
    confidence: Math.round(session.stats.confidence_score),
    substation,
    timestamp: ts,
    severity: 'low',
  })

  // Sample anomaly if available
  if (session.anomalySample?.length > 0) {
    const top = session.anomalySample[0]
    insights.push({
      id: 'sa1',
      type: 'alert',
      title: `Top anomaly: meter ${top.meter_id}`,
      detail: `Meter ${top.meter_id} recorded ${top.energy_kwh.toFixed(2)} kWh vs expected ${top.expected_kwh.toFixed(2)} kWh (z-score: ${top.z_score?.toFixed(1) ?? 'N/A'}). Reason: ${top.reason}.`,
      confidence: Math.min(CONFIDENCE_MAX, Math.round(Math.abs(top.z_score ?? HIGH_SEVERITY_Z) * Z_SCORE_CONFIDENCE_WEIGHT + CONFIDENCE_BASE)),
      substation,
      timestamp: new Date(top.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      severity: Math.abs(top.z_score ?? 0) > HIGH_SEVERITY_Z ? 'high' : 'medium',
    })
  }

  // AI interpretation if available
  if (session.aiInterpretation) {
    const interp = session.aiInterpretation
    const summary: string = interp?.analysis?.summary ?? interp?.summary ?? ''
    if (summary) {
      insights.push({
        id: 'ai1',
        type: 'recommendation',
        title: 'AI interpretation ready',
        detail: summary.length > 200 ? summary.slice(0, 200) + '…' : summary,
        confidence: Math.round(session.stats.confidence_score),
        substation,
        timestamp: ts,
        severity: 'low',
      })
    }
  }

  return insights
}

export function AIAnalysisPanel() {
  const activeSession = useAppStore(s => s.activeSession)
  const [activeIdx, setActiveIdx] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<AIInsight['type'] | 'all'>('all')

  // Build insights from real data, fall back to mock
  const insights = useMemo(() => {
    const real = buildInsightsFromSession(activeSession)
    return real.length > 0 ? real : MOCK_INSIGHTS
  }, [activeSession])

  const isRealData = useMemo(() => {
    const real = buildInsightsFromSession(activeSession)
    return real.length > 0
  }, [activeSession])

  useEffect(() => {
    setIsLoading(true)
    const timer = setTimeout(() => {
      setIsLoading(false)
    }, 600)
    return () => clearTimeout(timer)
  }, [insights])

  // Reset active index on insights or filter change
  useEffect(() => { setActiveIdx(0) }, [insights, filter])

  // Auto-rotate active insight
  useEffect(() => {
    const id = setInterval(() => {
      setActiveIdx(i => (i + 1) % Math.max(1, insights.length))
    }, 7000)
    return () => clearInterval(id)
  }, [insights])

  const filtered = filter === 'all' ? insights : insights.filter(i => i.type === filter)
  const active   = filtered[activeIdx % Math.max(1, filtered.length)]

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, rgba(0,212,255,0.2) 0%, rgba(139,92,246,0.2) 100%)',
            border: '1px solid rgba(0,212,255,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16,
          }}>
            🧠
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', fontWeight: 600 }}>AI Analysis Engine</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 1 }}>
              {isRealData ? (
                <span style={{ color: 'var(--green)' }}>● Live data · {activeSession?.substationId}</span>
              ) : (
                'Demo · Upload data for live analysis'
              )}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {(['all', 'anomaly', 'forecast', 'alert', 'recommendation'] as const).map(t => (
            <button
              key={t}
              onClick={() => { setFilter(t); setActiveIdx(0) }}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 8.5,
                textTransform: 'capitalize', letterSpacing: '0.04em',
                padding: '3px 7px', borderRadius: 4,
                cursor: 'pointer',
                background: filter === t ? 'rgba(0,212,255,0.1)' : 'transparent',
                border: `1px solid ${filter === t ? 'var(--cyan)' : 'var(--border-subtle)'}`,
                color: filter === t ? 'var(--cyan)' : 'var(--text-tertiary)',
                transition: 'all 0.15s ease',
              }}
            >
              {t === 'all' ? 'All' : TYPE_CFG[t].icon + ' ' + TYPE_CFG[t].label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[80, 60, 90].map((w, i) => (
            <div key={i} style={{ height: 14, background: 'var(--bg-elevated)', borderRadius: 4, width: `${w}%`, animation: 'pulse-dot 1.5s ease-in-out infinite' }} />
          ))}
        </div>
      ) : (
        <>
          {/* Active insight card */}
          {active && (
            <AnimatePresence mode="wait">
              <motion.div
                key={active.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.3 }}
                className="glass"
                style={{
                  padding: '14px 16px',
                  borderColor: TYPE_CFG[active.type].color + '33',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 18 }}>{TYPE_CFG[active.type].icon}</span>
                    <div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', fontWeight: 600 }}>
                        {active.title}
                      </div>
                      {active.substation && (
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--cyan)', marginTop: 1 }}>
                          📍 {active.substation}
                        </div>
                      )}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: TYPE_CFG[active.type].color, fontWeight: 300 }}>
                      {active.confidence}%
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)', textTransform: 'uppercase' }}>confidence</div>
                  </div>
                </div>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  <TypingText text={active.detail} speed={12} />
                </p>
                {/* Confidence bar */}
                <div style={{ height: 2, background: 'var(--border-subtle)', borderRadius: 1, marginTop: 10, overflow: 'hidden' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${active.confidence}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    style={{ height: '100%', background: TYPE_CFG[active.type].color, borderRadius: 1 }}
                  />
                </div>
              </motion.div>
            </AnimatePresence>
          )}

          {/* Insight list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {filtered.map((insight, i) => {
              const cfg = TYPE_CFG[insight.type]
              const isActive = insight.id === active?.id
              return (
                <button
                  key={insight.id}
                  onClick={() => setActiveIdx(i)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '8px 10px', borderRadius: 6,
                    background: isActive ? cfg.color + '11' : 'transparent',
                    border: `1px solid ${isActive ? cfg.color + '44' : 'transparent'}`,
                    cursor: 'pointer', textAlign: 'left', width: '100%',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 14, flexShrink: 0 }}>{cfg.icon}</span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{
                        fontFamily: 'var(--font-mono)', fontSize: 11,
                        color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {insight.title}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--text-dim)', marginTop: 1 }}>
                        {insight.timestamp}
                        {insight.substation && ` · ${insight.substation}`}
                      </div>
                    </div>
                  </div>
                  <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6, marginLeft: 8 }}>
                    {insight.severity && (
                      <span style={{
                        width: 6, height: 6, borderRadius: '50%',
                        background: SEVERITY_COLOR[insight.severity],
                        flexShrink: 0,
                      }} />
                    )}
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: cfg.color }}>
                      {insight.confidence}%
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

