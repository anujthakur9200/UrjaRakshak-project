'use client'

import Link from 'next/link'
import { useAppStore } from '@/store/useAppStore'

/**
 * SessionBanner — shows the active analysis session across all pages.
 *
 * When the user uploads data, a session is created in the global store.
 * This banner reads that session and renders key stats so every page
 * reflects the same data (SSOT guarantee).
 *
 * Renders nothing if no session is active.
 */
export function SessionBanner() {
  const { activeSession } = useAppStore()
  if (!activeSession) return null

  const { substationId, stats, filename, anomalySample, aiStatus, aiInterpretation } = activeSession
  const { residual_pct, confidence_score, anomalies_detected, anomaly_rate_pct } = stats

  const statusColor =
    residual_pct > 10 ? 'var(--red)' : residual_pct > 5 ? 'var(--amber)' : 'var(--green)'

  const aiRisk: string | undefined = aiInterpretation?.ai_interpretation?.risk_level
    ?? aiInterpretation?.ghi_snapshot?.classification

  return (
    <div
      style={{
        background: 'rgba(10,240,255,0.04)',
        border: '1px solid rgba(10,240,255,0.15)',
        borderRadius: 10,
        padding: '12px 18px',
        marginBottom: 20,
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 14,
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-secondary)',
      }}
    >
      {/* Session indicator */}
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            width: 7, height: 7, borderRadius: '50%',
            background: 'var(--cyan)',
            boxShadow: '0 0 6px var(--cyan)',
            display: 'inline-block',
          }}
        />
        <span style={{ color: 'var(--cyan)', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Active Session
        </span>
      </span>

      <Pill label="Substation" value={substationId} />
      <Pill label="File" value={filename} />

      <Pill
        label="Residual"
        value={`${residual_pct.toFixed(1)}%`}
        valueColor={statusColor}
      />
      <Pill
        label="Confidence"
        value={`${(confidence_score * 100).toFixed(0)}%`}
      />
      <Pill
        label="Anomalies"
        value={`${anomalies_detected} (${anomaly_rate_pct.toFixed(1)}%)`}
        valueColor={anomalies_detected > 0 ? 'var(--amber)' : 'var(--green)'}
      />

      {/* AI status */}
      {aiStatus === 'loading' && (
        <span style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>🤖 AI analysing…</span>
      )}
      {aiStatus === 'ready' && aiRisk && (
        <Pill
          label="AI Risk"
          value={aiRisk}
          valueColor={
            aiRisk === 'CRITICAL' || aiRisk === 'critical_imbalance' ? 'var(--red)'
              : aiRisk === 'HIGH' || aiRisk === 'significant_imbalance' ? 'var(--amber)'
                : 'var(--green)'
          }
        />
      )}

      {/* Navigation hint */}
      <span style={{ marginLeft: 'auto', color: 'var(--text-tertiary)' }}>
        <Link href="/dashboard" style={{ color: 'var(--cyan)', textDecoration: 'none' }}>
          Dashboard
        </Link>
        {' · '}
        <Link href="/analysis" style={{ color: 'var(--cyan)', textDecoration: 'none' }}>
          Analysis
        </Link>
        {anomalySample.length > 0 && (
          <>
            {' · '}
            <Link href="/anomaly" style={{ color: 'var(--amber)', textDecoration: 'none' }}>
              {anomalies_detected} anomaly{anomalies_detected !== 1 ? 'ies' : ''}
            </Link>
          </>
        )}
      </span>
    </div>
  )
}

function Pill({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={{ color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 10 }}>
        {label}
      </span>
      <span style={{ color: valueColor ?? 'var(--text-primary)', fontWeight: 600 }}>
        {value}
      </span>
    </span>
  )
}
