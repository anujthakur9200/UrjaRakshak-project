import dotenv from 'dotenv'
dotenv.config()

export const config = {
  port: parseInt(process.env.PORT || '4000'),
  mongoUrl: process.env.MONGODB_URL || 'mongodb://localhost:27017/urjarakshak',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  jwtSecret: process.env.JWT_SECRET || 'urjarakshak-jwt-secret-dev',
  jwtExpiresIn: process.env.JWT_EXPIRES_IN || '7d',
  pythonBackendUrl: process.env.PYTHON_BACKEND_URL || 'http://localhost:8001',
  nodeEnv: process.env.NODE_ENV || 'development',
  corsOrigins: (process.env.CORS_ORIGINS || 'http://localhost:3000').split(','),
}
