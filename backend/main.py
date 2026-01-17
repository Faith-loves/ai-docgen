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
from local_model import generate_comment as generate_with_local_model

# OPTIONAL: only if you still keep llm_provider.py
try:
    from llm_provider import llm_available
except Exception:
    def llm_available() -> bool:
        return False


app = FastAPI(title="AI Code Comment & Docs API", version="1.2")

# DEV CORS: allow any frontend port (5173, 5174, etc.)
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
        "local_model": True,
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
    Reject "AI summaries" that look like raw code instead of English.
    Example: "return text;" or "{...}"
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
    ALWAYS generate good beginner docs using rule-based logic,
    then optionally add ONE short AI summary if it looks good.
    """
    base = generate_rule_based(language, code, file_path)

    # Optional AI one-line summary using local model
    if use_ai:
        try:
            ai_summary = generate_with_local_model(code)

            if _looks_like_bad_ai_summary(ai_summary):
                base["note"] = "AI was requested, but the AI summary looked like raw code, so it was ignored."
                return base

            # add small AI summary at top of docs (optional)
            base["documentation"] = (
                "## AI One-line Summary (optional)\n"
                f"- {ai_summary.strip()}\n\n"
                + base["documentation"]
            )
            return base

        except Exception as e:
            base["note"] = f"AI failed, used rule-based docs. Error: {str(e)}"
            return base

    return base


@app.post("/generate")
def generate(req: GenerateRequest):
    return generate_any(req.language, req.code, "pasted_code", bool(req.use_ai))


def read_zip_and_generate(
    zip_bytes: bytes,
    preferred_language: Optional[str],
    use_ai: bool,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    results = []
    skipped = []

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

            results.append({
                "file": path,
                "language": lang,
                "commented_code": out["commented_code"],
                "documentation": out["documentation"],
                "note": out.get("note"),
            })

    return results, skipped


def _md_escape_backticks(s: str) -> str:
    return (s or "").replace("`", "\\`")


def build_project_readme(results: List[Dict[str, Any]], skipped: List[str]) -> str:
    """
    ✅ Improved project README:
    - Project purpose (best guess)
    - Run steps
    - FULL documentation embedded per file
    """

    lines: List[str] = []

    lines.append("# Project Documentation (Beginner-friendly)")
    lines.append("")
    lines.append("This ZIP contains an easy-to-read version of your project.")
    lines.append("Each supported file has:")
    lines.append("- clear beginner-friendly comments (not spam)")
    lines.append("- detailed documentation in simple English")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Files documented: **{len(results)}**")
    lines.append(f"- Files skipped: **{len(skipped)}**")
    lines.append("")

    # Try to guess project purpose from first file's docs
    project_purpose = "This project contains code files that work together."
    if results:
        first_doc = results[0]["documentation"]
        for line in first_doc.splitlines():
            if line.strip().startswith("-") and "Purpose" not in line:
                project_purpose = line.strip("- ").strip()
                break

    lines.append("## Project Purpose (What this project does)")
    lines.append(f"- {project_purpose}")
    lines.append("")

    lines.append("## Files included")
    for r in results:
        lines.append(f"- `{_md_escape_backticks(r['file'])}` ({r['language']})")
    lines.append("")

    if skipped:
        lines.append("## Skipped files")
        lines.append("These files were skipped because they are not in supported types:")
        for s in skipped:
            lines.append(f"- `{_md_escape_backticks(s)}`")
        lines.append("")

    # Show how to run based on file types
    lines.append("## How to run this project (Step-by-step)")
    has_python = any(r["language"] == "python" for r in results)
    has_web = any(r["language"] in ("html", "css", "javascript") for r in results)

    if has_python:
        py_file = None
        for r in results:
            if r["language"] == "python":
                py_file = os.path.basename(r["file"])
                break
        py_file = py_file or "main.py"

        lines.append("### Option A: Run with Python (recommended)")
        lines.append("1. Make sure Python is installed (Python 3).")
        lines.append("2. Open a terminal in the folder containing the file.")
        lines.append(f"3. Run: `python {py_file}`")
        lines.append("4. Follow the instructions shown on the screen.")
        lines.append("")

    if has_web:
        lines.append("### Option B: Run as a website")
        lines.append("1. Find the main `.html` file.")
        lines.append("2. Double-click it to open in your browser.")
        lines.append("3. CSS will style it, and JavaScript will add interactivity.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("# Full Documentation Per File")
    lines.append("")
    lines.append("Below is the full detailed documentation for every file.")
    lines.append("")

    for r in results:
        lines.append("---")
        lines.append("")
        lines.append(f"# File: `{_md_escape_backticks(r['file'])}`")
        lines.append("")
        lines.append(f"- Language: **{r['language']}**")
        if r.get("note"):
            lines.append(f"- Note: {r['note']}")
        lines.append("")
        lines.append(r["documentation"].strip())
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Note for Beginners")
    lines.append("- Start with the file that has the main entry point (often main.py or index.html).")
    lines.append("- If it is a web project: open the HTML first, then CSS, then JavaScript.")
    lines.append("- If it is Python: run the file with `python filename.py`.")
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
        # Write commented files
        for r in results:
            out.writestr(r["file"], r["commented_code"])

        # Write README
        readme = build_project_readme(results, skipped)
        out.writestr("PROJECT_README.md", readme)

        # Optional skipped list
        if skipped:
            out.writestr("SKIPPED_FILES.txt", "\n".join(skipped))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=docgen_project.zip"},
    )