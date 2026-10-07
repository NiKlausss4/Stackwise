import { useEffect, useRef, useState } from "react";
import { fetchRecords } from "../api.js";
import { inr, num } from "../format.js";

const COLS = [
  ["bill_no", "Bill"], ["order_datetime", "Date & time"], ["outlet", "Outlet"], ["group", "Category"],
  ["item", "Item"], ["order_type", "Type"], ["settlement", "Settlement"], ["price", "Price", "r"],
  ["quantity", "Qty", "r"], ["revenue", "Revenue", "r"],
];
const SORT_KEY = { group: "grp" };

// Server-side pagination + sorting: the browser only ever holds one page (15 rows) of 300K.
export default function RecordsTable({ filters }) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("order_datetime");
  const [dir, setDir] = useState("desc");
  const [res, setRes] = useState(null);
  const ctrl = useRef(null);

  useEffect(() => { setPage(1); }, [filters]);
  useEffect(() => {
    ctrl.current?.abort();
    const c = new AbortController(); ctrl.current = c;
    fetchRecords(filters, page, SORT_KEY[sort] || sort, dir, c.signal).then(setRes).catch(() => {});
  }, [filters, page, sort, dir]);

  const pages = res ? Math.max(1, Math.ceil(res.total / res.page_size)) : 1;
  const onSort = (k) => { if (k === sort) setDir(dir === "asc" ? "desc" : "asc"); else { setSort(k); setDir("desc"); } };

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h3>Raw records <small>{res ? `${num(res.total)} matching line items` : "loading…"}</small></h3>
      <div className="tablewrap">
        <table>
          <thead><tr>{COLS.map(([k, label, cls]) => (
            <th key={k} className={cls} onClick={() => onSort(k)}>{label}{sort === k ? (dir === "asc" ? " ▲" : " ▼") : ""}</th>
          ))}</tr></thead>
          <tbody>
            {res?.rows.map((r, i) => (
              <tr key={i}>
                <td>{r.bill_no}</td><td>{r.order_datetime}</td><td>{r.outlet}</td><td>{r.group}</td>
                <td>{r.item}</td><td>{r.order_type}</td><td>{r.settlement}</td>
                <td className="r">{inr(r.price)}</td><td className="r">{r.quantity}</td><td className="r">{inr(r.revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button className="btn" disabled={page <= 1} onClick={() => setPage(1)}>« First</button>
        <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
        <span>Page {num(page)} of {num(pages)}</span>
        <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next ›</button>
      </div>
    </div>
  );
}
