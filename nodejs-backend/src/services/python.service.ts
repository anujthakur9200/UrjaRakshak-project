import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import { config } from '../config'
import logger from '../utils/logger'

class PythonService {
  private readonly client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: config.pythonBackendUrl,
      timeout: 10_000,
      headers: { 'Content-Type': 'application/json' },
    })

    this.client.interceptors.response.use(
      (res) => res,
      (err) => {
        logger.warn(`Python backend error: ${err.message}`)
        return Promise.reject(err)
      }
    )
  }

  async get<T>(path: string, options?: AxiosRequestConfig): Promise<T> {
    const { data } = await this.client.get<T>(path, options)
    return data
  }

  async post<T>(path: string, body: unknown, options?: AxiosRequestConfig): Promise<T> {
    const { data } = await this.client.post<T>(path, body, options)
    return data
  }

  async predict(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>('/predict', payload)
  }

  async getAnomalies(params?: Record<string, string>): Promise<unknown[]> {
    return this.get<unknown[]>('/anomalies', { params })
  }

  async healthCheck(): Promise<boolean> {
    try {
      await this.get('/health')
      return true
    } catch {
      return false
    }
  }
}

export const pythonService = new PythonService()
