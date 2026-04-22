'use client'

import { useMemo } from 'react'

interface LossBreakdown {
  transmission: number
  distribution: number
  other: number
}

interface EnergyFlowSankeyProps {
  inputMwh: number
  outputMwh: number
  lossBreakdown: LossBreakdown
}

interface SankeyNode {
  id: string
  label: string
  x: number
  y: number
  height: number
  color: string
}

interface SankeyFlow {
  from: string
  to: string
  value: number
  color: string
}

const W = 560
const H = 300
const NODE_W = 18
const PADDING = 40

export function EnergyFlowSankey({ inputMwh, outputMwh, lossBreakdown }: EnergyFlowSankeyProps) {
  const totalLoss = lossBreakdown.transmission + lossBreakdown.distribution + lossBreakdown.other
  const consumptionMwh = outputMwh
  const lossMwh = inputMwh - consumptionMwh

  const { nodes, flows } = useMemo(() => {
    // Proportional heights mapped to available canvas space
    const usable = H - PADDING * 2
    const scale = usable / inputMwh

    const genH = inputMwh * scale
    const transH = inputMwh * scale
    const distH = (inputMwh - lossBreakdown.transmission) * scale
    const consH = consumptionMwh * scale

    const transLossH = lossBreakdown.transmission * scale
    const distLossH = lossBreakdown.distribution * scale
    const otherLossH = lossBreakdown.other * scale

    const colX = [40, 158, 278, 396, 500]

    const nodes: SankeyNode[] = [
      { id: 'gen',   label: 'Generation',    x: colX[0], y: PADDING, height: genH,   color: '#00E096' },
      { id: 'trans', label: 'Transmission',  x: colX[1], y: PADDING, height: transH, color: '#00D4FF' },
      { id: 'dist',  label: 'Distribution',  x: colX[2], y: PADDING, height: distH,  color: '#3B82F6' },
      { id: 'cons',  label: 'Consumption',   x: colX[3], y: PADDING, height: consH,  color: '#00E096' },
      {
        id: 'loss_trans', label: 'Trans. Loss',
        x: colX[4], y: PADDING,
        height: Math.max(transLossH, 4),
        color: '#FF4455',
      },
      {
        id: 'loss_dist', label: 'Dist. Loss',
        x: colX[4], y: PADDING + transLossH + 6,
        height: Math.max(distLossH, 4),
        color: '#FFB020',
      },
      {
        id: 'loss_other', label: 'Other Loss',
        x: colX[4], y: PADDING + transLossH + distLossH + 12,
        height: Math.max(otherLossH, 4),
        color: '#8B5CF6',
      },
    ]

    const flows: SankeyFlow[] = [
      { from: 'gen',   to: 'trans', value: inputMwh,                               color: '#00D4FF' },
      { from: 'trans', to: 'dist',  value: inputMwh - lossBreakdown.transmission,  color: '#3B82F6' },
      { from: 'dist',  to: 'cons',  value: consumptionMwh,                         color: '#00E096' },
      { from: 'trans', to: 'loss_trans', value: lossBreakdown.transmission,        color: '#FF4455' },
      { from: 'dist',  to: 'loss_dist',  value: lossBreakdown.distribution,        color: '#FFB020' },
      { from: 'dist',  to: 'loss_other', value: lossBreakdown.other,               color: '#8B5CF6' },
    ]

    return { nodes, flows }
  }, [inputMwh, outputMwh, consumptionMwh, lossBreakdown])

  function nodeById(id: string) {
    return nodes.find((n) => n.id === id)!
  }

  function buildPath(flow: SankeyFlow): string {
    const src = nodeById(flow.from)
    const dst = nodeById(flow.to)
    if (!src || !dst) return ''

    const scale = (H - PADDING * 2) / inputMwh
    const bandH = Math.max(flow.value * scale, 2)

    const x0 = src.x + NODE_W
    const x1 = dst.x
    const mx = (x0 + x1) / 2

    // Vertically center band within each node
    const srcMid = src.y + src.height / 2
    const dstMid = dst.y + dst.height / 2

    const y0t = srcMid - bandH / 2
    const y0b = srcMid + bandH / 2
    const y1t = dstMid - bandH / 2
    const y1b = dstMid + bandH / 2

    return `M ${x0} ${y0t} C ${mx} ${y0t}, ${mx} ${y1t}, ${x1} ${y1t}
            L ${x1} ${y1b} C ${mx} ${y1b}, ${mx} ${y0b}, ${x0} ${y0b} Z`
  }

  const lossTotal = lossMwh > 0 ? ((lossMwh / inputMwh) * 100).toFixed(1) : '0.0'
  const efficiency = inputMwh > 0 ? ((consumptionMwh / inputMwh) * 100).toFixed(1) : '0.0'

  return (
    <div style={{ width: '100%' }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', overflow: 'visible' }}
        aria-label="Energy flow Sankey diagram"
      >
        <defs>
          {flows.map((f, i) => (
            <linearGradient key={i} id={`flow-grad-${i}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={f.color} stopOpacity={0.55} />
              <stop offset="100%" stopColor={f.color} stopOpacity={0.25} />
            </linearGradient>
          ))}
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Flow paths */}
        {flows.map((f, i) => (
          <path
            key={i}
            d={buildPath(f)}
            fill={`url(#flow-grad-${i})`}
            stroke={f.color}
            strokeWidth={0.5}
            strokeOpacity={0.4}
          />
        ))}

        {/* Nodes */}
        {nodes.map((n) => (
          <g key={n.id} filter="url(#glow)">
            <rect
              x={n.x}
              y={n.y}
              width={NODE_W}
              height={Math.max(n.height, 4)}
              rx={3}
              fill={n.color}
              opacity={0.9}
            />
          </g>
        ))}

        {/* Node labels */}
        {nodes.map((n) => {
          const isRight = n.x >= 480
          return (
            <text
              key={`lbl-${n.id}`}
              x={isRight ? n.x + NODE_W + 4 : n.x + NODE_W / 2}
              y={n.y - 6}
              textAnchor={isRight ? 'start' : 'middle'}
              fill="#8DA0C0"
              fontSize={9}
              fontFamily="var(--font-mono)"
            >
              {n.label}
            </text>
          )
        })}

        {/* Summary labels */}
        <text x={W / 2} y={H - 4} textAnchor="middle" fill="#4E6080" fontSize={10} fontFamily="var(--font-mono)">
          Efficiency: {efficiency}%  •  Total Loss: {lossTotal}%  •  Input: {inputMwh.toLocaleString()} MWh
        </text>
      </svg>
    </div>
  )
}
