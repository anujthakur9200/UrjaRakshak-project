import { Router, Request, Response, NextFunction } from 'express'
import { getDashboard, getHistory } from '../controllers/metrics.controller'
import { authMiddleware } from '../middleware/auth.middleware'
import { AuthenticatedRequest } from '../types'

const router = Router()

function auth(req: Request, res: Response, next: NextFunction): void {
  authMiddleware(req as AuthenticatedRequest, res, next)
}

router.get('/dashboard', auth, getDashboard)
router.get('/history', auth, getHistory)

export default router
