import { createServer } from 'http'
import mongoose from 'mongoose'
import app from './app'
import { config } from './config'
import { setupSocketHandlers } from './socket/handlers'
import { cacheService } from './services/cache.service'
import logger from './utils/logger'

async function bootstrap(): Promise<void> {
  await mongoose.connect(config.mongoUrl)
  logger.info(`MongoDB connected: ${config.mongoUrl}`)

  await cacheService.connect()

  const httpServer = createServer(app)
  setupSocketHandlers(httpServer)

  httpServer.listen(config.port, () => {
    logger.info(`UrjaRakshak Node.js backend running on port ${config.port} [${config.nodeEnv}]`)
  })
}

process.on('unhandledRejection', (reason) => {
  logger.error('Unhandled rejection:', reason)
  process.exit(1)
})

process.on('uncaughtException', (err) => {
  logger.error('Uncaught exception:', err)
  process.exit(1)
})

bootstrap().catch((err) => {
  logger.error('Failed to start server:', err)
  process.exit(1)
})
