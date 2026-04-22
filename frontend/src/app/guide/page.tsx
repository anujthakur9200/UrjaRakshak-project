'use client'

import { useState } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'

// ── Step data ─────────────────────────────────────────────────────────────

interface GuideStep {
  id: number
  icon: string
  title: string
  color: 'cyan' | 'green' | 'amber' | 'blue' | 'violet' | 'red'
  time: string
  description: string
  actions: { label: string; href: string; primary?: boolean }[]
  tips: string[]
}

const GUIDE_STEPS: GuideStep[] = [
  {
    id: 1,
    icon: '🚀',
    title: 'Start Here — Create Your Account',
    color: 'cyan',
    time: '~1 min',
    description:
      'UrjaRakshak uses JWT-based authentication. You need an account to run analyses, see results, and use the AI assistant. Register once and your data is stored securely.',
    actions: [
      { label: 'Go to Login / Register', href: '/login', primary: true },
    ],
    tips: [
      'Use any email and a strong password.',
      'Your session token is stored in localStorage — logout to clear it.',
      'The demo account (demo@urjarakshak.in / demo1234) works for read-only exploration.',
    ],
  },
  {
    id: 2,
    icon: '📤',
    title: 'Upload Meter Data',
    color: 'blue',
    time: '~2 min',
    description:
      'Upload a CSV file with meter readings. Each row represents one reading from one meter at one point in time. The system accepts the standard UrjaRakshak CSV format.',
    actions: [
      { label: 'Upload Data', href: '/upload', primary: true },
    ],
    tips: [
      'Required columns: substation_id, meter_id, timestamp, energy_kwh.',
      'Optional columns: input_mwh, output_mwh, power_kw, voltage_v.',
      'Download the sample CSV from the Upload page to see the exact format.',
      'Data is validated immediately — you will see column errors before anything runs.',
    ],
  },
  {
    id: 3,
    icon: '⚡',
    title: 'Run Physics Analysis',
    color: 'amber',
    time: '~30 sec',
    description:
      'The Physics Truth Engine applies First-Law thermodynamics to your data. It calculates input energy, output energy, expected losses (I²R + transformer), and the residual unexplained gap.',
    actions: [
      { label: 'Go to Analysis', href: '/analysis', primary: true },
      { label: 'View Dashboard', href: '/dashboard' },
    ],
    tips: [
      'Press "Run Analysis" on the Analysis page after uploading data.',
      'The engine needs at least one substation with both input and output readings.',
      'A confidence score < 50% will block AI interpretation — collect more data first.',
      'Balance statuses: balanced → minor_imbalance → significant_imbalance → critical_imbalance.',
    ],
  },
  {
    id: 4,
    icon: '🔎',
    title: 'Inspect Anomaly Detection',
    color: 'red',
    time: '~2 min',
    description:
      'The ML Anomaly Detection engine uses an Isolation Forest + Z-score ensemble. Each reading is scored independently. Three gates must all agree before an anomaly is flagged.',
    actions: [
      { label: 'Anomaly Dashboard', href: '/anomaly', primary: true },
      { label: 'Run Anomaly Detection', href: '/analysis' },
    ],
    tips: [
      'Gate 1 — Physics gate: residual must exceed expected technical loss.',
      'Gate 2 — Z-score: reading must be ≥ 2.5σ from the rolling meter baseline.',
      'Gate 3 — Isolation Forest: anomaly score must exceed threshold.',
      'Anomaly scores range from 0 (normal) to 1 (highly anomalous).',
      'Low confidence or sparse data will return "refused" — not a bug.',
    ],
  },
  {
    id: 5,
    icon: '📊',
    title: 'Check Grid Health Index',
    color: 'green',
    time: '~1 min',
    description:
      'The Grid Health Index (GHI) is a composite score from 0 to 100 that summarises substation health. It combines physics balance, anomaly stability, confidence, trend stability, and data integrity.',
    actions: [
      { label: 'Dashboard — GHI Panel', href: '/dashboard', primary: true },
    ],
    tips: [
      'GHI = PBS×35% + ASS×20% + CS×15% + TSS×15% + DIS×15%.',
      '80–100: Healthy. 60–79: Stable. 40–59: Degraded. 20–39: Critical. 0–19: Severe.',
      'GHI is computed after every physics analysis automatically.',
      'Fleet GHI is the average across all substations in your organisation.',
    ],
  },
  {
    id: 6,
    icon: '🤖',
    title: 'Ask the AI Assistant',
    color: 'violet',
    time: '~1 min',
    description:
      'The AI Grid Assistant answers questions about your data in natural language. It is context-aware: it fetches the latest analysis for the substation you name before answering.',
    actions: [
      { label: 'Open AI Chat', href: '/ai-chat', primary: true },
    ],
    tips: [
      'Type a substation ID in the top input, then ask your question.',
      'Try: "What anomalies were detected today?" or "Explain the energy loss."',
      'The AI uses OpenAI GPT-4o-mini or Anthropic Claude when API keys are set.',
      'Without an API key, the assistant runs in offline mode with physics-based answers.',
      'All AI outputs are infrastructure-scoped — it will never name individuals.',
    ],
  },
  {
    id: 7,
    icon: '📡',
    title: 'Watch Live Meter Stream',
    color: 'cyan',
    time: 'Ongoing',
    description:
      'The Live Stream page connects to the backend Server-Sent Events feed. Each meter event is validated in real-time using physics rules and the ML anomaly engine.',
    actions: [
      { label: 'Open Live Stream', href: '/stream', primary: true },
    ],
    tips: [
      'Select a substation ID to subscribe to its event feed.',
      'Each event shows energy, anomaly score, and physics gate result.',
      'The stream is stateless — reconnects automatically on disconnect.',
      'Events are not stored unless you have a running analysis session.',
    ],
  },
  {
    id: 8,
    icon: '🗺',
    title: 'Explore the Grid Map',
    color: 'blue',
    time: '~1 min',
    description:
      'The Grid Map shows all substations with their current GHI status. Click a substation to see its latest physics result and trigger the AI interpretation pipeline.',
    actions: [
      { label: 'Open Grid Map', href: '/grid', primary: true },
    ],
    tips: [
      'Green = GHI ≥ 80 (Healthy). Amber = 50–79 (Degraded). Red = < 50 (Critical).',
      'Click any node to trigger a full GHI + AI pipeline run for that substation.',
      'The map auto-refreshes every 60 seconds.',
    ],
  },
]

const colorMap = {
  cyan:   { text: 'var(--cyan)',   bg: 'var(--cyan-dim)',   border: 'rgba(10,240,255,0.22)'  },
  green:  { text: 'var(--green)',  bg: 'var(--green-dim)',  border: 'rgba(5,232,154,0.22)'   },
  amber:  { text: 'var(--amber)',  bg: 'var(--amber-dim)',  border: 'rgba(255,186,48,0.22)'  },
  red:    { text: 'var(--red)',    bg: 'var(--red-dim)',    border: 'rgba(255,61,85,0.22)'   },
  blue:   { text: 'var(--blue)',   bg: 'var(--blue-dim)',   border: 'rgba(77,148,255,0.22)'  },
  violet: { text: 'var(--violet)', bg: 'var(--violet-dim)', border: 'rgba(155,114,255,0.22)' },
}

// ── Step card ─────────────────────────────────────────────────────────────

function StepCard({ step, active, onClick }: { step: GuideStep; active: boolean; onClick: () => void }) {
  const c = colorMap[step.color]
  return (
    <div
      className="panel"
      style={{
        borderColor: active ? c.border : 'var(--border-subtle)',
        cursor: 'pointer',
        transition: 'border-color 0.22s, box-shadow 0.22s',
        boxShadow: active ? `0 0 22px ${c.bg}` : undefined,
      }}
      onClick={onClick}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <div
          className="icon-circle icon-circle-md"
          style={{ background: c.bg, border: `1px solid ${c.border}`, flexShrink: 0 }}
        >
          {step.icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.08em' }}>
              Step {step.id}
            </span>
            <span
              className="chip"
              style={{ color: c.text, background: c.bg, borderColor: c.border, fontSize: 8 }}
            >
              {step.time}
            </span>
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, letterSpacing: '-0.01em' }}>
            {step.title}
          </div>
        </div>
        <span style={{ color: active ? c.text : 'var(--text-dim)', fontSize: 16, flexShrink: 0, marginTop: 4, transition: 'color 0.2s' }}>
          {active ? '▼' : '▶'}
        </span>
      </div>

      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ marginTop: 20, paddingTop: 20, borderTop: `1px solid ${c.border}` }}>
              <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.78, marginBottom: 20 }}>
                {step.description}
              </p>

              {/* Tips */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', marginBottom: 10 }}>
                  Tips
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {step.tips.map((tip, i) => (
                    <li key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      <span style={{ color: c.text, flexShrink: 0, marginTop: 1 }}>›</span>
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {step.actions.map(a => (
                  <Link
                    key={a.href}
                    href={a.href}
                    className={a.primary ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                  >
                    {a.label} →
                  </Link>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function GuidePage() {
  const [activeStep, setActiveStep] = useState<number>(1)

  function toggle(id: number) {
    setActiveStep(s => (s === id ? 0 : id))
  }

  return (
    <div className="page grid-bg">
      <div className="scan-line" />

      {/* Header */}
      <motion.div className="page-header" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="page-eyebrow">📋 How to Use</div>
        <h1 className="page-title glow-text">Getting Started with UrjaRakshak</h1>
        <p className="page-desc">
          Follow these steps to set up your account, upload meter data, run physics analysis,
          detect anomalies, and use the AI assistant. Each step takes only a few minutes.
        </p>
      </motion.div>

      {/* Quick links */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 36 }}>
        {[
          { href: '/upload',    label: '📤 Upload Data' },
          { href: '/dashboard', label: '📊 Dashboard' },
          { href: '/analysis',  label: '⚡ Analysis' },
          { href: '/anomaly',   label: '🔎 Anomalies' },
          { href: '/ai-chat',   label: '🤖 AI Chat' },
          { href: '/stream',    label: '📡 Live Stream' },
        ].map(l => (
          <Link key={l.href} href={l.href} className="btn btn-secondary btn-sm">
            {l.label}
          </Link>
        ))}
      </div>

      {/* Steps */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 56 }}>
        {GUIDE_STEPS.map((step, i) => (
          <motion.div
            key={step.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <StepCard
              step={step}
              active={activeStep === step.id}
              onClick={() => toggle(step.id)}
            />
          </motion.div>
        ))}
      </div>

      {/* Architecture overview */}
      <div className="panel" style={{ marginBottom: 40 }}>
        <div className="sec-label">System Architecture</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          {[
            { tier: 'Frontend', tech: 'Next.js 15 · TypeScript · CSS Variables', icon: '🖥', color: 'cyan' as const },
            { tier: 'Backend',  tech: 'FastAPI · Python 3.11 · Async SQLAlchemy', icon: '⚙', color: 'blue' as const },
            { tier: 'Database', tech: 'PostgreSQL (Supabase) · Pydantic v2', icon: '🗄', color: 'green' as const },
            { tier: 'ML Engine', tech: 'scikit-learn Isolation Forest · Z-Score ensemble', icon: '🤖', color: 'amber' as const },
            { tier: 'Physics',  tech: 'First-Law TE · I²R · IEC 60076-7 aging', icon: '⚛', color: 'violet' as const },
            { tier: 'AI',       tech: 'OpenAI GPT-4o-mini · Anthropic Claude Haiku', icon: '✨', color: 'red' as const },
          ].map(t => {
            const c = colorMap[t.color]
            return (
              <div key={t.tier} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div className="icon-circle icon-circle-sm" style={{ background: c.bg, border: `1px solid ${c.border}`, flexShrink: 0, marginTop: 2 }}>
                  {t.icon}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>{t.tier}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', lineHeight: 1.5 }}>{t.tech}</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Footer CTA */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 56 }}>
        <Link href="/upload" className="btn btn-primary">Upload Sample CSV →</Link>
        <Link href="/dashboard" className="btn btn-secondary">Open Dashboard</Link>
        <Link href="/docs" className="btn btn-secondary">Full Documentation</Link>
      </div>
    </div>
  )
}
