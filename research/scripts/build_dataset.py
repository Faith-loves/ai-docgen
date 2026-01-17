"""
build_dataset.py

Beginner-friendly dataset builder for AI-based code comment generation.

This script prepares training data for models like CodeT5 / CodeBERT by:
- loading local code samples (Nigeria-local)
- extracting real docstrings / JSDoc / Javadoc comments
- outputting normalized JSONL train/valid/test splits

Output format per line (JSONL):
{"language":"python","code":"...","comment":"..."}
"""

import ast
import json
import random
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Root paths
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Output files
TRAIN_FILE = PROCESSED_DIR / "train.jsonl"
VALID_FILE = PROCESSED_DIR / "valid.jsonl"
TEST_FILE = PROCESSED_DIR / "test.jsonl"


def ensure_dirs():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------
# Comment extractors
# -----------------------

def extract_python_docstrings(code: str) -> str:
    """
    Extracts module docstring + function docstrings.
    Returns a combined text string.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""

    parts: List[str] = []

    module_doc = ast.get_docstring(tree)
    if module_doc:
        parts.append(module_doc.strip())

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                parts.append(doc.strip())

    return "\n\n".join(parts).strip()


def extract_jsdoc(code: str) -> str:
    """
    Extracts JSDoc blocks like:
    /**
     * ...
     */
    """
    blocks = re.findall(r"/\*\*([\s\S]*?)\*/", code)
    cleaned = []
    for b in blocks:
        # remove leading stars
        lines = []
        for line in b.splitlines():
            line = re.sub(r"^\s*\*\s?", "", line).rstrip()
            if line:
                lines.append(line)
        text = "\n".join(lines).strip()
        if text:
            cleaned.append(text)
    return "\n\n".join(cleaned).strip()


def extract_javadoc(code: str) -> str:
    """
    Same style as JSDoc: /** ... */
    """
    return extract_jsdoc(code)


def guess_language_from_suffix(suffix: str) -> Optional[str]:
    s = suffix.lower()
    if s == ".py":
        return "python"
    if s == ".js":
        return "javascript"
    if s == ".java":
        return "java"
    if s == ".html" or s == ".htm":
        return "html"
    if s == ".css":
        return "css"
    return None


# -----------------------
# Dataset loading
# -----------------------

def load_local_nigeria_code() -> List[Dict[str, Any]]:
    """
    Load locally sourced Nigerian developer code samples from:
    research/data/raw/nigeria_local

    For training data, we need:
    - code: the code text
    - comment: docstrings/JSDoc/Javadoc extracted from the file
    """
    samples: List[Dict[str, Any]] = []
    base = RAW_DIR / "nigeria_local"

    for path in base.rglob("*"):
        if not path.is_file():
            continue

        lang = guess_language_from_suffix(path.suffix)
        if not lang:
            continue

        try:
            code = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if lang == "python":
            comment = extract_python_docstrings(code)
        elif lang == "javascript":
            comment = extract_jsdoc(code)
        elif lang == "java":
            comment = extract_javadoc(code)
        else:
            comment = ""

        # Only include if we have at least SOME comment text
        if not comment.strip():
            continue

        samples.append({
            "source": "nigeria_local",
            "language": lang,
            "file": str(path.relative_to(base)),
            "code": code,
            "comment": comment
        })

    return samples


def load_codesearchnet_stub() -> List[Dict[str, Any]]:
    """
    Placeholder for CodeSearchNet loading logic.
    We will implement it later after you confirm the local pipeline works.
    """
    return []


# -----------------------
# Split + Save
# -----------------------

def split_dataset(data: List[Dict[str, Any]], train_ratio=0.8, valid_ratio=0.1) -> Tuple[list, list, list]:
    random.shuffle(data)
    n = len(data)
    train_end = int(n * train_ratio)
    valid_end = train_end + int(n * valid_ratio)
    return data[:train_end], data[train_end:valid_end], data[valid_end:]


def write_jsonl(path: Path, data: List[Dict[str, Any]]):
    with path.open("w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    print("Building dataset...")
    ensure_dirs()

    data: List[Dict[str, Any]] = []
    data.extend(load_local_nigeria_code())
    data.extend(load_codesearchnet_stub())

    if not data:
        print("WARNING: No data found yet. Dataset will be empty.")

    train, valid, test = split_dataset(data)

    write_jsonl(TRAIN_FILE, train)
    write_jsonl(VALID_FILE, valid)
    write_jsonl(TEST_FILE, test)

    print("Dataset build complete.")
    print(f"Train: {len(train)} samples")
    print(f"Valid: {len(valid)} samples")
    print(f"Test : {len(test)} samples")


if __name__ == "__main__":
    main()
