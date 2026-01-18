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
    "Professional beginner-friendly comments",
    "Professional beginner-friendly notes",
    "Professional beginner-friendly CSS comments",
    "Professional beginner-friendly JS comments",
    "Professional beginner-friendly Java comments",
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
# PYTHON HELPERS (Purpose + Safe Parse)
# -----------------------------

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    """
    Parse python safely. If indentation/syntax is broken, return error string.
    """
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _summarize_python_code(code: str) -> Dict[str, Any]:
    """
    Extract useful info using AST when possible.
    Must NEVER crash.
    """
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

    # If AST fails, do fallback regex scan
    if not tree:
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
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            if node.module:
                imports.append(node.module)
            self.generic_visit(node)

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


def _guess_python_purpose(code: str) -> str:
    """
    BEST-EFFORT purpose (based strictly on code patterns).
    We do not invent fake descriptions.
    """
    c = code.lower()

    if "from tkinter" in c or "tkinter" in c:
        return "This program builds a small window (GUI) using Tkinter so the user can interact with buttons and inputs."

    if "from turtle" in c or "import turtle" in c or "turtle" in c:
        return "This program uses Turtle graphics to draw shapes or patterns in a drawing window."

    if "input(" in c:
        return "This program runs in the terminal and asks the user questions, then performs actions based on the answers."

    if "random" in c and ("randint" in c or "choice" in c):
        return "This program uses random numbers to create a game or simulation that changes each time it runs."

    return "This Python file contains code that performs a task when run, or provides functions that other files can use."


def _python_run_steps(file_path: str, code: str) -> str:
    """
    Beginner-friendly run steps that match what the code is doing.
    """
    filename = os.path.basename(file_path) if file_path else "main.py"
    c = code.lower()

    lines: List[str] = []
    lines.append("### Option A: Run with Python (recommended)")
    lines.append("1. Make sure Python is installed (Python 3).")
    lines.append("2. Open a terminal inside the folder containing the file.")
    lines.append(f"3. Run: `python {filename}`")

    if "tkinter" in c or "from tkinter" in c:
        lines.append("4. A window should open. Use the buttons/inputs in the window.")
    elif "turtle" in c or "from turtle" in c or "import turtle" in c:
        lines.append("4. A drawing window will open. Wait for the drawing to finish.")
        lines.append("5. Close the window to end the program.")
    elif "input(" in c:
        lines.append("4. Follow the instructions in the terminal and type your answers.")
    else:
        lines.append("4. If nothing happens, the file may only contain helper functions meant to be imported.")

    return "\n".join(lines)


# -----------------------------
# PYTHON COMMENTING (THIS IS YOUR STYLE ✅)
# -----------------------------

def _add_python_comments(code: str, file_path: str = "pasted_code") -> str:
    """
    ✅ Professional beginner-friendly comments (your style)
    - Explains what the program does
    - Explains key sections clearly
    - NO spam comments per line
    - Avoids guessing behavior we cannot see
    """
    code = _clean_existing_auto_headers(code)
    info = _summarize_python_code(code)
    purpose = _guess_python_purpose(code)

    out: List[str] = []
    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("#")
    out.append("# What this program does:")
    out.append(f"# - {purpose}")
    out.append("")

    # Add a helpful note if parsing failed
    if not info.get("parse_ok", True):
        out.append("# NOTE:")
        out.append("# - This file has an indentation/syntax issue, so analysis may be limited.")
        out.append("# - Fix spacing inside functions (usually 4 spaces), then try again.")
        out.append("")

    lines = code.splitlines()

    # We only add comments at key places (imports, functions, loops, main guard)
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Imports
        if stripped.startswith("import ") or stripped.startswith("from "):
            # Only add one import comment before the first import
            if not any("Imports" in x for x in out):
                out.append("# Imports: bring in libraries that this file needs.")
            out.append(line)
            continue

        # Function definitions
        m = re.match(r"^(\s*)def\s+([a-zA-Z_]\w*)\s*\(", line)
        if m:
            indent = m.group(1)
            fn_name = m.group(2)

            # Add a short clear explanation above the function
            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# Function: {fn_name}()")
            out.append(f"{indent}# This function handles one part of the program.")
            out.append(f"{indent}# ---------------------------------------")
            out.append(line)
            continue

        # Loop explanation
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below multiple times.")
            out.append(line)
            continue

        # Main guard explanation
        if stripped == 'if __name__ == "__main__":':
            out.append("")
            out.append("# This means: run the main program only when this file is executed directly.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    """
    Produces:
    - commented_code (your clean style)
    - documentation (beginner-friendly and specific)
    """
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    purpose = _guess_python_purpose(code_clean)
    how_to_run = _python_run_steps(file_path, code_clean)

    parse_note = ""
    if not info.get("parse_ok", True):
        parse_note = (
            "## Important Note\n"
            "This file has an indentation/syntax issue, so deeper analysis may be limited.\n"
            "Fix indentation (usually 4 spaces inside functions) and try again.\n\n"
        )

    documentation_lines: List[str] = []
    documentation_lines.append(f"# File Documentation - `{os.path.basename(file_path)}`")
    documentation_lines.append("")
    if parse_note:
        documentation_lines.append(parse_note.strip())
        documentation_lines.append("")

    documentation_lines.append("## Purpose")
    documentation_lines.append(f"- {purpose}")
    documentation_lines.append("")

    documentation_lines.append("## Key Components")
    documentation_lines.append(f"- Lines of code (non-empty): **{loc}**")
    documentation_lines.append(f"- Imports detected: **{len(info.get('imports', []))}**")
    documentation_lines.append(f"- Loops detected: **{info.get('loops', 0)}**")
    documentation_lines.append(f"- Functions detected: **{len(info.get('functions', []))}**")
    documentation_lines.append(f"- Classes detected: **{len(info.get('classes', []))}**")
    documentation_lines.append("")

    if info.get("functions"):
        documentation_lines.append("### Functions")
        for fn in info["functions"]:
            documentation_lines.append(f"- `{fn}()` – a function that handles part of the program logic.")
        documentation_lines.append("")

    documentation_lines.append("## Inputs / Outputs")
    if info.get("has_input"):
        documentation_lines.append("- **Input:** the user types values in the terminal (because `input(...)` is used).")
    else:
        documentation_lines.append("- **Input:** function arguments or user actions (GUI/program events).")
    documentation_lines.append("- **Output:** printed messages, returned values, or changes on the screen/window.")
    documentation_lines.append("")

    documentation_lines.append("## How to run (Step-by-step)")
    documentation_lines.append(how_to_run)
    documentation_lines.append("")

    documentation_lines.append("## Important Notes")
    documentation_lines.append("- If the program needs extra files (images/data), they must be inside the same folder or correct path.")
    documentation_lines.append("- If nothing happens when you run it, the file may only contain helper functions for other files.")
    documentation_lines.append("")

    documentation = "\n".join(documentation_lines).strip() + "\n"
    commented_code = _add_python_comments(code_clean, file_path)

    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# HTML COMMENTING (Clean + Professional)
# -----------------------------

def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional beginner-friendly comments -->")
    out.append("<!-- ======================================= -->")
    out.append("<!-- This file defines the structure of a web page. -->")
    out.append("")

    seen = set()

    def add_once(key: str, text: str):
        if key not in seen:
            out.append(text)
            seen.add(key)

    for line in lines:
        s = line.strip().lower()

        if s.startswith("<!doctype"):
            add_once("doctype", "<!-- DOCTYPE: tells the browser this is modern HTML5 -->")
        if s.startswith("<html"):
            add_once("html", "<!-- <html>: the root element that wraps the entire page -->")
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: contains settings like title, CSS links and meta tags -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: name shown on the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: everything the user can see on the page -->")
        if s.startswith("<header"):
            add_once("header", "<!-- <header>: the top section (logo/title/menu) -->")
        if s.startswith("<main"):
            add_once("main", "<!-- <main>: the main content area -->")
        if s.startswith("<footer"):
            add_once("footer", "<!-- <footer>: bottom of the page (links/copyright) -->")
        if s.startswith("<script"):
            add_once("script", "<!-- <script>: JavaScript code that adds behavior (clicks/actions) -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# CSS COMMENTING (Clean + Pro)
# -----------------------------

def _comment_css(code: str) -> str:
    code = _clean_existing_auto_headers(code)

    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional beginner-friendly comments */")
    out.append("/* ======================================= */")
    out.append("/* CSS controls the LOOK of the page: colors, layout, spacing, and fonts. */")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# JAVASCRIPT COMMENTING (You said it's OK)
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
# JAVA COMMENTING (Clean + Pro)
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

    for line in lines:
        s = line.strip()

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: a container that groups methods together.")
            out.append(line)
            continue

        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): the program starts running here.")
            out.append(line)
            continue

        m = re.match(r"^public\s+static\s+(\w+)\s+(\w+)\s*\((.*?)\)", s)
        if m and "main" not in s:
            out.append(f"// Method: {m.group(2)}()")
            out.append(f"// - Returns: {m.group(1)}")
            out.append(f"// - Inputs: {m.group(3).strip() or 'none'}")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# SIMPLE DOCS FOR NON-PYTHON FILES
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

    purpose_map = {
        "html": "Defines the structure/content of a web page.",
        "css": "Defines styles (colors/layout/fonts) of a web page.",
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
        documentation += "Run steps depend on the project setup.\n"

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation}