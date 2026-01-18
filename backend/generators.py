from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Shared helpers
# -----------------------------

AUTO_MARKERS = [
    "Beginner-friendly comments (auto-added)",
    "Beginner-friendly notes (auto-added)",
    "Beginner-friendly CSS notes (auto-added)",
    "Beginner-friendly JS notes (auto-added)",
    "Beginner-friendly Java notes (auto-added)",
]


def _count_nonempty_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def _clean_existing_auto_headers(code: str) -> str:
    """
    Remove previously generated auto headers so we do not stack them forever.
    Works across Python/HTML/CSS/JS/Java.
    """
    lines = code.splitlines()
    out: List[str] = []
    skipping = False

    for line in lines:
        if any(m in line for m in AUTO_MARKERS):
            skipping = True
            continue

        if skipping:
            # stop skipping after a blank line
            if line.strip() == "":
                skipping = False
            continue

        out.append(line)

    cleaned = "\n".join(out).strip()
    return cleaned + ("\n" if code.endswith("\n") else "")


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
        # fallback regex summary if indentation is broken
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


def _python_docstring_for_function(fn_name: str, args: List[str]) -> str:
    """
    Create a short, accurate docstring skeleton for a function when one is missing.
    We do NOT invent behavior; we describe role in neutral terms.
    """
    args_text = ", ".join(args) if args else "none"
    return (
        f'    """\n'
        f"    {fn_name}(...)\n\n"
        f"    Args:\n"
        f"        {args_text}\n\n"
        f"    Returns:\n"
        f"        Depends on what the function returns.\n"
        f'    """\n'
    )


def _add_python_comments(code: str) -> str:
    """
    Professional Python commenting rules:
    - One header at top
    - Comment imports once
    - Comment main loops / try-except / important blocks
    - Add docstring ONLY if function has none
    - No repeated spam blocks
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append("")
    out.append("# This file has been lightly commented to explain the main logic.")
    out.append("")

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        # imports
        if s.startswith("import ") or s.startswith("from "):
            if not any("Imports" in x for x in out[-5:]):
                out.append("# Imports: bring in libraries this file needs.")
            out.append(line)
            i += 1
            continue

        # function defs: add docstring only if missing
        m = re.match(r"^(\s*)def\s+([a-zA-Z_]\w*)\s*\((.*?)\)\s*:", line)
        if m:
            indent = m.group(1)
            fn_name = m.group(2)
            args_raw = m.group(3).strip()
            args = []
            if args_raw:
                args = [a.strip().split("=")[0].strip() for a in args_raw.split(",") if a.strip()]

            out.append(line)

            # lookahead: next meaningful line
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                out.append(lines[j])
                j += 1

            # if no docstring, inject one
            if j < len(lines) and not lines[j].lstrip().startswith(('"""', "'''")):
                out.append(f"{indent}# Function: {fn_name} — one reusable step in the program.")
                out.append(_python_docstring_for_function(fn_name, args).rstrip("\n"))

            i = j
            continue

        # loops
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below multiple times.")
            out.append(line)
            i += 1
            continue

        # try/except
        if re.match(r"^\s*try\s*:", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Try/except: prevents the program from crashing if an error happens.")
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
            "This Python file has a syntax/indentation issue, so some deep analysis is limited.\n"
            "Fix indentation (usually 4 spaces) and try again.\n\n"
        )

    documentation = (
        f"# File Documentation - `{os.path.basename(file_path)}`\n\n"
        f"{parse_note}"
        f"## Key Components\n"
        f"- Lines of code (non-empty): **{loc}**\n"
        f"- Imports detected: **{len(info.get('imports', []))}**\n"
        f"- Loops detected: **{info.get('loops', 0)}**\n"
        f"- Functions detected: **{len(info.get('functions', []))}**\n"
        f"- Classes detected: **{len(info.get('classes', []))}**\n\n"
        f"## Inputs / Outputs\n"
        f"- **Inputs:** {'Uses terminal input (`input(...)`).' if info.get('has_input') else 'Function parameters or events.'}\n"
        f"- **Outputs:** printed text, returned values, or UI changes.\n\n"
        f"## How to run (step-by-step)\n"
        f"1. Open a terminal in the file folder.\n"
        f"2. Run: `python {os.path.basename(file_path)}`\n"
        f"3. Follow any prompts or UI windows.\n"
    )

    commented_code = _add_python_comments(code_clean)
    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# HTML (professional + accurate)
# -----------------------------

def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional beginner-friendly comments -->")
    out.append("<!-- ======================================= -->")
    out.append("<!-- This file describes the structure of a web page. -->")
    out.append("")

    seen = set()

    for line in lines:
        s = line.strip().lower()

        def add_once(key: str, comment: str):
            if key not in seen:
                out.append(comment)
                seen.add(key)

        if s.startswith("<!doctype"):
            add_once("doctype", "<!-- DOCTYPE: tells the browser this is modern HTML5 -->")
        if s.startswith("<html"):
            add_once("html", "<!-- <html>: the root element of the page -->")
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: page settings (title, CSS links, meta tags) -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: everything the user can see on the page -->")
        if s.startswith("<header"):
            add_once("header", "<!-- <header>: top section (usually logo/title/menu) -->")
        if s.startswith("<main"):
            add_once("main", "<!-- <main>: the main content area -->")
        if s.startswith("<footer"):
            add_once("footer", "<!-- <footer>: bottom section (copyright/links) -->")
        if s.startswith("<script"):
            add_once("script", "<!-- <script>: JavaScript code that adds behavior -->")
        if "href=" in s and "<link" in s:
            add_once("csslink", "<!-- <link>: connects this HTML to a CSS file -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# CSS (professional + accurate)
# -----------------------------

def _explain_css_selector(selector: str) -> str:
    sel = selector.strip()
    if sel.startswith("."):
        return f"Targets elements with class `{sel[1:]}`."
    if sel.startswith("#"):
        return f"Targets the element with id `{sel[1:]}`."
    return f"Targets all `<{sel}>` elements."


def _comment_css(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    text = code.strip()

    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional beginner-friendly comments */")
    out.append("/* ======================================= */")
    out.append("/* CSS controls how the page LOOKS (layout, colors, spacing, fonts). */")
    out.append("")

    # Add short notes above each rule block
    pattern = re.compile(r"([^{]+)\{([^}]*)\}", re.S)
    pos = 0
    for m in pattern.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            out.append(before)
            out.append("")
        selector = m.group(1).strip()
        body = m.group(2).strip()

        out.append(f"/* { _explain_css_selector(selector) } */")
        out.append(f"{selector} {{")
        # keep properties as-is, but we can add tiny explanations for common ones
        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue
            # add inline explanations only for key properties (clean + pro)
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* space between items */")
            elif t.startswith("background"):
                out.append(f"  {t} /* background color */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font-family"):
                out.append(f"  {t} /* font style */")
            elif t.startswith("padding"):
                out.append(f"  {t} /* inner spacing */")
            elif t.startswith("margin"):
                out.append(f"  {t} /* outer spacing */")
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
# Java (professional + accurate)
# -----------------------------

def _comment_java(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append("// This file defines Java classes and methods used in a Java program.")
    out.append("")

    for i, line in enumerate(lines):
        s = line.strip()

        # class
        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: a container that holds methods (functions) and data.")
            out.append(line)
            continue

        # main method
        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): the program starts running here.")
            out.append(line)
            continue

        # other methods
        m = re.match(r"^public\s+static\s+(\w+)\s+(\w+)\s*\((.*?)\)", s)
        if m and "main" not in s:
            ret_type = m.group(1)
            name = m.group(2)
            args = m.group(3).strip()

            out.append(f"// Method: {name}()")
            out.append(f"// - Returns: {ret_type}")
            if args:
                out.append(f"// - Inputs: {args}")
            else:
                out.append("// - Inputs: none")
            out.append(line)
            continue

        # return lines
        if s.startswith("return "):
            out.append("// Return: send a result back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# JavaScript (kept simple — you said it's OK)
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
    commented = code_clean
    if language == "html":
        commented = _comment_html(code_clean)
    elif language == "css":
        commented = _comment_css(code_clean)
    elif language == "javascript":
        commented = _comment_js(code_clean)
    elif language == "java":
        commented = _comment_java(code_clean)

    # Documentation
    purpose_map = {
        "html": "Defines the structure/content of a web page.",
        "css": "Defines the styles (colors/layout/fonts) of a web page.",
        "javascript": "Adds behavior/logic to a web page.",
        "java": "Defines a class and methods used in a Java program.",
    }
    purpose = purpose_map.get(language, "Part of a software project.")

    documentation = (
        f"# File Documentation - `{filename}`\n\n"
        f"## Purpose\n- {purpose}\n\n"
        f"## Key Components\n- Lines of code (non-empty): **{loc}**\n\n"
        f"## Inputs / Outputs\n"
        f"- **Inputs:** depends on the code (user actions or parameters).\n"
        f"- **Outputs:** depends on the code (page changes, prints, returns).\n\n"
        f"## How to run / use (step-by-step)\n"
    )

    if language in ("html", "css", "javascript"):
        documentation += (
            "1. Open the `.html` file in a browser.\n"
            "2. CSS works automatically if linked in the HTML.\n"
            "3. JavaScript runs automatically if linked in the HTML.\n"
        )
    elif language == "java":
        documentation += (
            "1. Install Java (JDK).\n"
            "2. Compile: `javac FileName.java`\n"
            "3. Run (if it has main): `java FileName`\n"
        )
    else:
        documentation += "Run steps depend on the project.\n"

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation}