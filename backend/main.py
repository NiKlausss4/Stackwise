"""FastAPI backend: read-only aggregate API over the SQLite database.

Design notes
- One combined /api/dashboard endpoint returns every chart + KPI in a single
  round trip, so a filter change costs one request instead of eight.
- Filters are turned into a parameterised WHERE clause (no string-built values,
  column names come from a whitelist), so there is no SQL injection surface.
- The data is static, so results are cached in-process keyed by the normalised
  filter set. Responses also carry Cache-Control so browsers/CDNs can reuse them.
"""
import csv
import io
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sales.db"
DIST = ROOT / "frontend" / "dist"

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    prewarm()
    yield


app = FastAPI(title="Stackwise Analytics API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ---------- database ----------
def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA mmap_size = 268435456")
    con.execute("PRAGMA cache_size = -65536")
    return con


_local = threading.local()


def db() -> sqlite3.Connection:
    if not hasattr(_local, "con"):
        _local.con = connect()
    return _local.con


def rows(sql: str, params: list) -> list[dict]:
    return [dict(r) for r in db().execute(sql, params).fetchall()]


# ---------- tiny LRU cache ----------
class LRU:
    def __init__(self, size: int = 512):
        self.size, self.data, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, k):
        with self.lock:
            if k in self.data:
                self.data.move_to_end(k)
                return self.data[k]

    def set(self, k, v):
        with self.lock:
            self.data[k] = v
            self.data.move_to_end(k)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


cache = LRU()


# ---------- filters ----------
MULTI = {"outlets": "outlet", "groups": "grp", "order_types": "order_type", "settlements": "settlement"}


def build_where(start, end, outlets, groups, order_types, settlements):
    clauses, params = [], []
    if start:
        clauses.append("order_date >= ?"); params.append(start)
    if end:
        clauses.append("order_date <= ?"); params.append(end)
    for key, vals in (("outlets", outlets), ("groups", groups),
                      ("order_types", order_types), ("settlements", settlements)):
        if vals:
            clauses.append(f"{MULTI[key]} IN ({','.join('?' * len(vals))})")
            params.extend(vals)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def filter_key(*parts):
    return tuple(tuple(sorted(p)) if isinstance(p, list) else p for p in parts)


# ---------- endpoints ----------
@app.get("/api/meta")
def meta(response: Response):
    response.headers["Cache-Control"] = "public, max-age=3600"
    k = ("meta",)
    if (hit := cache.get(k)):
        return hit
    r = rows("SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date, "
             "COUNT(*) AS total_rows, COUNT(DISTINCT bill_no) AS total_orders FROM line_items", [])[0]
    out = {**r,
           "outlets": [x["outlet"] for x in rows("SELECT DISTINCT outlet FROM line_items ORDER BY 1", [])],
           "groups": [x["grp"] for x in rows("SELECT DISTINCT grp FROM line_items ORDER BY 1", [])],
           "order_types": [x["order_type"] for x in rows("SELECT DISTINCT order_type FROM line_items ORDER BY 1", [])],
           "settlements": [x["settlement"] for x in rows("SELECT DISTINCT settlement FROM line_items ORDER BY 1", [])]}
    cache.set(k, out)
    return out


def orders_expr(groups):
    """Exact order count. Fast path (SUM of a precomputed flag) unless filtering by category,
    where an order can contain several selected categories and must not be double counted."""
    return "COUNT(DISTINCT bill_no)" if groups else "SUM(is_first)"


def pct_change(cur, prev):
    return None if not prev else round((cur - prev) / prev * 100, 1)


def inr_short(n):
    if n >= 1e7: return f"₹{n/1e7:.2f} Cr"
    if n >= 1e5: return f"₹{n/1e5:.1f} L"
    return f"₹{n:,.0f}"


def make_insights(kpis, by_outlet, by_type, by_group, heat, monthly):
    """Rule-based insights computed from the filtered data (no external API needed).
    A comparison is only emitted when the selection still has something to compare."""
    if not kpis["revenue"]:
        return ["No data for the selected filters."]
    rev, out = kpis["revenue"], []
    if len(by_outlet) > 1:
        t = by_outlet[0]
        out.append(f"{t['name']} is the top outlet with {inr_short(t['revenue'])} ({t['revenue']/rev*100:.0f}% of revenue); "
                   f"{by_outlet[-1]['name']} is the lowest at {by_outlet[-1]['revenue']/rev*100:.0f}%.")
    if len(by_group) > 1:
        out.append(f"{by_group[0]['name']} is the top category at {by_group[0]['revenue']/rev*100:.0f}% of revenue.")
    if len(by_type) > 1:
        t = by_type[0]
        out.append(f"{t['name']} is the biggest channel ({t['revenue']/rev*100:.0f}% of revenue), "
                   f"with an average order of {inr_short(t['revenue']/max(t['orders'],1))}.")
    elif by_type:
        out.append(f"All selected orders are {by_type[0]['name']}, averaging {inr_short(kpis['aov'])} per order.")
    by_hour = {}
    for h in heat:
        by_hour[h["hour"]] = by_hour.get(h["hour"], 0) + h["revenue"]
    if by_hour:
        peak = max(by_hour, key=by_hour.get)
        out.append(f"Peak trading hour is {peak:02d}:00–{peak+1:02d}:00 ({by_hour[peak]/rev*100:.0f}% of revenue).")
    full = [m for m in monthly if m["days"] >= 25]  # skip partial months
    if len(full) >= 2:
        a, b = full[-2], full[-1]
        ch = pct_change(b["revenue"], a["revenue"])
        if ch is not None:
            out.append(f"Revenue in {b['month']} was {abs(ch)}% {'up' if ch >= 0 else 'down'} vs {a['month']}.")
    return out


def bucket_trend(daily, granularity):
    """Roll the cached daily series up to week/month in Python (orders are per-day exact, so sums are exact)."""
    if granularity == "day":
        return daily
    from datetime import date
    out = OrderedDict()
    for d in daily:
        y, m, dd = map(int, d["period"].split("-"))
        if granularity == "month":
            k = d["period"][:7]
        else:
            iso = date(y, m, dd).isocalendar()
            k = f"{iso[0]}-W{iso[1]:02d}"
        o = out.setdefault(k, {"period": k, "revenue": 0, "orders": 0})
        o["revenue"] += d["revenue"]; o["orders"] += d["orders"]
    return list(out.values())


def compute_dashboard(start, end, outlets, groups, order_types, settlements):
    where, p = build_where(start, end, outlets, groups, order_types, settlements)

    # Scan 1: one pass grouped by every filterable dimension (<= ~500 rows). All KPIs and
    # breakdown charts are rolled up from this small result in Python instead of 6 more scans.
    cube = rows(f"""SELECT outlet, grp, order_type, settlement, SUM(revenue) AS revenue,
                    SUM(quantity) AS units, COUNT(*) AS lines, SUM(is_first) AS orders,
                    SUM(is_first_grp) AS grp_orders FROM line_items{where}
                    GROUP BY outlet, grp, order_type, settlement""", p)

    def roll(dim, orders_key):
        acc = {}
        for r in cube:
            a = acc.setdefault(r[dim], {"name": r[dim], "revenue": 0, "units": 0, "orders": 0})
            a["revenue"] += r["revenue"]; a["units"] += r["units"]; a["orders"] += r[orders_key]
        return sorted(acc.values(), key=lambda x: -x["revenue"])

    by_outlet = roll("outlet", "orders")
    by_type = roll("order_type", "orders")
    by_settlement = roll("settlement", "orders")
    by_group = roll("grp", "grp_orders")  # orders that contain each category
    orders_total = sum(r["orders"] for r in cube)

    if groups and cube:
        # An order can hold several selected categories, so summing flags would double count.
        # Fall back to exact COUNT(DISTINCT) for the order-based figures (slower, rarer path).
        orders_total = rows(f"SELECT COUNT(DISTINCT bill_no) AS n FROM line_items{where}", p)[0]["n"]
        for dim, col, target in (("outlet", "outlet", by_outlet), ("order_type", "order_type", by_type),
                                 ("settlement", "settlement", by_settlement)):
            exact = {r["k"]: r["n"] for r in rows(
                f"SELECT {col} AS k, COUNT(DISTINCT bill_no) AS n FROM line_items{where} GROUP BY {col}", p)}
            for t in target:
                t["orders"] = exact.get(t["name"], 0)

    revenue = sum(r["revenue"] for r in cube)
    lines = sum(r["lines"] for r in cube)
    kpis = {"revenue": revenue, "line_items": lines, "orders": orders_total,
            "units": sum(r["units"] for r in cube),
            "aov": round(revenue / orders_total, 2) if orders_total else 0,
            "items_per_order": round(lines / orders_total, 2) if orders_total else 0}

    # Scan 2: daily series (also feeds the weekly/monthly views and the month-over-month insight)
    oe = orders_expr(groups)
    daily = rows(f"""SELECT order_date AS period, SUM(revenue) AS revenue, {oe} AS orders
                     FROM line_items{where} GROUP BY order_date ORDER BY order_date""", p)

    # Scan 3: top items.  Scan 4: weekday x hour heatmap.
    top_items = rows(f"""SELECT item AS name, grp AS category, SUM(revenue) AS revenue,
                         SUM(quantity) AS units FROM line_items{where}
                         GROUP BY item ORDER BY revenue DESC LIMIT 10""", p)
    heat = rows(f"""SELECT order_dow AS dow, order_hour AS hour, SUM(revenue) AS revenue
                    FROM line_items{where} GROUP BY order_dow, order_hour""", p)

    months = OrderedDict()
    for d in daily:
        m = months.setdefault(d["period"][:7], {"month": d["period"][:7], "revenue": 0, "days": 0})
        m["revenue"] += d["revenue"]; m["days"] += 1

    return {"kpis": kpis, "daily": daily, "by_outlet": by_outlet, "by_group": by_group,
            "by_order_type": by_type, "by_settlement": by_settlement,
            "top_items": top_items, "heatmap": heat,
            "insights": make_insights(kpis, by_outlet, by_type, by_group, heat, list(months.values()))}


_inflight: dict = {}
_inflight_lock = threading.Lock()


@app.get("/api/dashboard")
def dashboard(
    response: Response,
    start: Optional[str] = None, end: Optional[str] = None,
    outlets: list[str] = Query(default=[]), groups: list[str] = Query(default=[]),
    order_types: list[str] = Query(default=[]), settlements: list[str] = Query(default=[]),
    granularity: str = Query("day", pattern="^(day|week|month)$"),
):
    response.headers["Cache-Control"] = "public, max-age=300"
    key = filter_key("dash", start, end, outlets, groups, order_types, settlements)
    result = cache.get(key)
    if result is None:
        # De-duplicate identical concurrent requests (e.g. several tabs / rapid filter clicks):
        # the first computes, the rest wait on the same lock instead of re-scanning the table.
        with _inflight_lock:
            lock = _inflight.setdefault(key, threading.Lock())
        with lock:
            result = cache.get(key)
            if result is None:
                result = compute_dashboard(start, end, outlets, groups, order_types, settlements)
                cache.set(key, result)
        with _inflight_lock:
            _inflight.pop(key, None)
    out = {k: v for k, v in result.items() if k != "daily"}
    out["trend"] = bucket_trend(result["daily"], granularity)
    return out


def prewarm():
    """Compute the default (unfiltered) view at boot so the first visitor gets a cached response."""
    if DB_PATH.exists():
        threading.Thread(target=lambda: cache.set(filter_key("dash", None, None, [], [], [], []),
                         compute_dashboard(None, None, [], [], [], [])), daemon=True).start()


SORTABLE = {"bill_no", "order_datetime", "outlet", "grp", "order_type", "item",
            "price", "quantity", "revenue", "settlement"}


@app.get("/api/records")
def records(
    response: Response,
    start: Optional[str] = None, end: Optional[str] = None,
    outlets: list[str] = Query(default=[]), groups: list[str] = Query(default=[]),
    order_types: list[str] = Query(default=[]), settlements: list[str] = Query(default=[]),
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    sort: str = "order_datetime", direction: str = Query("desc", pattern="^(asc|desc)$"),
):
    """Server-side pagination so the browser never holds more than one page of rows."""
    response.headers["Cache-Control"] = "public, max-age=300"
    if sort not in SORTABLE:
        sort = "order_datetime"
    where, p = build_where(start, end, outlets, groups, order_types, settlements)
    key = filter_key("rec", start, end, outlets, groups, order_types, settlements,
                     page, page_size, sort, direction)
    if (hit := cache.get(key)):
        return hit
    total = rows(f"SELECT COUNT(*) AS n FROM line_items{where}", p)[0]["n"]
    data = rows(f"""SELECT bill_no, order_datetime, outlet, grp AS "group", order_type, item,
                    price, quantity, revenue, settlement FROM line_items{where}
                    ORDER BY {sort} {direction}, bill_no LIMIT ? OFFSET ?""",
                p + [page_size, (page - 1) * page_size])
    out = {"total": total, "page": page, "page_size": page_size, "rows": data}
    cache.set(key, out)
    return out


@app.get("/api/export.csv")
def export_csv(
    start: Optional[str] = None, end: Optional[str] = None,
    outlets: list[str] = Query(default=[]), groups: list[str] = Query(default=[]),
    order_types: list[str] = Query(default=[]), settlements: list[str] = Query(default=[]),
):
    """Streams the filtered rows as CSV without materialising them in memory."""
    where, p = build_where(start, end, outlets, groups, order_types, settlements)
    cols = ["bill_no", "outlet", "order_datetime", "grp", "order_type", "item",
            "price", "quantity", "revenue", "settlement"]

    def gen():
        con = connect()  # own connection: the generator outlives the request thread
        cur = con.execute(f"SELECT {','.join(cols)} FROM line_items{where} ORDER BY order_datetime", p)
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["BillNo", "Outlet", "Order_Datetime", "Group", "Order_Type", "Item",
                    "Price", "Quantity", "Revenue", "Settlement"])
        yield buf.getvalue()
        while chunk := cur.fetchmany(5000):
            buf.seek(0); buf.truncate()
            w.writerows([tuple(r) for r in chunk])
            yield buf.getvalue()
        con.close()

    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=burger-town-export.csv"})


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- serve the built React app (production) ----------
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
