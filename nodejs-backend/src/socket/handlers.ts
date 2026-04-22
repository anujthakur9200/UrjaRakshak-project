import { Server as HttpServer } from 'http'
import { Server as SocketServer, Socket } from 'socket.io'
import { config } from '../config'
import logger from '../utils/logger'
import jwt from 'jsonwebtoken'
import { JwtUserPayload } from '../types'

interface LiveEvent {
  substationId: string
  meterId: string
  energyKwh: number
  voltageKv: number
  currentA: number
  powerFactorPct: number
  isAnomaly: boolean
  anomalyScore: number
  timestamp: string
}

const SUBSTATION_IDS = ['SS-001', 'SS-002', 'SS-003', 'SS-004', 'SS-005']
const METER_PREFIX = 'MTR'

function generateLiveEvent(substationId: string): LiveEvent {
  const isAnomaly = Math.random() < 0.04
  return {
    substationId,
    meterId: `${METER_PREFIX}-${substationId}-${String(Math.floor(Math.random() * 100) + 1).padStart(3, '0')}`,
    energyKwh: +(Math.random() * 900 + 100).toFixed(2),
    voltageKv: +(Math.random() * 12 + 215).toFixed(2),
    currentA: +(Math.random() * 60 + 80).toFixed(2),
    powerFactorPct: +(Math.random() * 8 + 90).toFixed(2),
    isAnomaly,
    anomalyScore: isAnomaly ? +(Math.random() * 0.4 + 0.6).toFixed(3) : +(Math.random() * 0.3).toFixed(3),
    timestamp: new Date().toISOString(),
  }
}

export function setupSocketHandlers(httpServer: HttpServer): SocketServer {
  const io = new SocketServer(httpServer, {
    cors: {
      origin: config.corsOrigins,
      methods: ['GET', 'POST'],
      credentials: true,
    },
  })

  io.use((socket, next) => {
    const token = socket.handshake.auth['token'] as string | undefined
    if (!token) {
      return next(new Error('Authentication token required'))
    }
    try {
      const payload = jwt.verify(token, config.jwtSecret) as JwtUserPayload
      socket.data['user'] = payload
      next()
    } catch {
      next(new Error('Invalid token'))
    }
  })

  io.on('connection', (socket: Socket) => {
    const user = socket.data['user'] as JwtUserPayload
    logger.info(`Socket connected: ${socket.id} (user: ${user.email})`)

    socket.emit('connected', {
      message: 'Connected to UrjaRakshak live grid stream',
      substations: SUBSTATION_IDS,
    })

    socket.on('subscribe:substation', (substationId: string) => {
      if (SUBSTATION_IDS.includes(substationId)) {
        void socket.join(`substation:${substationId}`)
        socket.emit('subscribed', { substationId })
        logger.debug(`${socket.id} subscribed to substation:${substationId}`)
      } else {
        socket.emit('error', { message: `Unknown substationId: ${substationId}` })
      }
    })

    socket.on('unsubscribe:substation', (substationId: string) => {
      void socket.leave(`substation:${substationId}`)
      socket.emit('unsubscribed', { substationId })
    })

    socket.on('subscribe:all', () => {
      SUBSTATION_IDS.forEach((id) => void socket.join(`substation:${id}`))
      socket.emit('subscribed', { substationId: 'all' })
    })

    socket.on('disconnect', () => {
      logger.info(`Socket disconnected: ${socket.id}`)
    })
  })

  const broadcastInterval = setInterval(() => {
    SUBSTATION_IDS.forEach((substationId) => {
      const event = generateLiveEvent(substationId)
      io.to(`substation:${substationId}`).emit('grid:event', event)

      if (event.isAnomaly) {
        io.to(`substation:${substationId}`).emit('grid:anomaly', {
          ...event,
          severity: event.anomalyScore > 0.85 ? 'high' : 'medium',
          alertMessage: `Anomaly detected at ${event.substationId} — meter ${event.meterId}`,
        })
        logger.debug(`Anomaly emitted for ${substationId}`)
      }
    })

    io.emit('grid:topology:update', {
      timestamp: new Date().toISOString(),
      substationLoads: SUBSTATION_IDS.map((id) => ({
        substationId: id,
        loadPercent: +(Math.random() * 40 + 50).toFixed(1),
      })),
    })
  }, 5000)

  io.on('close', () => clearInterval(broadcastInterval))

  return io
}
