'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import { parseApiError } from '@/lib/api'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

// ── Security questions ────────────────────────────────────────────────────

const SECURITY_QUESTIONS = [
  "What is your mother's maiden name?",
  "What was the name of your first pet?",
  "What city were you born in?",
  "What was the name of your primary school?",
  "What is your oldest sibling's middle name?",
  "What street did you grow up on?",
  "What was your childhood nickname?",
]

type Tab = 'login' | 'register' | 'forgot'

async function apiFetch<T>(path: string, body: object): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(
      `Cannot reach the backend at ${BASE}. Make sure the backend is running: cd backend && uvicorn app.main:app --reload --port 8000`
    )
  }
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(parseApiError(json) || `HTTP ${res.status}`)
  }
  return json as T
}

// ── Login form ────────────────────────────────────────────────────────────

function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiFetch<{ access_token: string; role: string; user_id: string }>(
        '/api/v1/auth/login',
        { email, password },
      )
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'viewer')
      localStorage.setItem('urjarakshak_user_id', res.user_id || '')
      onSuccess()
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Email</label>
        <input
          className="input"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          autoComplete="email"
        />
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Password</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          autoComplete="current-password"
        />
      </div>
      {error && (
        <div className="chip chip-err" style={{ fontSize: 12, padding: '6px 10px' }}>{error}</div>
      )}
      <button className="btn btn-primary" type="submit" disabled={loading} style={{ marginTop: 4 }}>
        {loading ? 'Signing in…' : 'Sign In'}
      </button>
    </form>
  )
}

// ── Register form ─────────────────────────────────────────────────────────

function RegisterForm({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [dob, setDob] = useState('')
  const [secQuestion, setSecQuestion] = useState(SECURITY_QUESTIONS[0])
  const [secAnswer, setSecAnswer] = useState('')
  const [showRecovery, setShowRecovery] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setInfo('')
    setLoading(true)
    try {
      await apiFetch('/api/v1/auth/register', {
        email,
        password,
        full_name: fullName || undefined,
        date_of_birth: dob || undefined,
        security_question: showRecovery ? secQuestion : undefined,
        security_answer: (showRecovery && secAnswer) ? secAnswer : undefined,
      })
      // Auto-login
      const res = await apiFetch<{ access_token: string; role: string; user_id: string }>(
        '/api/v1/auth/login',
        { email, password },
      )
      localStorage.setItem('urjarakshak_token', res.access_token)
      localStorage.setItem('urjarakshak_role', res.role || 'viewer')
      localStorage.setItem('urjarakshak_user_id', res.user_id || '')
      setInfo(res.role === 'admin' ? '🎉 Admin account created! Redirecting…' : 'Account created! Redirecting…')
      setTimeout(onSuccess, 800)
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Full Name (optional)</label>
        <input
          className="input"
          value={fullName}
          onChange={e => setFullName(e.target.value)}
          placeholder="Your name"
          autoComplete="name"
        />
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Email</label>
        <input
          className="input"
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          autoComplete="email"
        />
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Password <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>(min 8 chars)</span></label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          minLength={8}
          autoComplete="new-password"
        />
      </div>

      {/* Password recovery setup */}
      <div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setShowRecovery(v => !v)}
          style={{ fontSize: 12 }}
        >
          {showRecovery ? '▲ Hide' : '▼ Add'} Password Recovery (recommended)
        </button>
      </div>

      <AnimatePresence>
        {showRecovery && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 4 }}>
              <div style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.15)', fontSize: 12, color: 'var(--text-secondary)' }}>
                Set up recovery so you can reset your password if you forget it.
              </div>
              <div>
                <label className="metric-label" style={{ marginBottom: 6 }}>Date of Birth</label>
                <input
                  className="input"
                  type="date"
                  value={dob}
                  onChange={e => setDob(e.target.value)}
                />
              </div>
              <div>
                <label className="metric-label" style={{ marginBottom: 6 }}>Security Question</label>
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
                <label className="metric-label" style={{ marginBottom: 6 }}>Security Answer</label>
                <input
                  className="input"
                  value={secAnswer}
                  onChange={e => setSecAnswer(e.target.value)}
                  placeholder="Your answer (case-insensitive)"
                  autoComplete="off"
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && <div className="chip chip-err" style={{ fontSize: 12, padding: '6px 10px' }}>{error}</div>}
      {info && <div className="chip chip-ok" style={{ fontSize: 12, padding: '6px 10px' }}>{info}</div>}

      <button className="btn btn-primary" type="submit" disabled={loading} style={{ marginTop: 4 }}>
        {loading ? 'Creating account…' : 'Create Account'}
      </button>

      <p style={{ fontSize: 11, color: 'var(--text-dim)', textAlign: 'center', lineHeight: 1.5 }}>
        The first account created automatically becomes the Admin account.
      </p>
    </form>
  )
}

// ── Forgot password form ──────────────────────────────────────────────────

type ForgotStep = 'identify' | 'reset' | 'done'

function ForgotPasswordForm() {
  const [step, setStep] = useState<ForgotStep>('identify')
  const [email, setEmail] = useState('')
  const [dob, setDob] = useState('')
  const [secAnswer, setSecAnswer] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!dob && !secAnswer) {
      setError('Please enter your date of birth and/or security answer.')
      return
    }
    setLoading(true)
    try {
      await apiFetch('/api/v1/auth/forgot-password/verify', {
        email,
        date_of_birth: dob || undefined,
        security_answer: secAnswer || undefined,
      })
      setStep('reset')
    } catch (err: any) {
      setError(err.message || 'Verification failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (newPassword !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await apiFetch('/api/v1/auth/forgot-password/reset', {
        email,
        date_of_birth: dob || undefined,
        security_answer: secAnswer || undefined,
        new_password: newPassword,
      })
      setStep('done')
    } catch (err: any) {
      setError(err.message || 'Password reset failed')
    } finally {
      setLoading(false)
    }
  }

  if (step === 'done') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, alignItems: 'center', padding: '20px 0' }}>
        <div style={{ fontSize: 40 }}>✅</div>
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>Password Reset Successfully</div>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', textAlign: 'center' }}>
          Your password has been updated. You can now sign in with your new password.
        </p>
        <Link href="/login" className="btn btn-primary">Go to Sign In →</Link>
      </div>
    )
  }

  if (step === 'reset') {
    return (
      <form onSubmit={handleReset} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'rgba(5,232,154,0.05)', border: '1px solid rgba(5,232,154,0.2)', fontSize: 13, color: 'var(--green)' }}>
          Identity verified ✓ — enter your new password below.
        </div>
        <div>
          <label className="metric-label" style={{ marginBottom: 6 }}>New Password</label>
          <input className="input" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="••••••••" required minLength={8} />
        </div>
        <div>
          <label className="metric-label" style={{ marginBottom: 6 }}>Confirm New Password</label>
          <input className="input" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="••••••••" required />
        </div>
        {error && <div className="chip chip-err" style={{ fontSize: 12, padding: '6px 10px' }}>{error}</div>}
        <button className="btn btn-primary" type="submit" disabled={loading}>{loading ? 'Resetting…' : 'Reset Password'}</button>
      </form>
    )
  }

  // step === 'identify'
  return (
    <form onSubmit={handleVerify} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'rgba(255,186,48,0.06)', border: '1px solid rgba(255,186,48,0.2)', fontSize: 13, color: 'var(--amber)' }}>
        Verify your identity using the recovery information you set during registration.
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Email</label>
        <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Date of Birth (if set)</label>
        <input className="input" type="date" value={dob} onChange={e => setDob(e.target.value)} />
      </div>
      <div>
        <label className="metric-label" style={{ marginBottom: 6 }}>Security Answer (if set)</label>
        <input className="input" value={secAnswer} onChange={e => setSecAnswer(e.target.value)} placeholder="Your answer" autoComplete="off" />
      </div>
      {error && <div className="chip chip-err" style={{ fontSize: 12, padding: '6px 10px' }}>{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>{loading ? 'Verifying…' : 'Verify Identity'}</button>
    </form>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function LoginPage() {
  const router = useRouter()
  const [tab, setTab] = useState<Tab>('login')
  const [redirectTo, setRedirectTo] = useState('/upload')

  useEffect(() => {
    // If already logged in, redirect
    const token = localStorage.getItem('urjarakshak_token')
    if (token) {
      router.push('/upload')
      return
    }
    // Parse ?next= and ?tab= query params
    const params = new URLSearchParams(window.location.search)
    const next = params.get('next')
    if (next) setRedirectTo(next)
    const tabParam = params.get('tab') as Tab | null
    if (tabParam && ['login', 'register', 'forgot'].includes(tabParam)) {
      setTab(tabParam)
    }
  }, [router])

  function handleSuccess() {
    router.push(redirectTo)
  }

  const TAB_LABELS: { id: Tab; label: string }[] = [
    { id: 'login', label: 'Sign In' },
    { id: 'register', label: 'Register' },
    { id: 'forgot', label: 'Forgot Password?' },
  ]

  return (
    <div className="page grid-bg" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="scan-line" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ width: '100%', maxWidth: 460 }}
      >
        {/* Logo / brand */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>⚡</div>
          <h1 className="page-title" style={{ fontSize: 26, marginBottom: 4 }}>UrjaRakshak</h1>
          <p style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Grid Intelligence Platform</p>
        </div>

        <div className="panel" style={{ padding: '28px 28px 24px' }}>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', padding: 4 }}>
            {TAB_LABELS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  flex: 1,
                  padding: '7px 4px',
                  borderRadius: 'var(--r-sm)',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 12,
                  fontWeight: tab === t.id ? 700 : 400,
                  background: tab === t.id ? 'var(--cyan)' : 'transparent',
                  color: tab === t.id ? '#000' : 'var(--text-secondary)',
                  transition: 'background 0.18s, color 0.18s',
                  fontFamily: 'var(--font-ui)',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.18 }}
            >
              {tab === 'login' && <LoginForm onSuccess={handleSuccess} />}
              {tab === 'register' && <RegisterForm onSuccess={handleSuccess} />}
              {tab === 'forgot' && <ForgotPasswordForm />}
            </motion.div>
          </AnimatePresence>
        </div>

        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Link href="/guide" style={{ fontSize: 12, color: 'var(--text-dim)' }}>
            ← Back to How to Use
          </Link>
        </div>
      </motion.div>
    </div>
  )
}
