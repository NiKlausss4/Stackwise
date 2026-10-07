// Indian-style formatting: lakh / crore for large rupee amounts.
export const inr = (n) => "₹" + Math.round(n || 0).toLocaleString("en-IN");
export function inrCompact(n) {
  n = n || 0;
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`;
  return `₹${Math.round(n)}`;
}
export const num = (n) => (n || 0).toLocaleString("en-IN");
