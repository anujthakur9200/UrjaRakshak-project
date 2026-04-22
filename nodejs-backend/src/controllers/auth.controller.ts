import { Request, Response } from 'express'
import jwt from 'jsonwebtoken'
import { z } from 'zod'
import { User } from '../models/User'
import { config } from '../config'
import { AuthenticatedRequest, ApiResponse } from '../types'
import { createError } from '../middleware/errorHandler'

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  role: z.enum(['analyst', 'admin', 'viewer']).optional(),
})

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})

function signToken(user: { _id: unknown; email: string; role: string }): string {
  return jwt.sign(
    { id: String(user._id), email: user.email, role: user.role },
    config.jwtSecret,
    { expiresIn: config.jwtExpiresIn } as jwt.SignOptions
  )
}

export async function register(req: Request, res: Response): Promise<void> {
  const parsed = registerSchema.safeParse(req.body)
  if (!parsed.success) {
    res.status(400).json({ success: false, error: parsed.error.message })
    return
  }

  const { email, password, role } = parsed.data
  const existing = await User.findOne({ email })
  if (existing) {
    throw createError('Email already registered', 409)
  }

  const user = await User.create({ email, password, role: role ?? 'viewer' })
  const token = signToken(user)

  const response: ApiResponse<{ token: string; user: { id: string; email: string; role: string } }> = {
    success: true,
    data: {
      token,
      user: { id: String(user._id), email: user.email, role: user.role },
    },
  }
  res.status(201).json(response)
}

export async function login(req: Request, res: Response): Promise<void> {
  const parsed = loginSchema.safeParse(req.body)
  if (!parsed.success) {
    res.status(400).json({ success: false, error: parsed.error.message })
    return
  }

  const { email, password } = parsed.data
  const user = await User.findOne({ email }).select('+password')
  if (!user) {
    throw createError('Invalid credentials', 401)
  }

  const valid = await user.comparePassword(password)
  if (!valid) {
    throw createError('Invalid credentials', 401)
  }

  const token = signToken(user)

  res.json({
    success: true,
    data: {
      token,
      user: { id: String(user._id), email: user.email, role: user.role },
    },
  })
}

export async function me(req: AuthenticatedRequest, res: Response): Promise<void> {
  if (!req.user) {
    throw createError('Unauthorized', 401)
  }

  const user = await User.findById(req.user.id)
  if (!user) {
    throw createError('User not found', 404)
  }

  res.json({
    success: true,
    data: { id: String(user._id), email: user.email, role: user.role },
  })
}
