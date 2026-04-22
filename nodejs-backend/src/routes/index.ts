import { Router, Request, Response } from 'express'
import authRoutes from './auth.routes'
import gridRoutes from './grid.routes'
import metricsRoutes from './metrics.routes'

const router = Router()

router.get('/health', (_req: Request, res: Response) => {
  res.json({ success: true, message: 'UrjaRakshak API is running', timestamp: new Date().toISOString() })
})

router.use('/auth', authRoutes)
router.use('/grid', gridRoutes)
router.use('/metrics', metricsRoutes)

export default router
