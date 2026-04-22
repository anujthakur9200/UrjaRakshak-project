'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { api, ghiApi, AIStatus } from '@/lib/api'

const STATUS_COLORS: Record<string, string> = {
  balanced:               'var(--green)',
  minor_imbalance:        'var(--cyan)',
  significant_imbalance:  'var(--amber)',
  critical_imbalance:     'var(--red)',
  uncertain:              'var(--text-dim)',
  refused:                'var(--red)',
}

const RISK_COLORS: Record<string, string> = {
  LOW:      'var(--green)',
  MEDIUM:   'var(--cyan)',
  HIGH:     'var(--amber)',
  CRITICAL: 'var(--red)',
}

const SECURITY_QUESTIONS = [
  "What is your mother's maiden name?",
  "What was the name of your first pet?",
  "What city were you born in?",
  "What was the name of your primary school?",
  "What is your oldest sibling's middle name?",
  "What street did you grow up on?",
  "What was your childhood nickname?",
]

export default function AnalysisPage() {
  const [analyses, setAnalyses]   = useState<any[]>([])
  const [total, setTotal]         = useState(0)
  const [loading, setLoading]     = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [aiStatus, setAiStatus]   = useState<AIStatus | null>(null)

  // Per-analysis AI state
  const [aiResults, setAiResults]   = useState<Record<string, any>>({})
  const [aiLoading, setAiLoading]   = useState<Record<string, boolean>>({})
  const [expanded, setExpanded]     = useState<Record<string, boolean>>({})

  // Auth
  const [authEmail, setAuthEmail]     = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError]     = useState('')
  const [authMode, setAuthMode]       = useState<'login' | 'register'>('login')
  // Register extras (security question for password recovery)
  const [showRecovery, setShowRecovery] = useState(false)
  const [secQuestion, setSecQuestion] = useState(SECURITY_QUESTIONS[0])
  const [secAnswer, setSecAnswer]     = useState('')

  const fetchAnalyses = useCallback(async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const [listRes, statusRes] = await Promise.all([
        api.listAnalyses({ limit: 50 }),
        ghiApi.getStatus().catch(() => null),
      ])
      setAnalyses(listRes.items || [])
      setTotal(listRes.total || 0)
      setAiStatus(statusRes)
    } catch (e: any) {
      const msg: string = e.message || 'Failed to load analyses'
      if (
        msg.includes('401') || msg.includes('Authentication') ||
        msg.includes('Not authenticated') || msg.includes('403') || msg.includes('forbidden')
      ) {
        setFetchError('auth_required')
      } else {
        setFetchError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchAnalyses() }, [fetchAnalyses])

  const handleLogin = async () => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const res = await api.login(authEmail, authPassword)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setFetchError(null)
      fetchAnalyses()
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
      await api.register(authEmail, authPassword, 'analyst', {
        security_question: showRecovery ? secQuestion : undefined,
        security_answer: (showRecovery && secAnswer) ? secAnswer : undefined,
      })
      const res = await api.login(authEmail, authPassword)
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'analyst')
      setFetchError(null)
      fetchAnalyses()
    } catch (e: any) {
      setAuthError(e.message || 'Registration failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const runAiAnalysis = async (analysisId: string) => {
    setAiLoading(prev => ({ ...prev, [analysisId]: true }))
    try {
      const result = await ghiApi.interpret(analysisId)
      setAiResults(prev => ({ ...prev, [analysisId]: result }))
      setExpanded(prev => ({ ...prev, [analysisId]: true }))
    } catch (e: any) {
      setAiResults(prev => ({ ...prev, [analysisId]: { error: e.message } }))
      setExpanded(prev => ({ ...prev, [analysisId]: true }))
    } finally {
      setAiLoading(prev => ({ ...prev, [analysisId]: false }))
    }
  }

  const toggleExpand = (id: string) =>
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 'calc(100vh - 120px)' }}>
      <div className="spinner spinner-lg" />
      <span>Loading analyses…</span>
    </div>
  )

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header fade-in">
        <div className="page-eyebrow">Physics + AI</div>
        <h1 className="page-title">Analysis History</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <p className="page-desc" style={{ margin: 0 }}>
            Physics-validated energy analyses with AI interpretation.
            Each analysis runs GHI scoring and can be enriched with LLM insight.
          </p>
          {aiStatus && (
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              padding: '3px 8px',
              borderRadius: 'var(--r-sm)',
              background: aiStatus.configured ? 'rgba(0,212,255,0.08)' : 'rgba(255,255,255,0.04)',
              color: aiStatus.configured ? 'var(--cyan)' : 'var(--text-dim)',
              border: `1px solid ${aiStatus.configured ? 'rgba(0,212,255,0.2)' : 'var(--border-ghost)'}`,
              flexShrink: 0,
            }}>
              {aiStatus.configured
                ? `AI Live · ${aiStatus.preferred_provider}`
                : 'AI Offline Mode'}
            </span>
          )}
        </div>
      </div>

      {/* Auth gate */}
      {fetchError === 'auth_required' && (
        <div className="panel fade-in" style={{ marginBottom: 24, maxWidth: 460 }}>
          <div className="sec-label accent">Authentication Required</div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16, lineHeight: 1.6 }}>
            Analysis history requires an analyst account. Register instantly.
          </p>

          {/* Login / Register tabs */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', padding: 4 }}>
            {(['login', 'register'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => { setAuthMode(mode); setAuthError(''); setShowRecovery(false) }}
                style={{
                  flex: 1,
                  padding: '6px 4px',
                  borderRadius: 'var(--r-sm)',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: authMode === mode ? 700 : 400,
                  background: authMode === mode ? 'var(--cyan)' : 'transparent',
                  color: authMode === mode ? '#000' : 'var(--text-secondary)',
                  transition: 'background 0.18s, color 0.18s',
                  fontFamily: 'var(--font-ui)',
                  textTransform: 'capitalize',
                }}
              >
                {mode === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 14 }}>
            <input className="input" type="email" placeholder="Email address"
              value={authEmail} onChange={e => setAuthEmail(e.target.value)} autoComplete="email" />
            <input className="input" type="password" placeholder="Password (min 8 chars)"
              value={authPassword} onChange={e => setAuthPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (authMode === 'login' ? handleLogin() : handleRegister())}
              autoComplete={authMode === 'login' ? 'current-password' : 'new-password'} />
          </div>

          {/* Security question section (register only) */}
          {authMode === 'register' && (
            <div style={{ marginBottom: 14 }}>
              <button
                type="button"
                onClick={() => setShowRecovery(v => !v)}
                aria-expanded={showRecovery}
                aria-controls="recovery-section"
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 12, color: 'var(--cyan)', padding: 0, marginBottom: showRecovery ? 10 : 0,
                  fontFamily: 'var(--font-ui)',
                }}
              >
                {showRecovery ? '▾ Hide' : '▸ Add'} password recovery (security question)
              </button>
              {showRecovery && (
                <div id="recovery-section" style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '10px 12px', background: 'rgba(0,212,255,0.04)', borderRadius: 'var(--r-sm)', border: '1px solid rgba(0,212,255,0.12)' }}>
                  <div>
                    <label className="metric-label" style={{ marginBottom: 4 }}>Security Question</label>
                    <select
                      className="input"
                      value={secQuestion}
                      onChange={e => setSecQuestion(e.target.value)}
                      style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-primary)' }}
                    >
                      {SECURITY_QUESTIONS.map(q => (
                        <option key={q} value={q}>{q}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="metric-label" style={{ marginBottom: 4 }}>Security Answer</label>
                    <input
                      className="input"
                      value={secAnswer}
                      onChange={e => setSecAnswer(e.target.value)}
                      placeholder="Your answer (case-insensitive)"
                      autoComplete="off"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {authError && <div className="alert alert-err" style={{ marginBottom: 12 }}>{authError}</div>}

          <button
            onClick={authMode === 'login' ? handleLogin : handleRegister}
            disabled={authLoading || !authEmail || !authPassword}
            className="btn btn-primary"
            style={{ width: '100%', marginBottom: 10 }}
          >
            {authLoading
              ? (authMode === 'login' ? 'Signing in…' : 'Registering…')
              : (authMode === 'login' ? 'Sign In' : 'Create Account')}
          </button>

          {/* Forgot password link */}
          <div style={{ textAlign: 'center' }}>
            <Link
              href="/login?tab=forgot&next=/analysis"
              style={{ fontSize: 12, color: 'var(--text-dim)', textDecoration: 'underline' }}
            >
              Forgot your password?
            </Link>
          </div>
        </div>
      )}

      {fetchError && fetchError !== 'auth_required' && (
        <div className="alert alert-err fade-in" style={{ marginBottom: 20 }}>
          {fetchError}
        </div>
      )}

      {/* AI offline note */}
      {!fetchError && aiStatus && !aiStatus.configured && (
        <div className="alert alert-warn fade-in" style={{ marginBottom: 20 }}>
          <strong>AI running in offline mode.</strong>{' '}
          Set <code>ANTHROPIC_API_KEY</code>, <code>GROQ_API_KEY</code>, or <code>OPENAI_API_KEY</code> on the backend to enable live LLM analysis.
          Offline mode produces deterministic physics-based risk assessments without an LLM call.
        </div>
      )}

      {/* Empty state */}
      {!fetchError && !loading && analyses.length === 0 && (
        <div className="panel fade-in">
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <div className="empty-title">No analyses yet</div>
            <div className="empty-desc">
              Upload meter data to create your first physics-validated analysis,
              then return here to view AI interpretations.
            </div>
            <Link href="/upload" className="btn btn-primary" style={{ marginTop: 8 }}>
              Upload Meter Data →
            </Link>
          </div>
        </div>
      )}

      {/* Summary bar */}
      {!fetchError && analyses.length > 0 && (
        <>
          <div className="grid-4 fade-in stagger-1" style={{ marginBottom: 16 }}>
            <div className="metric-card">
              <div className="metric-label">Total Analyses</div>
              <div className="metric-value">{total}</div>
              <div className="metric-sub">physics-validated</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">AI Interpreted</div>
              <div className="metric-value">
                {Object.keys(aiResults).length + analyses.filter(a => a.has_ai).length}
              </div>
              <div className="metric-sub">this session + cached</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Needs Review</div>
              <div className="metric-value" style={{ color: 'var(--amber)' }}>
                {analyses.filter(a => a.requires_review).length}
              </div>
              <div className="metric-sub">high residual loss</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Critical</div>
              <div className="metric-value" style={{ color: 'var(--red)' }}>
                {analyses.filter(a => a.status === 'critical_imbalance').length}
              </div>
              <div className="metric-sub">critical imbalance</div>
            </div>
          </div>

          {/* Analysis list */}
          <div className="fade-in stagger-2">
            {analyses.map((analysis, idx) => {
              const aiResult = aiResults[analysis.id]
              const isAiLoading = aiLoading[analysis.id]
              const isExpanded = expanded[analysis.id]
              const ai = aiResult?.ai_interpretation
              const ghiSnap = aiResult?.ghi_snapshot || aiResult?.ghi

              return (
                <div
                  key={analysis.id}
                  className="panel"
                  style={{
                    marginBottom: 12,
                    borderLeft: `3px solid ${STATUS_COLORS[analysis.status] || 'var(--border-dim)'}`,
                    transition: 'all 0.2s',
                  }}
                >
                  {/* Top row */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: isExpanded ? 16 : 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--cyan)', fontWeight: 500 }}>
                          {analysis.substation_id}
                        </span>
                        <span className={`chip ${
                          analysis.status === 'balanced' ? 'chip-ok' :
                          analysis.status === 'critical_imbalance' ? 'chip-err' :
                          analysis.status === 'significant_imbalance' ? 'chip-warn' :
                          'chip-info'
                        }`}>
                          {analysis.status?.replace(/_/g, ' ')}
                        </span>
                        {analysis.requires_review && (
                          <span className="chip chip-warn">review needed</span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
                          {analysis.created_at?.slice(0, 16).replace('T', ' ')}
                        </span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)' }}>
                          In: {analysis.input_mwh != null ? analysis.input_mwh.toFixed(2) : '—'} MWh · Out: {analysis.output_mwh != null ? analysis.output_mwh.toFixed(2) : '—'} MWh
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, flexWrap: 'wrap' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 300, color: STATUS_COLORS[analysis.status] || 'var(--cyan)', letterSpacing: '-0.02em' }}>
                          {analysis.residual_pct != null ? analysis.residual_pct.toFixed(1) + '%' : '—'}
                        </div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>residual</div>
                      </div>

                      {/* AI button / status */}
                      {isAiLoading ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div className="spinner" style={{ width: 14, height: 14 }} />
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)' }}>Analyzing…</span>
                        </div>
                      ) : aiResult && !aiResult.error ? (
                        <button onClick={() => toggleExpand(analysis.id)} className="btn btn-secondary btn-sm">
                          {isExpanded ? 'Hide AI ↑' : 'Show AI ↓'}
                        </button>
                      ) : (
                        <button
                          onClick={() => runAiAnalysis(analysis.id)}
                          className="btn btn-primary btn-sm"
                        >
                          ✦ Run AI Analysis
                        </button>
                      )}
                    </div>
                  </div>

                  {/* AI error */}
                  {aiResult?.error && (
                    <div className="alert alert-warn" style={{ marginTop: 12, fontSize: 12 }}>
                      AI analysis failed: {aiResult.error}
                    </div>
                  )}

                  {/* AI results panel */}
                  {isExpanded && aiResult && !aiResult.error && (
                    <div style={{
                      borderTop: '1px solid var(--border-subtle)',
                      paddingTop: 16,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 12,
                    }}>
                      {/* Provider badge */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                        <div className="sec-label accent" style={{ marginBottom: 0 }}>AI Interpretation</div>
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          color: aiResult.ai_configured ? 'var(--green)' : 'var(--text-dim)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                        }}>
                          {aiResult.cached ? 'Cached · ' : ''}
                          {aiResult.ai_configured === false ? 'Offline mode' : `Live · ${aiResult.ai_provider || 'AI'}`}
                        </span>
                      </div>

                      {/* GHI + Risk KPIs */}
                      <div className="grid-3">
                        {ghiSnap && (
                          <div className="metric-card">
                            <div className="metric-label">GHI Score</div>
                            <div className="metric-value" style={{
                              color: ghiSnap.ghi_score >= 70 ? 'var(--green)' : ghiSnap.ghi_score >= 50 ? 'var(--amber)' : 'var(--red)',
                            }}>
                              {typeof ghiSnap.ghi_score === 'number' ? ghiSnap.ghi_score.toFixed(1) : ghiSnap.ghi_score}
                            </div>
                            <div className="metric-sub">{ghiSnap.classification}</div>
                          </div>
                        )}
                        {ai?.risk_level && (
                          <div className="metric-card">
                            <div className="metric-label">Risk Level</div>
                            <div className="metric-value" style={{ fontSize: 18, color: RISK_COLORS[ai.risk_level] || 'var(--cyan)' }}>
                              {ai.risk_level}
                            </div>
                            <div className="metric-sub">{ai.inspection_priority} priority</div>
                          </div>
                        )}
                        {ai?.estimated_investigation_scope && (
                          <div className="metric-card">
                            <div className="metric-label">Investigation Scope</div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                              {ai.estimated_investigation_scope.replace(/_/g, ' ')}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Primary hypothesis */}
                      {ai?.primary_infrastructure_hypothesis && (
                        <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)', padding: '12px 16px', border: '1px solid var(--border-ghost)' }}>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--cyan)', marginBottom: 6 }}>Primary Hypothesis</div>
                          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.65 }}>
                            {ai.primary_infrastructure_hypothesis}
                          </p>
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

                      <div className="grid-2">
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

                      {/* Inspection link if auto-created */}
                      {aiResult.inspection_auto_created && (
                        <div className="alert alert-warn" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>⚠ Inspection ticket auto-created for this analysis</span>
                          <Link href="/inspections" className="btn btn-secondary btn-sm">View →</Link>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Footer actions */}
      <div style={{ marginTop: 16, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button onClick={fetchAnalyses} className="btn btn-secondary btn-sm">↻ Refresh</button>
        <Link href="/upload" className="btn btn-secondary btn-sm">Upload Data →</Link>
        <Link href="/ghi" className="btn btn-secondary btn-sm">GHI Dashboard →</Link>
        <Link href="/inspections" className="btn btn-secondary btn-sm">Inspections →</Link>
      </div>
    </div>
  )
}
