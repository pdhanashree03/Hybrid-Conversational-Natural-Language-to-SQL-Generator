export default function ResultTable({ sql, explanation, confidence, data }) {
  return (
    <div>
      <div style={{ background: "#f0f7ff", border: "1px solid #c8dff8",
                    borderRadius: 10, padding: "1rem 1.25rem", marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: "#555" }}>{explanation}</span>
          <span style={{ fontSize: 12, color: "#888" }}>
            confidence {Math.round(confidence * 100)}%
          </span>
        </div>
        <pre style={{ margin: 0, fontSize: 12, fontFamily: "monospace",
                      color: "#333", whiteSpace: "pre-wrap" }}>{sql}</pre>
      </div>

      {data.rows.length === 0 ? (
        <p style={{ color: "#888", fontSize: 14 }}>No results found.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <p style={{ fontSize: 13, color: "#888", marginBottom: 8 }}>
            {data.count} row{data.count !== 1 ? "s" : ""}
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr>
                {data.columns.map(c => (
                  <th key={c} style={{ textAlign: "left", padding: "8px 12px",
                                       background: "#f5f5f5", borderBottom: "2px solid #e8e8e8",
                                       fontWeight: 600, fontSize: 13 }}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  {data.columns.map(c => (
                    <td key={c} style={{ padding: "8px 12px" }}>{String(row[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}