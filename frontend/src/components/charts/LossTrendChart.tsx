'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend,
} from 'recharts'

interface LossTrendPoint {
  ts: string
  residual_pct: number
  confidence: number
  substation: string
}

interface LossTrendChartProps {
  data: LossTrendPoint[]
}

function formatDate(ts: string): string {
  try {
    return new Date(ts).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  } catch {
    return ts
  }
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-md)',
        padding: '10px 14px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-primary)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
      }}
    >
      <p style={{ color: 'var(--text-secondary)', marginBottom: 6 }}>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color, margin: '2px 0' }}>
          {entry.name}: {Number(entry.value).toFixed(2)}
          {entry.dataKey === 'residual_pct' ? '%' : ''}
        </p>
      ))}
    </div>
  )
}

export function LossTrendChart({ data }: LossTrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        style={{
          height: 260,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
        }}
      >
        No trend data available
      </div>
    )
  }

  const chartData = data.map((d) => ({
    ...d,
    date: formatDate(d.ts),
    confidenceBand: d.confidence * 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#00D4FF" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#00D4FF" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#FFB020" stopOpacity={0.18} />
            <stop offset="95%" stopColor="#FFB020" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#8DA0C0', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
        />
        <YAxis
          yAxisId="loss"
          tick={{ fill: '#8DA0C0', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => `${v}%`}
        />
        <YAxis
          yAxisId="conf"
          orientation="right"
          tick={{ fill: '#8DA0C0', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          domain={[0, 100]}
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-secondary)',
          }}
        />
        <Area
          yAxisId="loss"
          type="monotone"
          dataKey="residual_pct"
          name="Loss %"
          stroke="#00D4FF"
          strokeWidth={2}
          fill="url(#lossGrad)"
          dot={false}
          activeDot={{ r: 4, fill: '#00D4FF' }}
        />
        <Area
          yAxisId="conf"
          type="monotone"
          dataKey="confidenceBand"
          name="Confidence %"
          stroke="#FFB020"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          fill="url(#confGrad)"
          dot={false}
          activeDot={{ r: 3, fill: '#FFB020' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
