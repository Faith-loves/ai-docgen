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

# Optional: llm_provider.py
try:
    from llm_provider import llm_available
except Exception:
    def llm_available() -> bool:
        return False


# ============================================================
# Local AI model safety:
# - NEVER import torch/model at startup
# - Only try when user requests AI
# - If it fails, still return rule-based output
# ============================================================

def _local_ai_is_available() -> bool:
    try:
        from local_model import generate_comment as _gen  # noqa: F401
        return True
    except Exception:
        return False


def _generate_with_local_model(code: str) -> str:
    from local_model import generate_comment as _gen
    return _gen(code)


app = FastAPI(title="AI Code Comment & Docs API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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


def generate_rule_based(language: str, code: str, file_path: str) -> Dict[str, Any]:
    if language == "python":
        return generate_python_docs(code, file_path=file_path)
    return generate_simple_docs(language, code, file_path=file_path)


def _looks_like_bad_ai_summary(text: str) -> bool:
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
    base = generate_rule_based(language, code, file_path)

    if not use_ai:
        return base

    # AI requested:
    if not _local_ai_is_available():
        base["note"] = "AI was requested, but AI is disabled on this server. Used rule-based output."
        return base

    try:
        ai_summary = _generate_with_local_model(code)
        if _looks_like_bad_ai_summary(ai_summary):
            base["note"] = "AI summary looked like code, ignored it."
            return base

        base["documentation"] = (
            "## Optional AI summary\n"
            f"- {ai_summary.strip()}\n\n"
            + base["documentation"]
        )
        return base
    except Exception as e:
        base["note"] = f"AI failed; used rule-based output. Error: {str(e)}"
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


def build_project_readme(results: List[Dict[str, Any]], skipped: List[str]) -> str:
    lines: List[str] = []

    lines.append("# Project README")
    lines.append("")
    lines.append("This README was generated automatically.")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Files documented: **{len(results)}**")
    lines.append(f"- Files skipped (unsupported): **{len(skipped)}**")
    lines.append("")
    lines.append("## Files included")
    for r in results:
        lines.append(f"- `{_md_escape_backticks(r['file'])}` ({r['language']})")
    lines.append("")
    if skipped:
        lines.append("## Skipped files")
        for s in skipped:
            lines.append(f"- `{_md_escape_backticks(s)}`")
        lines.append("")
    lines.append("## Notes")
    lines.append("- Comments are designed to explain confusing parts without spamming every line.")
    lines.append("- If you turn on AI, it may be disabled in production servers.")
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
