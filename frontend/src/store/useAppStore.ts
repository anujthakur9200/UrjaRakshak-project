import { create } from 'zustand'

// ── Types ─────────────────────────────────────────────────────────────────

export interface LiveEvent {
  id: string
  substationId: string
  type: 'normal' | 'anomaly' | 'critical'
  value: number
  timestamp: string
}

export interface LiveMetrics {
  substationCount: number
  activeAlerts: number
  avgEfficiency: number
  totalLoadMW: number
  lastUpdated: string
}

export interface Anomaly {
  meter_id: string
  timestamp: string
  energy_kwh: number
  expected_kwh: number
  z_score: number
  anomaly_score: number
  reason: string
}

export interface AnalysisStats {
  total_energy_kwh: number
  residual_pct: number
  confidence_score: number
  anomalies_detected: number
  anomaly_rate_pct: number
}

export interface AnalysisSession {
  analysisId: string
  batchId: string
  substationId: string
  filename: string
  rowsParsed: number
  stats: AnalysisStats
  anomalySample: Anomaly[]
  createdAt: string
  /** Full analysis detail fetched from GET /api/v1/analysis/{id} */
  detail: any | null
  aiInterpretation: any | null
  aiStatus: 'idle' | 'loading' | 'ready' | 'error'
  aiError: string | null
}

// ── Store interface ────────────────────────────────────────────────────────

interface AppState {
  // ── Live metrics (legacy / SSE) ───────────────────────────────────────
  liveMetrics: LiveMetrics
  recentEvents: LiveEvent[]
  selectedSubstation: string | null
  setSelectedSubstation: (id: string | null) => void
  updateLiveMetrics: (metrics: LiveMetrics) => void
  addEvent: (event: LiveEvent) => void

  // ── Active analysis session (SSOT) ───────────────────────────────────
  /** The currently active analysis session, populated after an upload */
  activeSession: AnalysisSession | null
  /** All sessions in this browser session (most recent first) */
  sessions: AnalysisSession[]
  setActiveSession: (session: AnalysisSession) => void
  updateSessionDetail: (analysisId: string, detail: any) => void
  updateSessionAI: (
    analysisId: string,
    ai: any,
    status: AnalysisSession['aiStatus'],
    error?: string | null
  ) => void
  clearActiveSession: () => void

  // ── Selected region / meter (for map ↔ graph sync) ───────────────────
  selectedRegion: string | null
  selectedMeter: string | null
  setSelectedRegion: (regionId: string | null) => void
  setSelectedMeter: (meterId: string | null) => void

  // ── Live simulation data ──────────────────────────────────────────────
  simulatedEvents: Array<{
    meter_id: string
    substation_id: string
    energy_kwh: number
    is_anomaly: boolean
    event_ts: string
    z_score: number | null
  }>
  isSimulating: boolean
  addSimulatedEvent: (event: AppState['simulatedEvents'][0]) => void
  setIsSimulating: (v: boolean) => void
  clearSimulatedEvents: () => void
}

// ── Store implementation ───────────────────────────────────────────────────

export const useAppStore = create<AppState>((set) => ({
  // ── Live metrics ──────────────────────────────────────────────────────
  liveMetrics: {
    substationCount: 0,
    activeAlerts: 0,
    avgEfficiency: 0,
    totalLoadMW: 0,
    lastUpdated: '',
  },
  recentEvents: [],
  selectedSubstation: null,

  setSelectedSubstation: (id) => set({ selectedSubstation: id }),
  updateLiveMetrics: (metrics) => set({ liveMetrics: metrics }),
  addEvent: (event) =>
    set((state) => ({
      // Keep only the most recent 100 events
      recentEvents: [event, ...state.recentEvents].slice(0, 100),
    })),

  // ── Active analysis session (SSOT) ───────────────────────────────────
  activeSession: null,
  sessions: [],

  setActiveSession: (session) =>
    set((state) => ({
      activeSession: session,
      sessions: [session, ...state.sessions.filter((s) => s.analysisId !== session.analysisId)].slice(0, 20),
    })),

  updateSessionDetail: (analysisId, detail) =>
    set((state) => {
      const update = (s: AnalysisSession): AnalysisSession =>
        s.analysisId === analysisId ? { ...s, detail } : s
      return {
        activeSession: state.activeSession?.analysisId === analysisId
          ? { ...state.activeSession, detail }
          : state.activeSession,
        sessions: state.sessions.map(update),
      }
    }),

  updateSessionAI: (analysisId, ai, status, error = null) =>
    set((state) => {
      const update = (s: AnalysisSession): AnalysisSession =>
        s.analysisId === analysisId
          ? { ...s, aiInterpretation: ai, aiStatus: status, aiError: error }
          : s
      return {
        activeSession: state.activeSession?.analysisId === analysisId
          ? { ...state.activeSession, aiInterpretation: ai, aiStatus: status, aiError: error }
          : state.activeSession,
        sessions: state.sessions.map(update),
      }
    }),

  clearActiveSession: () => set({ activeSession: null }),

  // ── Selected region / meter ───────────────────────────────────────────
  selectedRegion: null,
  selectedMeter: null,
  setSelectedRegion: (regionId) => set({ selectedRegion: regionId }),
  setSelectedMeter: (meterId) => set({ selectedMeter: meterId }),

  // ── Live simulation ───────────────────────────────────────────────────
  simulatedEvents: [],
  isSimulating: false,
  addSimulatedEvent: (event) =>
    set((state) => ({
      simulatedEvents: [event, ...state.simulatedEvents].slice(0, 200),
    })),
  setIsSimulating: (v) => set({ isSimulating: v }),
  clearSimulatedEvents: () => set({ simulatedEvents: [] }),
}))
