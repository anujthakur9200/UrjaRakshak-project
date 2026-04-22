'use client'

import { useState } from 'react'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

interface AnomalyResult {
  is_anomaly: boolean
  anomaly_score: number
  confidence: number
  method_used: string
  primary_reason: string
  recommended_action: string
  feature_contributions?: Record<string, number>
}

interface DetectionResponse {
  anomaly_result_id: string | null
  result: AnomalyResult
  metadata: { model: Record<string, string | number | boolean> }
}

const DEFAULT_CONFIDENCE_SCORE = 0.9

interface FormState {
  substation_id: string
  input_mwh: string
  output_mwh: string
  time_of_day_hour: string
  day_of_week: string
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  const pct = Math.round(value * 100)
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)' }}>
          Score
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, fontWeight: 600 }}>
          {value.toFixed(3)}
        </span>
      </div>
      <div style={{ height: 6, background: 'var(--bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 3,
            transition: 'width 0.8s cubic-bezier(0.22, 1, 0.36, 1)',
            boxShadow: `0 0 8px ${color}66`,
          }}
        />
      </div>
    </div>
  )
}

function FeatureBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.abs(value) * 100, 100)
  const color = value > 0.3 ? 'var(--red)' : value > 0.1 ? 'var(--amber)' : 'var(--green)'
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)' }}>
          {label}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color }}>
          {value.toFixed(3)}
        </span>
      </div>
      <div style={{ height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 2,
            transition: 'width 0.6s ease',
          }}
        />
      </div>
    </div>
  )
}

export default function AnomalyPage() {
  const [form, setForm] = useState<FormState>({
    substation_id: 'demo-sub-01',
    input_mwh: '10.0',
    output_mwh: '8.2',
    time_of_day_hour: '14',
    day_of_week: '3',
  })
  const [result, setResult] = useState<DetectionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function updateField(key: keyof FormState, value: string) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function runDetection() {
    setLoading(true)
    setError(null)
    setResult(null)

    const token = typeof window !== 'undefined' ? localStorage.getItem('urjarakshak_token') : null
    if (!token) {
      setError('Authentication required. Please log in to use anomaly detection.')
      setLoading(false)
      return
    }
    const headers: Record<string, string> = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

    const inputMwh = parseFloat(form.input_mwh)
    const outputMwh = parseFloat(form.output_mwh)
    const residualMwh = inputMwh - outputMwh

    try {
      const res = await fetch(`${BASE}/api/v1/analysis/anomaly/detect`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          substation_id: form.substation_id,
          input_mwh: inputMwh,
          output_mwh: outputMwh,
          residual_mwh: residualMwh,
          residual_percent: inputMwh > 0 ? (residualMwh / inputMwh) * 100 : 0,
          confidence_score: DEFAULT_CONFIDENCE_SCORE,
          time_of_day_hour: parseFloat(form.time_of_day_hour),
          day_of_week: parseFloat(form.day_of_week),
        }),
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `HTTP ${res.status}`)
      }

      const data: DetectionResponse = await res.json()
      setResult(data)
    } catch (err: any) {
      setError(err?.message || 'Detection failed')
    } finally {
      setLoading(false)
    }
  }

  const isAnomaly = result?.result?.is_anomaly
  const score = result?.result?.anomaly_score ?? 0
  const anomalyColor = isAnomaly ? 'var(--red)' : score > 0.5 ? 'var(--amber)' : 'var(--green)'

  return (
    <main className="page">
      <div className="page-header">
        <div className="page-eyebrow">ML — Isolation Forest + Z-Score</div>
        <h1 className="page-title">Anomaly Detection</h1>
        <p className="page-desc">
          Submit a meter reading to the ML anomaly engine. The engine uses an Isolation Forest trained on
          synthetic grid data, combined with a statistical Z-score gate, to detect abnormal consumption patterns.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }} className="anomaly-grid">

        {/* Input form */}
        <div className="panel">
          <div className="sec-label">Reading Parameters</div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Substation */}
            <div>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 6 }}>
                Substation ID
              </label>
              <input
                className="input"
                value={form.substation_id}
                onChange={e => updateField('substation_id', e.target.value)}
                placeholder="e.g. sub-north-01"
              />
            </div>

            {/* Energy */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 6 }}>
                  Input Energy (MWh)
                </label>
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  value={form.input_mwh}
                  onChange={e => updateField('input_mwh', e.target.value)}
                />
              </div>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 6 }}>
                  Output Energy (MWh)
                </label>
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  value={form.output_mwh}
                  onChange={e => updateField('output_mwh', e.target.value)}
                />
              </div>
            </div>

            {/* Time */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 6 }}>
                  Hour of Day (0–23)
                </label>
                <input
                  className="input"
                  type="number"
                  min="0"
                  max="23"
                  value={form.time_of_day_hour}
                  onChange={e => updateField('time_of_day_hour', e.target.value)}
                />
              </div>
              <div>
                <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 6 }}>
                  Day of Week (1–7)
                </label>
                <input
                  className="input"
                  type="number"
                  min="1"
                  max="7"
                  value={form.day_of_week}
                  onChange={e => updateField('day_of_week', e.target.value)}
                />
              </div>
            </div>

            {/* Computed residual preview */}
            {form.input_mwh && form.output_mwh && (
              <div style={{ padding: '10px 14px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                <span style={{ color: 'var(--text-tertiary)' }}>Residual: </span>
                <span style={{ color: 'var(--cyan)' }}>
                  {(parseFloat(form.input_mwh) - parseFloat(form.output_mwh)).toFixed(3)} MWh
                  ({parseFloat(form.input_mwh) > 0
                    ? (((parseFloat(form.input_mwh) - parseFloat(form.output_mwh)) / parseFloat(form.input_mwh)) * 100).toFixed(1)
                    : '0.0'}%)
                </span>
              </div>
            )}

            <button
              className="btn btn-primary"
              onClick={runDetection}
              disabled={loading}
              style={{ marginTop: 4 }}
            >
              {loading ? (
                <>
                  <span className="spinner spinner-sm" />
                  Running Detection…
                </>
              ) : (
                '⚡ Run ML Detection'
              )}
            </button>
          </div>
        </div>

        {/* Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {error && (
            <div className="alert alert-err">
              <strong>Error:</strong> {error}
            </div>
          )}

          {!result && !loading && !error && (
            <div className="empty-state">
              <div className="empty-icon">🔎</div>
              <div className="empty-title">No result yet</div>
              <div className="empty-desc">
                Fill in the reading parameters and press &quot;Run ML Detection&quot; to analyse a meter reading.
              </div>
            </div>
          )}

          {result && (
            <>
              {/* Verdict */}
              <div
                className="panel"
                style={{
                  borderColor: anomalyColor,
                  background: isAnomaly ? 'rgba(255,61,85,0.04)' : 'rgba(5,232,154,0.03)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <span style={{ fontSize: 32 }}>{isAnomaly ? '🚨' : '✅'}</span>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: anomalyColor, letterSpacing: '-0.01em' }}>
                      {isAnomaly ? 'Anomaly Detected' : 'Normal Reading'}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      Method: {result.result.method_used} · Confidence: {(result.result.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>

                <ScoreBar value={score} color={anomalyColor} />

                <div style={{ marginTop: 16, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.68 }}>
                  <strong style={{ color: 'var(--text-primary)' }}>Finding: </strong>
                  {result.result.primary_reason}
                </div>

                {result.result.recommended_action && (
                  <div style={{ marginTop: 10, padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', fontSize: 12.5, color: 'var(--text-secondary)' }}>
                    <strong style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Action:</strong>
                    <br />
                    {result.result.recommended_action}
                  </div>
                )}
              </div>

              {/* Feature contributions */}
              {result.result.feature_contributions &&
                Object.keys(result.result.feature_contributions).length > 0 && (
                <div className="panel">
                  <div className="sec-label">Feature Contributions</div>
                  {Object.entries(result.result.feature_contributions).map(([k, v]) => (
                    <FeatureBar key={k} label={k} value={v as number} />
                  ))}
                  <p style={{ fontSize: 11.5, color: 'var(--text-dim)', marginTop: 12, lineHeight: 1.6 }}>
                    Higher values indicate features that contributed more to the anomaly score.
                    The Isolation Forest isolates points that differ on these dimensions.
                  </p>
                </div>
              )}

              {/* Model info */}
              {result.metadata?.model && (
                <div className="panel">
                  <div className="sec-label">Model Info</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {Object.entries(result.metadata.model).map(([k, v]) => (
                      <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        <span style={{ color: 'var(--text-tertiary)' }}>{k}</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <style>{`
        @media (max-width: 767px) {
          .anomaly-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </main>
  )
}
