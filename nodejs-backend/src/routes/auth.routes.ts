import { Router } from 'express'
import { register, login, me } from '../controllers/auth.controller'
import { authMiddleware } from '../middleware/auth.middleware'
import { authRateLimiter } from '../middleware/rateLimiter'
import { AuthenticatedRequest } from '../types'
import { Request, Response, NextFunction } from 'express'

const router = Router()

router.post('/register', authRateLimiter, register)
router.post('/login', authRateLimiter, login)
router.get(
  '/me',
  (req: Request, res: Response, next: NextFunction) =>
    authMiddleware(req as AuthenticatedRequest, res, next),
  (req: Request, res: Response) => me(req as AuthenticatedRequest, res)
)

export default router
