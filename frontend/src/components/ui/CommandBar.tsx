'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { UrjaRakshakLogo } from '@/components/ui/UrjaRakshakLogo'

export function CommandBar() {
  const pathname = usePathname()
  const [isLive, setIsLive] = useState<boolean | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
    fetch(`${apiUrl}/health`)
      .then(r => setIsLive(r.ok))
      .catch(() => setIsLive(false))
  }, [])

  // Close drawer on route change
  useEffect(() => { setMenuOpen(false) }, [pathname])

  // Prevent body scroll when drawer open
  useEffect(() => {
    document.body.style.overflow = menuOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [menuOpen])

  const nav = [
    { href: '/',            label: 'Home' },
    { href: '/dashboard',   label: 'Dashboard' },
    { href: '/simulation',  label: 'Simulation' },
    { href: '/guide',       label: 'How to Use' },
    { href: '/anomaly',     label: 'Anomaly' },
    { href: '/grid',        label: 'Grid Map' },
    { href: '/upload',      label: 'Upload' },
    { href: '/analysis',    label: 'Analysis' },
    { href: '/stream',      label: 'Live' },
    { href: '/ai-chat',     label: 'AI Chat' },
    { href: '/docs',        label: 'Docs' },
  ]

  const liveState = isLive === null ? 'checking' : isLive ? 'online' : 'offline'
  const liveLabel = isLive === null ? 'Connecting' : isLive ? 'Online' : 'Offline'

  return (
    <>
      <header className="nav-bar">
        <Link href="/" className="nav-brand">
          <div className="nav-brand-mark">
            <UrjaRakshakLogo size={26} />
          </div>
          <div className="nav-brand-text">
            <span className="nav-brand-name">UrjaRakshak</span>
            <span className="nav-brand-sub">Grid Intelligence</span>
          </div>
        </Link>

        <div className="nav-divider desktop-only" />

        {/* Desktop nav */}
        <nav className="nav-links">
          {nav.map(n => (
            <Link
              key={n.href}
              href={n.href}
              className={`nav-link ${pathname === n.href ? 'active' : ''}`}
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="nav-end">
          <ThemeToggle compact />

          <div className={`live-pill ${liveState} nav-status`}>
            <span className="live-dot" />
            {liveLabel}
          </div>

          {/* Hamburger */}
          <button
            className={`nav-hamburger ${menuOpen ? 'open' : ''}`}
            onClick={() => setMenuOpen(o => !o)}
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
          >
            <span /><span /><span />
          </button>
        </div>
      </header>

      {/* Mobile drawer */}
      <div className={`nav-drawer ${menuOpen ? 'open' : ''}`} role="dialog" aria-label="Navigation menu">
        {nav.map(n => (
          <Link
            key={n.href}
            href={n.href}
            className={`nav-link ${pathname === n.href ? 'active' : ''}`}
            onClick={() => setMenuOpen(false)}
          >
            {n.label}
          </Link>
        ))}
        <div className="nav-drawer-sep" />
        <div className="nav-drawer-meta" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div className={`live-pill ${liveState}`}>
            <span className="live-dot" />
            Backend {liveLabel}
          </div>
          <ThemeToggle />
        </div>
      </div>

      {/* Backdrop */}
      {menuOpen && (
        <div
          onClick={() => setMenuOpen(false)}
          style={{ position:'fixed', inset:0, zIndex:998, background:'rgba(0,0,0,0.4)' }}
        />
      )}
    </>
  )
}
