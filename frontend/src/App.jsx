import { useState } from "react";

const API_BASE = "http://127.0.0.1:8000";

export default function App() {
  const [language, setLanguage] = useState("javascript");
  const [code, setCode] = useState(`function capitalize(text) {
  if (!text) return "";
  return text[0].toUpperCase() + text.slice(1);
}`);
  const [useAi, setUseAi] = useState(true);

  const [commentedCode, setCommentedCode] = useState("");
  const [documentation, setDocumentation] = useState("");
  const [error, setError] = useState("");

  // ZIP upload
  const [zipFile, setZipFile] = useState(null);
  const [preferredLanguage, setPreferredLanguage] = useState(""); // optional

  async function handleGenerate() {
    setError("");
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
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleZipGenerate() {
    setError("");

    if (!zipFile) {
      setError("Please choose a .zip file first.");
      return;
    }

    try {
      const form = new FormData();
      form.append("zip_file", zipFile);
      form.append("use_ai", useAi ? "true" : "false");
      if (preferredLanguage.trim()) {
        form.append("preferred_language", preferredLanguage.trim());
      }

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
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ fontFamily: "Arial, sans-serif", padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <h1>AI Code Comment & Documentation Generator</h1>

      {error ? (
        <div style={{ background: "#ffe0e0", padding: 12, borderRadius: 8, marginBottom: 12 }}>
          <b>Error:</b> {error}
        </div>
      ) : null}

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Language:{" "}
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="java">Java</option>
            <option value="html">HTML</option>
            <option value="css">CSS</option>
          </select>
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
          Use AI (local CodeT5)
        </label>

        <button onClick={handleGenerate} style={{ padding: "8px 12px", cursor: "pointer" }}>
          Generate (Paste Code)
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          rows={10}
          style={{ width: "100%", padding: 10, fontFamily: "Consolas, monospace", fontSize: 14 }}
        />
      </div>

      <h2 style={{ marginTop: 20 }}>Output</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <h3>Commented Code</h3>
          <pre style={{ background: "#111", color: "#eee", padding: 12, borderRadius: 8, overflowX: "auto" }}>
            {commentedCode}
          </pre>
        </div>

        <div>
          <h3>Documentation</h3>
          <pre style={{ background: "#111", color: "#eee", padding: 12, borderRadius: 8, overflowX: "auto" }}>
            {documentation}
          </pre>
        </div>
      </div>

      <hr style={{ margin: "28px 0" }} />

      <h2>Upload a Folder (ZIP) and Download Documented Project</h2>
      <p>
        Put your project folder into a <b>.zip</b> file, upload it here, then download the documented version.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="file"
          accept=".zip"
          onChange={(e) => setZipFile(e.target.files?.[0] || null)}
        />

        <label>
          Preferred language (optional):{" "}
          <select value={preferredLanguage} onChange={(e) => setPreferredLanguage(e.target.value)}>
            <option value="">Auto-detect</option>
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="java">Java</option>
            <option value="html">HTML</option>
            <option value="css">CSS</option>
          </select>
        </label>

        <button onClick={handleZipGenerate} style={{ padding: "8px 12px", cursor: "pointer" }}>
          Generate ZIP (Download)
        </button>
      </div>

      <p style={{ marginTop: 10, fontSize: 13, opacity: 0.85 }}>
        Tip: If your folder has many files, this may take a bit longer on CPU.
      </p>
    </div>
  );
}

