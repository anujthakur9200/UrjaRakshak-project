# UrjaRakshak — Render Free Deployment Guide
## 100% Free Stack: Render + Supabase + Vercel

**Developer & Founder: Vipin Baniya**

---

## Free Services Used

| Service | What It Does | Free Tier Limits |
|---------|-------------|-----------------|
| **Render** | Backend hosting (FastAPI) | 512MB RAM, 0.1 CPU, spins down after 15min |
| **Supabase** | PostgreSQL database | 500MB DB, 2GB bandwidth |
| **Vercel** | Frontend hosting (Next.js) | Unlimited deploys, 100GB bandwidth |
| **GitHub** | Source control + CI/CD | Free for public repos |

**Total cost: $0.00/month** ✅

---

## Step 1 — Prepare Your GitHub Repository

Your code must be on GitHub for Render to deploy it.

```bash
# In your project root (the folder containing /backend and /frontend)
git init
git add .
git commit -m "UrjaRakshak initial commit"

# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/urjarakshak.git
git push -u origin main
```

**Repo structure Render expects:**
```
urjarakshak/
├── backend/           ← Render deploys THIS folder
│   ├── app/
│   ├── requirements.txt
│   └── render.yaml
└── frontend/          ← Vercel deploys THIS folder
```

---

## Step 2 — Set Up Supabase (Free Database)

1. Go to [supabase.com](https://supabase.com) → **Start your project** → Sign up free
2. Click **New Project**
   - Name: `urjarakshak`
   - Database Password: (save this securely)
   - Region: pick nearest to you
3. Wait ~2 minutes for project to provision
4. Go to **Settings → Database → Connection String**
5. Select **URI** tab → copy the connection string

It looks like:
```
postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

⚠️ **For async FastAPI, change `postgresql://` to `postgresql+asyncpg://`**

Final DATABASE_URL:
```
postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

---

## Step 3 — Deploy Backend on Render (Free)

### Option A: Blueprint Deploy (Recommended — 1 click)

1. Go to [render.com](https://render.com) → Sign up free (use GitHub)
2. Click **New → Blueprint**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` in `/backend`
5. Click **Apply** → Service is created

### Option B: Manual Deploy

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect GitHub → select your repo
3. Fill in:
   - **Name**: `urjarakshak-backend`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: **Free**

### Set Environment Variables in Render Dashboard

Go to your service → **Environment** tab → Add:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | Your Supabase URL (postgresql+asyncpg://...) |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `ENABLE_STRICT_ETHICS` | `true` |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app` (set after frontend deploy) |
| `SECRET_KEY` | Click "Generate" — Render creates a secure random value |

Click **Save Changes** → Render auto-redeploys.

### Verify Backend is Live

After deploy (~3-5 min), your backend URL will be:
```
https://urjarakshak-backend.onrender.com
```

Test it:
```bash
curl https://urjarakshak-backend.onrender.com/health
```

Expected response:
```json
{"status": "healthy", "version": "2.0.0", ...}
```

---

## Step 4 — Deploy Frontend on Vercel (Free)

1. Go to [vercel.com](https://vercel.com) → Sign up free (use GitHub)
2. Click **Add New → Project**
3. Import your GitHub repo
4. Set **Root Directory** to `frontend`
5. Framework: **Next.js** (auto-detected)
6. Add Environment Variable:
   - `NEXT_PUBLIC_API_URL` = `https://urjarakshak-backend.onrender.com`
7. Click **Deploy**

Your frontend URL: `https://urjarakshak.vercel.app`

---

## Step 5 — Update CORS After Both Are Live

Go back to Render → your service → **Environment** tab:
- Update `ALLOWED_ORIGINS` to your actual Vercel URL:
  ```
  https://urjarakshak.vercel.app
  ```
- Save → Render redeploys automatically.

---

## Step 6 — Seed Demo Data (First Run)

Without this step the dashboard opens empty. Run the seeder once after deployment:

```bash
# In your backend directory, with DATABASE_URL pointing to your Supabase DB:
cd backend
pip install -r requirements.txt
DATABASE_URL="postgresql+asyncpg://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres" \
  python seed_demo_data.py

# Creates: 5 substations, ~300 analyses, GHI snapshots, inspections, aging records
# Login: admin@urjarakshak.dev / demo1234
```

Or on Render — go to your service → **Shell** tab (available on paid plans) and run `python seed_demo_data.py`.

---

## Step 7 — Enable AI Interpretation (Optional)

With an OpenAI key, each physics analysis gets an AI-generated engineering narrative.

In Render → your service → **Environment** tab, add:
```
OPENAI_API_KEY = sk-...
```

Save → Render redeploys. AI interpretation now runs automatically in the background
after every analysis. Results appear on `GET /api/v1/analysis/{id}` under `ai_interpretation`.

**Cost:** GPT-4o-mini at ~$0.00015/1K tokens. A typical analysis uses ~600 tokens = $0.0001.
Running 100 analyses/day = ~$0.30/month.

---

## Free Tier Limitations & Workarounds

### ⚠️ Cold Starts (Most Important)
Render free services **spin down after 15 minutes of inactivity**. The next request takes ~30 seconds to cold start.

**Workaround — Keep-Alive Ping (Free):**
Use [UptimeRobot](https://uptimerobot.com) (free) to ping your `/health` endpoint every 14 minutes:
1. Sign up at uptimerobot.com (free)
2. Add monitor → HTTP(S)
3. URL: `https://urjarakshak-backend.onrender.com/health`
4. Interval: **14 minutes**
5. This keeps your service warm 24/7 — completely free!

### Database Connection Limit
Supabase free tier: 60 simultaneous connections max.
FastAPI with asyncpg uses connection pooling — this is fine for development/demo.

### 512MB RAM
The optimized `requirements-render-free.txt` removes heavy ML packages.
Use it by updating `render.yaml` buildCommand to:
```yaml
buildCommand: "pip install -r requirements-render-free.txt"
```

---

## Debugging on Render

View live logs: Render Dashboard → your service → **Logs** tab

Common issues:

| Error | Fix |
|-------|-----|
| `connection refused` | Wrong DATABASE_URL format — must be `postgresql+asyncpg://` |
| `Module not found` | Check `requirements.txt` includes the missing package |
| `port already in use` | Use `$PORT` not hardcoded 8000 in start command |
| Service won't start | Check Render logs → first line of error is usually the cause |
| CORS error in frontend | Update `ALLOWED_ORIGINS` in Render env vars |

---

## Full Architecture (Free)

```
User Browser
     │
     ▼
Vercel (Frontend - Next.js)
     │ API calls
     ▼
Render Free (Backend - FastAPI)
     │ SQL queries
     ▼
Supabase Free (PostgreSQL)
```

---

## Quick Commands

```bash
# Test backend locally before deploying
cd backend
pip install -r requirements.txt
cp .env.example .env          # Edit .env with your values
uvicorn app.main:app --reload

# Test frontend locally
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

---

## Support

**Developer & Founder:** Vipin Baniya  
**Platform:** UrjaRakshak — Physics-Based Grid Intelligence

---

*UrjaRakshak — Energy is a civilizational lifeline. We protect it with intelligence, humility, and ethics.*
