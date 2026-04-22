'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { api, ghiApi, UploadResult } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'

type Stage = 'idle' | 'auth' | 'uploading' | 'done' | 'error'

export default function UploadPage() {
  const [stage, setStage] = useState<Stage>('idle')
  const [file, setFile] = useState<File | null>(null)
  const [substationId, setSubstationId] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [result, setResult] = useState<UploadResult | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [dragging, setDragging] = useState(false)
  const [authError, setAuthError] = useState('')
  const [isAuthed, setIsAuthed] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)
  const [aiResult, setAiResult] = useState<any>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { setActiveSession, updateSessionDetail, updateSessionAI } = useAppStore()

  useEffect(() => {
    const token = localStorage.getItem('urjarakshak_token')
    if (token) {
      setIsAuthed(true)
      api.getStatsSummary().catch(() => {
        localStorage.removeItem('urjarakshak_token')
        localStorage.removeItem('urjarakshak_role')
        setIsAuthed(false)
      })
    }
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }, [])

  const handleLogin = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const res = await api.login(email, password)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'viewer')
      setIsAuthed(true)
      setStage('idle')
    } catch (e: any) {
      setAuthError(e.message || 'Login failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleRegister = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      await api.register(email, password, 'analyst')
      const res = await api.login(email, password)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setIsAuthed(true)
      setStage('idle')
    } catch (e: any) {
      setAuthError(e.message || 'Registration failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleUpload = async () => {
    if (!file) return
    if (!substationId.trim()) { setErrorMsg('Substation ID is required'); return }
    const token = localStorage.getItem('urjarakshak_token')
    if (!token) { setStage('auth'); return }

    setStage('uploading')
    setErrorMsg('')
    setAiResult(null)
    setAiError(null)
    try {
      const res = await api.uploadMeterData(file, substationId.trim())
      setResult(res)
      setStage('done')

      // Populate global SSOT store with this analysis session
      if (res.analysis_id) {
        const session = {
          analysisId: res.analysis_id,
          batchId: res.batch_id,
          substationId: res.substation_id,
          filename: res.filename,
          rowsParsed: res.rows_parsed,
          stats: res.summary,
          anomalySample: res.anomaly_sample,
          createdAt: new Date().toISOString(),
          detail: null,
          aiInterpretation: null,
          aiStatus: 'idle' as const,
          aiError: null,
        }
        setActiveSession(session)

        // Fetch full analysis detail in background
        api.getAnalysis(res.analysis_id).then((detail) => {
          updateSessionDetail(res.analysis_id!, detail)
        }).catch((err) => {
          console.warn('Could not fetch analysis detail:', err?.message)
        })

        // Auto-fetch AI interpretation
        setAiLoading(true)
        updateSessionAI(res.analysis_id, null, 'loading')
        try {
          const ai = await ghiApi.interpret(res.analysis_id)
          setAiResult(ai)
          updateSessionAI(res.analysis_id, ai, 'ready')
        } catch (err: any) {
          console.warn('AI interpretation unavailable:', err?.message)
          const errMsg = 'AI analysis unavailable — the backend may not have an AI provider configured.'
          setAiError(errMsg)
          updateSessionAI(res.analysis_id, null, 'error', errMsg)
        } finally {
          setAiLoading(false)
        }
      }
    } catch (e: any) {
      const msg: string = e.message || 'Upload failed'
      if (msg.includes('401') || msg.includes('expired') || msg.includes('Authentication')) {
        localStorage.removeItem('urjarakshak_token')
        setIsAuthed(false)
        setStage('auth')
        setAuthError('Session expired — please log in again.')
      } else {
        setErrorMsg(msg)
        setStage('error')
      }
    }
  }

  const reset = () => {
    setStage('idle')
    setFile(null)
    setResult(null)
    setErrorMsg('')
    setAiResult(null)
    setAiError(null)
  }

  const formatSize = (bytes: number) =>
    bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`

  return (
    <div className="page" style={{ maxWidth: 900 }}>

      {/* Header */}
      <div className="page-header fade-in">
        <div className="page-eyebrow">Data Ingestion</div>
        <h1 className="page-title">Meter Data Upload</h1>
        <p className="page-desc">
          Upload CSV or Excel meter readings. Per-meter Z-score anomaly detection runs automatically.
          Results appear in your dashboard immediately.
        </p>
      </div>

      {/* Format spec */}
      <div className="panel fade-in stagger-1" style={{ marginBottom: 24 }}>
        <div className="sec-label">Expected File Format</div>
        <div className="grid-2">
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--cyan)', marginBottom: 10 }}>Required Columns</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                ['timestamp', 'YYYY-MM-DD HH:MM:SS'],
                ['meter_id', 'Unique meter identifier'],
                ['energy_kwh', 'Numeric, positive'],
              ].map(([col, desc]) => (
                <div key={col} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cyan)', minWidth: 110, flexShrink: 0 }}>{col}</code>
                  <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{desc}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--cyan)', marginBottom: 10 }}>Example</div>
            <div className="code-block" style={{ fontSize: 11 }}>
              <div><span className="code-cyan">timestamp</span>,<span className="code-cyan">meter_id</span>,<span className="code-cyan">energy_kwh</span></div>
              <div>2026-01-01 00:00:00,MTR001,12.5</div>
              <div>2026-01-01 01:00:00,MTR001,13.1</div>
              <div>2026-01-01 00:00:00,MTR002,8.2</div>
            </div>
            <div style={{ marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
              .csv · .xlsx · .xls — max 50,000 rows / 10 MB
            </div>
          </div>
        </div>
      </div>

      {/* Auth Gate */}
      {stage === 'auth' && (
        <div className="panel fade-in" style={{ marginBottom: 24, maxWidth: 440 }}>
          <div className="sec-label accent">Authentication Required</div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 1.6 }}>
            Upload requires an analyst account. Register instantly for free.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <input
              className="input"
              type="email"
              placeholder="Email address"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="email"
              inputMode="email"
            />
            <input
              className="input"
              type="password"
              placeholder="Password (min 8 chars)"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              autoComplete="current-password"
            />
          </div>
          {authError && <div className="alert alert-err" style={{ marginBottom: 14 }}>{authError}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleLogin}
              disabled={authLoading || !email || !password}
              className="btn btn-primary"
              style={{ flex: 1 }}
            >
              {authLoading ? 'Logging in…' : 'Login'}
            </button>
            <button
              onClick={handleRegister}
              disabled={authLoading || !email || !password}
              className="btn btn-secondary"
              style={{ flex: 1 }}
            >
              Register
            </button>
          </div>
        </div>
      )}

      {/* Logged-in status */}
      {isAuthed && stage !== 'auth' && (
        <div className="alert alert-ok fade-in" style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>✓ Authenticated — ready to upload</span>
          <button
            onClick={() => {
              localStorage.removeItem('urjarakshak_token')
              localStorage.removeItem('urjarakshak_role')
              setIsAuthed(false)
            }}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'currentColor', background: 'none', border: 'none', cursor: 'pointer', opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em' }}
          >
            Log out
          </button>
        </div>
      )}

      {/* Upload form */}
      {(stage === 'idle' || stage === 'error') && (
        <div className="fade-in stagger-2">
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', display: 'block', marginBottom: 8 }}>
              Substation ID *
            </label>
            <input
              className="input"
              type="text"
              placeholder="e.g. SS001"
              value={substationId}
              onChange={e => setSubstationId(e.target.value)}
              style={{ maxWidth: 300 }}
            />
          </div>

          {/* Drop zone */}
          <div
            onClick={() => inputRef.current?.click()}
            onDrop={onDrop}
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            style={{
              border: `2px dashed ${dragging ? 'var(--cyan)' : file ? 'rgba(0,212,255,0.3)' : 'var(--border-dim)'}`,
              borderRadius: 'var(--r-lg)',
              padding: 'clamp(24px, 5vw, 40px) 24px',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragging ? 'rgba(0,212,255,0.04)' : file ? 'rgba(0,212,255,0.02)' : 'var(--bg-panel)',
              transition: 'all 0.2s',
              marginBottom: 20,
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f) }}
            />
            {file ? (
              <div>
                <div style={{ fontSize: 24, marginBottom: 8 }}>📄</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--cyan)', marginBottom: 4 }}>{file.name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>{formatSize(file.size)}</div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 28, marginBottom: 12, opacity: 0.5 }}>📁</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                  Drop CSV or Excel file here, or tap to browse
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>.csv · .xlsx · .xls — max 10 MB</div>
              </div>
            )}
          </div>

          {errorMsg && <div className="alert alert-err" style={{ marginBottom: 16 }}>{errorMsg}</div>}

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              onClick={handleUpload}
              disabled={!file || !substationId.trim()}
              className="btn btn-primary btn-lg btn-block-mobile"
            >
              {file && substationId.trim() ? 'Run Analysis →' : 'Select file & substation first'}
            </button>
            {file && (
              <button onClick={() => setFile(null)} className="btn btn-secondary">Clear</button>
            )}
          </div>
        </div>
      )}

      {/* Processing */}
      {stage === 'uploading' && (
        <div className="loading-state">
          <div className="spinner spinner-lg" />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--cyan)', marginBottom: 6 }}>Processing {file?.name}</div>
            <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Parsing → Z-score detection → Storing to database…</div>
          </div>
        </div>
      )}

      {/* Results */}
      {stage === 'done' && result && (
        <div className="fade-in">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
            <div className="sec-label accent" style={{ marginBottom: 0 }}>Analysis Complete</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button onClick={reset} className="btn btn-secondary btn-sm">Upload Another</button>
              <Link href="/dashboard" className="btn btn-primary btn-sm">View Dashboard →</Link>
            </div>
          </div>

          <div className="grid-4" style={{ marginBottom: 20 }}>
            <ResultCard label="Rows Processed" value={result.rows_parsed.toLocaleString()} />
            <ResultCard label="Total Energy" value={`${result.summary.total_energy_kwh.toLocaleString()} kWh`} />
            <ResultCard
              label="Anomalies"
              value={result.summary.anomalies_detected.toString()}
              sub={`${result.summary.anomaly_rate_pct}% rate`}
              alert={result.summary.anomalies_detected > 0}
            />
            <ResultCard
              label="Confidence"
              value={`${(result.summary.confidence_score * 100).toFixed(1)}%`}
            />
          </div>

          {result.rows_skipped > 0 && (
            <div className="alert alert-warn" style={{ marginBottom: 16 }}>
              {result.rows_skipped} rows skipped (invalid timestamps, negative values, or missing meter_id)
            </div>
          )}

          {(result.anomaly_sample?.length ?? 0) > 0 && (
            <div className="panel panel-flush" style={{ marginBottom: 20 }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
                <div className="sec-label" style={{ marginBottom: 0 }}>Top Anomalous Readings (by Z-score)</div>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Meter ID</th>
                      <th>Timestamp</th>
                      <th>Actual kWh</th>
                      <th className="hide-mobile">Expected kWh</th>
                      <th>Z-Score</th>
                      <th className="hide-mobile">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.anomaly_sample?.map((row, i) => (
                      <tr key={i}>
                        <td style={{ color: 'var(--cyan)' }}>{row.meter_id}</td>
                        <td>{row.timestamp.replace('T', ' ').slice(0, 16)}</td>
                        <td>{row.energy_kwh.toFixed(2)}</td>
                        <td className="hide-mobile">{row.expected_kwh?.toFixed(2) ?? '—'}</td>
                        <td style={{ color: Math.abs(row.z_score) > 3 ? 'var(--red)' : 'var(--amber)' }}>
                          {row.z_score > 0 ? '+' : ''}{row.z_score?.toFixed(2)}σ
                        </td>
                        <td className="hide-mobile" style={{ color: 'var(--text-tertiary)' }}>
                          {(row.anomaly_score * 100).toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* AI Analysis Results */}
          {(aiLoading || aiResult || aiError) && (
            <div className="panel fade-in" style={{ marginBottom: 20, borderLeft: '3px solid var(--cyan)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div className="sec-label accent" style={{ marginBottom: 0 }}>AI Grid Analysis</div>
                {aiLoading && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><div className="spinner" style={{ width: 16, height: 16 }} /><span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>Analyzing…</span></div>}
                {aiResult && !aiLoading && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: aiResult.ai_configured === false ? 'var(--text-dim)' : 'var(--green)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{aiResult.ai_configured === false ? 'Offline Mode' : `Live · ${aiResult.ai_provider || 'AI'}`}</span>}
              </div>

              {aiError && <div className="alert alert-warn" style={{ marginBottom: 12 }}>{aiError}</div>}

              {aiResult && (() => {
                const ai = aiResult.ai_interpretation
                const ghiSnap = aiResult.ghi_snapshot || aiResult.ghi
                const ghiScore = ghiSnap?.ghi_score ?? ghiSnap?.ghi
                const ghiClass = ghiSnap?.classification

                const GHI_COLORS: Record<string, string> = { HEALTHY: 'var(--green)', STABLE: 'var(--cyan)', DEGRADED: 'var(--amber)', CRITICAL: '#FF6B35', SEVERE: 'var(--red)' }
                const RISK_COLORS: Record<string, string> = { LOW: 'var(--green)', MEDIUM: 'var(--cyan)', HIGH: 'var(--amber)', CRITICAL: 'var(--red)', SEVERE: 'var(--red)' }

                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {/* GHI + Risk row */}
                    <div className="grid-3">
                      {ghiScore != null && (
                        <div className="metric-card">
                          <div className="metric-label">GHI Score</div>
                          <div className="metric-value" style={{ color: GHI_COLORS[ghiClass] || 'var(--cyan)' }}>{typeof ghiScore === 'number' ? ghiScore.toFixed(1) : ghiScore}</div>
                          <div className="metric-sub">{ghiClass || '—'}</div>
                        </div>
                      )}
                      {ai?.risk_level && (
                        <div className="metric-card">
                          <div className="metric-label">Risk Level</div>
                          <div className="metric-value" style={{ fontSize: 20, color: RISK_COLORS[ai.risk_level] || 'var(--cyan)' }}>{ai.risk_level}</div>
                          <div className="metric-sub">{ai.inspection_priority || '—'} priority</div>
                        </div>
                      )}
                      {aiResult.inspection_auto_created && (
                        <div className="metric-card">
                          <div className="metric-label">Inspection</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--amber)', marginTop: 4 }}>Auto-Created</div>
                          <div className="metric-sub"><Link href="/inspections" style={{ color: 'var(--cyan)' }}>View ticket →</Link></div>
                        </div>
                      )}
                    </div>

                    {/* AI hypothesis */}
                    {ai?.primary_infrastructure_hypothesis && (
                      <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '12px 16px', border: '1px solid var(--border-ghost)' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--cyan)', marginBottom: 6 }}>Primary Hypothesis</div>
                        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.65 }}>{ai.primary_infrastructure_hypothesis}</p>
                      </div>
                    )}

                    {/* Recommended actions */}
                    {ai?.recommended_actions && ai.recommended_actions.length > 0 && (
                      <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '12px 16px', border: '1px solid var(--border-ghost)' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--amber)', marginBottom: 8 }}>Recommended Actions</div>
                        <ul style={{ margin: 0, paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {ai.recommended_actions.map((action: string, i: number) => (
                            <li key={i} style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{action}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Confidence commentary */}
                    {ai?.confidence_commentary && (
                      <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '12px 16px', border: '1px solid var(--border-ghost)' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 6 }}>Confidence Assessment</div>
                        <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: 0, lineHeight: 1.6 }}>{ai.confidence_commentary}</p>
                      </div>
                    )}

                    {/* Trend assessment */}
                    {ai?.trend_assessment && (
                      <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '12px 16px', border: '1px solid var(--border-ghost)' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 6 }}>Trend Assessment</div>
                        <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: 0, lineHeight: 1.6 }}>{ai.trend_assessment}</p>
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>
          )}

          <div className="panel" style={{ background: 'rgba(0,212,255,0.03)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--cyan)', marginBottom: 6 }}>Ethics Guardrail</div>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.7 }}>{result.ethics_note}</p>
          </div>
        </div>
      )}
    </div>
  )
}

function ResultCard({ label, value, sub, alert }: { label: string; value: string; sub?: string; alert?: boolean }) {
  return (
    <div className="metric-card" style={{ textAlign: 'center' }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ fontSize: 'clamp(20px, 3vw, 28px)', color: alert ? 'var(--amber)' : 'var(--cyan)' }}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}
