# AirRev Engine API

Canadian investment property analyzer backend for [AirRev.io](https://airrev.io).
FastAPI · CREA DDF · Supabase · Railway-ready

---

## What It Does

- `POST /analyze/listing` — Full LTR + STR investment analysis from an MLS® number
- `POST /analyze/quick-calc` — Fast back-of-napkin calculation (no MLS lookup)
- `POST /calculator/investment` — Standalone investment calculator
- `POST /calculator/rent-insight` — Rent estimates by community + bedrooms
- `GET  /calculator/mortgage-breakdown` — Mortgage numbers for UI sliders
- `POST /neighborhood/insights` — Full community investment profile
- `GET  /neighborhood/communities` — List all 170+ Calgary communities
- `GET  /creb/monthly-summary` — Monthly CREB-style market report

---

## Quick Start

```bash
# 1. Clone and set up environment
cd airrev-engine
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your DDF keys, Supabase URL, etc.

# 3. Set up Supabase tables
# Paste supabase_schema.sql into your Supabase SQL Editor

# 4. Run locally
uvicorn app.main:app --reload --port 8000

# 5. View API docs
open http://localhost:8000/docs
```

---

## DDF Setup

Your CREA DDF access gives you the data advantage. Configure:

```
DDF_ACCESS_KEY=your-key
DDF_SECRET_KEY=your-secret
```

DDF OData v1 docs: https://ddfapi.realtor.ca/

---

## Connecting to Lovable

In your Lovable project, add these to **Cloud → Secrets**:

```
AIRREV_API_URL = https://your-railway-app.railway.app
AIRREV_API_KEY = your-secret-key-from-.env
```

Example Lovable fetch:
```typescript
const response = await fetch(`${process.env.AIRREV_API_URL}/analyze/listing`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-AirRev-Key': process.env.AIRREV_API_KEY,
  },
  body: JSON.stringify({
    mls_number: 'A2123456',
    analysis_type: 'both',
  }),
});
const report = await response.json();
```

---

## Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up

# Set environment variables in Railway dashboard
# (or use railway variables set KEY=VALUE)
```

Add a `Procfile`:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## Adding AI Analysis (Future)

When ready, flip `AI_ENABLED=true` in `.env` and add your key:
```
ANTHROPIC_API_KEY=sk-ant-...
```

The AI layer slots in as a post-processor on the `/analyze/listing` response,
adding narrative insights without changing the JSON contract.

---

## Project Structure

```
airrev-engine/
├── app/
│   ├── main.py                  # FastAPI app + routers
│   ├── core/
│   │   ├── config.py            # All settings + Canadian defaults
│   │   └── security.py          # API key auth
│   ├── models/
│   │   └── schemas.py           # All Pydantic models
│   ├── routers/
│   │   ├── analyze.py           # /analyze/listing (core endpoint)
│   │   ├── calculator.py        # /calculator/*
│   │   ├── neighborhood.py      # /neighborhood/*
│   │   └── creb.py              # /creb/monthly-summary
│   └── services/
│       ├── ddf_service.py       # CREA DDF API client
│       ├── calculator_service.py # All financial math
│       ├── rent_service.py      # Community rent benchmarks
│       └── supabase_service.py  # Logging + caching
├── supabase_schema.sql          # Run in Supabase SQL Editor
├── requirements.txt
├── .env.example
└── README.md
```

---

## Canadian-Specific Logic

- **Mortgage**: Semi-annual compounding (Canadian standard), not monthly
- **Amortization**: 25 years default (not 30 like US tools)
- **Property Tax**: 0.99% Calgary mill rate (2024)
- **LTR Vacancy**: 4% (Calgary 2024)
- **STR Occupancy**: 70% default (Calgary Airbnb market)
- **STR Insurance**: 0.5% (higher than LTR due to short-term nature)
