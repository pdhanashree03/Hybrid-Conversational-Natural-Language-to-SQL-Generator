export default function PipelineTrace({ trace }) {
  const steps = [
    { label: "Intent",      value: trace.intent },
    { label: "Aggregation", value: trace.aggregation || "none" },
    { label: "Tables hint", value: trace.candidate_tables.join(", ") || "—" },
    { label: "Entities",    value: trace.entities.map(e => `${e.text} (${e.label})`).join(", ") || "none" },
    { label: "Filters",     value: trace.filters.length
                                     ? trace.filters.map(f => `${f.column} ${f.operator} ${f.value}`).join(", ")
                                     : "none" },
    { label: "Limit",       value: trace.limit ?? "none" },
    { label: "Temporal",    value: trace.temporal_filter || "none" },
    { label: "Tokens",      value: trace.tokens.join(", ") },
  ];

  return (
    <div style={{ background: "#f8f8f8", border: "1px solid #e8e8e8",
                  borderRadius: 10, padding: "1rem 1.25rem", margin: "1.5rem 0" }}>
      <p style={{ fontSize: 12, fontWeight: 600, color: "#888",
                  letterSpacing: 1, marginBottom: 12 }}>NLP PIPELINE TRACE</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 24px" }}>
        {steps.map(s => (
          <div key={s.label} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
            <span style={{ fontSize: 12, color: "#999", minWidth: 90 }}>{s.label}</span>
            <span style={{ fontSize: 13, fontFamily: "monospace",
                           color: "#333", wordBreak: "break-all" }}>{String(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}