'use client'

import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'urjarakshak_theme'

/** Apply theme to the html element */
function applyTheme(theme: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme)
  }
}

/** Read the saved theme (default: dark) */
function readTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  return (localStorage.getItem(STORAGE_KEY) as Theme) ?? 'dark'
}

/** Global bootstrap — call this once, early (e.g. in layout) */
export function initTheme() {
  if (typeof window === 'undefined') return
  const saved = readTheme()
  applyTheme(saved)
}

const ICONS: Record<Theme, string> = { dark: '🌙', light: '☀️', system: '⚙️' }
const LABELS: Record<Theme, string> = { dark: 'Dark', light: 'Light', system: 'System' }

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [theme, setTheme] = useState<Theme>('dark')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const saved = readTheme()
    setTheme(saved)
    applyTheme(saved)
  }, [])

  function select(t: Theme) {
    setTheme(t)
    applyTheme(t)
    localStorage.setItem(STORAGE_KEY, t)
    setOpen(false)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        title={`Theme: ${LABELS[theme]}`}
        aria-label={`Theme: ${LABELS[theme]} — click to change`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: compact ? 0 : 6,
          padding: compact ? '6px 8px' : '7px 12px',
          border: '1px solid var(--border-dim)',
          borderRadius: 'var(--r-md)',
          background: 'transparent',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-ui)',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'all 0.18s',
          whiteSpace: 'nowrap',
        }}
      >
        <span style={{ fontSize: 13, lineHeight: 1 }}>{ICONS[theme]}</span>
        {!compact && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.05em' }}>
            {LABELS[theme]}
          </span>
        )}
        <span style={{ marginLeft: compact ? 2 : 4, opacity: 0.6, fontSize: 9 }}>▾</span>
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 1010 }}
          />
          {/* Dropdown */}
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 1020,
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-dim)',
            borderRadius: 'var(--r-md)',
            boxShadow: 'var(--shadow-lg)',
            overflow: 'hidden',
            minWidth: 132,
          }}>
            {(['dark', 'light', 'system'] as Theme[]).map(t => (
              <button
                key={t}
                onClick={() => select(t)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 14px',
                  background: theme === t ? 'var(--cyan-dim)' : 'transparent',
                  border: 'none',
                  borderBottom: '1px solid var(--border-ghost)',
                  color: theme === t ? 'var(--cyan)' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-ui)',
                  fontSize: 13,
                  fontWeight: theme === t ? 600 : 400,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'background 0.12s, color 0.12s',
                }}
              >
                <span style={{ fontSize: 14 }}>{ICONS[t]}</span>
                <span>{LABELS[t]}</span>
                {theme === t && <span style={{ marginLeft: 'auto', fontSize: 10 }}>✓</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
