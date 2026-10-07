// Thin API layer. Filters -> query string (repeated keys for multi-selects).
export function toQuery(filters, extra = {}) {
  const q = new URLSearchParams();
  if (filters.start) q.set("start", filters.start);
  if (filters.end) q.set("end", filters.end);
  for (const k of ["outlets", "groups", "order_types", "settlements"])
    (filters[k] || []).forEach((v) => q.append(k, v));
  Object.entries(extra).forEach(([k, v]) => q.set(k, v));
  return q.toString();
}

async function get(url, signal) {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export const fetchMeta = () => get("/api/meta");
export const fetchDashboard = (f, granularity, signal) =>
  get(`/api/dashboard?${toQuery(f, { granularity })}`, signal);
export const fetchRecords = (f, page, sort, direction, signal) =>
  get(`/api/records?${toQuery(f, { page, page_size: 15, sort, direction })}`, signal);
export const exportUrl = (f) => `/api/export.csv?${toQuery(f)}`;
