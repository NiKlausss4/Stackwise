"""Correctness tests: the fast aggregates must equal exact SQL ground truth.
Run (after `python backend/etl.py`):  pip install pytest httpx && pytest backend -q
"""
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
con = sqlite3.connect(Path(main.DB_PATH))


def truth(where="1=1", params=()):
    return con.execute(f"SELECT COUNT(DISTINCT bill_no), SUM(revenue), COUNT(*) FROM line_items WHERE {where}", params).fetchone()


def test_unfiltered_kpis():
    k = client.get("/api/dashboard").json()["kpis"]
    assert (k["orders"], k["revenue"], k["line_items"]) == truth()


def test_filtered_kpis_and_breakdowns_sum_to_total():
    j = client.get("/api/dashboard?outlets=HSR%20Layout&outlets=MG%20Road&start=2026-01-01&end=2026-03-31").json()
    t = truth("outlet IN ('HSR Layout','MG Road') AND order_date BETWEEN '2026-01-01' AND '2026-03-31'")
    assert (j["kpis"]["orders"], j["kpis"]["revenue"]) == t[:2]
    assert sum(x["orders"] for x in j["by_order_type"]) == t[0]
    assert sum(x["orders"] for x in j["trend"]) == t[0]


def test_multi_category_filter_does_not_double_count_orders():
    j = client.get("/api/dashboard?groups=Burgers&groups=Sides").json()
    assert j["kpis"]["orders"] == truth("grp IN ('Burgers','Sides')")[0]


def test_week_and_month_buckets_preserve_totals():
    for g in ("week", "month"):
        j = client.get(f"/api/dashboard?granularity={g}").json()
        assert sum(x["revenue"] for x in j["trend"]) == j["kpis"]["revenue"]


def test_records_pagination_and_safe_sort():
    r = client.get("/api/records?page=2&page_size=10&sort=revenue;DROP TABLE line_items").json()
    assert len(r["rows"]) == 10 and r["total"] == 300000


def test_empty_selection():
    j = client.get("/api/dashboard?start=2030-01-01").json()
    assert j["kpis"]["orders"] == 0
