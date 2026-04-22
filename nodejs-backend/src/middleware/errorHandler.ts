import { Request, Response, NextFunction } from 'express'
import { config } from '../config'
import logger from '../utils/logger'

export interface AppError extends Error {
  statusCode?: number
  isOperational?: boolean
}

export function errorHandler(
  err: AppError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  const statusCode = err.statusCode ?? 500
  const message = err.message || 'Internal Server Error'

  if (config.nodeEnv !== 'test') {
    logger.error({
      message: err.message,
      stack: err.stack,
      statusCode,
    })
  }

  res.status(statusCode).json({
    success: false,
    error: config.nodeEnv === 'production' && statusCode === 500
      ? 'Internal Server Error'
      : message,
  })
}

export function createError(message: string, statusCode: number): AppError {
  const err: AppError = new Error(message)
  err.statusCode = statusCode
  err.isOperational = true
  return err
}
