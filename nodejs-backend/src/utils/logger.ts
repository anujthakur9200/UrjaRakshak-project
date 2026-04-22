import { createLogger, format, transports } from 'winston'
import { config } from '../config'

const logger = createLogger({
  level: config.nodeEnv === 'production' ? 'info' : 'debug',
  format: format.combine(
    format.timestamp(),
    format.errors({ stack: true }),
    config.nodeEnv === 'production'
      ? format.json()
      : format.combine(format.colorize(), format.simple())
  ),
  transports: [new transports.Console()],
  silent: config.nodeEnv === 'test',
})

export default logger
