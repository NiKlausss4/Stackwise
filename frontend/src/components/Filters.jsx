const FIELDS = [
  ["outlets", "Outlet"], ["groups", "Category"], ["order_types", "Order type"], ["settlements", "Settlement"],
];

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function Filters({ meta, filters, onChange, onReset, active }) {
  const toggle = (key, v) => {
    const cur = filters[key];
    onChange({ ...filters, [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] });
  };
  const preset = (days) => onChange({ ...filters, start: days ? addDays(meta.max_date, -(days - 1)) : "", end: days ? meta.max_date : "" });

  return (
    <div className="card filters">
      <div className="frow">
        <div className="fgroup">
          <span className="flabel">Date range</span>
          <div className="dates">
            <input type="date" aria-label="Start date" min={meta.min_date} max={meta.max_date}
              value={filters.start} onChange={(e) => onChange({ ...filters, start: e.target.value })} />
            <span>→</span>
            <input type="date" aria-label="End date" min={meta.min_date} max={meta.max_date}
              value={filters.end} onChange={(e) => onChange({ ...filters, end: e.target.value })} />
            <button className="chip" onClick={() => preset(30)}>Last 30d</button>
            <button className="chip" onClick={() => preset(90)}>Last 90d</button>
            <button className="chip" onClick={() => preset(0)}>All time</button>
          </div>
        </div>
        {active && <button className="btn" style={{ alignSelf: "flex-end" }} onClick={onReset}>Reset filters</button>}
      </div>
      <div className="frow">
        {FIELDS.map(([key, label]) => (
          <div className="fgroup" key={key}>
            <span className="flabel">{label}</span>
            <div className="chips">
              {meta[key].map((v) => (
                <button key={v} className={"chip" + (filters[key].includes(v) ? " on" : "")}
                  aria-pressed={filters[key].includes(v)} onClick={() => toggle(key, v)}>{v}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
