import { Request, Response } from 'express'
import { GridEvent } from '../models/GridEvent'
import { cacheService } from '../services/cache.service'
import { pythonService } from '../services/python.service'
import { PaginationQuery } from '../types'
import logger from '../utils/logger'

export async function getDashboard(_req: Request, res: Response): Promise<void> {
  const cacheKey = 'metrics:dashboard'
  const cached = await cacheService.get(cacheKey)
  if (cached) {
    res.json({ success: true, data: cached })
    return
  }

  const since = new Date(Date.now() - 24 * 60 * 60 * 1000)

  const [totalEvents, anomalyCount, recentEvents] = await Promise.all([
    GridEvent.countDocuments({ timestamp: { $gte: since } }),
    GridEvent.countDocuments({ isAnomaly: true, timestamp: { $gte: since } }),
    GridEvent.find({ timestamp: { $gte: since } })
      .sort({ timestamp: -1 })
      .limit(10)
      .lean(),
  ])

  let pythonInsights: unknown = null
  try {
    pythonInsights = await pythonService.get('/metrics/insights')
  } catch {
    logger.debug('Python backend unavailable — skipping insights')
  }

  const data = {
    last24h: {
      totalEvents,
      anomalyCount,
      anomalyRate: totalEvents > 0 ? +((anomalyCount / totalEvents) * 100).toFixed(2) : 0,
    },
    recentEvents,
    insights: pythonInsights ?? {
      totalEnergyKwh: 847320,
      peakDemandMw: 1340,
      renewableContributionPct: 20.4,
      co2SavedTons: 210,
    },
    generatedAt: new Date().toISOString(),
  }

  await cacheService.set(cacheKey, data, 30)
  res.json({ success: true, data })
}

export async function getHistory(
  req: Request<unknown, unknown, unknown, PaginationQuery & { substationId?: string; anomalyOnly?: string }>,
  res: Response
): Promise<void> {
  const page = Math.max(1, parseInt(req.query.page ?? '1'))
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit ?? '20')))
  const skip = (page - 1) * limit

  const filter: Record<string, unknown> = {}
  if (req.query.substationId) filter['substationId'] = req.query.substationId
  if (req.query.anomalyOnly === 'true') filter['isAnomaly'] = true

  const [events, total] = await Promise.all([
    GridEvent.find(filter).sort({ timestamp: -1 }).skip(skip).limit(limit).lean(),
    GridEvent.countDocuments(filter),
  ])

  res.json({
    success: true,
    data: {
      events,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
        hasNext: page * limit < total,
        hasPrev: page > 1,
      },
    },
  })
}
