'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from 'recharts'

interface LossBreakdownItem {
  name: string
  loss_pct: number
  color: string
}

interface LossBreakdownChartProps {
  data: LossBreakdownItem[]
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-md)',
        padding: '8px 12px',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-primary)',
        boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
      }}
    >
      <p style={{ color: d.fill, fontWeight: 600 }}>{d.payload.name}</p>
      <p style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
        Loss: {Number(d.value).toFixed(2)}%
      </p>
    </div>
  )
}

export function LossBreakdownChart({ data }: LossBreakdownChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        style={{
          height: 220,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
        }}
      >
        No breakdown data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 56, bottom: 4, left: 8 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          horizontal={false}
          stroke="rgba(255,255,255,0.04)"
        />
        <XAxis
          type="number"
          tick={{ fill: '#8DA0C0', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickLine={false}
          tickFormatter={(v) => `${v}%`}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={110}
          tick={{ fill: '#8DA0C0', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
        <Bar dataKey="loss_pct" radius={[0, 4, 4, 0]} maxBarSize={24}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
          <LabelList
            dataKey="loss_pct"
            position="right"
            formatter={(v: number) => `${Number(v).toFixed(1)}%`}
            style={{
              fill: '#8DA0C0',
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
            }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
