import { createClient, RedisClientType } from 'redis'
import { config } from '../config'
import logger from '../utils/logger'

class CacheService {
  private client: RedisClientType | null = null
  private connected = false

  async connect(): Promise<void> {
    try {
      this.client = createClient({ url: config.redisUrl }) as RedisClientType
      this.client.on('error', (err: Error) => {
        logger.warn(`Redis error: ${err.message}`)
        this.connected = false
      })
      this.client.on('connect', () => {
        this.connected = true
        logger.info('Redis connected')
      })
      await this.client.connect()
    } catch (err) {
      logger.warn('Redis unavailable — cache disabled')
      this.client = null
    }
  }

  async get<T>(key: string): Promise<T | null> {
    if (!this.client || !this.connected) return null
    try {
      const value = await this.client.get(key)
      return value ? (JSON.parse(value) as T) : null
    } catch {
      return null
    }
  }

  async set(key: string, value: unknown, ttlSeconds = 60): Promise<void> {
    if (!this.client || !this.connected) return
    try {
      await this.client.setEx(key, ttlSeconds, JSON.stringify(value))
    } catch {
      // cache is best-effort
    }
  }

  async del(key: string): Promise<void> {
    if (!this.client || !this.connected) return
    try {
      await this.client.del(key)
    } catch {
      // cache is best-effort
    }
  }

  isConnected(): boolean {
    return this.connected
  }
}

export const cacheService = new CacheService()
