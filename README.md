# ⚡ UrjaRakshak v2.3
### Physics-Based Energy Integrity & Grid Intelligence Platform

> *Energy is a civilisational lifeline. We protect it with intelligence, humility, and ethics.*

**Developer & Founder:** Vipin Baniya

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ **or** a [Supabase](https://supabase.com) project (free tier works)

---

### 1 · Backend

```bash
cd backend
cp .env.example .env          # edit DATABASE_URL and SECRET_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The server starts even without a `.env` file (uses safe dev defaults with a warning).
API docs: **http://localhost:8000/api/docs**

#### Supabase setup
1. Create a free project at supabase.com
2. Run `deployment/supabase/schema.sql` in the Supabase SQL editor
3. Set `DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres`
   — SSL is auto-enabled when a `*.supabase.co` host is detected

---

### 2 · Frontend

```bash
cd frontend
# .env.local is already provided (points to http://localhost:8000)
# To override: edit frontend/.env.local
npm install
npm run dev
```

Open **http://localhost:3000**

> **Both terminals must run simultaneously.** The frontend is a Next.js dev server; the backend is uvicorn.

---

### 3 · First upload

1. Go to **http://localhost:3000/upload**
2. Select a substation ID (e.g. `SS001`)
3. Drag in a CSV file with columns `timestamp, meter_id, energy_kwh`
4. Click **Run Analysis** — you'll be prompted to Register/Login
5. Register creates an `analyst` account immediately and logs you in

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ prod | local postgres | PostgreSQL connection string |
| `SECRET_KEY` | ✅ prod | dev default | JWT signing key (32+ chars) |
| `ENVIRONMENT` | | `development` | `development` / `staging` / `production` |
| `ALLOWED_ORIGINS` | | `http://localhost:3000,3001` | Comma-separated CORS origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | `60` | JWT expiry |
| `OPENAI_API_KEY`    | optional | — | AI interpretation via GPT-4o-mini (recommended) |
| `ANTHROPIC_API_KEY` | optional | — | AI interpretation via Claude (alternative; takes priority if both set) |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL |

---

## Architecture

```
urjarakshak/
├── backend/                      # FastAPI + Python 3.11
│   ├── app/
│   │   ├── api/v1/               # REST endpoints
│   │   │   ├── auth_routes.py    # POST /auth/register, /auth/login
│   │   │   ├── upload.py         # POST /upload/meter-data
│   │   │   ├── analysis.py       # POST /analysis/validate
│   │   │   ├── ai.py             # GHI + AI interpretation
│   │   │   ├── inspection.py     # Inspection workflow
│   │   │   ├── stream.py         # SSE live streaming
│   │   │   └── governance.py     # Drift / aging / audit
│   │   ├── core/                 # Physics & AI engines
│   │   │   ├── ghi_engine.py
│   │   │   ├── physics_constrained_anomaly.py
│   │   │   ├── load_forecasting_engine.py
│   │   │   ├── drift_detection_engine.py
│   │   │   ├── transformer_aging_engine.py
│   │   │   └── ai_interpretation_engine.py
│   │   ├── auth/__init__.py      # JWT + RBAC
│   │   ├── config.py             # Settings
│   │   ├── database.py           # Async SQLAlchemy (asyncpg)
│   │   └── main.py               # App entry, CORS, middleware
│   └── .env.example
│
├── frontend/                     # Next.js 14 + TypeScript
│   ├── src/app/
│   │   ├── dashboard/            # Live metrics dashboard
│   │   ├── upload/               # Meter data upload + auth
│   │   ├── ghi/                  # Grid Health Index
│   │   ├── inspections/          # Inspection workflow
│   │   ├── stream/               # Real-time SSE monitoring
│   │   └── governance/           # Drift / aging / audit
│   ├── src/lib/api.ts            # Typed API client
│   ├── .env.local                # NEXT_PUBLIC_API_URL (gitignored)
│   └── .env.local.example        # Template
│
└── deployment/
    └── supabase/schema.sql       # Complete DB schema (idempotent)
```

---

## Design Principles

| Principle | Implementation |
|---|---|
| Physics-first | PBS subscores 35% of GHI; physics gate hard-overrides ML |
| Explainable | Every formula documented; Fourier decomposition shown |
| Hard to game | 3-gate anomaly logic (physics + z-score + Isolation Forest) |
| Uncertainty-aware | 95%/99% confidence bands; refuses when confidence < 0.5 |
| Ethics | No individual attribution; infrastructure-scope only |
| Auditable | SHA-256 hash chain; prompt_hash on every AI call |
| Offline-capable | Full functionality without AI API keys |
