import 'express-async-errors'
import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import morgan from 'morgan'
import { config } from './config'
import routes from './routes'
import { errorHandler } from './middleware/errorHandler'
import { defaultRateLimiter } from './middleware/rateLimiter'

const app = express()

app.use(helmet())
app.use(
  cors({
    origin: config.corsOrigins,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  })
)
app.use(morgan(config.nodeEnv === 'production' ? 'combined' : 'dev'))
app.use(express.json({ limit: '1mb' }))
app.use(express.urlencoded({ extended: true }))
app.use(defaultRateLimiter)

app.use('/api/v1', routes)

app.use(errorHandler)

export default app
