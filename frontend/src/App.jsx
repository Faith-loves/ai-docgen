import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API_BASE = "https://ai-docgen-backend-production-caa2.up.railway.app";

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

function Toasts({ toasts, removeToast }) {
  return (
    <div className="toasts" aria-live="polite" aria-relevant="additions">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <div className="toast-title">{t.title}</div>
          {t.message ? <div className="toast-msg">{t.message}</div> : null}
          <button
            className="toast-x"
            onClick={() => removeToast(t.id)}
            aria-label="Close"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  // ✅ THEME (only change)
  const THEMES = useMemo(
    () => [
      { id: "gold", name: "Gold" },
      { id: "emerald", name: "Emerald" },
      { id: "royal", name: "Royal" },
      { id: "rose", name: "Rose" },
    ],
    [],
  );

  const [theme, setTheme] = useState(
    () => localStorage.getItem("docgen_theme") || "gold",
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("docgen_theme", theme);
  }, [theme]);

  const [language, setLanguage] = useState("javascript");
  const [code, setCode] = useState(`function capitalize(text) {
  if (!text) return "";
  return text[0].toUpperCase() + text.slice(1);
}`);
  const [useAi, setUseAi] = useState(true);

  const [commentedCode, setCommentedCode] = useState("");
  const [documentation, setDocumentation] = useState("");

  const [loading, setLoading] = useState(false);

  // ZIP
  const [zipFile, setZipFile] = useState(null);
  const [preferredLanguage, setPreferredLanguage] = useState("");

  // Toasts
  const [toasts, setToasts] = useState([]);
  const toastTimers = useRef(new Map());

  function pushToast(type, title, message = "", ttl = 3500) {
    const id = uid();
    setToasts((prev) => [{ id, type, title, message }, ...prev].slice(0, 4));

    const timer = setTimeout(() => removeToast(id), ttl);
    toastTimers.current.set(id, timer);
  }

  function removeToast(id) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = toastTimers.current.get(id);
    if (timer) clearTimeout(timer);
    toastTimers.current.delete(id);
  }

  useEffect(() => {
    return () => {
      for (const t of toastTimers.current.values()) clearTimeout(t);
      toastTimers.current.clear();
    };
  }, []);

  const canShowOutput = useMemo(
    () => commentedCode.trim() || documentation.trim(),
    [commentedCode, documentation],
  );

  async function safeCopy(text, label) {
    try {
      if (!text?.trim()) return;
      await navigator.clipboard.writeText(text);
      pushToast("success", "Copied", `${label} copied to clipboard.`);
    } catch {
      pushToast(
        "error",
        "Copy failed",
        "Your browser blocked clipboard access.",
      );
    }
  }

  async function handleGenerate() {
    setLoading(true);
    setCommentedCode("");
    setDocumentation("");

    try {
      const res = await fetch(`${API_BASE}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          language,
          code,
          use_ai: useAi,
        }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setCommentedCode(data.commented_code || "");
      setDocumentation(data.documentation || "");
      pushToast(
        "success",
        "Generated",
        "Your commented code + docs are ready.",
      );
    } catch (e) {
      pushToast("error", "Generate failed", String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function handleZipGenerate() {
    if (!zipFile) {
      pushToast("info", "Upload needed", "Please choose a .zip file first.");
      return;
    }

    setLoading(true);
    try {
      const form = new FormData();
      form.append("zip_file", zipFile);
      form.append("use_ai", useAi ? "true" : "false");
      if (preferredLanguage)
        form.append("preferred_language", preferredLanguage);

      const res = await fetch(`${API_BASE}/generate-zip-download`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = "docgen_project.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      pushToast(
        "success",
        "ZIP Ready",
        "Your documented ZIP download started.",
      );
    } catch (e) {
      pushToast("error", "ZIP failed", String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  // ✅ Theme label for pill
  const themeLabel = THEMES.find((t) => t.id === theme)?.name || "Gold";

  return (
    <div className="page">
      <Toasts toasts={toasts} removeToast={removeToast} />

      {/* Top bar */}
      <header className="topbar">
        <div className="brand">
          <div className="logoMark" aria-hidden="true" />
          <div>
            <h1>AI DocGen</h1>
            <p className="subtitle">
              Commented code + documentation in seconds.
            </p>
          </div>
        </div>

        {/* ✅ THEME PICKER (only new UI) */}
        <div className="themePill" title="Theme">
          <span className="dot" />
          <select
            className="themeSelect"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            aria-label="Choose theme"
          >
            {THEMES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <span className="themeLabel">{themeLabel}</span>
        </div>
      </header>

      {/* Hero */}
      <section className="hero">
        <div className="heroCard">
          <div className="heroGlow" aria-hidden="true" />
          <div className="heroText">
            <div className="heroBadge">Premium • Theme Edition</div>
            <h2 className="heroTitle">
              AI Code Comment & Documentation Generator
            </h2>
            <p className="heroDesc">
              Paste code or upload a ZIP. Get clean comments, beginner-friendly
              docs, and a ready-to-download documented project.
            </p>

            <div className="heroActions">
              <button
                className="btnPrimary"
                onClick={handleGenerate}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="spinner" aria-hidden="true" /> Generating…
                  </>
                ) : (
                  "Generate (Paste Code)"
                )}
              </button>

              <a
                className="btnGhost linkBtn"
                href={`${API_BASE}`}
                target="_blank"
                rel="noreferrer"
              >
                Open Backend
              </a>
            </div>

            <div className="heroMeta">
              <span className="metaChip">Responsive UI</span>
              <span className="metaChip">ZIP → Documented ZIP</span>
              <span className="metaChip">Copy buttons + toasts</span>
            </div>
          </div>
        </div>
      </section>

      <main className="container">
        {/* Controls */}
        <section className="card">
          <div className="cardHeader">
            <h3>Paste Code</h3>
            <p>Choose language, optionally enable AI, then generate.</p>
          </div>

          <div className="controls">
            <label className="field">
              <span>Language</span>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="java">Java</option>
                <option value="html">HTML</option>
                <option value="css">CSS</option>
              </select>
            </label>

            <label className="check">
              <input
                type="checkbox"
                checked={useAi}
                onChange={(e) => setUseAi(e.target.checked)}
              />
              <span>Use AI (local)</span>
            </label>

            <button
              className="btnPrimary"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Generating…
                </>
              ) : (
                "Generate"
              )}
            </button>
          </div>

          <div className="editorWrap">
            <textarea
              className="editor"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              spellCheck={false}
              placeholder="Paste your code here…"
            />
          </div>
        </section>

        {/* Output */}
        <section className="card">
          <div className="cardHeader rowBetween">
            <div>
              <h3>Output</h3>
              <p>Results show here after generation.</p>
            </div>

            <div className="miniActions">
              <button
                className="btnGhost"
                onClick={() => safeCopy(commentedCode, "Commented Code")}
                disabled={!commentedCode.trim()}
              >
                Copy Comments
              </button>
              <button
                className="btnGhost"
                onClick={() => safeCopy(documentation, "Documentation")}
                disabled={!documentation.trim()}
              >
                Copy Docs
              </button>
            </div>
          </div>

          {!canShowOutput ? (
            <div className="empty">
              <div className="emptyTitle">Nothing yet</div>
              <div className="emptyText">
                Click <b>Generate</b> to see commented code and documentation.
              </div>
            </div>
          ) : (
            <div className="outputGrid">
              <div className="panel">
                <div className="panelHead">
                  <span>Commented Code</span>
                  <button
                    className="iconBtn"
                    onClick={() => safeCopy(commentedCode, "Commented Code")}
                    disabled={!commentedCode.trim()}
                    title="Copy"
                  >
                    Copy
                  </button>
                </div>
                <pre className="codeBlock">{commentedCode}</pre>
              </div>

              <div className="panel">
                <div className="panelHead">
                  <span>Documentation</span>
                  <button
                    className="iconBtn"
                    onClick={() => safeCopy(documentation, "Documentation")}
                    disabled={!documentation.trim()}
                    title="Copy"
                  >
                    Copy
                  </button>
                </div>
                <pre className="codeBlock">{documentation}</pre>
              </div>
            </div>
          )}
        </section>

        {/* ZIP */}
        <section className="card">
          <div className="cardHeader">
            <h3>Upload ZIP → Download Documented ZIP</h3>
            <p>Upload a project ZIP to generate a documented version.</p>
          </div>

          <div className="zipRow">
            <label className="filePick">
              <input
                type="file"
                accept=".zip"
                onChange={(e) => setZipFile(e.target.files?.[0] || null)}
              />
              <span>{zipFile?.name ? zipFile.name : "Choose a .zip file"}</span>
            </label>

            <label className="field">
              <span>Preferred language (optional)</span>
              <select
                value={preferredLanguage}
                onChange={(e) => setPreferredLanguage(e.target.value)}
              >
                <option value="">Auto-detect</option>
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="java">Java</option>
                <option value="html">HTML</option>
                <option value="css">CSS</option>
              </select>
            </label>

            <button
              className="btnPrimary"
              onClick={handleZipGenerate}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Working…
                </>
              ) : (
                "Generate ZIP (Download)"
              )}
            </button>
          </div>

          <div className="hint">
            Tip: If a ZIP is huge, try smaller first. Keep file types supported
            (py/js/html/css/java).
          </div>
        </section>

        <footer className="footer">
          <span>Backend:</span>
          <a href={API_BASE} target="_blank" rel="noreferrer">
            {API_BASE}
          </a>
        </footer>
      </main>

      {/* Loading overlay */}
      {loading ? (
        <div className="overlay" role="status" aria-label="Loading">
          <div className="overlayCard">
            <div className="overlaySpinner" aria-hidden="true" />
            <div className="overlayText">Processing…</div>
            <div className="overlaySub">Please keep this tab open.</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
