from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Goals for this file
# - Generate comments that look professional and not “spammy”
# - Avoid lying about what code does (no fake explanations)
# - Make output readable for beginners (clear, minimal, accurate)
# - Ensure ZIP uploads use the same improved logic
# ============================================================


# -----------------------------
# Header cleanup
# -----------------------------
AUTO_MARKERS = [
    "Beginner-friendly comments (auto-added)",
    "Beginner-friendly notes (auto-added)",
    "Beginner-friendly CSS notes (auto-added)",
    "Beginner-friendly JS notes (auto-added)",
    "Beginner-friendly Java notes (auto-added)",
    "Professional beginner-friendly comments",
    "Professional beginner-friendly notes",
]


def _count_nonempty_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def _clean_existing_auto_headers(code: str) -> str:
    """
    Remove previously generated headers so we do not stack them forever.

    Safe approach:
    - Only removes known auto header blocks near the top of the file.
    - Does not delete real code farther down.
    """
    raw = code.replace("\r\n", "\n")
    lines = raw.splitlines()

    # Only inspect the first N lines for auto headers
    N = min(60, len(lines))
    head = lines[:N]
    tail = lines[N:]

    # If none of the markers exist in the head, do nothing.
    head_text = "\n".join(head)
    if not any(m in head_text for m in AUTO_MARKERS):
        return raw

    out: List[str] = []
    skipping = False
    skipped_any = False

    for i, line in enumerate(lines):
        # only allow skipping inside first 60 lines
        in_safe_zone = i < 60

        if in_safe_zone and any(m in line for m in AUTO_MARKERS):
            skipping = True
            skipped_any = True
            continue

        if skipping and in_safe_zone:
            # stop skipping after we pass a blank line AND we've already skipped something
            if line.strip() == "":
                skipping = False
            continue

        out.append(line)

    cleaned = "\n".join(out).strip("\n")
    # Keep trailing newline if original had it
    return cleaned + ("\n" if raw.endswith("\n") else "")


# -----------------------------
# Name heuristics (for more accurate comments)
# -----------------------------
def _humanize_name(name: str) -> str:
    """
    Convert snake_case / camelCase names into readable phrases.
    """
    if not name:
        return "this item"

    # camelCase -> words
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    # snake_case -> words
    s2 = s1.replace("_", " ")
    return s2.strip().lower()


def _guess_purpose_from_name(name: str) -> str:
    """
    Conservative: we do NOT claim exact behavior.
    We only provide safe hints based on common naming conventions.
    """
    n = name.lower()

    if n.startswith(("get_", "fetch_", "read_", "load_")):
        return "retrieves data"
    if n.startswith(("set_", "update_", "write_", "save_")):
        return "updates or stores data"
    if n.startswith(("is_", "has_", "can_", "should_")):
        return "returns a true/false result"
    if "parse" in n:
        return "parses text into a structured form"
    if "validate" in n or "check" in n:
        return "checks whether something is valid"
    if "format" in n:
        return "formats text for display"
    if "build" in n or "create" in n or "make" in n:
        return "builds/creates something"
    if "convert" in n or "to_" in n:
        return "converts something into another form"
    if "calc" in n or "compute" in n:
        return "computes a result"
    if "capitalize" in n:
        return "changes text casing"
    return "performs a specific task"


# -----------------------------
# Python (professional + accurate)
# -----------------------------
def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _summarize_python_code(code: str) -> Dict[str, Any]:
    tree, err = _safe_parse_python(code)

    summary: Dict[str, Any] = {
        "parse_ok": tree is not None,
        "parse_error": err,
        "imports": [],
        "functions": [],
        "classes": [],
        "loops": 0,
        "has_input": "input(" in code.lower(),
    }

    if not tree:
        # fallback summary if syntax is broken
        summary["loops"] = len(re.findall(r"\b(for|while)\b", code))
        summary["functions"] = re.findall(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(", code, flags=re.M)
        summary["classes"] = re.findall(r"^\s*class\s+([a-zA-Z_]\w*)\s*[:\(]", code, flags=re.M)
        summary["imports"] = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", code, flags=re.M)
        return summary

    imports: List[str] = []
    functions: List[str] = []
    classes: List[str] = []
    loops = 0

    class V(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> Any:
            for n in node.names:
                imports.append(n.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            if node.module:
                imports.append(node.module)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            functions.append(node.name)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            functions.append(node.name)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            classes.append(node.name)
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> Any:
            nonlocal loops
            loops += 1
            self.generic_visit(node)

        def visit_While(self, node: ast.While) -> Any:
            nonlocal loops
            loops += 1
            self.generic_visit(node)

    V().visit(tree)
    summary["imports"] = sorted(set(imports))
    summary["functions"] = functions
    summary["classes"] = classes
    summary["loops"] = loops
    return summary


def _python_has_docstring_after_def(lines: List[str], def_index: int) -> bool:
    """
    Check if a function has a real docstring immediately after its def line.
    """
    j = def_index + 1
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    if j >= len(lines):
        return False
    s = lines[j].lstrip()
    return s.startswith('"""') or s.startswith("'''") or s.startswith('r"""') or s.startswith("r'''")


def _add_python_comments(code: str) -> str:
    """
    Python commenting strategy (professional + accurate):
    - Add a small header
    - Comment imports once
    - Add one clean comment above each function/class based on name (conservative)
    - Add a short loop comment above for/while
    - Add a try/except comment above try
    - DO NOT inject fake docstrings or claim exact behavior
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    # Header
    out.append("# =======================================")
    out.append("# Professional comments (auto-added)")
    out.append("# =======================================")
    out.append("# Notes:")
    out.append("# - Comments explain structure and intent without guessing hidden behavior.")
    out.append("")

    imports_commented = False

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        # imports block
        if s.startswith("import ") or s.startswith("from "):
            if not imports_commented:
                out.append("# Imports: external libraries and modules used by this file.")
                imports_commented = True
            out.append(line)
            i += 1
            continue

        # class
        m_cls = re.match(r"^(\s*)class\s+([A-Za-z_]\w*)\b", line)
        if m_cls:
            indent = m_cls.group(1)
            cls_name = m_cls.group(2)
            out.append(f"{indent}# Class: {cls_name} — groups related functions/data together.")
            out.append(line)
            i += 1
            continue

        # function
        m_fn = re.match(r"^(\s*)def\s+([A-Za-z_]\w*)\s*\(", line)
        if m_fn:
            indent = m_fn.group(1)
            fn_name = m_fn.group(2)

            # Add a one-line comment above the def (professional, no guessing)
            purpose = _guess_purpose_from_name(fn_name)
            out.append(f"{indent}# Function: {fn_name} — {purpose}.")
            out.append(line)

            # If a docstring already exists, we do NOT add anything.
            i += 1
            continue

        # loop
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below until the condition ends.")
            out.append(line)
            i += 1
            continue

        # try/except
        if re.match(r"^\s*try\s*:", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Error handling: try this block and catch errors instead of crashing.")
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    parse_note = ""
    if not info.get("parse_ok", True):
        parse_note = (
            "## Important Note\n"
            "This Python file has a syntax/indentation issue, so deep analysis is limited.\n"
            "Fix indentation (usually 4 spaces) and try again.\n\n"
        )

    documentation = (
        f"# File Documentation - `{os.path.basename(file_path)}`\n\n"
        f"{parse_note}"
        f"## Overview\n"
        f"- Non-empty lines: **{loc}**\n"
        f"- Imports: **{len(info.get('imports', []))}**\n"
        f"- Functions: **{len(info.get('functions', []))}**\n"
        f"- Classes: **{len(info.get('classes', []))}**\n"
        f"- Loops: **{info.get('loops', 0)}**\n\n"
        f"## Inputs / Outputs\n"
        f"- Inputs: {'Uses terminal input (`input(...)`).' if info.get('has_input') else 'Parameters / function calls / events.'}\n"
        f"- Outputs: printed text, returned values, or side effects (e.g., file/network).\n\n"
        f"## How to run (basic)\n"
        f"1. Open a terminal in the file folder.\n"
        f"2. Run: `python {os.path.basename(file_path)}`\n"
    )

    commented_code = _add_python_comments(code_clean)
    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# HTML (professional + less spam)
# -----------------------------
def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional comments (auto-added)      -->")
    out.append("<!-- ======================================= -->")
    out.append("<!-- HTML defines the structure of the page (head + body). -->")
    out.append("")

    seen: set = set()

    def add_once(key: str, text: str) -> None:
        if key not in seen:
            out.append(text)
            seen.add(key)

    for line in lines:
        s = line.strip().lower()

        if s.startswith("<!doctype"):
            add_once("doctype", "<!-- DOCTYPE: tells the browser this is HTML5 -->")
        elif s.startswith("<html"):
            add_once("html", "<!-- <html>: root element wrapping the whole page -->")
        elif s.startswith("<head"):
            add_once("head", "<!-- <head>: metadata, title, CSS links, and page settings -->")
        elif s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")
        elif "<link" in s and "stylesheet" in s:
            add_once("linkcss", "<!-- <link rel=\"stylesheet\">: attaches a CSS file to style this page -->")
        elif s.startswith("<body"):
            add_once("body", "<!-- <body>: visible page content shown to the user -->")
        elif s.startswith("<script"):
            add_once("script", "<!-- <script>: JavaScript that adds interaction/logic -->")
        elif "onclick=" in s:
            # comment close to the line (but not too noisy)
            out.append("<!-- onclick: clicking this element will run a JavaScript function -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# CSS (professional + property hints)
# -----------------------------
def _explain_css_selector(selector: str) -> str:
    sel = selector.strip()
    if sel.startswith("."):
        return f"Styles elements with class `{sel[1:]}`."
    if sel.startswith("#"):
        return f"Styles the element with id `{sel[1:]}`."
    # tag selector
    return f"Styles all `<{sel}>` elements."


def _comment_css(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    text = code.strip()

    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional comments (auto-added)      */")
    out.append("/* ======================================= */")
    out.append("/* CSS controls layout + colors + spacing + typography. */")
    out.append("")

    pattern = re.compile(r"([^{]+)\{([^}]*)\}", re.S)
    pos = 0

    for m in pattern.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            out.append(before)
            out.append("")

        selector = m.group(1).strip()
        body = m.group(2).strip()

        out.append(f"/* {_explain_css_selector(selector)} */")
        out.append(f"{selector} {{")

        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue

            # Minimal, professional inline hints for common properties
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* spacing between items */")
            elif t.startswith(("background:", "background-color:")):
                out.append(f"  {t} /* background */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font-family:"):
                out.append(f"  {t} /* font choice */")
            elif t.startswith("padding"):
                out.append(f"  {t} /* inner spacing */")
            elif t.startswith("margin"):
                out.append(f"  {t} /* outer spacing */")
            elif t.startswith("border"):
                out.append(f"  {t} /* border styling */")
            else:
                out.append(f"  {t}")

        out.append("}")
        out.append("")
        pos = m.end()

    tail = text[pos:].strip()
    if tail:
        out.append(tail)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# Java (professional + conservative)
# -----------------------------
def _comment_java(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional comments (auto-added)")
    out.append("// =======================================")
    out.append("// Java files commonly define classes and methods used by the program.")
    out.append("")

    for line in lines:
        s = line.strip()

        # package/imports
        if s.startswith("package "):
            out.append("// Package: groups related Java files together.")
            out.append(line)
            continue
        if s.startswith("import "):
            out.append("// Import: brings in classes from other packages/libraries.")
            out.append(line)
            continue

        # class
        if re.match(r"^(public\s+)?class\s+\w+", s):
            out.append("// Class: a blueprint that groups methods (functions) and data.")
            out.append(line)
            continue

        # main
        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): program entry point (starts running here).")
            out.append(line)
            continue

        # methods (static/public/common patterns)
        m = re.match(r"^(public|private|protected)\s+(static\s+)?([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*\{?\s*$", s)
        if m and " main" not in s:
            ret_type = m.group(3)
            method = m.group(4)
            args = m.group(5).strip()
            purpose = _guess_purpose_from_name(method)

            out.append(f"// Method: {method}() — {purpose}.")
            out.append(f"// Returns: {ret_type}")
            if args:
                out.append(f"// Inputs: {args}")
            out.append(line)
            continue

        if s.startswith("return "):
            out.append("// return: sends a value back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# JavaScript (you said JS is OK)
# -----------------------------
def _comment_js(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("/* =======================================")
    out.append("   Beginner-friendly JS notes (auto-added)")
    out.append("   ======================================= */")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# Public API: generate_simple_docs
# -----------------------------
def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")
    loc = _count_nonempty_lines(code_clean)
    filename = os.path.basename(file_path) if file_path else "pasted_code"

    # Commenting
    if language == "html":
        commented = _comment_html(code_clean)
    elif language == "css":
        commented = _comment_css(code_clean)
    elif language == "javascript":
        commented = _comment_js(code_clean)
    elif language == "java":
        commented = _comment_java(code_clean)
    else:
        commented = code_clean.rstrip() + "\n"

    purpose_map = {
        "html": "Defines the structure/content of a web page.",
        "css": "Defines the styles (layout, colors, fonts) of a web page.",
        "javascript": "Adds behavior/logic to a web page.",
        "java": "Defines classes and methods used in a Java program.",
    }
    purpose = purpose_map.get(language, "Part of a software project.")

    documentation = (
        f"# File Documentation - `{filename}`\n\n"
        f"## Purpose\n- {purpose}\n\n"
        f"## Quick stats\n- Non-empty lines: **{loc}**\n\n"
        f"## Inputs / Outputs\n"
        f"- Inputs: user actions, parameters, or external files (depends on code).\n"
        f"- Outputs: UI changes, printed logs, returned values (depends on code).\n\n"
        f"## How to run / use\n"
    )

    if language in ("html", "css", "javascript"):
        documentation += (
            "1. Open the `.html` file in a browser.\n"
            "2. CSS applies automatically if linked in `<head>`.\n"
            "3. JavaScript runs automatically if linked via `<script>`.\n"
        )
    elif language == "java":
        documentation += (
            "1. Install Java (JDK).\n"
            "2. Compile: `javac FileName.java`\n"
            "3. Run (if it has main): `java FileName`\n"
        )
    else:
        documentation += "Run steps depend on the project.\n"

    return {"commented_code": commented, "documentation": documentation}
