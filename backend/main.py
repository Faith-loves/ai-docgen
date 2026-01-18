from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
import zipfile
import io
import os
import re

from generators import generate_python_docs, generate_simple_docs

# Optional: llm_provider.py (if you still keep it)
try:
    from llm_provider import llm_available
except Exception:
    def llm_available() -> bool:
        return False


# ============================================================
# IMPORTANT: Option A behavior (Production-safe)
# - On Railway (or anywhere without model), AI is disabled safely.
# - Rule-based generation always works.
# ============================================================

def _local_ai_is_available() -> bool:
    """
    Returns True only if the local model can be imported and used.
    In production (Railway), this will typically be False.
    """
    try:
        # Import inside the function so startup never crashes
        from local_model import generate_comment as _gen  # noqa: F401
        return True
    except Exception:
        return False


def _generate_with_local_model(code: str) -> str:
    """
    Calls the local model if available, otherwise raises RuntimeError.
    """
    try:
        from local_model import generate_comment as _gen
        return _gen(code)
    except Exception as e:
        raise RuntimeError(f"Local model not available: {e}")


app = FastAPI(title="AI Code Comment & Docs API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    language: str
    code: str
    use_ai: Optional[bool] = False


EXTENSIONS_BY_LANGUAGE = {
    "python": [".py"],
    "javascript": [".js"],
    "html": [".html", ".htm"],
    "css": [".css"],
    "java": [".java"],
}

ALL_SUPPORTED_EXTS = sorted({e for v in EXTENSIONS_BY_LANGUAGE.values() for e in v})


@app.get("/")
def root():
    return {
        "status": "ok",
        # This is the truth: local AI might be available only on your laptop
        "local_model_available": _local_ai_is_available(),
        "llm_available": llm_available(),
        "supported_languages": list(EXTENSIONS_BY_LANGUAGE.keys()),
    }


def guess_language_from_filename(filename: str) -> Optional[str]:
    _, ext = os.path.splitext(filename.lower())
    for lang, exts in EXTENSIONS_BY_LANGUAGE.items():
        if ext in exts:
            return lang
    return None


def generate_rule_based(language: str, code: str, file_path: str = "") -> Dict[str, Any]:
    """
    Rule-based generator:
    - python => generate_python_docs (detailed)
    - others => generate_simple_docs
    """
    if language == "python":
        return generate_python_docs(code, file_path=file_path)
    return generate_simple_docs(language, code, file_path=file_path)


def _looks_like_bad_ai_summary(text: str) -> bool:
    """
    Reject AI summaries that look like raw code instead of English.
    """
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 12:
        return True
    if ";" in t or "{" in t or "}" in t:
        return True
    if re.match(r"^(return|var|let|const|public|private|function)\b", t, re.I):
        return True
    return False


def generate_any(language: str, code: str, file_path: str, use_ai: bool) -> Dict[str, Any]:
    """
    Option A behavior:
    - Always generate rule-based docs/comments
    - If AI is requested but not available, DO NOT FAIL.
      Return rule-based output + a friendly note.
    """
    base = generate_rule_based(language, code, file_path)

    if not use_ai:
        return base

    # AI requested
    if not _local_ai_is_available():
        base["note"] = "AI was requested, but AI is disabled on this server. Used rule-based output."
        return base

    # AI available (likely only on your laptop)
    try:
        ai_summary = _generate_with_local_model(code)

        if _looks_like_bad_ai_summary(ai_summary):
            base["note"] = "AI was requested, but the AI summary looked like raw code, so it was ignored."
            return base

        base["documentation"] = (
            "## AI One-line Summary (optional)\n"
            f"- {ai_summary.strip()}\n\n"
            + base["documentation"]
        )
        return base

    except Exception as e:
        base["note"] = f"AI failed; used rule-based output instead. Error: {str(e)}"
        return base


@app.post("/generate")
def generate(req: GenerateRequest):
    return generate_any(req.language, req.code, "pasted_code", bool(req.use_ai))


def read_zip_and_generate(
    zip_bytes: bytes,
    preferred_language: Optional[str],
    use_ai: bool,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    results: List[Dict[str, Any]] = []
    skipped: List[str] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue

            path = info.filename
            _, ext = os.path.splitext(path.lower())

            if ext not in ALL_SUPPORTED_EXTS:
                skipped.append(path)
                continue

            raw = z.read(info)
            code = raw.decode("utf-8", errors="replace")

            lang = preferred_language or guess_language_from_filename(path) or "unknown"
            out = generate_any(lang, code, path, use_ai)

            results.append(
                {
                    "file": path,
                    "language": lang,
                    "commented_code": out["commented_code"],
                    "documentation": out["documentation"],
                    "note": out.get("note"),
                }
            )

    return results, skipped


def _md_escape_backticks(s: str) -> str:
    return (s or "").replace("`", "\\`")


def _extract_first_value(doc_text: str, header: str) -> str:
    """
    Extract the first bullet under a section like:
    ## What it does
    - something...
    """
    lines = doc_text.splitlines()
    found = False
    for line in lines:
        if line.strip().lower() == header.strip().lower():
            found = True
            continue
        if found:
            if line.strip().startswith("## "):
                break
            if line.strip().startswith("- "):
                return line.strip()[2:].strip()
    return ""


def build_project_readme(results: List[Dict[str, Any]], skipped: List[str]) -> str:
    """
    Project README Format:
    1) Title
    2) What it does
    3) Requirements
    4) How to run
    5) Explanation of logic
    6) Example input/output
    7) Edge cases / notes

    (No "code section" per your instruction.)
    """
    lines: List[str] = []

    # 1) Title
    lines.append("# Project README (Beginner-friendly)")
    lines.append("")
    lines.append("This documentation was generated automatically from the project source code.")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- Files documented: **{len(results)}**")
    lines.append(f"- Files skipped (unsupported): **{len(skipped)}**")
    lines.append("")

    # 2) What it does
    project_description = "This project contains code files that work together."
    if results:
        first_doc = results[0]["documentation"]
        guess = _extract_first_value(first_doc, "## 2) What it does")
        if guess:
            project_description = guess

    lines.append("## 2) What it does")
    lines.append(f"- {project_description}")
    lines.append("")

    # 3) Requirements
    reqs: List[str] = []
    langs = sorted({r["language"] for r in results})

    if "python" in langs:
        reqs.append("Python 3 installed")
    if "java" in langs:
        reqs.append("Java JDK installed")
    if any(l in langs for l in ["html", "css", "javascript"]):
        reqs.append("A web browser (Chrome/Edge/Firefox)")
        reqs.append("Optional: Live Server extension in VS Code")

    if not reqs:
        reqs.append("No special requirements detected")

    lines.append("## 3) Requirements")
    for r in reqs:
        lines.append(f"- {r}")
    lines.append("")

    # 4) How to run
    lines.append("## 4) How to run")
    if "python" in langs:
        py_file = next((os.path.basename(r["file"]) for r in results if r["language"] == "python"), "main.py")
        lines.append("### Run as Python")
        lines.append("1. Open a terminal inside the project folder.")
        lines.append(f"2. Run: `python {py_file}`")
        lines.append("3. Follow any prompts shown on the terminal.")
        lines.append("")
    if any(l in langs for l in ["html", "css", "javascript"]):
        html_file = next((r["file"] for r in results if r["language"] == "html"), None)
        lines.append("### Run as Website")
        if html_file:
            lines.append(f"1. Open `{html_file}` in a browser.")
        else:
            lines.append("1. Open the main `.html` file in a browser.")
        lines.append("2. CSS and JavaScript will load automatically if linked.")
        lines.append("")
    if "java" in langs:
        java_file = next((os.path.basename(r["file"]) for r in results if r["language"] == "java"), "Main.java")
        lines.append("### Run as Java")
        lines.append(f"1. Compile: `javac {java_file}`")
        lines.append(f"2. Run: `java {java_file.replace('.java','')}`")
        lines.append("")

    # Files included
    lines.append("## Files included")
    for r in results:
        lines.append(f"- `{_md_escape_backticks(r['file'])}` ({r['language']})")
    lines.append("")

    if skipped:
        lines.append("## Skipped files")
        lines.append("- These files were skipped because they are not supported.")
        for s in skipped:
            lines.append(f"  - `{_md_escape_backticks(s)}`")
        lines.append("")

    # Per-file docs
    lines.append("---")
    lines.append("")
    lines.append("# Detailed Documentation Per File")
    lines.append("")

    for r in results:
        lines.append("---")
        lines.append("")
        lines.append(f"## {os.path.basename(r['file'])}")
        lines.append(f"- File path: `{_md_escape_backticks(r['file'])}`")
        lines.append(f"- Language: **{r['language']}**")
        if r.get("note"):
            lines.append(f"- Note: {r['note']}")
        lines.append("")
        lines.append(r["documentation"].strip())
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 7) Edge cases / notes")
    lines.append("- This README is generated based only on the code that was included in the uploaded ZIP.")
    lines.append("- If some required images/data/config files are missing, the project may not run fully.")
    lines.append("")

    return "\n".join(lines)


@app.post("/generate-zip-download")
async def generate_zip_download(
    zip_file: UploadFile = File(...),
    preferred_language: Optional[str] = Form(default=None),
    use_ai: Optional[bool] = Form(default=False),
):
    data = await zip_file.read()
    results, skipped = read_zip_and_generate(data, preferred_language, bool(use_ai))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for r in results:
            out.writestr(r["file"], r["commented_code"])

        readme = build_project_readme(results, skipped)
        out.writestr("PROJECT_README.md", readme)

        if skipped:
            out.writestr("SKIPPED_FILES.txt", "\n".join(skipped))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=docgen_project.zip"},
    )