/**
 * UrjaRakshak API Client
 * Centralised fetch wrapper for all backend calls.
 */

// NEXT_PUBLIC_API_URL is baked in at build time by next.config.js.
// Empty-string guard ensures we never send requests to the same-origin
// Next.js dev server (which has no /api/v1 routes).
const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

/**
 * Parse a FastAPI error response body into a human-readable string.
 * Handles both plain string detail and Pydantic validation arrays.
 */
export function parseApiError(body: any): string {
  const detail = body?.detail
  if (Array.isArray(detail)) {
    return detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join('; ')
  }
  return detail || body?.message || ''
}

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch (networkErr: any) {
    // Network-level failure (backend not running, CORS preflight rejected, etc.)
    throw new Error(
      `Cannot reach the backend at ${BASE}. ` +
      `Make sure the backend is running: cd backend && uvicorn app.main:app --reload --port 8000`
    )
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    // Auto-clear expired/invalid token so user sees login prompt on next attempt
    if (res.status === 401 && typeof window !== 'undefined') {
      const isAuthEndpoint = path.includes('/auth/login') || path.includes('/auth/register')
      if (!isAuthEndpoint) {
        localStorage.removeItem('urjarakshak_token')
        localStorage.removeItem('urjarakshak_role')
        localStorage.removeItem('urjarakshak_user_id')
      }
    }
    // Pydantic validation errors return detail as an array of objects
    throw new Error(parseApiError(body) || `HTTP ${res.status}`)
  }
  return res.json()
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('urjarakshak_token')
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Public endpoints ──────────────────────────────────────────────────────

export const api = {
  getApiUrl: () => BASE,

  health: () => fetcher<any>('/health'),

  getPhysicsInfo: () => fetcher<any>('/api/v1/physics/info').catch(() => null),

  /** Live dashboard data — no auth required */
  getDashboard: () => fetcher<DashboardData>('/api/v1/upload/dashboard'),

  // ── Auth ─────────────────────────────────────────────────────────────
  login: (email: string, password: string) =>
    fetcher<{ access_token: string; token_type: string; expires_in: number; role: string; user_id: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (
    email: string,
    password: string,
    role = 'viewer',
    opts?: { full_name?: string; date_of_birth?: string; security_question?: string; security_answer?: string },
  ) =>
    fetcher<any>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, role, ...opts }),
    }),

  forgotPasswordVerify: (email: string, date_of_birth?: string, security_answer?: string) =>
    fetcher<{ reset_token: string; message: string }>('/api/v1/auth/forgot-password/verify', {
      method: 'POST',
      body: JSON.stringify({ email, date_of_birth, security_answer }),
    }),

  forgotPasswordReset: (email: string, new_password: string, date_of_birth?: string, security_answer?: string) =>
    fetcher<{ message: string }>('/api/v1/auth/forgot-password/reset', {
      method: 'POST',
      body: JSON.stringify({ email, new_password, date_of_birth, security_answer }),
    }),

  getMe: () =>
    fetcher<any>('/api/v1/auth/me', { headers: { ...authHeaders() } }),

  // ── Analysis ─────────────────────────────────────────────────────────
  validate: (payload: AnalysisPayload) =>
    fetcher<any>('/api/v1/analysis/validate', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    }),

  getStatsSummary: () =>
    fetcher<any>('/api/v1/analysis/stats/summary', { headers: authHeaders() }),

  listAnalyses: (params?: { limit?: number; offset?: number }) => {
    const clean: Record<string, string> = {}
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== undefined && v !== null) clean[k] = String(v)
    }
    const qs = new URLSearchParams(clean).toString()
    return fetcher<any>(`/api/v1/analysis/${qs ? '?' + qs : ''}`, { headers: authHeaders() })
  },

  getAnalysis: (id: string) =>
    fetcher<any>(`/api/v1/analysis/${id}`, { headers: authHeaders() }),

  // ── Upload ───────────────────────────────────────────────────────────
  uploadMeterData: async (file: File, substationId: string): Promise<UploadResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('substation_id', substationId)
    const token = getToken()

    let res: Response
    try {
      res = await fetch(`${BASE}/api/v1/upload/meter-data`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      })
    } catch {
      throw new Error(
        `Cannot reach the backend at ${BASE}. ` +
        `Make sure the backend is running: cd backend && uvicorn app.main:app --reload --port 8000`
      )
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      if (res.status === 401 && typeof window !== 'undefined') {
        localStorage.removeItem('urjarakshak_token')
        localStorage.removeItem('urjarakshak_role')
        localStorage.removeItem('urjarakshak_user_id')
      }
      throw new Error(parseApiError(body) || `HTTP ${res.status}`)
    }
    return res.json()
  },

  listBatches: () =>
    fetcher<any>('/api/v1/upload/batches', { headers: authHeaders() }),

  getBatch: (id: string, anomaliesOnly = false) =>
    fetcher<any>(
      `/api/v1/upload/batches/${id}?anomalies_only=${anomaliesOnly}`,
      { headers: authHeaders() }
    ),
}

// ── Types ─────────────────────────────────────────────────────────────────

export interface DashboardData {
  has_data: boolean
  latest_analysis: {
    substation_id: string
    input_energy_mwh: number
    output_energy_mwh: number
    technical_loss_pct: number
    residual_pct: number          // backend sends residual_pct (not residual_percentage)
    confidence_score: number      // backend sends 0–100 (already multiplied)
    balance_status: string
    requires_review: boolean
    created_at: string
  } | null
  latest_batch: {
    batch_id: string
    filename: string
    substation_id: string
    row_count: number
    anomalies_detected: number
    total_energy_kwh: number
    residual_pct: number
    confidence_score: number
    created_at: string
  } | null
  aggregates: {
    total_analyses: number
    avg_residual_pct: number
    avg_confidence_pct: number
    pending_review: number
    total_anomaly_checks: number
    anomalies_flagged: number
    anomaly_flag_rate_pct: number
    total_batches_uploaded: number
    total_meter_readings: number
    total_meter_anomalies: number
    meter_anomaly_rate_pct: number
  }
  by_status: Record<string, number>
  high_risk_substations: Array<{ substation: string; avg_residual_pct: number; analyses: number }>
  trend: Array<{ ts: string; residual_pct: number; confidence: number; substation: string }>
}

export interface UploadResult {
  batch_id: string
  analysis_id: string | null
  status: string
  filename: string
  substation_id: string
  rows_received: number
  rows_parsed: number
  rows_skipped: number
  summary: {
    total_energy_kwh: number
    residual_pct: number
    confidence_score: number
    anomalies_detected: number
    anomaly_rate_pct: number
  }
  anomaly_sample: Array<{
    meter_id: string
    timestamp: string
    energy_kwh: number
    expected_kwh: number
    z_score: number
    anomaly_score: number
    reason: string
  }>
  ethics_note: string
}

export interface AnalysisPayload {
  substation_id: string
  input_energy_mwh: number
  output_energy_mwh: number
  time_window_hours?: number
  components: Array<{
    component_id: string
    component_type: string
    rated_capacity_kva?: number
    efficiency_rating?: number
    age_years?: number
    voltage_kv?: number
    resistance_ohms?: number
    length_km?: number
  }>
}

// ── GHI & AI ──────────────────────────────────────────────────────────────

export const ghiApi = {
  getDashboard: () =>
    fetcher<GHIDashboard>('/api/v1/ai/ghi/dashboard'),

  getLatest: (substationId: string) =>
    fetcher<GHISnapshot>(`/api/v1/ai/ghi/latest/${substationId}`, { headers: authHeaders() }),

  getHistory: (substationId: string, limit = 30) =>
    fetcher<{ substation_id: string; count: number; avg_ghi: number | null; history: GHISnapshot[] }>(
      `/api/v1/ai/ghi/history/${substationId}?limit=${limit}`,
      { headers: authHeaders() }
    ),

  interpret: (analysisId: string) =>
    fetcher<any>(`/api/v1/ai/interpret/${analysisId}`, {
      method: 'POST', headers: authHeaders(),
    }),

  getStatus: () =>
    fetcher<AIStatus>('/api/v1/ai/status', { headers: authHeaders() }),
}

export const inspectionApi = {
  list: (params?: { status?: string; priority?: string; substation_id?: string; limit?: number }) => {
    // Strip undefined/null/empty values so they aren't sent as "undefined" strings
    const clean: Record<string, string> = {}
    for (const [k, v] of Object.entries(params ?? {})) {
      if (v !== undefined && v !== null && v !== '') clean[k] = String(v)
    }
    const qs = new URLSearchParams(clean).toString()
    return fetcher<{ total: number; items: Inspection[] }>(
      `/api/v1/inspections/${qs ? '?' + qs : ''}`, { headers: authHeaders() }
    )
  },

  getStats: () =>
    fetcher<InspectionStats>('/api/v1/inspections/stats/summary', { headers: authHeaders() }),

  update: (id: string, body: Partial<{ status: string; findings: string; resolution_notes: string; resolution: string }>) =>
    fetcher<{ inspection: Inspection; updated: boolean }>(`/api/v1/inspections/${id}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body),
    }),
}

// ── Additional types ──────────────────────────────────────────────────────

export interface GHIDashboard {
  has_data: boolean
  total_ghi_snapshots: number
  total_ai_interpretations: number
  live_ai_interpretations: number
  avg_ghi_all_time: number | null
  by_classification: Record<string, number>
  open_inspections: number
  critical_open: number
  substations: GHISubstationSummary[]
  trend: Array<{ ts: string; ghi: number; class: string; substation: string }>
}

export interface GHISubstationSummary {
  substation_id: string
  ghi_score: number
  classification: string
  action_required: boolean
  inspection_priority: string
  updated_at: string
}

export interface GHISnapshot {
  id: string
  substation_id: string
  analysis_id: string
  ghi_score: number
  classification: string
  action_required: boolean
  interpretation: string
  inspection_priority: string
  inspection_category: string
  urgency: string
  confidence_in_ghi: number
  components: { PBS: number; ASS: number; CS: number; TSS: number; DIS: number }
  created_at: string
}

export interface AIStatus {
  configured: boolean
  preferred_provider: string
  offline_mode: boolean
  offline_note: string | null
}

export interface Inspection {
  id: string
  substation_id: string
  priority: string
  category: string
  urgency: string
  status: string
  description: string
  recommended_actions: string[]
  findings: string | null
  resolution_notes: string | null
  resolution: string | null
  assigned_to: string | null
  analysis_id: string | null
  ai_recommendation: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface InspectionStats {
  total: number
  critical_open: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
  top_substations: Array<{ substation: string; open_count: number }>
}

// ── Streaming / Real-Time ────────────────────────────────────────────────

export const streamApi = {
  ingest: (event: MeterEventIn) =>
    fetcher<any>('/api/v1/stream/ingest', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(event),
    }),

  getRecent: (substationId: string, limit = 50, anomaliesOnly = false) =>
    fetcher<{ substation_id: string; count: number; events: LiveEvent[] }>(
      `/api/v1/stream/recent/${substationId}?limit=${limit}${anomaliesOnly ? '&anomalies_only=true' : ''}`,
      { headers: authHeaders() }
    ),

  getMeterStability: (meterId: string, substationId: string) =>
    fetcher<MeterStability>(
      `/api/v1/stream/meter/${meterId}/stability?substation_id=${substationId}`,
      { headers: authHeaders() }
    ),

  getSubstationStability: (substationId: string) =>
    fetcher<SubstationStability>(`/api/v1/stream/substation/${substationId}/stability`, {
      headers: authHeaders(),
    }),

  getSubscriberCount: () =>
    fetcher<{ total_connections: number; by_substation: Record<string, number> }>(
      '/api/v1/stream/subscribers', { headers: authHeaders() }
    ),

  /**
   * Open a Server-Sent Events simulation stream for a substation.
   * Returns an EventSource that emits synthetic meter readings every `intervalMs` ms.
   * The caller is responsible for calling `.close()` on the returned EventSource.
   */
  openSimulation: (
    substationId: string,
    opts?: {
      meterCount?: number
      intervalMs?: number
      baselineMinKwh?: number
      baselineMaxKwh?: number
      anomalyPct?: number
    }
  ): EventSource => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('urjarakshak_token') : null
    const params = new URLSearchParams()
    if (opts?.meterCount) params.set('meter_count', String(opts.meterCount))
    if (opts?.intervalMs) params.set('interval_ms', String(opts.intervalMs))
    if (opts?.baselineMinKwh !== undefined) params.set('baseline_min_kwh', String(opts.baselineMinKwh))
    if (opts?.baselineMaxKwh !== undefined) params.set('baseline_max_kwh', String(opts.baselineMaxKwh))
    if (opts?.anomalyPct !== undefined) params.set('anomaly_pct', String(opts.anomalyPct))
    // EventSource doesn't support custom headers; pass token as query param
    if (token) params.set('token', token)
    const url = `${BASE}/api/v1/stream/simulate/${substationId}?${params.toString()}`
    return new EventSource(url)
  },
}

export const governanceApi = {
  createOrg: (body: { slug: string; name: string; plan?: string; contact_email?: string }) =>
    fetcher<any>('/api/v1/org/', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
    }),

  listMyOrgs: () =>
    fetcher<{ organizations: any[]; count: number }>('/api/v1/org/my', { headers: authHeaders() }),

  getOrg: (slug: string) =>
    fetcher<any>(`/api/v1/org/${slug}`, { headers: authHeaders() }),

  checkDrift: (refDays = 30, evalDays = 7) =>
    fetcher<DriftResult>(
      `/api/v1/org/drift/check?reference_days=${refDays}&evaluation_days=${evalDays}`,
      { headers: authHeaders() }
    ),

  getDriftHistory: (limit = 30) =>
    fetcher<{ count: number; history: DriftResult[] }>(
      `/api/v1/org/drift/history?limit=${limit}`, { headers: authHeaders() }
    ),

  computeAging: (body: AgingRequest) =>
    fetcher<AgingResult>('/api/v1/org/aging/compute', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
    }),

  getFleetAging: () =>
    fetcher<FleetAging>('/api/v1/org/aging/fleet', { headers: authHeaders() }),

  getAuditLog: (limit = 50) =>
    fetcher<{ count: number; entries: AuditEntry[] }>(
      `/api/v1/org/audit/recent?limit=${limit}`, { headers: authHeaders() }
    ),

  verifyChain: () =>
    fetcher<{ verified: boolean; entries_checked: number; broken_links: any[] }>(
      '/api/v1/org/audit/verify', { headers: authHeaders() }
    ),
}

// ── New types ─────────────────────────────────────────────────────────────

export interface MeterEventIn {
  meter_id: string
  substation_id: string
  energy_kwh: number
  event_ts?: string
  voltage_v?: number
  current_a?: number
  power_factor?: number
  source?: string
}

export interface LiveEvent {
  id: string
  meter_id: string
  event_ts: string
  energy_kwh: number
  z_score: number | null
  is_anomaly: boolean
  anomaly_score: number | null
  source: string
  type?: string
}

export interface MeterStability {
  meter_id: string
  substation_id: string
  stability_score: number | null
  window_size: number
  rolling_mean_kwh: number | null
  rolling_std_kwh: number | null
  rolling_cv: number | null
  trend_direction: string
  trend_slope: number | null
  anomaly_rate_30d: number | null
  p5_kwh: number | null
  p95_kwh: number | null
  total_readings: number
  last_reading_kwh: number | null
}

export interface SubstationStability {
  substation_id: string
  meter_count: number
  has_data: boolean
  avg_stability_score: number | null
  unstable_meters: number
  trending_up_count: number
  meters: MeterStability[]
}

export interface DriftResult {
  model_name: string
  drift_level: string
  requires_retraining: boolean
  psi: number | null
  ks_statistic: number | null
  ks_pvalue: number | null
  reference_anomaly_rate: number
  current_anomaly_rate: number
  rate_shift: number
  n_reference: number
  n_evaluation: number
  sufficient_data: boolean
  interpretation: string
  detected_at?: string
}

export interface AgingRequest {
  substation_id: string
  transformer_tag: string
  install_year?: number
  designed_life_years?: number
  load_factor?: number
  ambient_temp_c?: number
  rated_kva?: number
}

export interface AgingResult {
  substation_id: string
  transformer_tag: string
  hotspot_temp_c: number
  thermal_aging_factor: number
  life_consumed_pct: number
  estimated_rul_years: number
  failure_probability: number
  health_index: number
  condition_class: string
  maintenance_flag: boolean
  replacement_flag: boolean
  scenarios: Array<{ load_factor: number; hotspot_c: number; rul_years: number; health_index: number; condition: string }>
}

export interface FleetAging {
  transformer_count: number
  has_data: boolean
  avg_health_index: number | null
  critical_count: number
  poor_count: number
  replace_within_3yr: number
  by_condition: Record<string, number>
  transformers: AgingResult[]
}

export interface AuditEntry {
  sequence_no: number
  event_type: string
  user_email: string | null
  org_id: string | null
  substation_id: string | null
  summary: string | null
  entry_hash: string
  recorded_at: string
  ip_address: string | null
}
