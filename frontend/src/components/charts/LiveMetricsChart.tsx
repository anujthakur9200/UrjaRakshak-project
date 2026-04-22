'use client'

import { useEffect, useState, useRef } from 'react'
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { motion } from 'framer-motion'

interface MetricPoint {
  t: string
  voltage: number
  frequency: number
  load: number
  loss: number
}

function makePoint(i: number, prev?: MetricPoint): MetricPoint {
  const freq  = prev ? clamp(prev.frequency + (Math.random() - 0.5) * 0.04, 49.8, 50.2) : 50.0
  const volt  = prev ? clamp(prev.voltage   + (Math.random() - 0.5) * 1.5,  227,  233)   : 230
  const load  = prev ? clamp(prev.load      + (Math.random() - 0.5) * 20,   400,  900)   : 650
  const loss  = +(Math.random() * 4 + 1).toFixed(2)
  const now   = new Date(Date.now() - (29 - i) * 5000)
  return {
    t:         now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    voltage:   +volt.toFixed(1),
    frequency: +freq.toFixed(3),
    load:      +load.toFixed(0),
    loss,
  }
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

const HISTORY = 30

interface LiveMetricsChartProps {
  title?: string
  /** Which metric to show on the primary chart: 'voltage' | 'frequency' | 'load' | 'loss' */
  metric?: 'voltage' | 'frequency' | 'load' | 'loss'
}

const METRIC_CFG = {
  voltage:   { label: 'Voltage',    unit: 'V',   color: '#00D4FF', ref: 230,   domain: [226, 234]  as [number,number] },
  frequency: { label: 'Frequency',  unit: 'Hz',  color: '#00E096', ref: 50,    domain: [49.7, 50.3] as [number,number] },
  load:      { label: 'Load',       unit: 'MW',  color: '#8B5CF6', ref: 650,   domain: [350, 950]  as [number,number] },
  loss:      { label: 'Loss',       unit: '%',   color: '#FFB020', ref: 3,     domain: [0, 8]      as [number,number] },
}

export function LiveMetricsChart({ title, metric = 'load' }: LiveMetricsChartProps) {
  const [data, setData] = useState<MetricPoint[]>([])
  const [activeMetric, setActiveMetric] = useState(metric)
  const lastRef = useRef<MetricPoint | undefined>(undefined)

  useEffect(() => {
    const initial: MetricPoint[] = []
    for (let i = 0; i < HISTORY; i++) {
      const p = makePoint(i, initial[i - 1])
      initial.push(p)
    }
    setData(initial)
    lastRef.current = initial[initial.length - 1]
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      const next = makePoint(HISTORY - 1, lastRef.current)
      lastRef.current = next
      setData(prev => [...prev.slice(1), next])
    }, 2000)
    return () => clearInterval(id)
  }, [])

  const cfg = METRIC_CFG[activeMetric]
  const latest = data[data.length - 1]

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
            {title || 'Live Metrics'}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 300, color: cfg.color, letterSpacing: '-0.02em' }}>
              {latest ? latest[activeMetric] : '—'}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>{cfg.unit}</span>
            <motion.span
              key={latest?.[activeMetric]}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: 'var(--green)', marginLeft: 4,
              }}
            >
              LIVE
            </motion.span>
          </div>
        </div>

        {/* Metric selector */}
        <div style={{ display: 'flex', gap: 4 }}>
          {(Object.keys(METRIC_CFG) as (keyof typeof METRIC_CFG)[]).map(m => (
            <button
              key={m}
              onClick={() => setActiveMetric(m)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.06em',
                textTransform: 'uppercase',
                padding: '4px 8px', borderRadius: 4, cursor: 'pointer',
                background: activeMetric === m ? METRIC_CFG[m].color + '22' : 'transparent',
                border: `1px solid ${activeMetric === m ? METRIC_CFG[m].color : 'var(--border-dim)'}`,
                color: activeMetric === m ? METRIC_CFG[m].color : 'var(--text-tertiary)',
                transition: 'all 0.15s ease',
              }}
            >
              {METRIC_CFG[m].label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div style={{ height: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id={`grad-${activeMetric}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={cfg.color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={cfg.color} stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,180,255,0.06)" />
            <XAxis
              dataKey="t"
              tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }}
              tickLine={false}
              axisLine={false}
              interval={5}
            />
            <YAxis
              domain={cfg.domain}
              tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-dim)' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-elevated)',
                border: `1px solid ${cfg.color}33`,
                borderRadius: 8,
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--text-primary)',
              }}
              formatter={(v: number) => [`${v} ${cfg.unit}`, cfg.label]}
              labelStyle={{ color: 'var(--text-tertiary)', fontSize: 9 }}
            />
            <ReferenceLine y={cfg.ref} stroke={cfg.color} strokeDasharray="4 4" strokeOpacity={0.35} />
            <Area
              type="monotone"
              dataKey={activeMetric}
              stroke={cfg.color}
              strokeWidth={2}
              fill={`url(#grad-${activeMetric})`}
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Mini stats row */}
      <div style={{ display: 'flex', gap: 16, borderTop: '1px solid var(--border-ghost)', paddingTop: 10 }}>
        {(['voltage', 'frequency', 'load', 'loss'] as const).map(m => {
          const c = METRIC_CFG[m]
          return (
            <div key={m} style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>{c.label}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: c.color }}>
                {latest ? latest[m] : '—'} <span style={{ fontSize: 9, color: 'var(--text-dim)' }}>{c.unit}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
