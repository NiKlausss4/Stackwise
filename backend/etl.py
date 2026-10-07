"""ETL: raw sales file -> indexed SQLite database.

Run once at build time (see Dockerfile), never at request time.
Reading the original .xlsx takes ~30s for 300K rows, so the repo ships a
gzipped CSV copy (data/sales.csv.gz) that loads in ~1s. Both are supported.

    python backend/etl.py [input_path] [output_db]
"""
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "sales.csv.gz"
DB = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "sales.db"

EXPECTED = ["BillNo", "Outlet_Name", "Order_Datetime", "Group", "Order_Type",
            "Item", "Price", "Quantity", "Settlement", "Brand"]


def load(path: Path) -> pd.DataFrame:
    if path.suffix in (".xlsx", ".xlsm"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    missing = set(EXPECTED) - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {missing}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # The brief says DD-MM-YYYY HH:MM:SS; Excel may hand us real datetimes instead.
    if df["Order_Datetime"].dtype == object or str(df["Order_Datetime"].dtype).startswith("str"):
        parsed = pd.to_datetime(df["Order_Datetime"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
        iso = pd.to_datetime(df["Order_Datetime"], errors="coerce")
        df["Order_Datetime"] = parsed.fillna(iso)
    else:
        df["Order_Datetime"] = pd.to_datetime(df["Order_Datetime"])

    before = len(df)
    df = df.dropna(subset=["BillNo", "Order_Datetime", "Price", "Quantity"])
    df = df.drop_duplicates()
    # The is_first trick needs bill-level fields to be constant; fail loudly if a new file breaks that.
    g = df.groupby("BillNo")[["Outlet_Name", "Order_Type", "Settlement", "Order_Datetime"]].nunique()
    assert (g.max().max() == 1), "bill-level columns vary within a BillNo; use COUNT(DISTINCT) instead"
    if before != len(df):
        print(f"dropped {before - len(df)} invalid/duplicate rows")

    for c in ["Outlet_Name", "Group", "Order_Type", "Item", "Settlement", "Brand"]:
        df[c] = df[c].astype(str).str.strip()
    df["BillNo"] = df["BillNo"].astype("int64")
    df["Price"] = df["Price"].astype("int64")
    df["Quantity"] = df["Quantity"].astype("int64")

    # Derived columns so the API never computes them per request.
    dt = df["Order_Datetime"]
    df["order_date"] = dt.dt.strftime("%Y-%m-%d")
    df["order_month"] = dt.dt.strftime("%Y-%m")
    df["order_hour"] = dt.dt.hour
    df["order_dow"] = dt.dt.dayofweek  # 0 = Monday
    iso = dt.dt.isocalendar()
    df["order_week"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    df["revenue"] = df["Price"] * df["Quantity"]
    # Outlet/time/type/settlement are constant within a bill (verified on this data), so an
    # order can be counted as SUM(is_first) instead of the much slower COUNT(DISTINCT bill_no).
    # is_first_grp does the same per (bill, category) for category breakdowns.
    df["is_first"] = (~df.duplicated("BillNo")).astype(int)
    df["is_first_grp"] = (~df.duplicated(["BillNo", "Group"])).astype(int)
    df["order_datetime"] = dt.dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def main() -> None:
    t0 = time.time()
    df = clean(load(SRC))
    out = df.rename(columns={
        "BillNo": "bill_no", "Outlet_Name": "outlet", "Group": "grp",
        "Order_Type": "order_type", "Item": "item", "Price": "price",
        "Quantity": "quantity", "Settlement": "settlement", "Brand": "brand",
    })[["bill_no", "outlet", "order_datetime", "order_date", "order_month",
        "order_week", "order_hour", "order_dow", "is_first", "is_first_grp", "grp", "order_type", "item", "price",
        "quantity", "revenue", "settlement", "brand"]]

    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    out.to_sql("line_items", con, index=False, chunksize=50_000)
    for col in ["order_date", "outlet", "grp", "order_type", "settlement", "bill_no"]:
        con.execute(f"CREATE INDEX idx_{col} ON line_items({col})")
    # Most dashboard queries filter by date range first, then one more dimension.
    con.execute("CREATE INDEX idx_date_outlet ON line_items(order_date, outlet)")
    con.execute("ANALYZE")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"loaded {len(out):,} rows into {DB} ({DB.stat().st_size/1e6:.1f} MB) in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
