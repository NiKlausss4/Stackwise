# 🍔 Stackwise — Sales Analytics Dashboard

Stackwise is a web dashboard over ~300,000 Burger Town restaurant line items (110,478 orders, 6 outlets, Jun 2025 – Jun 2026).

**Live app:** https://stackwise-tx5o.onrender.com · **Repo:** https://github.com/NiKlausss4/Stackwise

![stack](https://img.shields.io/badge/React-Vite-blue) ![stack](https://img.shields.io/badge/FastAPI-SQLite-green)

## Features
- **KPIs:** revenue, orders, average order value, line items, units, items per order
- **Charts:** revenue trend (day/week/month toggle), order-type donut, revenue by outlet, by category, by settlement, top 10 items, weekday × hour heatmap
- **Filters:** date range (+ 30/90-day presets), outlet, category, order type, settlement. All combine and update every chart
- **Raw records table:** server-side pagination and sorting
- **Bonus:** filtered CSV export (streamed), auto-generated insights, responsive + dark-mode layout, in-memory caching, correctness tests

## Run locally
```bash
# 1. Backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python backend/etl.py                                   # builds data/sales.db (~5 s)
uvicorn backend.main:app --reload --port 8000

# 2. Frontend (second terminal)
cd frontend && npm install && npm run dev               # http://localhost:5173 (proxies /api to :8000)

# Tests (compare fast aggregates with exact SQL ground truth)
pip install pytest httpx && pytest backend -q
```
Production-style (single process serves API + built UI): `cd frontend && npm run build`, then run uvicorn as above and open `http://localhost:8000`.

## Architecture & decisions

```
data/sales.csv.gz ──ETL (build time)──▶ SQLite (indexed) ──▶ FastAPI (/api/*) ──▶ React + Recharts
                                              └── in-process LRU cache
```

**1. Why a database, and why SQLite?**
Reading the Excel file directly takes ~30 s per load, which rules out doing it per request or at every cold start. 300K rows is small enough that a heavyweight server (Postgres) would add operational cost with no benefit: the data is **read-only and static**, so SQLite gives indexed SQL, zero infrastructure, and a single deployable artifact. If the data grew to tens of millions of rows or needed live writes, I would move to PostgreSQL (the SQL is plain and portable) and add materialised rollups.

**2. ETL at build time, not request time.** `backend/etl.py` parses and validates the file, derives columns once (date, week, month, hour, weekday, revenue = price × quantity), and creates indexes. The Docker build runs it, so the container boots with a ready database. The repo ships a gzipped CSV (2.5 MB) instead of the 13 MB xlsx because it loads in ~1 s instead of ~30 s; the ETL accepts either. It also asserts that outlet, time, order type and settlement are constant within a `BillNo`, which the order-count optimisation below relies on.

**3. Counting orders fast and exactly.** The data is line-item grain, so "orders" means distinct `BillNo`. `COUNT(DISTINCT)` over 300K rows was the main cost of my first version (about 1 s per dashboard load). Because bill-level fields don't vary within a bill, the ETL flags each bill's first row (`is_first`) and orders become `SUM(is_first)`. When a *category* filter is active, one order can contain several selected categories, so the API falls back to exact `COUNT(DISTINCT)` there to avoid double counting. Tests verify both paths against ground truth.

**4. One request per filter change.** `/api/dashboard` returns every KPI and chart in one response. Internally it runs 4 table scans (one grouped by every dimension, from which all breakdowns and KPIs are rolled up in Python, plus daily trend, top items, heatmap) rather than ~9. Day/week/month views are derived from the cached daily series, so switching granularity costs nothing.

**5. Caching.** Data never changes, so results are cached in an in-process LRU keyed by the normalised filter set; identical concurrent requests share one computation; the default view is pre-warmed at startup; responses are gzip'd and send `Cache-Control`. Caveat: the cache is per process, so with multiple workers each warms its own (fine here; Redis would be the next step).

**6. Frontend performance.** The browser never receives raw rows except one 15-row page of the table (server-side pagination/sort). Filter changes are debounced (150 ms) and in-flight requests are aborted so stale responses can't overwrite fresh ones. Charts are in a separate vendor chunk (≈156 KB gzipped); the app code itself is ≈5 KB gzipped. The heatmap is plain CSS grid.

**7. Security.** All filters are bound parameters; sortable columns come from a whitelist; the DB is opened read-only.

## Measured performance
Measured in a slow single-core sandbox (a typical cloud instance should be faster):

| Request | Time |
|---|---|
| Default dashboard (pre-warmed / cached) | ~5 ms |
| New filter combination, cold | ~150–800 ms (most under 300 ms) |
| Same filters again | ~5 ms |
| Records page (any sort) | ~35 ms |
| Export 2.7 MB CSV (one outlet) | ~240 ms, streamed |

## Assumptions & trade-offs
- **Revenue = Price × Quantity** per line, as specified. No tax, discount or delivery fee is in the data, so none is modelled.
- **Free items:** 8,611 rows have `Price = 0` (BBQ/Mayo dips). They are kept: they count as line items and units but add no revenue.
- **"Region" → Outlet.** The dataset has no region column; outlet is the geographic dimension. `Brand` has a single value (Burger Town), so it is not offered as a filter.
- **Timestamps** are treated as local time with no timezone conversion. The ETL accepts both real datetimes and the `DD-MM-YYYY HH:MM:SS` strings from the brief.
- **Partial months:** the data starts mid-June 2025 and ends mid-June 2026, so the month-over-month insight only uses months with ≥ 25 days of data.
- **Insights are rule-based**, not LLM-generated: deterministic, free, and no API key to leak. An LLM summary layer could be added on top of the same aggregates.
- **Free-tier hosting** (Render) sleeps after inactivity, so the first request after idle can take ~30–60 s while the container wakes; the app is fast once warm.
- **Not done:** authentication, comparison-to-previous-period KPIs, Redis cache, CI.

## Deploy (Render, free)
1. Push this repo to GitHub (public).
2. Render → **New + → Blueprint** → pick the repo (`render.yaml` is included), or **New + → Web Service → Docker**.
3. Wait for the build (it builds the React app and runs the ETL), then paste the URL at the top of this README.

## Project structure
```
backend/   main.py (API) · etl.py (ingest) · test_api.py
frontend/  src/App.jsx · components/{Filters,Charts,Heatmap,RecordsTable}.jsx
data/      sales.csv.gz (source data; sales.db is generated, git-ignored)
Dockerfile · render.yaml · requirements.txt
```
