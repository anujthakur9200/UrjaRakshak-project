#!/bin/bash
# UrjaRakshak — Local Quick Start
# Starts backend + frontend, seeds demo data on first run.
# Requirements: Python 3.11+, Node 20+, PostgreSQL running locally
#               OR just Docker (see docker option below)

set -e
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}⚡ UrjaRakshak — Quick Start${NC}"
echo ""

# ── Docker option (simplest) ────────────────────────────────────────────────
if command -v docker &>/dev/null && command -v docker-compose &>/dev/null; then
  echo -e "${GREEN}Docker detected.${NC} Starting with docker-compose..."
  docker-compose up -d
  echo ""
  echo "Waiting for backend..."
  for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      echo -e "${GREEN}✓ Backend healthy${NC}"
      break
    fi
    sleep 2
  done
  # Seed on first run (no data yet)
  if [ "$(curl -sf http://localhost:8000/api/v1/upload/dashboard 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("has_data","false"))' 2>/dev/null)" != "True" ]; then
    echo "Seeding demo data..."
    docker-compose exec api python seed_demo_data.py
  fi
  echo ""
  echo -e "${GREEN}🎉 Running!${NC}"
  echo "  Frontend : http://localhost:3000"
  echo "  Backend  : http://localhost:8000"
  echo "  API Docs : http://localhost:8000/api/docs"
  echo "  Login    : admin@urjarakshak.dev / demo1234"
  exit 0
fi

# ── Manual option ────────────────────────────────────────────────────────────
echo "Starting manually (no Docker)..."
echo ""

# Check prerequisites
if ! command -v python3 &>/dev/null; then echo -e "${RED}✗ Python 3 required${NC}"; exit 1; fi
if ! command -v node &>/dev/null;    then echo -e "${RED}✗ Node.js required${NC}"; exit 1; fi
echo -e "${GREEN}✓ Python and Node found${NC}"

# Backend
echo ""
echo "── Backend ──────────────────────────────────"
cd backend

if [ ! -f .env ]; then
  cp .env.example .env
  echo -e "${YELLOW}⚠ Created .env from template — edit DATABASE_URL and SECRET_KEY${NC}"
  echo "  Then re-run this script."
  exit 1
fi

if [ ! -d venv ]; then
  python3 -m venv venv
  echo "Created virtualenv"
fi
source venv/bin/activate
pip install -r requirements.txt -q
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Start backend in background
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for it
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend healthy${NC}"
    break
  fi
  sleep 1
done

# Seed if empty
DATA=$(curl -sf http://localhost:8000/api/v1/upload/dashboard 2>/dev/null)
HAS_DATA=$(echo "$DATA" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("has_data",False))' 2>/dev/null)
if [ "$HAS_DATA" != "True" ]; then
  echo "Seeding demo data..."
  python seed_demo_data.py
fi

cd ..

# Frontend
echo ""
echo "── Frontend ─────────────────────────────────"
cd frontend
npm install -q
echo -e "${GREEN}✓ Frontend deps installed${NC}"
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}🎉 Running!${NC}"
echo "  Frontend : http://localhost:3000"
echo "  Backend  : http://localhost:8000"
echo "  API Docs : http://localhost:8000/api/docs"
echo "  Login    : admin@urjarakshak.dev / demo1234"
echo ""
echo "Stop: kill $BACKEND_PID $FRONTEND_PID"
echo ""
wait
