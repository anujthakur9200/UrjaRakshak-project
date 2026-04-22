'use client'

export function Footer() {
  return (
    <footer className="footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 22, height: 22, borderRadius: '50%',
          background: 'linear-gradient(145deg, var(--cyan), var(--blue))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11,
        }}>⚡</div>
        <span className="footer-text">
          UrjaRakshak v2.3 — Physics-Based Grid Intelligence
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <span className="footer-text">Built by Vipin Baniya</span>
        <span className="key">PTE v2.1</span>
        <span className="key">SSE</span>
        <span className="key">IEC 60076-7</span>
      </div>
    </footer>
  )
}
