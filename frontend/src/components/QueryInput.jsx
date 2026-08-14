import { useState } from "react";

const EXAMPLES = [
  "Show me top 5 customers by revenue",
  "Count orders placed this month",
  "Average order value by product category",
  "List products with stock less than 10",
];

export default function QueryInput({ onSubmit, loading }) {
  const [q, setQ] = useState("");
  return (
    <div>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={q} onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === "Enter" && q.trim() && onSubmit(q)}
          placeholder="Ask anything about your database…"
          style={{ flex: 1, padding: "10px 14px", border: "1px solid #ddd",
                   borderRadius: 8, fontSize: 15 }} />
        <button onClick={() => q.trim() && onSubmit(q)} disabled={loading}
          style={{ padding: "10px 20px", background: "#5b47e0", color: "#fff",
                   border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 500 }}>
          {loading ? "…" : "Ask"}
        </button>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        {EXAMPLES.map(ex => (
          <button key={ex} onClick={() => { setQ(ex); onSubmit(ex); }}
            style={{ fontSize: 12, padding: "4px 10px", border: "1px solid #ddd",
                     borderRadius: 20, background: "#fff", cursor: "pointer", color: "#555" }}>
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}