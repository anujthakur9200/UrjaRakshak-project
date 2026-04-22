'use client'

import { useEffect, useRef } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'

interface MetricCardProps {
  label: string
  value: number
  unit?: string
  delta?: number
  deltaType?: 'up' | 'down' | 'neutral'
  color?: string
  icon?: React.ReactNode
}

function AnimatedValue({ value, decimals = 1 }: { value: number; decimals?: number }) {
  const motionVal = useMotionValue(0)
  const spring = useSpring(motionVal, { stiffness: 60, damping: 18 })
  const display = useTransform(spring, (v) => v.toFixed(decimals))

  const prevRef = useRef<number>(0)
  useEffect(() => {
    motionVal.set(prevRef.current)
    motionVal.set(value)
    prevRef.current = value
  }, [value, motionVal])

  return <motion.span>{display}</motion.span>
}

export function MetricCard({
  label,
  value,
  unit,
  delta,
  deltaType = 'neutral',
  color = 'var(--cyan)',
  icon,
}: MetricCardProps) {
  const deltaColor =
    deltaType === 'up'
      ? 'var(--green)'
      : deltaType === 'down'
      ? 'var(--red)'
      : 'var(--text-tertiary)'

  const deltaArrow = deltaType === 'up' ? '↑' : deltaType === 'down' ? '↓' : '—'

  const decimals = value % 1 !== 0 ? 2 : 0

  return (
    <div className="metric-card" style={{ borderColor: `${color}22` }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <span className="metric-label">{label}</span>
        {icon && (
          <span style={{ color, opacity: 0.75, fontSize: 18, lineHeight: 1 }}>{icon}</span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span className="metric-value" style={{ color }}>
          <AnimatedValue value={value} decimals={decimals} />
        </span>
        {unit && (
          <span
            style={{
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
            }}
          >
            {unit}
          </span>
        )}
      </div>

      {delta !== undefined && (
        <div
          style={{
            marginTop: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: deltaColor,
          }}
        >
          <span>{deltaArrow}</span>
          <span>
            {delta > 0 ? '+' : ''}
            {delta.toFixed(2)}
            {unit}
          </span>
          <span style={{ color: 'var(--text-tertiary)', marginLeft: 2 }}>vs last</span>
        </div>
      )}
    </div>
  )
}
