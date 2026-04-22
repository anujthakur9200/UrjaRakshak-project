'use client'

import React, { useState } from 'react'

const NAV = [
  { group: 'System',   items: [{ id: 'architecture', label: 'Architecture' }, { id: 'ethics', label: 'Ethics Framework' }] },
  { group: 'Engines',  items: [{ id: 'physics', label: 'Physics Engine' }, { id: 'ghi', label: 'Grid Health Index' }, { id: 'ml', label: 'Anomaly Detection' }, { id: 'aging', label: 'Transformer Aging' }] },
  { group: 'Interface',items: [{ id: 'api', label: 'API Reference' }, { id: 'auth', label: 'Authentication' }] },
]

const CONTENT: Record<string, { title: string; body: React.ReactNode }> = {
  architecture: {
    title: 'System Architecture',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          UrjaRakshak is a physics-first energy integrity platform. Every analysis starts with a thermodynamic
          ground truth and works outward — never the other way.
        </p>
        <div className="sec-label accent">Stack</div>
        {[
          ['Backend', 'FastAPI + Python 3.11, SQLAlchemy async (asyncpg), PostgreSQL / Supabase'],
          ['Frontend', 'Next.js 14, TypeScript, responsive CSS (no Tailwind runtime)'],
          ['Auth', 'JWT (HS256) with role-based access — admin / analyst / viewer'],
          ['ML', 'scikit-learn Isolation Forest + statistical z-score ensemble'],
          ['Streaming', 'Server-Sent Events — in-memory queues per substation, no Redis required'],
          ['Audit', 'SHA-256 hash chain (AuditLedger table) — tamper-evident, per-action'],
        ].map(([k, v]) => (
          <div key={k} style={{ display: 'flex', gap: 16, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cyan)', minWidth: 110, flexShrink: 0 }}>{k}</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{v}</span>
          </div>
        ))}
        <div className="sec-label" style={{ marginTop: 24 }}>Data Flow</div>
        {[
          '1. CSV/Excel upload → per-meter Z-score anomaly detection → stored in MeterReading table',
          '2. Physics validation → I²R losses + transformer losses → residual = actual − expected',
          '3. GHI engine → PBS·0.35 + ASS·0.20 + CS·0.15 + TSS·0.15 + DIS·0.15 → score 0–100',
          '4. Risk classifier → inspection ticket auto-created if residual > 8% or GHI < 50',
          '5. AI interpretation (optional) → Claude/OpenAI generates structured narrative',
          '6. Drift detection → PSI + K-S test → auto-retrain trigger if SEVERE',
        ].map((s, i) => (
          <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', padding: '6px 0', lineHeight: 1.6 }}>{s}</div>
        ))}
      </div>
    ),
  },
  ethics: {
    title: 'Ethics Framework',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          UrjaRakshak is built for infrastructure-scope analysis only. Individual attribution is
          deliberately out of scope — the system is not designed to identify people.
        </p>
        <div className="sec-label accent">Hard Constraints</div>
        {[
          ['No individual attribution', 'Loss causes are attributed to infrastructure categories, never to people. The Attribution Engine refuses individual-level outputs.'],
          ['Uncertainty-first', 'The physics engine quantifies uncertainty explicitly and refuses to output when confidence < 0.5.'],
          ['Explainable outputs', 'Every formula is documented. The GHI computation shows all five subscores. No black-box results.'],
          ['Audit trail', 'Every analysis, upload, and AI call is recorded in the AuditLedger with a SHA-256 hash chain.'],
          ['Strict mode', 'When ENABLE_STRICT_ETHICS=true, the physics engine applies additional refusal conditions on low-quality measurements.'],
        ].map(([k, v]) => (
          <div key={k} style={{ marginBottom: 14, padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cyan)', marginBottom: 5 }}>{k}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>{v}</div>
          </div>
        ))}
      </div>
    ),
  },
  physics: {
    title: 'Physics Truth Engine (PTE v2.1)',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          The core of UrjaRakshak. Validates energy conservation using the First Law of Thermodynamics.
          Computes expected technical losses from component parameters. The residual is the gap
          between actual and expected — the signal worth investigating.
        </p>
        <div className="sec-label accent">Formula</div>
        <div className="panel panel-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 2 }}>
          <div><span style={{ color: 'var(--cyan)' }}>Energy_in</span> = Energy_out + Technical_losses + Residual</div>
          <div><span style={{ color: 'var(--cyan)' }}>Residual</span> = Actual_loss − Expected_technical_loss</div>
          <div><span style={{ color: 'var(--cyan)' }}>Residual%</span> = |Residual| / Energy_in × 100</div>
        </div>
        <div className="sec-label">Component Loss Models</div>
        {[
          ['Transformer', 'No-load loss (core) = rated_kva × 0.002 × (1 − η) × aging_factor\nLoad loss (copper) = rated_kva × 0.008 × (load_fraction)²\nAging factor = 1 + age_years / 100'],
          ['Distribution line', 'I²R loss (W) = I² × R_total where I = P / (√3 × V_kv × 1000)\nR_total = resistance_ohm_per_km × length_km\nTemperature correction: R_T = R_20 × (1 + α × (T − 20))'],
        ].map(([k, v]) => (
          <div key={k} style={{ marginBottom: 14 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)', marginBottom: 8 }}>{k}</div>
            <div className="panel panel-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-line', lineHeight: 1.8 }}>{v}</div>
          </div>
        ))}
        <div className="sec-label" style={{ marginTop: 20 }}>Classification Thresholds</div>
        {[
          ['balanced', '< 1.5%', 'var(--green)'],
          ['minor_imbalance', '1.5% – 4.0%', 'var(--cyan)'],
          ['significant_imbalance', '4.0% – 8.0%', 'var(--amber)'],
          ['critical_imbalance', '> 8.0%', 'var(--red)'],
        ].map(([status, range, color]) => (
          <div key={status} style={{ display: 'flex', gap: 16, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: color as string, minWidth: 180 }}>{status}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{range}</span>
          </div>
        ))}
      </div>
    ),
  },
  ghi: {
    title: 'Grid Health Index (GHI)',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          A composite score (0–100) that combines physics balance, anomaly signals,
          confidence, temporal stability, and data integrity into a single actionable metric.
        </p>
        <div className="sec-label accent">Formula</div>
        <div className="panel panel-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 2 }}>
          <div>GHI = (0.35 × PBS + 0.20 × ASS + 0.15 × CS + 0.15 × TSS + 0.15 × DIS) × 100</div>
        </div>
        <div className="sec-label">Subscores</div>
        {[
          ['PBS', 'Physics Balance Score (35%)', 'Piecewise linear on residual%: ≤1% → 1.0, 1–3% → linear to 0.5, 3–7% → linear to 0, >7% → 0'],
          ['ASS', 'Anomaly Stability Score (20%)', 'Exponential decay: exp(−10 × anomaly_rate). A 10% anomaly rate gives ASS = 0.37.'],
          ['CS',  'Confidence Score (15%)', 'Direct from the physics engine: [0, 1]. Low-quality measurements reduce this.'],
          ['TSS', 'Temporal Stability Score (15%)', 'Rolling volatility of residual history. High variance → low TSS.'],
          ['DIS', 'Data Integrity Score (15%)', 'Penalises missing and invalid readings: 1 − missing_ratio − invalid_ratio.'],
        ].map(([code, name, desc]) => (
          <div key={code} style={{ marginBottom: 12, padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', marginBottom: 5 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--cyan)', fontWeight: 600 }}>{code}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>{name}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{desc}</div>
          </div>
        ))}
        <div className="sec-label" style={{ marginTop: 4 }}>Classification</div>
        {[['≥ 90', 'HEALTHY', 'var(--green)'], ['≥ 70', 'STABLE', 'var(--cyan)'], ['≥ 50', 'DEGRADED', 'var(--amber)'], ['≥ 30', 'CRITICAL', '#FF6B35'], ['< 30', 'SEVERE', 'var(--red)']].map(([range, cls, color]) => (
          <div key={cls} style={{ display: 'flex', gap: 16, padding: '7px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', minWidth: 50 }}>{range}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: color as string }}>{cls}</span>
          </div>
        ))}
      </div>
    ),
  },
  ml: {
    title: 'Anomaly Detection',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          Three-gate ensemble. All three gates must agree before a reading is flagged as anomalous.
          This makes the system hard to game and reduces false positives.
        </p>
        {[
          ['Gate 1 — Physics', 'First Law of Thermodynamics. Output > Input is refused outright before any ML runs.'],
          ['Gate 2 — Z-Score', 'Per-meter rolling baseline. Z = (reading − μ) / σ. Flagged if |Z| > 2.5 (configurable threshold).'],
          ['Gate 3 — Isolation Forest', 'scikit-learn IsolationForest trained on 7 features: input_mwh, output_mwh, residual_mwh, residual_percent, confidence_score, time_of_day_hour, day_of_week. Contamination = 0.05.'],
        ].map(([gate, desc]) => (
          <div key={gate} style={{ marginBottom: 14, padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)', marginBottom: 6 }}>{gate}</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>{desc}</div>
          </div>
        ))}
        <div className="sec-label" style={{ marginTop: 8 }}>Per-meter upload analysis</div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          When a CSV is uploaded, Z-scores are computed per meter against that meter&apos;s rolling
          mean and standard deviation within the uploaded batch. The top anomalies by absolute
          Z-score are returned in the upload response.
        </p>
      </div>
    ),
  },
  aging: {
    title: 'Transformer Aging Engine',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          IEC 60076-7:2018 thermal aging model. The Arrhenius equation applied to paper
          insulation degradation — every 6°C rise halves insulation life.
        </p>
        <div className="sec-label accent">Key Equations</div>
        <div className="panel panel-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 20, lineHeight: 2 }}>
          <div><span style={{ color: 'var(--cyan)' }}>Hot-spot (°C)</span>: Θh = Θamb + ΔΘo_rated × K^(2n) + ΔΘh_rated × K^(2m)</div>
          <div><span style={{ color: 'var(--cyan)' }}>Aging factor V</span>: exp(15000/383 − 15000/(Θh + 273))</div>
          <div><span style={{ color: 'var(--cyan)' }}>RUL (years)</span>: (designed_life − years_installed) / V</div>
          <div><span style={{ color: 'var(--cyan)' }}>Health Index</span>: 100 × (1 − life_consumed_pct)</div>
          <div><span style={{ color: 'var(--cyan)' }}>P(fail 12m)</span>: 1 / (1 + exp(−10 × (life_consumed − 0.75)))</div>
        </div>
        <div className="sec-label">Parameters</div>
        {[['K', 'Load factor (actual / rated)'], ['n', 'Oil exponent (ONAN: 0.8)'], ['m', 'Winding exponent (ONAN: 1.3)'], ['ΔΘo_rated', 'Rated top-oil rise: 55°C'], ['ΔΘh_rated', 'Rated hot-spot rise over oil: 23°C']].map(([p, d]) => (
          <div key={p} style={{ display: 'flex', gap: 16, padding: '7px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--amber)', minWidth: 120 }}>{p}</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{d}</span>
          </div>
        ))}
      </div>
    ),
  },
  api: {
    title: 'API Reference',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          REST API at <code style={{ background: 'var(--bg-elevated)', padding: '1px 6px', borderRadius: 3, fontFamily: 'var(--font-mono)', fontSize: 12 }}>http://localhost:8000</code>.
          Interactive docs at <code style={{ background: 'var(--bg-elevated)', padding: '1px 6px', borderRadius: 3, fontFamily: 'var(--font-mono)', fontSize: 12 }}>/api/docs</code>.
        </p>
        {[
          { group: 'Auth', routes: [
            ['POST', '/api/v1/auth/register', 'Register (email, password, role)'],
            ['POST', '/api/v1/auth/login', 'Login → JWT access_token'],
          ]},
          { group: 'Upload', routes: [
            ['POST', '/api/v1/upload/meter-data', 'Upload CSV/Excel (multipart). Runs Z-score detection.'],
            ['GET',  '/api/v1/upload/dashboard', 'Aggregated dashboard data (public)'],
          ]},
          { group: 'Analysis', routes: [
            ['POST', '/api/v1/analysis/validate', 'Physics validation. GHI + AI runs as BackgroundTask.'],
            ['GET',  '/api/v1/analysis/stats/summary', 'Aggregated stats (30s cache)'],
            ['GET',  '/api/v1/analysis/{id}', 'Single analysis with GHI + AI data'],
          ]},
          { group: 'GHI & AI', routes: [
            ['GET',  '/api/v1/ai/ghi/dashboard', 'Fleet GHI overview'],
            ['GET',  '/api/v1/ai/ghi/latest/{sub}', 'Latest GHI for a substation'],
            ['GET',  '/api/v1/ai/status', 'AI engine configuration'],
          ]},
          { group: 'Inspections', routes: [
            ['GET',  '/api/v1/inspections/', 'List (filterable by status, priority)'],
            ['PATCH', '/api/v1/inspections/{id}', 'Update status, findings, resolution_notes'],
            ['GET',  '/api/v1/inspections/stats/summary', 'Open / critical counts'],
          ]},
          { group: 'Stream', routes: [
            ['GET',  '/api/v1/stream/live/{sub_id}', 'SSE stream for a substation (token= param)'],
            ['POST', '/api/v1/stream/ingest', 'Push a single live event'],
            ['GET',  '/api/v1/stream/substation/{sub}/stability', 'Meter stability scores'],
          ]},
          { group: 'Governance', routes: [
            ['GET',  '/api/v1/org/drift/check', 'Run PSI + K-S drift detection now'],
            ['POST', '/api/v1/org/aging/compute', 'IEC 60076-7 transformer aging'],
            ['GET',  '/api/v1/org/aging/fleet', 'Fleet aging summary'],
            ['GET',  '/api/v1/org/audit/recent', 'Audit log entries'],
            ['GET',  '/api/v1/org/audit/verify', 'Verify SHA-256 hash chain'],
          ]},
        ].map(({ group, routes }) => (
          <div key={group} style={{ marginBottom: 20 }}>
            <div className="sec-label">{group}</div>
            {routes.map(([method, path, desc]) => (
              <div key={path} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--border-subtle)', flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: method === 'GET' ? 'var(--green)' : method === 'POST' ? 'var(--cyan)' : 'var(--amber)', minWidth: 44, textTransform: 'uppercase' }}>{method}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', minWidth: 280 }}>{path}</span>
                <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{desc}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    ),
  },
  auth: {
    title: 'Authentication',
    body: (
      <div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.75, marginBottom: 20 }}>
          JWT-based (HS256). Tokens expire after 60 minutes by default. Include in every
          protected request as a Bearer token.
        </p>
        <div className="sec-label accent">Roles</div>
        {[
          ['admin',   'Full access. Can manage users, view all data.'],
          ['analyst', 'Can upload data, run analyses, view all results. Cannot manage users.'],
          ['viewer',  'Read-only. Can view dashboards and reports.'],
        ].map(([role, desc]) => (
          <div key={role} style={{ display: 'flex', gap: 16, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--cyan)', minWidth: 80 }}>{role}</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{desc}</span>
          </div>
        ))}
        <div className="sec-label" style={{ marginTop: 20 }}>Quick start</div>
        <div className="panel panel-sm" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.9 }}>
          <div><span style={{ color: 'var(--green)' }}># 1. Register</span></div>
          <div>POST /api/v1/auth/register</div>
          <div>{'{"email":"you@example.com","password":"min8chars","role":"analyst"}'}</div>
          <div style={{ marginTop: 8 }}><span style={{ color: 'var(--green)' }}># 2. Login → get token</span></div>
          <div>POST /api/v1/auth/login</div>
          <div>{'{"email":"you@example.com","password":"min8chars"}'}</div>
          <div style={{ marginTop: 8 }}><span style={{ color: 'var(--green)' }}># 3. Use token</span></div>
          <div><span style={{ color: 'var(--cyan)' }}>Authorization: Bearer &lt;access_token&gt;</span></div>
        </div>
        <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 'var(--r-sm)', background: 'rgba(0,212,255,0.05)', border: '1px solid var(--border-dim)', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
          Demo credentials (after running seed_demo_data.py):<br />
          <span style={{ color: 'var(--cyan)' }}>admin@urjarakshak.dev</span> / demo1234
        </div>
      </div>
    ),
  },
}

export default function Docs() {
  const [active, setActive] = useState('architecture')
  const section = CONTENT[active]

  return (
    <div className="page" style={{ display: 'flex', gap: 32, alignItems: 'flex-start', paddingTop: 'clamp(24px,4vw,48px)' }}>

      {/* Sidebar */}
      <aside style={{
        width: 200, flexShrink: 0,
        position: 'sticky', top: 'calc(var(--nav-h) + 20px)',
        maxHeight: 'calc(100vh - var(--nav-h) - 40px)',
        overflowY: 'auto',
      }} className="hide-mobile">
        {NAV.map(({ group, items }) => (
          <div key={group} style={{ marginBottom: 20 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 8, padding: '0 8px' } as React.CSSProperties}>
              {group}
            </div>
            {items.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setActive(id)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '7px 10px', borderRadius: 'var(--r-sm)', border: 'none',
                  cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
                  background: active === id ? 'var(--cyan-dim)' : 'transparent',
                  color: active === id ? 'var(--cyan)' : 'var(--text-tertiary)',
                  transition: 'all var(--t-fast)',
                  marginBottom: 1,
                }}
              >
                {label}
              </button>
            ))}
          </div>
        ))}
      </aside>

      {/* Mobile tab bar */}
      <div className="show-mobile" style={{ width: '100%' }}>
        <div className="tab-bar" style={{ marginBottom: 20 }}>
          {NAV.flatMap(g => g.items).map(({ id, label }) => (
            <button key={id} className={`tab-btn ${active === id ? 'active' : ''}`} onClick={() => setActive(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="page-header fade-in">
          <div className="page-eyebrow">Documentation</div>
          <h1 className="page-title">{section.title}</h1>
        </div>
        <div className="fade-in" key={active}>
          {section.body}
        </div>
      </div>
    </div>
  )
}
