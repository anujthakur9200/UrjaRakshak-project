import { Request, Response, NextFunction } from 'express'
import { JwtPayload } from 'jsonwebtoken'
import { Document } from 'mongoose'

export interface IUser extends Document {
  email: string
  password: string
  role: 'analyst' | 'admin' | 'viewer'
  createdAt: Date
  updatedAt: Date
  comparePassword(candidate: string): Promise<boolean>
}

export interface IGridEvent extends Document {
  substationId: string
  meterId: string
  energyKwh: number
  timestamp: Date
  isAnomaly: boolean
  anomalyScore: number
  source: string
  metadata: Record<string, unknown>
}

export interface AuthenticatedRequest extends Request {
  user?: {
    id: string
    email: string
    role: string
  }
}

export interface JwtUserPayload extends JwtPayload {
  id: string
  email: string
  role: string
}

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  message?: string
  error?: string
}

export interface PaginationQuery {
  page?: string
  limit?: string
}

export type AsyncMiddleware = (
  req: Request,
  res: Response,
  next: NextFunction
) => Promise<void>
