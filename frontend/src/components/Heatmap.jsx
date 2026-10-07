import { Fragment } from "react";
import { inr, inrCompact } from "../format.js";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Weekday x hour revenue heatmap built from plain CSS grid (lighter than another chart library).
export default function Heatmap({ data }) {
  const hours = [...new Set(data.map((d) => d.hour))].sort((a, b) => a - b);
  const map = new Map(data.map((d) => [`${d.dow}-${d.hour}`, d.revenue]));
  const max = Math.max(1, ...data.map((d) => d.revenue));
  return (
    <div className="card">
      <h3>When do we sell? <small>revenue by weekday × hour</small></h3>
      <div className="heat" style={{ "--cols": hours.length }}>
        <div />
        {hours.map((h) => <div key={h} className="hl">{h}</div>)}
        {DAYS.map((day, dow) => (
          <Fragment key={day}>
            <div className="dl">{day}</div>
            {hours.map((h) => {
              const v = map.get(`${dow}-${h}`) || 0;
              return <div key={`${dow}-${h}`} className="cell" title={`${day} ${h}:00 — ${inr(v)}`}
                style={{ background: `color-mix(in srgb, var(--c1) ${Math.round((v / max) * 100)}%, var(--grid))` }} />;
            })}
          </Fragment>
        ))}
      </div>
      <div className="sub" style={{ marginTop: 10 }}>Darker = more revenue (peak cell {inrCompact(max)}). Hours in 24h clock.</div>
    </div>
  );
}
