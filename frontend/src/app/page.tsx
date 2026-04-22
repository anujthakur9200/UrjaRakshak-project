'use client'

import Link from 'next/link'
import { useEffect, useState, useRef } from 'react'

// ── Animated typewriter hook ───────────────────────────────────────────────
function useTypewriter(phrases: string[], typingSpeed = 60, pauseMs = 2200) {
  const [displayed, setDisplayed] = useState('')
  const [phraseIdx, setPhraseIdx] = useState(0)
  const [charIdx, setCharIdx] = useState(0)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    const current = phrases[phraseIdx]
    let timeout: ReturnType<typeof setTimeout>

    if (!deleting && charIdx <= current.length) {
      timeout = setTimeout(() => {
        setDisplayed(current.slice(0, charIdx))
        setCharIdx(c => c + 1)
      }, typingSpeed)
    } else if (!deleting && charIdx > current.length) {
      timeout = setTimeout(() => setDeleting(true), pauseMs)
    } else if (deleting && charIdx >= 0) {
      timeout = setTimeout(() => {
        setDisplayed(current.slice(0, charIdx))
        setCharIdx(c => c - 1)
      }, typingSpeed / 2)
    } else {
      setDeleting(false)
      setPhraseIdx(i => (i + 1) % phrases.length)
    }
    return () => clearTimeout(timeout)
  }, [charIdx, deleting, phraseIdx, phrases, typingSpeed, pauseMs])

  return displayed
}

// ── Animated counter hook ──────────────────────────────────────────────────
function useCounter(target: number, duration = 1600, start = false) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!start) return
    let startTime: number | null = null
    const step = (ts: number) => {
      if (!startTime) startTime = ts
      const progress = Math.min((ts - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out-cubic
      setValue(Math.round(eased * target))
      if (progress < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [target, duration, start])
  return value
}

export default function Home() {
  const [ghiScore, setGhiScore] = useState<number | null>(null)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [statsVisible, setStatsVisible] = useState(false)
  const statsRef = useRef<HTMLDivElement>(null)

  const typewriterText = useTypewriter([
    'Thermodynamics',
    'Physics Truth',
    'Grid Intelligence',
    'Anomaly Detection',
  ])

  useEffect(() => {
    const base = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
    fetch(`${base}/health`)
      .then(r => { setBackendOk(r.ok); return r.json() })
      .catch(() => setBackendOk(false))
    fetch(`${base}/api/v1/ai/ghi/dashboard`)
      .then(r => r.json())
      .then(d => { if (d?.avg_ghi_all_time != null) setGhiScore(d.avg_ghi_all_time) })
      .catch(() => {})
  }, [])

  // Intersection observer for stats section
  useEffect(() => {
    const el = statsRef.current
    if (!el) return
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setStatsVisible(true); obs.disconnect() }
    }, { threshold: 0.3 })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const detectionAccuracy = useCounter(99, 1600, statsVisible)
  const gateEnsemble = useCounter(3, 1400, statsVisible)
  const auditCompliance = useCounter(100, 1800, statsVisible)
  const liveMonitoring = useCounter(24, 1200, statsVisible)

  const principles = [
    {
      icon: '⚛',
      color: 'cyan' as const,
      title: 'Physics-first',
      desc: 'Every result is grounded in First-Law thermodynamics. The engine refuses to output when confidence is insufficient.',
    },
    {
      icon: '🔍',
      color: 'blue' as const,
      title: 'Explainable',
      desc: 'Every formula is documented. Fourier decomposition shown. No black-box outputs. Engineers can verify every calculation.',
    },
    {
      icon: '🛡',
      color: 'green' as const,
      title: 'Hard to game',
      desc: '3-gate anomaly logic: physics gate + Z-score + Isolation Forest. All three must agree before flagging.',
    },
    {
      icon: '⚖',
      color: 'violet' as const,
      title: 'Ethics-aware',
      desc: 'No individual attribution. Infrastructure-scope only. SHA-256 audit chain on every action.',
    },
  ]

  const stack = [
    { icon: '⚡', color: 'cyan' as const,   label: 'Physics Truth Engine', sub: 'PTE v2.1',            desc: 'First-law thermodynamics. I²R losses per component. Temperature-corrected resistance. Uncertainty quantification.' },
    { icon: '📊', color: 'green' as const,  label: 'Grid Health Index',    sub: 'GHI — 0 to 100',      desc: 'Composite score: PBS×35% + ASS×20% + CS×15% + TSS×15% + DIS×15%. Classifies HEALTHY → SEVERE.' },
    { icon: '🔎', color: 'amber' as const,  label: 'Anomaly Detection',    sub: 'IF + Z-Score ensemble', desc: 'Isolation Forest trained on synthetic grid data. Statistical z-score gate. Per-meter rolling baselines.' },
    { icon: '🌡', color: 'red' as const,    label: 'Transformer Aging',    sub: 'IEC 60076-7',          desc: 'Arrhenius thermal aging model. Hot-spot temperature, aging factor V, failure probability over 12 months.' },
    { icon: '📉', color: 'blue' as const,   label: 'Drift Detection',      sub: 'PSI + K-S test',       desc: 'Population Stability Index and Kolmogorov-Smirnov test detect when the ML model has become stale.' },
    { icon: '📡', color: 'violet' as const, label: 'Live Streaming',       sub: 'SSE — no Redis',       desc: 'Server-Sent Events with in-memory queues per substation. Per-meter stability scores updated on every event.' },
  ]

  const colorMap = {
    cyan:   { text: 'var(--cyan)',   bg: 'var(--cyan-dim)',   border: 'rgba(10,240,255,0.2)'  },
    green:  { text: 'var(--green)',  bg: 'var(--green-dim)',  border: 'rgba(5,232,154,0.2)'   },
    amber:  { text: 'var(--amber)',  bg: 'var(--amber-dim)',  border: 'rgba(255,186,48,0.2)'  },
    red:    { text: 'var(--red)',    bg: 'var(--red-dim)',    border: 'rgba(255,61,85,0.2)'   },
    blue:   { text: 'var(--blue)',   bg: 'var(--blue-dim)',   border: 'rgba(77,148,255,0.2)'  },
    violet: { text: 'var(--violet)', bg: 'var(--violet-dim)', border: 'rgba(155,114,255,0.2)' },
  }

  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: 'clamp(52px,6.5vw,88px) var(--page-pad-x) 0' }}>

      {/* Hero */}
      <section style={{ paddingBottom: 80 }}>
        <div className="fade-in stagger-1" style={{ marginBottom: 20 }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.14em',
            textTransform: 'uppercase', color: 'var(--cyan)',
          }}>
            <span className="key key-cyan">v2.3</span>
            Physics Truth Engine Active
          </span>
        </div>

        <h1 className="fade-in stagger-2" style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(34px, 5.5vw, 66px)',
          fontWeight: 700,
          letterSpacing: '-0.025em',
          lineHeight: 1.06,
          color: 'var(--text-primary)',
          maxWidth: 800,
          marginBottom: 26,
        }}>
          Grid Intelligence<br />
          Meets{' '}
          <span style={{
            background: 'linear-gradient(120deg, var(--cyan), var(--blue))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            display: 'inline-block',
            minWidth: 'clamp(200px, 28vw, 420px)',
          }}>
            {typewriterText}
            <span className="typewriter-cursor" style={{ background: 'var(--cyan)', WebkitTextFillColor: 'initial' }} />
          </span>
        </h1>

        <p className="fade-in stagger-3" style={{
          fontSize: 17, color: 'var(--text-secondary)',
          maxWidth: 560, marginBottom: 44, lineHeight: 1.75,
          fontWeight: 400,
        }}>
          A physics-grounded system for energy integrity analysis.
          First Law of Thermodynamics as ground truth, not heuristics.
          Designed for transparency, explainability, and human oversight.
        </p>

        <div className="fade-in stagger-4" style={{ display: 'flex', gap: 12, marginBottom: 68, flexWrap: 'wrap', alignItems: 'center' }}>
          <Link href="/dashboard" className="btn btn-primary btn-lg btn-animated">
            <span>Launch Dashboard</span>
            <span>→</span>
          </Link>
          <Link href="/upload" className="btn btn-secondary btn-lg">Upload Data</Link>
          <Link href="/guide" className="btn btn-secondary btn-lg">How to Use</Link>
          <Link href="/docs" className="btn btn-secondary btn-lg">Documentation</Link>
        </div>

        {/* Live status strip */}
        <div className="fade-in stagger-5" style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <div className={`live-pill ${backendOk === null ? '' : backendOk ? 'online' : 'offline'}`}>
            <span className="live-dot" />
            Backend {backendOk === null ? 'connecting' : backendOk ? 'online' : 'offline'}
          </div>
          {ghiScore !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
              Fleet GHI:
              <span className="key" style={{
                color: ghiScore >= 70 ? 'var(--green)' : ghiScore >= 50 ? 'var(--amber)' : 'var(--red)',
                background: ghiScore >= 70 ? 'var(--green-dim)' : ghiScore >= 50 ? 'var(--amber-dim)' : 'var(--red-dim)',
                borderColor: ghiScore >= 70 ? 'rgba(5,232,154,0.3)' : ghiScore >= 50 ? 'rgba(255,186,48,0.3)' : 'rgba(255,61,85,0.3)',
              }}>
                {ghiScore}
              </span>
            </div>
          )}
        </div>
      </section>

      {/* Stats counters */}
      <section ref={statsRef} style={{ paddingBottom: 80, borderTop: '1px solid var(--border-subtle)', paddingTop: 56 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 24 }}>
          {[
            { value: detectionAccuracy, suffix: '%', label: 'Detection Accuracy', color: 'var(--cyan)' },
            { value: gateEnsemble,      suffix: '',  label: 'Gate Ensemble',      color: 'var(--green)' },
            { value: auditCompliance,   suffix: '',  label: 'Audit Compliance',   color: 'var(--violet)' },
            { value: liveMonitoring,    suffix: '/7', label: 'Live Monitoring',   color: 'var(--amber)' },
          ].map((s, i) => (
            <div key={i} className="panel" style={{ textAlign: 'center', padding: '24px 16px' }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 'clamp(28px,4vw,44px)', fontWeight: 300,
                color: s.color, lineHeight: 1, letterSpacing: '-0.03em', marginBottom: 8,
              }}>
                {statsVisible ? s.value : 0}{s.suffix}
              </div>
              <div style={{ fontFamily: 'var(--font-ui)', fontSize: 12, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Principles */}
      <section style={{ paddingBottom: 80, borderTop: '1px solid var(--border-subtle)', paddingTop: 56 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, marginBottom: 36,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--text-tertiary)' }}>
            Design Principles
          </div>
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }} />
        </div>
        <div className="grid-4">
          {principles.map(p => {
            const c = colorMap[p.color]
            return (
              <div key={p.title} className="panel panel-glow slide-up" style={{ background: 'var(--bg-panel)' }}>
                <div className="icon-circle icon-circle-md" style={{
                  background: c.bg,
                  border: `1px solid ${c.border}`,
                  marginBottom: 16,
                  transition: 'transform var(--t-base), box-shadow var(--t-base)',
                }}>
                  {p.icon}
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8, letterSpacing: '-0.01em' }}>{p.title}</div>
                <div style={{ fontSize: 13.5, color: 'var(--text-secondary)', lineHeight: 1.68 }}>{p.desc}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Stack */}
      <section style={{ paddingBottom: 80, borderTop: '1px solid var(--border-subtle)', paddingTop: 56 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, marginBottom: 36,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--text-tertiary)' }}>
            What&apos;s inside
          </div>
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }} />
        </div>
        <div className="grid-3">
          {stack.map(s => {
            const c = colorMap[s.color]
            return (
              <div key={s.label} className="panel panel-glow">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                  <div className="icon-circle icon-circle-sm" style={{ background: c.bg, border: `1px solid ${c.border}` }}>
                    {s.icon}
                  </div>
                  <span className="chip" style={{ color: c.text, background: c.bg, borderColor: c.border }}>{s.sub}</span>
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8, letterSpacing: '-0.01em' }}>{s.label}</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.68 }}>{s.desc}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* CTA */}
      <section style={{ paddingBottom: 88, borderTop: '1px solid var(--border-subtle)', paddingTop: 56, textAlign: 'center' }}>
        <h2 className="glow-text" style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(24px, 3.2vw, 38px)',
          fontWeight: 700,
          letterSpacing: '-0.02em',
          marginBottom: 16,
          color: 'var(--text-primary)',
        }}>
          Start with sample data
        </h2>
        <p style={{ fontSize: 15, color: 'var(--text-secondary)', maxWidth: 500, margin: '0 auto 32px', lineHeight: 1.72 }}>
          Upload the included sample CSV and see physics validation, anomaly detection, and GHI scoring in action in under 2 minutes.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link href="/upload" className="btn btn-primary btn-lg">Upload Sample CSV →</Link>
          <Link href="/guide" className="btn btn-secondary btn-lg">📋 How to Use</Link>
          <Link href="/dashboard" className="btn btn-secondary btn-lg">View Dashboard</Link>
        </div>
      </section>

      <style>{`
        @keyframes cursorBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}
