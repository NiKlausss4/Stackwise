import { ResponsiveContainer, LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend } from "recharts";
import { inr, inrCompact, num } from "../format.js";

const COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)", "var(--c7)"];
const axis = { fontSize: 11, fill: "var(--muted)" };

function Tip({ active, payload, label, extra }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tooltip">
      <b>{label ?? p.name}</b>
      <div>Revenue: {inr(p.revenue)}</div>
      {p.orders != null && <div>Orders: {num(p.orders)}</div>}
      {p.units != null && <div>Units: {num(p.units)}</div>}
    </div>
  );
}

export function TrendChart({ data, granularity, onGranularity }) {
  return (
    <div className="card">
      <h3>
        Revenue trend
        <span className="seg" style={{ float: "right" }}>
          {["day", "week", "month"].map((g) => (
            <button key={g} className={granularity === g ? "on" : ""} onClick={() => onGranularity(g)}>{g}</button>
          ))}
        </span>
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="period" tick={axis} minTickGap={40} tickFormatter={(v) => (granularity === "day" ? v.slice(5) : v)} />
          <YAxis tick={axis} tickFormatter={inrCompact} width={56} />
          <Tooltip content={<Tip />} />
          <Line type="monotone" dataKey="revenue" stroke="var(--c1)" strokeWidth={2} dot={data.length < 40} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BarBreakdown({ title, data }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 12 }}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" tick={axis} tickFormatter={inrCompact} />
          <YAxis type="category" dataKey="name" tick={axis} width={86} />
          <Tooltip content={<Tip />} cursor={{ fill: "var(--grid)" }} />
          <Bar dataKey="revenue" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Donut({ title, data }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} dataKey="revenue" nameKey="name" innerRadius="52%" outerRadius="82%" paddingAngle={2} isAnimationActive={false}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="var(--card)" />)}
          </Pie>
          <Tooltip content={<Tip />} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TopItems({ data }) {
  return (
    <div className="card">
      <h3>Top 10 items <small>by revenue</small></h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 12 }}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" tick={axis} tickFormatter={inrCompact} />
          <YAxis type="category" dataKey="name" tick={axis} width={150} />
          <Tooltip content={<Tip />} cursor={{ fill: "var(--grid)" }} />
          <Bar dataKey="revenue" fill="var(--c2)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
