import { Router, Request, Response, NextFunction } from 'express'
import { getTopology, getLiveMetrics, getRegions } from '../controllers/grid.controller'
import { authMiddleware } from '../middleware/auth.middleware'
import { AuthenticatedRequest } from '../types'

const router = Router()

function auth(req: Request, res: Response, next: NextFunction): void {
  authMiddleware(req as AuthenticatedRequest, res, next)
}

router.get('/topology', auth, getTopology)
router.get('/live', auth, getLiveMetrics)
router.get('/regions', auth, getRegions)

export default router
