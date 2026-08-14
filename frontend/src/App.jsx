import { useState, useRef } from "react";

const PURPLE    = "#534AB7";
const PURPLE_LT = "#EEEDFE";
const PURPLE_MD = "#7F77DD";
const TEAL_LT   = "#E1F5EE";
const TEAL_DK   = "#085041";

const EXAMPLES = [
  "Show all artists",
  "Count tracks by genre",
  "Top 5 customers by total",
  "Total revenue per country",
  "Average invoice total",
  "Show albums and artists",
  "Customers from Germany",
  "Invoices with total more than 10",
  "Count tracks per genre ordered by count",
  "Average invoice total by customer from USA",
];

export default function App() {
  const [uploading, setUploading] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [dbInfo,    setDbInfo]    = useState(null);
  const [dbUrl,     setDbUrl]     = useState(null);
  const [result,    setResult]    = useState(null);
  const [error,     setError]     = useState(null);
  const [query,     setQuery]     = useState("");
  const [dragOver,  setDragOver]  = useState(false);
  const [history,   setHistory]   = useState([]);
  const [conversation, setConversation] = useState([]);
  const fileRef = useRef();

  async function handleUpload(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["db","sqlite","sqlite3"].includes(ext)) {
      setError(`Unsupported file type .${ext} — use .db, .sqlite, or .sqlite3`);
      return;
    }
    setUploading(true);
    setError(null);
    setResult(null);
    setHistory([]);
    setConversation([]);
    try {
      await fetch("/api/clear-session", { method: "POST" }).catch(() => {});
      const form = new FormData();
      form.append("file", file);
      const res  = await fetch("/api/upload-db", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      setDbUrl(data.db_url);
      setDbInfo({ filename: data.filename, tables: data.tables });
    } catch (e) {
      setError("Upload failed: " + e.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleQuery(q) {
    const text = (q || query).trim();
    if (!text || !dbUrl) return;
    setQuery(text);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("query",  text);
      form.append("db_url", dbUrl);
      const res  = await fetch("/api/ask", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Query failed");
      setResult(data);
      setHistory(h => [{ query: text, rows: data.data.count }, ...h].slice(0, 8));
      setConversation(data.conversation || []);

    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f8f7ff", fontFamily: "'Segoe UI', system-ui, sans-serif" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } * { box-sizing: border-box; }`}</style>

      <div style={{
        background: "#fff", borderBottom: "0.5px solid #e8e5f8",
        padding: "0 2rem", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 56,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 30, height: 30, background: PURPLE_LT, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={PURPLE} strokeWidth="2">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
            </svg>
          </div>
          <span style={{ fontWeight: 600, fontSize: 15, color: "#1a1a2e" }}>NL-to-SQL</span>
          <span style={{ fontSize: 11, padding: "2px 8px", background: PURPLE_LT, color: PURPLE, borderRadius: 20, fontWeight: 500 }}>NLP powered</span>
        </div>
        {dbInfo && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, background: TEAL_LT, color: TEAL_DK, fontSize: 12, padding: "4px 12px", borderRadius: 20, fontWeight: 500 }}>
              ✓ {dbInfo.filename}
            </div>
            <span style={{ fontSize: 12, color: "#888" }}>{dbInfo.tables.length} tables</span>
          </div>
        )}
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "2rem 1rem" }}>

        {!dbInfo && (
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6, background: PURPLE_LT, color: PURPLE, fontSize: 12, fontWeight: 500, padding: "5px 14px", borderRadius: 20, marginBottom: 16 }}>
              ✦ Ask your database in plain English
            </div>
            <h1 style={{ fontSize: 32, fontWeight: 700, color: "#1a1a2e", marginBottom: 10, lineHeight: 1.3 }}>
              Query any database,<br />no SQL needed
            </h1>
            <p style={{ fontSize: 15, color: "#666", maxWidth: 480, margin: "0 auto 28px" }}>
              Our NLP engine understands your question, builds the SQL, and fetches the answer — all in seconds.
            </p>
            <div style={{ display: "flex", justifyContent: "center", gap: 32, marginBottom: 32 }}>
              {[["🔍","Filters & JOINs"],["📊","Aggregations"],["📅","Date queries"],["🗃️","Any SQLite DB"]].map(([ic,lb]) => (
                <div key={lb} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 22, marginBottom: 4 }}>{ic}</div>
                  <div style={{ fontSize: 12, color: "#888" }}>{lb}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!dbInfo && (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? PURPLE_MD : "#d4d0f0"}`,
              borderRadius: 16, padding: "3rem 2rem", textAlign: "center",
              cursor: "pointer", background: dragOver ? PURPLE_LT : "#fff",
              transition: "all 0.2s", marginBottom: 24,
            }}
          >
            <input ref={fileRef} type="file" accept=".db,.sqlite,.sqlite3"
              onChange={e => handleUpload(e.target.files[0])} style={{ display: "none" }} />
            {uploading ? (
              <div>
                <div style={{ width: 48, height: 48, border: `3px solid ${PURPLE_LT}`, borderTopColor: PURPLE, borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 16px" }}/>
                <p style={{ color: "#888", fontSize: 14 }}>Uploading and reading schema…</p>
              </div>
            ) : (
              <>
                <div style={{ width: 56, height: 56, background: PURPLE_LT, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", fontSize: 24 }}>🗄️</div>
                <p style={{ fontWeight: 600, fontSize: 16, color: "#1a1a2e", marginBottom: 6 }}>Drop your database file here</p>
                <p style={{ fontSize: 13, color: "#999", marginBottom: 16 }}>or click to browse your files</p>
                <div style={{ display: "flex", justifyContent: "center", gap: 8 }}>
                  {[".db",".sqlite",".sqlite3"].map(ext => (
                    <span key={ext} style={{ fontSize: 12, padding: "3px 10px", background: "#f3f2fb", border: "0.5px solid #d4d0f0", borderRadius: 8, color: "#666" }}>{ext}</span>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {dbInfo && (
          <>
            <div style={{ background: "#fff", border: "0.5px solid #e8e5f8", borderRadius: 12, padding: "12px 16px", marginBottom: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, color: "#888", flexShrink: 0 }}>Tables:</span>
              {dbInfo.tables.map(t => (
                <span key={t} style={{ fontSize: 12, padding: "3px 10px", background: PURPLE_LT, color: PURPLE, borderRadius: 20, fontWeight: 500 }}>{t}</span>
              ))}
              <button onClick={() => { setDbInfo(null); setDbUrl(null); setResult(null); setHistory([]); }}
                style={{ marginLeft: "auto", fontSize: 12, color: "#999", background: "none", border: "none", cursor: "pointer" }}>
                ✕ Change file
              </button>
            </div>

            <div style={{ background: "#fff", border: "0.5px solid #e8e5f8", borderRadius: 16, overflow: "hidden", marginBottom: 16, boxShadow: "0 2px 12px rgba(83,74,183,0.06)" }}>
              <div style={{ display: "flex" }}>
                <div style={{ padding: "14px 16px", borderRight: "0.5px solid #e8e5f8", display: "flex", alignItems: "center" }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#aaa" strokeWidth="2">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                  </svg>
                </div>
                <input value={query} onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleQuery()}
                  placeholder="Ask anything — e.g. show top 5 customers by revenue…"
                  disabled={loading}
                  style={{ flex: 1, border: "none", padding: "14px 16px", fontSize: 15, outline: "none", background: "transparent", color: "#1a1a2e" }} />
                <button onClick={() => handleQuery()} disabled={loading || !query.trim()}
                  style={{ margin: 8, padding: "10px 20px", background: loading || !query.trim() ? "#c5c0e8" : PURPLE, color: "#fff", border: "none", borderRadius: 10, cursor: loading || !query.trim() ? "not-allowed" : "pointer", fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 6, transition: "background 0.2s" }}>
                  {loading ? (
                    <><div style={{ width: 14, height: 14, border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>Running…</>
                  ) : "Ask →"}
                </button>
              </div>
              <div style={{ padding: "10px 16px", borderTop: "0.5px solid #f0eeff", display: "flex", flexWrap: "wrap", gap: 6, background: "#faf9ff" }}>
                <span style={{ fontSize: 11, color: "#bbb", alignSelf: "center", marginRight: 4 }}>Try:</span>
                {EXAMPLES.map(ex => (
                  <button key={ex} onClick={() => { setQuery(ex); handleQuery(ex); }}
                    style={{ fontSize: 12, padding: "4px 12px", border: "0.5px solid #e0ddf5", borderRadius: 20, background: "#fff", cursor: "pointer", color: "#555", transition: "all 0.15s" }}
                    onMouseEnter={e => { e.target.style.background = PURPLE_LT; e.target.style.borderColor = PURPLE_MD; e.target.style.color = PURPLE; }}
                    onMouseLeave={e => { e.target.style.background = "#fff"; e.target.style.borderColor = "#e0ddf5"; e.target.style.color = "#555"; }}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
                        {conversation.length > 1 && (
              <div style={{
                background: "#fff", border: "0.5px solid #e8e5f8",
                borderRadius: 12, padding: "12px 16px", marginBottom: 16,
              }}>
                <p style={{ fontSize: 11, color: "#bbb", marginBottom: 8,
                            letterSpacing: ".04em", margin: "0 0 8px" }}>
                  CONVERSATION HISTORY
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {conversation.map(t => (
                    <div key={t.turn}
                      onClick={() => { setQuery(t.query); handleQuery(t.query); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "6px 10px", borderRadius: 8,
                        background: "#faf9ff", cursor: "pointer",
                      }}
                    >
                      <span style={{
                        width: 20, height: 20, borderRadius: "50%",
                        background: PURPLE_LT, color: PURPLE,
                        fontSize: 11, fontWeight: 600, flexShrink: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        {t.turn}
                      </span>
                      <span style={{ fontSize: 12, color: "#555", flex: 1 }}>{t.query}</span>
                      <span style={{ fontSize: 11, color: "#bbb" }}>
                        {t.tables?.join(", ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {history.length > 1 && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
                {history.slice(1).map((h, i) => (
                  <button key={i} onClick={() => { setQuery(h.query); handleQuery(h.query); }}
                    style={{ fontSize: 11, padding: "3px 10px", border: "0.5px solid #e0ddf5", borderRadius: 20, background: "#fff", cursor: "pointer", color: "#888", display: "flex", alignItems: "center", gap: 4 }}>
                    ↺ {h.query.length > 30 ? h.query.slice(0,30)+"…" : h.query}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {loading && (
          <div style={{ background: "#fff", border: "0.5px solid #e8e5f8", borderRadius: 12, padding: "20px 24px", marginBottom: 16, display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ width: 36, height: 36, background: PURPLE_LT, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <div style={{ width: 18, height: 18, border: `2px solid ${PURPLE_LT}`, borderTopColor: PURPLE, borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>
            </div>
            <div>
              <p style={{ fontSize: 14, fontWeight: 500, color: "#1a1a2e", marginBottom: 2 }}>Running NLP pipeline…</p>
              <p style={{ fontSize: 12, color: "#999" }}>Extracting intent → building query plan → generating SQL → fetching results</p>
            </div>
          </div>
        )}

        {error && (
          <div style={{ background: "#fff5f5", border: "0.5px solid #fecaca", borderRadius: 12, padding: "14px 18px", marginBottom: 16, display: "flex", gap: 12 }}>
            <span style={{ fontSize: 18, flexShrink: 0 }}>⚠️</span>
            <div>
              <p style={{ fontSize: 13, fontWeight: 500, color: "#991b1b", marginBottom: 4 }}>Something went wrong</p>
              <p style={{ fontSize: 12, color: "#b91c1c", whiteSpace: "pre-wrap" }}>{error}</p>
            </div>
          </div>
        )}

        {result && <ResultCard result={result} />}
      </div>
    </div>
  );
}

function ResultCard({ result }) {
  const [traceOpen, setTraceOpen] = useState(false);
  const { sql, explanation, confidence, data, trace, used_llm } = result;
  return (
    <div style={{ background: "#fff", border: "0.5px solid #e8e5f8", borderRadius: 16, overflow: "hidden", boxShadow: "0 2px 16px rgba(83,74,183,0.07)" }}>
      <div style={{ padding: "14px 20px", borderBottom: "0.5px solid #f0eeff", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 28, height: 28, background: TEAL_LT, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>✓</div>
          <span style={{ fontSize: 13, color: "#444" }}>{explanation}</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {used_llm && <span style={{ fontSize: 11, padding: "3px 8px", background: "#FAEEDA", color: "#633806", borderRadius: 20 }}>LLM assisted</span>}
          <span style={{ fontSize: 11, padding: "3px 8px", background: TEAL_LT, color: TEAL_DK, borderRadius: 20 }}>{Math.round((confidence||0.95)*100)}% confidence</span>
          <span style={{ fontSize: 11, padding: "3px 8px", background: PURPLE_LT, color: PURPLE, borderRadius: 20 }}>{data.count} row{data.count!==1?"s":""}</span>
        </div>
      </div>

      <div style={{ background: "#1e1e2e", padding: "14px 20px", fontFamily: "monospace", fontSize: 13, lineHeight: 1.7, color: "#cdd6f4", overflowX: "auto" }}>
        <SyntaxSQL sql={sql} />
      </div>

      <div style={{ borderBottom: "0.5px solid #f0eeff" }}>
        <button onClick={() => setTraceOpen(o => !o)}
          style={{ width: "100%", padding: "10px 20px", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 8, color: "#888", fontSize: 12, textAlign: "left" }}>
          <span style={{ width: 18, height: 18, background: "#f0eeff", borderRadius: 4, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10 }}>
            {traceOpen ? "▲" : "▼"}
          </span>
          NLP pipeline trace
          {trace && (
            <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
              {trace.tables?.length > 0 && <TTag label={`🗄 ${trace.tables.join(", ")}`} />}
              {trace.aggregate && <TTag label={`∑ ${trace.aggregate}(${trace.aggregate_col||"*"})`} />}
              {trace.group_by && <TTag label={`⊞ GROUP`} />}
              {trace.joins?.length > 0 && <TTag label={`⟺ ${trace.joins.length} JOIN`} />}
            </div>
          )}
        </button>
        {traceOpen && trace && (
          <div style={{ padding: "12px 20px 16px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 32px", background: "#faf9ff", borderTop: "0.5px solid #f0eeff" }}>
            {[
              ["Tables",    trace.tables?.join(", ")||"—"],
              ["Aggregate", trace.aggregate ? `${trace.aggregate}(${trace.aggregate_col||"*"})` : "none"],
              ["Joins",     trace.joins?.map(j=>`${j.table} ON ${j.on}`).join(", ")||"none"],
              ["Filters",   trace.filters?.filter(f=>f.col).map(f=>`${f.col} ${f.operator} ${f.value}`).join(", ")||"none"],
              ["Group by",  trace.group_by||"none"],
              ["Order by",  trace.order_by ? `${trace.order_by} ${trace.order_dir}` : "none"],
              ["Limit",     trace.limit||"none"],
              ["Built by",  trace.used_llm ? "LLM" : "NLP engine"],
            ].map(([label, value]) => (
              <div key={label} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span style={{ fontSize: 11, color: "#bbb", minWidth: 80 }}>{label}</span>
                <span style={{ fontSize: 12, fontFamily: "monospace", color: "#555", wordBreak: "break-all" }}>{String(value)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {data.count === 0 ? (
        <div style={{ padding: "2rem", textAlign: "center", color: "#aaa" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
          <p style={{ fontSize: 14 }}>No results found.</p>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#faf9ff" }}>
                {data.columns.map(col => (
                  <th key={col} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 500, fontSize: 12, color: "#888", borderBottom: "0.5px solid #f0eeff", whiteSpace: "nowrap" }}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: "0.5px solid #f7f5ff" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#faf9ff"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  {data.columns.map(col => (
                    <td key={col} style={{ padding: "9px 16px", color: "#1a1a2e", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {formatCell(row[col])}
                    </td>
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

function TTag({ label }) {
  return <span style={{ fontSize: 11, padding: "2px 8px", background: "#f0eeff", color: PURPLE, borderRadius: 20 }}>{label}</span>;
}

function SyntaxSQL({ sql }) {
  if (!sql) return null;
  const keywords = ["SELECT","FROM","WHERE","JOIN","ON","GROUP BY","ORDER BY","LIMIT",
    "HAVING","LEFT","INNER","OUTER","AS","AND","OR","NOT","IN","BETWEEN","LIKE",
    "COUNT","SUM","AVG","MAX","MIN","DISTINCT","DESC","ASC"];
  let html = sql;
  keywords.forEach(kw => {
    html = html.replace(new RegExp(`\\b${kw}\\b`, "g"),
      `<span style="color:#cba6f7;font-weight:500">${kw}</span>`);
  });
  html = html.replace(/'([^']*)'/g, `<span style="color:#a6e3a1">'$1'</span>`);
  html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, `<span style="color:#fab387">$1</span>`);
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

function formatCell(val) {
  if (val === null || val === undefined) return <span style={{ color: "#ccc" }}>null</span>;
  const str = String(val);
  if (typeof val === "number") {
    return Number.isInteger(val) ? val.toLocaleString() : parseFloat(val.toFixed(2)).toLocaleString();
  }
  return str.length > 80 ? str.slice(0, 80) + "…" : str;
}