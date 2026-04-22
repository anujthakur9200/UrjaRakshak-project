'use client'

import { useState } from 'react'

interface HeatmapPoint {
  substation: string
  hour: number
  confidence: number
}

interface ConfidenceHeatmapProps {
  data: HeatmapPoint[]
}

function confidenceColor(value: number): string {
  // 0 = red, 0.5 = amber, 1 = green
  if (value >= 0.85) return '#00E096'
  if (value >= 0.70) return '#3B82F6'
  if (value >= 0.55) return '#FFB020'
  if (value >= 0.40) return '#FF8C20'
  return '#FF4455'
}

function confidenceLabel(value: number): string {
  if (value >= 0.85) return 'High'
  if (value >= 0.70) return 'Good'
  if (value >= 0.55) return 'Fair'
  if (value >= 0.40) return 'Low'
  return 'Poor'
}

interface TooltipState {
  x: number
  y: number
  point: HeatmapPoint
}

export function ConfidenceHeatmap({ data }: ConfidenceHeatmapProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)

  if (!data || data.length === 0) {
    return (
      <div
        style={{
          height: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
        }}
      >
        No heatmap data available
      </div>
    )
  }

  const substations = Array.from(new Set(data.map((d) => d.substation))).sort()
  const hours = Array.from({ length: 24 }, (_, i) => i)

  const lookup = new Map(data.map((d) => [`${d.substation}|${d.hour}`, d.confidence]))

  const CELL_W = 22
  const CELL_H = 22
  const LABEL_W = 90
  const HEADER_H = 24
  const GAP = 2

  const svgW = LABEL_W + hours.length * (CELL_W + GAP)
  const svgH = HEADER_H + substations.length * (CELL_H + GAP) + 24

  return (
    <div style={{ position: 'relative', overflowX: 'auto' }}>
      <svg
        width={svgW}
        height={svgH}
        style={{ fontFamily: 'var(--font-mono)', display: 'block' }}
      >
        {/* Hour labels */}
        {hours.map((h) => (
          <text
            key={h}
            x={LABEL_W + h * (CELL_W + GAP) + CELL_W / 2}
            y={HEADER_H - 6}
            textAnchor="middle"
            fontSize={8}
            fill="#4E6080"
          >
            {h % 6 === 0 ? `${h}h` : ''}
          </text>
        ))}

        {/* Substation rows */}
        {substations.map((sub, si) => (
          <g key={sub}>
            {/* Row label */}
            <text
              x={LABEL_W - 6}
              y={HEADER_H + si * (CELL_H + GAP) + CELL_H / 2 + 4}
              textAnchor="end"
              fontSize={9}
              fill="#8DA0C0"
            >
              {sub.length > 10 ? sub.slice(0, 10) + '…' : sub}
            </text>

            {/* Cells */}
            {hours.map((h) => {
              const conf = lookup.get(`${sub}|${h}`) ?? null
              const cx = LABEL_W + h * (CELL_W + GAP)
              const cy = HEADER_H + si * (CELL_H + GAP)

              return (
                <rect
                  key={h}
                  x={cx}
                  y={cy}
                  width={CELL_W}
                  height={CELL_H}
                  rx={3}
                  fill={conf !== null ? confidenceColor(conf) : '#0A1020'}
                  opacity={conf !== null ? 0.85 : 0.3}
                  style={{ cursor: conf !== null ? 'pointer' : 'default' }}
                  onMouseEnter={(e) => {
                    if (conf === null) return
                    const rect = (e.currentTarget as SVGRectElement)
                      .closest('svg')!
                      .getBoundingClientRect()
                    setTooltip({
                      x: e.clientX - rect.left + 10,
                      y: e.clientY - rect.top - 10,
                      point: { substation: sub, hour: h, confidence: conf },
                    })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })}
          </g>
        ))}

        {/* Colour legend */}
        {(['Poor', 'Low', 'Fair', 'Good', 'High'] as const).map((label, i) => {
          const colors = ['#FF4455', '#FF8C20', '#FFB020', '#3B82F6', '#00E096']
          const lx = LABEL_W + i * 90
          const ly = svgH - 12
          return (
            <g key={label}>
              <rect x={lx} y={ly - 10} width={12} height={10} rx={2} fill={colors[i]} opacity={0.85} />
              <text x={lx + 15} y={ly} fontSize={9} fill="#4E6080">
                {label}
              </text>
            </g>
          )
        })}
      </svg>

      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: tooltip.x,
            top: tooltip.y,
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-md)',
            padding: '7px 11px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text-primary)',
            pointerEvents: 'none',
            zIndex: 20,
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            whiteSpace: 'nowrap',
          }}
        >
          <p style={{ color: 'var(--text-secondary)', marginBottom: 3 }}>
            {tooltip.point.substation} — {tooltip.point.hour}:00
          </p>
          <p style={{ color: confidenceColor(tooltip.point.confidence), fontWeight: 600 }}>
            {confidenceLabel(tooltip.point.confidence)} — {(tooltip.point.confidence * 100).toFixed(1)}%
          </p>
        </div>
      )}
    </div>
  )
}
