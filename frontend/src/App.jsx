import { useEffect, useMemo, useRef, useState } from "react";
import { fetchMeta, fetchDashboard, exportUrl } from "./api.js";
import { num, inr, inrCompact } from "./format.js";
import Filters from "./components/Filters.jsx";
import { TrendChart, BarBreakdown, Donut, TopItems } from "./components/Charts.jsx";
import Heatmap from "./components/Heatmap.jsx";
import RecordsTable from "./components/RecordsTable.jsx";

const EMPTY = { start: "", end: "", outlets: [], groups: [], order_types: [], settlements: [] };

function Kpi({ label, value, hint }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [filters, setFilters] = useState(EMPTY);
  const [granularity, setGranularity] = useState("day");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);

  useEffect(() => { fetchMeta().then(setMeta).catch((e) => setError(e.message)); }, []);

  // Refetch on filter change. Debounced so rapid chip clicks send one request, and any
  // in-flight request is aborted so a slow stale response can never overwrite a newer one.
  useEffect(() => {
    const t = setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      fetchDashboard(filters, granularity, ctrl.signal)
        .then((d) => { setData(d); setError(null); setLoading(false); })
        .catch((e) => { if (e.name !== "AbortError") { setError(e.message); setLoading(false); } });
    }, 150);
    return () => clearTimeout(t);
  }, [filters, granularity]);

  const active = useMemo(
    () => !!(filters.start || filters.end || filters.outlets.length || filters.groups.length ||
             filters.order_types.length || filters.settlements.length), [filters]);

  const k = data?.kpis;
  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>🍔 Stackwise <span style={{ fontWeight: 400, color: "var(--muted)" }}>· Burger Town Sales</span></h1>
          <div className="sub">
            {meta ? `${num(meta.total_rows)} line items · ${num(meta.total_orders)} orders · ${meta.min_date} → ${meta.max_date}` : "Loading dataset…"}
          </div>
        </div>
        <a className="btn primary" href={exportUrl(filters)} download>⬇ Export filtered CSV</a>
      </header>

      {meta && <Filters meta={meta} filters={filters} onChange={setFilters} onReset={() => setFilters(EMPTY)} active={active} />}

      {error && <div className="card error">Couldn’t load data: {error}</div>}

      {!data && !error && <div className="card"><div className="skeleton" /></div>}

      {data && (
        <div className={loading ? "loading" : ""}>
          <div className="kpis">
            <Kpi label="Total revenue" value={inrCompact(k.revenue)} hint={inr(k.revenue)} />
            <Kpi label="Orders" value={num(k.orders)} hint="distinct BillNo" />
            <Kpi label="Avg order value" value={inr(k.aov)} hint="revenue ÷ orders" />
            <Kpi label="Line items" value={num(k.line_items)} hint={`${k.items_per_order} per order`} />
            <Kpi label="Units sold" value={num(k.units)} />
          </div>

          {k.orders === 0 ? (
            <div className="card empty">No records match these filters. Try widening the date range.</div>
          ) : (
            <>
              <div className="card insights">
                <h3>Insights <small>auto-generated from the current selection</small></h3>
                <ul>{data.insights.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>

              <div className="grid g-2-1">
                <TrendChart data={data.trend} granularity={granularity} onGranularity={setGranularity} />
                <Donut title="Revenue by order type" data={data.by_order_type} />
              </div>
              <div className="grid g-3">
                <BarBreakdown title="Revenue by outlet" data={data.by_outlet} />
                <BarBreakdown title="Revenue by category" data={data.by_group} />
                <Donut title="Revenue by settlement" data={data.by_settlement} />
              </div>
              <div className="grid g-1-1">
                <TopItems data={data.top_items} />
                <Heatmap data={data.heatmap} />
              </div>
            </>
          )}
        </div>
      )}

      {data && <RecordsTable filters={filters} />}
    </div>
  );
}
