'use client'

import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'

export interface GridNode {
  id: string
  label: string
  health: 'healthy' | 'warning' | 'critical'
  load: number
}

export interface GridEdge {
  source: string
  target: string
  flow: number
}

interface AnimatedGridMapProps {
  nodes: GridNode[]
  edges: GridEdge[]
}

const HEALTH_COLOR: Record<GridNode['health'], string> = {
  healthy: '#00E096',
  warning: '#FFB020',
  critical: '#FF4455',
}

const HEALTH_GLOW: Record<GridNode['health'], string> = {
  healthy: 'rgba(0,224,150,0.35)',
  warning: 'rgba(255,176,32,0.35)',
  critical: 'rgba(255,68,85,0.35)',
}

interface D3Node extends d3.SimulationNodeDatum, GridNode {}
interface D3Edge extends d3.SimulationLinkDatum<D3Node> {
  flow: number
  _source?: D3Node
  _target?: D3Node
}

interface TooltipState {
  x: number
  y: number
  node: GridNode
}

export function AnimatedGridMap({ nodes, edges }: AnimatedGridMapProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return

    const container = containerRef.current
    const width = container.clientWidth || 600
    const height = container.clientHeight || 400

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    svg.attr('width', width).attr('height', height)

    // Defs: glow filters + gradients
    const defs = svg.append('defs')

    nodes.forEach((n) => {
      const color = HEALTH_COLOR[n.health]
      const filter = defs.append('filter').attr('id', `glow-${n.id}`)
      filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur')
      const merge = filter.append('feMerge')
      merge.append('feMergeNode').attr('in', 'blur')
      merge.append('feMergeNode').attr('in', 'SourceGraphic')

      const grad = defs
        .append('radialGradient')
        .attr('id', `node-grad-${n.id}`)
        .attr('cx', '40%')
        .attr('cy', '35%')
      grad.append('stop').attr('offset', '0%').attr('stop-color', '#fff').attr('stop-opacity', 0.25)
      grad.append('stop').attr('offset', '100%').attr('stop-color', color).attr('stop-opacity', 1)
    })

    const linkGroup = svg.append('g').attr('class', 'links')
    const particleGroup = svg.append('g').attr('class', 'particles')
    const nodeGroup = svg.append('g').attr('class', 'nodes')

    // Simulation data (deep copy to avoid mutation)
    const simNodes: D3Node[] = nodes.map((n) => ({ ...n }))
    const nodeMap = new Map(simNodes.map((n) => [n.id, n]))

    const simEdges: D3Edge[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: nodeMap.get(e.source)!,
        target: nodeMap.get(e.target)!,
        flow: e.flow,
      }))

    const simulation = d3
      .forceSimulation<D3Node>(simNodes)
      .force('link', d3.forceLink<D3Node, D3Edge>(simEdges).id((d) => d.id).distance(120).strength(0.6))
      .force('charge', d3.forceManyBody<D3Node>().strength(-280))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<D3Node>(36))
      .alphaDecay(0.03)

    // Draw edges
    const linkLines = linkGroup
      .selectAll<SVGLineElement, D3Edge>('line')
      .data(simEdges)
      .join('line')
      .attr('stroke', 'rgba(0,212,255,0.18)')
      .attr('stroke-width', (d) => Math.max(1, Math.min(d.flow / 20, 4)))
      .attr('stroke-dasharray', '4 4')

    // Animated dashes on edges
    let dashOffset = 0
    function animateDashes() {
      dashOffset -= 0.5
      linkLines.attr('stroke-dashoffset', dashOffset)
      rafRef.current = requestAnimationFrame(animateDashes)
    }
    rafRef.current = requestAnimationFrame(animateDashes)

    // Particle state per edge
    interface Particle {
      edgeIndex: number
      t: number       // progress 0→1
      speed: number
    }
    const particles: Particle[] = simEdges.flatMap((_, i) => [
      { edgeIndex: i, t: 0, speed: 0.004 + Math.random() * 0.004 },
      { edgeIndex: i, t: 0.5, speed: 0.004 + Math.random() * 0.004 },
    ])

    const particleDots = particleGroup
      .selectAll<SVGCircleElement, Particle>('circle')
      .data(particles)
      .join('circle')
      .attr('r', 2.5)
      .attr('fill', '#00D4FF')
      .attr('opacity', 0.75)

    // Draw nodes
    const nodeGs = nodeGroup
      .selectAll<SVGGElement, D3Node>('g')
      .data(simNodes)
      .join('g')
      .attr('class', 'node')
      .style('cursor', 'pointer')

    // Outer pulse ring
    nodeGs
      .append('circle')
      .attr('r', 20)
      .attr('fill', 'none')
      .attr('stroke', (d) => HEALTH_GLOW[d.health])
      .attr('stroke-width', 1.5)
      .attr('class', 'pulse-ring')

    // Main node circle
    nodeGs
      .append('circle')
      .attr('r', 14)
      .attr('fill', (d) => `url(#node-grad-${d.id})`)
      .attr('stroke', (d) => HEALTH_COLOR[d.health])
      .attr('stroke-width', 1.5)
      .attr('filter', (d) => `url(#glow-${d.id})`)

    // Node label
    nodeGs
      .append('text')
      .text((d) => d.label)
      .attr('dy', 28)
      .attr('text-anchor', 'middle')
      .attr('fill', '#8DA0C0')
      .attr('font-size', 10)
      .attr('font-family', 'var(--font-mono)')
      .style('pointer-events', 'none')

    // Pulse animation via CSS on SVG
    const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
    style.textContent = `
      @keyframes pulse-ring {
        0%   { r: 16; opacity: 0.8; }
        100% { r: 26; opacity: 0; }
      }
      .pulse-ring { animation: pulse-ring 2s ease-out infinite; }
      .node:hover .pulse-ring { animation-duration: 1s; }
    `
    svg.append(() => style)

    // Hover tooltip
    nodeGs
      .on('mouseenter', function (event: MouseEvent, d: D3Node) {
        const rect = svgRef.current!.getBoundingClientRect()
        setTooltip({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
          node: d,
        })
        d3.select(this).select<SVGCircleElement>('circle:nth-child(2)').attr('r', 17)
      })
      .on('mousemove', function (event: MouseEvent) {
        const rect = svgRef.current!.getBoundingClientRect()
        setTooltip((prev) => prev ? { ...prev, x: event.clientX - rect.left, y: event.clientY - rect.top } : null)
      })
      .on('mouseleave', function (_event: MouseEvent, _d: D3Node) {
        setTooltip(null)
        d3.select(this).select<SVGCircleElement>('circle:nth-child(2)').attr('r', 14)
      })

    // Drag behaviour
    const drag = d3
      .drag<SVGGElement, D3Node>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    nodeGs.call(drag)

    // Tick: update positions
    simulation.on('tick', () => {
      linkLines
        .attr('x1', (d) => (d.source as D3Node).x!)
        .attr('y1', (d) => (d.source as D3Node).y!)
        .attr('x2', (d) => (d.target as D3Node).x!)
        .attr('y2', (d) => (d.target as D3Node).y!)

      // Move particles along edges (advance once per tick)
      particles.forEach((p) => {
        p.t = (p.t + p.speed) % 1
      })

      particleDots
        .attr('cx', (p) => {
          const edge = simEdges[p.edgeIndex]
          if (!edge) return 0
          const s = edge.source as D3Node
          const t = edge.target as D3Node
          return (s.x ?? 0) + ((t.x ?? 0) - (s.x ?? 0)) * p.t
        })
        .attr('cy', (p) => {
          const edge = simEdges[p.edgeIndex]
          if (!edge) return 0
          const s = edge.source as D3Node
          const t = edge.target as D3Node
          return (s.y ?? 0) + ((t.y ?? 0) - (s.y ?? 0)) * p.t
        })

      nodeGs.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => {
      simulation.stop()
      cancelAnimationFrame(rafRef.current)
    }
  }, [nodes, edges])

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', width: '100%', height: 400, background: 'var(--bg-panel)', borderRadius: 'var(--r-lg)' }}
    >
      <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />

      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: tooltip.x + 14,
            top: tooltip.y - 10,
            background: 'var(--bg-elevated)',
            border: `1px solid ${HEALTH_COLOR[tooltip.node.health]}`,
            borderRadius: 'var(--r-md)',
            padding: '8px 12px',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-primary)',
            pointerEvents: 'none',
            zIndex: 10,
            boxShadow: `0 0 16px ${HEALTH_GLOW[tooltip.node.health]}`,
            minWidth: 140,
          }}
        >
          <p style={{ fontWeight: 600, marginBottom: 4 }}>{tooltip.node.label}</p>
          <p style={{ color: HEALTH_COLOR[tooltip.node.health], textTransform: 'capitalize' }}>
            ● {tooltip.node.health}
          </p>
          <p style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
            Load: {tooltip.node.load.toFixed(1)} MW
          </p>
        </div>
      )}
    </div>
  )
}
