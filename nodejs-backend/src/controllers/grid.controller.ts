import { Request, Response } from 'express'
import { cacheService } from '../services/cache.service'
import { pythonService } from '../services/python.service'
import logger from '../utils/logger'

interface Substation {
  id: string
  name: string
  lat: number
  lng: number
  capacity: number
  load: number
  status: 'online' | 'offline' | 'warning'
  connections: string[]
}

interface Region {
  id: string
  name: string
  totalCapacityMw: number
  currentLoadMw: number
  renewablePercent: number
  substationIds: string[]
}

const SUBSTATIONS: Substation[] = [
  { id: 'SS-001', name: 'Delhi North Grid', lat: 28.71, lng: 77.1, capacity: 500, load: 320, status: 'online', connections: ['SS-002', 'SS-003'] },
  { id: 'SS-002', name: 'Delhi South Grid', lat: 28.52, lng: 77.2, capacity: 400, load: 290, status: 'online', connections: ['SS-001', 'SS-004'] },
  { id: 'SS-003', name: 'Noida Sector Grid', lat: 28.54, lng: 77.39, capacity: 300, load: 180, status: 'warning', connections: ['SS-001', 'SS-005'] },
  { id: 'SS-004', name: 'Gurugram Grid', lat: 28.46, lng: 77.03, capacity: 350, load: 200, status: 'online', connections: ['SS-002'] },
  { id: 'SS-005', name: 'Faridabad Grid', lat: 28.41, lng: 77.31, capacity: 280, load: 160, status: 'online', connections: ['SS-003'] },
]

const REGIONS: Region[] = [
  { id: 'R-001', name: 'North Delhi', totalCapacityMw: 900, currentLoadMw: 610, renewablePercent: 22, substationIds: ['SS-001', 'SS-003'] },
  { id: 'R-002', name: 'South Delhi & NCR', totalCapacityMw: 1030, currentLoadMw: 650, renewablePercent: 18, substationIds: ['SS-002', 'SS-004', 'SS-005'] },
]

export async function getTopology(_req: Request, res: Response): Promise<void> {
  const cacheKey = 'grid:topology'
  const cached = await cacheService.get(cacheKey)
  if (cached) {
    res.json({ success: true, data: cached })
    return
  }

  const data = {
    substations: SUBSTATIONS,
    connections: SUBSTATIONS.flatMap((s) =>
      s.connections.map((target) => ({ source: s.id, target }))
    ),
    lastUpdated: new Date().toISOString(),
  }

  await cacheService.set(cacheKey, data, 30)
  res.json({ success: true, data })
}

export async function getLiveMetrics(_req: Request, res: Response): Promise<void> {
  try {
    const pythonData = await pythonService.get<Record<string, unknown>>('/metrics/live')
    res.json({ success: true, data: pythonData })
    return
  } catch {
    logger.debug('Python backend unavailable — returning mock live metrics')
  }

  const metrics = SUBSTATIONS.map((s) => ({
    substationId: s.id,
    name: s.name,
    energyKwh: +(Math.random() * 1000 + 200).toFixed(2),
    voltageKv: +(Math.random() * 10 + 220).toFixed(2),
    currentA: +(Math.random() * 50 + 100).toFixed(2),
    powerFactorPct: +(Math.random() * 5 + 92).toFixed(2),
    isAnomaly: Math.random() < 0.05,
    timestamp: new Date().toISOString(),
  }))

  res.json({ success: true, data: metrics })
}

export async function getRegions(_req: Request, res: Response): Promise<void> {
  const cacheKey = 'grid:regions'
  const cached = await cacheService.get(cacheKey)
  if (cached) {
    res.json({ success: true, data: cached })
    return
  }

  const enriched = REGIONS.map((r) => ({
    ...r,
    utilizationPercent: +((r.currentLoadMw / r.totalCapacityMw) * 100).toFixed(1),
    substations: SUBSTATIONS.filter((s) => r.substationIds.includes(s.id)),
  }))

  await cacheService.set(cacheKey, enriched, 60)
  res.json({ success: true, data: enriched })
}
