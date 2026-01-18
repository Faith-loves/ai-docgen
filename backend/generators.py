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
    "Professional beginner-friendly JS notes",
    "Professional beginner-friendly CSS notes",
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
# Python analysis (safe)
# -----------------------------

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _summarize_python_code(code: str) -> Dict[str, Any]:
    """
    AST summary. Must never crash.
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


def _guess_python_purpose(code: str) -> str:
    """
    Try to describe what the program is, using safe hints (imports, keywords).
    We keep it accurate and beginner-friendly.
    """
    c = code.lower()

    if "from tkinter" in c or "import tkinter" in c:
        return "This program creates a simple desktop window (GUI) using Tkinter."

    if "from turtle" in c or "import turtle" in c:
        return "This program draws graphics on the screen using the Turtle library."

    if "input(" in c:
        return "This program runs in the terminal and asks the user questions, then performs actions based on the answers."

    if "random" in c and ("randint" in c or "choice" in c):
        return "This program uses random numbers to create a small simulation or game."

    return "This Python program contains logic (functions and steps) that runs when the file is executed."


def _describe_python_function(fn_name: str) -> str:
    """
    Generate a clear beginner-friendly description based on function name.
    We do NOT guess deep hidden behavior — we describe based on naming.
    """
    name = fn_name.lower()

    if name == "main":
        return "Main menu loop (program starts here)."

    # To-do list patterns
    if "show" in name and ("task" in name or "todo" in name or "list" in name):
        return "Show all tasks currently in the list."
    if ("add" in name or "create" in name) and ("task" in name or "todo" in name):
        return "Add a new task into the list."
    if ("remove" in name or "delete" in name) and ("task" in name or "todo" in name):
        return "Remove a task using its number (index)."

    # Calculator / numbers
    if "calc" in name or "calculate" in name:
        return "Calculate a result based on the input values."
    if "sum" in name:
        return "Add numbers together and return the result."

    # File operations
    if "load" in name:
        return "Load information from a file or saved storage."
    if "save" in name:
        return "Save information to a file or storage."
    if "read" in name:
        return "Read and return information."
    if "write" in name:
        return "Write information to a file or output."

    # Default
    return f"Function: {fn_name}() — performs one specific job in the program."


def _add_python_comments(code: str, file_path: str = "pasted_code") -> str:
    """
    ✅ Professional Python commenting (your style):
    - Explains purpose at top
    - Adds clean section headers
    - Gives meaningful descriptions for common function names
    - Keeps comments simple and beginner-friendly
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

    if not info.get("parse_ok", True):
        out.append("# NOTE:")
        out.append("# - This file has an indentation/syntax issue.")
        out.append("# - Fix spacing inside functions (usually 4 spaces), then try again.")
        out.append("")

    lines = code.splitlines()

    for line in lines:
        stripped = line.strip()

        # Imports
        if stripped.startswith("import ") or stripped.startswith("from "):
            if not any("Imports:" in x for x in out[-6:]):
                out.append("# Imports: bring in libraries that this file needs.")
            out.append(line)
            continue

        # Function definitions
        m = re.match(r"^(\s*)def\s+([a-zA-Z_]\w*)\s*\(", line)
        if m:
            indent = m.group(1)
            fn_name = m.group(2)
            desc = _describe_python_function(fn_name)

            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# {desc}")
            out.append(f"{indent}# ---------------------------------------")
            out.append(line)
            continue

        # Loop explanations
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below multiple times.")
            out.append(line)
            continue

        # main guard
        if stripped == 'if __name__ == "__main__":':
            out.append("")
            out.append("# This means: only run the program when this file is executed directly.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _python_how_to_run(code: str, file_path: str) -> str:
    filename = os.path.basename(file_path) if file_path else "main.py"
    c = code.lower()

    steps: List[str] = []
    steps.append("### Option A: Run with Python (recommended)")
    steps.append("1. Make sure Python is installed (Python 3).")
    steps.append("2. Open a terminal in the folder containing the file.")
    steps.append(f"3. Run: `python {filename}`")

    if "tkinter" in c:
        steps.append("4. A window should open. Use the buttons/fields in the window.")
    elif "turtle" in c:
        steps.append("4. A drawing window should open. Wait for it to finish drawing.")
        steps.append("5. Close the window to end the program.")
    elif "input(" in c:
        steps.append("4. Follow the prompts in the terminal and type your input.")
    else:
        steps.append("4. If nothing happens, the file may only define functions for other files to use.")

    return "\n".join(steps)


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    """
    Produces:
    - commented_code
    - documentation (beginner-friendly + step-by-step)
    """
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    parse_note = ""
    if not info.get("parse_ok", True):
        parse_note = (
            "## Important Note\n"
            "This Python file has a syntax/indentation issue, so full analysis may be limited.\n"
            "Fix indentation (usually 4 spaces) and try again.\n\n"
        )

    purpose = _guess_python_purpose(code_clean)
    how_to = _python_how_to_run(code_clean, file_path)

    documentation = (
        f"# File Documentation - `{os.path.basename(file_path)}`\n\n"
        f"{parse_note}"
        f"## Purpose\n"
        f"- {purpose}\n\n"
        f"## Key Components\n"
        f"- Lines of code (non-empty): **{loc}**\n"
        f"- Imports detected: **{len(info.get('imports', []))}**\n"
        f"- Loops detected: **{info.get('loops', 0)}**\n"
        f"- Functions detected: **{len(info.get('functions', []))}**\n"
        f"- Classes detected: **{len(info.get('classes', []))}**\n\n"
        f"## Inputs / Outputs\n"
        f"- **Inputs:** {'User types input in terminal (`input(...)`).' if info.get('has_input') else 'Function parameters or user actions.'}\n"
        f"- **Outputs:** printed text, returned values, or UI changes.\n\n"
        f"## How to run (step-by-step)\n"
        f"{how_to}\n"
    )

    commented_code = _add_python_comments(code_clean, file_path=file_path)
    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# HTML (professional comments)
# -----------------------------

def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional beginner-friendly comments -->")
    out.append("<!-- ======================================= -->")
    out.append("<!-- This file defines the STRUCTURE of a web page. -->")
    out.append("")

    seen = set()

    def add_once(key: str, comment: str):
        if key not in seen:
            out.append(comment)
            seen.add(key)

    for line in lines:
        s = line.strip().lower()

        if s.startswith("<!doctype"):
            add_once("doctype", "<!-- DOCTYPE: tells the browser this is modern HTML5 -->")
        if s.startswith("<html"):
            add_once("html", "<!-- <html>: the root element of the whole page -->")
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: page settings (title, CSS links, meta tags) -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: everything the user can see on the page -->")
        if s.startswith("<header"):
            add_once("header", "<!-- <header>: top section (logo/title/menu) -->")
        if s.startswith("<main"):
            add_once("main", "<!-- <main>: main page content area -->")
        if s.startswith("<footer"):
            add_once("footer", "<!-- <footer>: bottom section (copyright/links) -->")
        if s.startswith("<script"):
            add_once("script", "<!-- <script>: JavaScript that adds behavior to the page -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# CSS (professional comments)
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
    out.append("/* CSS controls the LOOK of the page (colors, layout, spacing, fonts). */")
    out.append("")

    # Add short notes above each rule block
    pattern = re.compile(r"([^{]+)\{([^}]*)\}", re.S)
    for m in pattern.finditer(text):
        selector = m.group(1).strip()
        body = m.group(2).strip()

        out.append(f"/* {_explain_css_selector(selector)} */")
        out.append(f"{selector} {{")

        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue

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

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# Java (professional comments)
# -----------------------------

def _comment_java(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append("// This file defines a Java class and its methods.")
    out.append("")

    for line in lines:
        s = line.strip()

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: a container that holds methods (functions) and data.")
            out.append(line)
            continue

        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): the program starts running here.")
            out.append(line)
            continue

        m = re.match(r"^public\s+static\s+(\w+)\s+(\w+)\s*\((.*?)\)", s)
        if m and "main" not in s:
            ret_type = m.group(1)
            name = m.group(2)
            args = m.group(3).strip()

            out.append(f"// Method: {name}()")
            out.append(f"// - Returns: {ret_type}")
            out.append(f"// - Inputs: {args if args else 'none'}")
            out.append(line)
            continue

        if s.startswith("return "):
            out.append("// Return: send the result back to whoever called this method.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# JavaScript (you said it is OK)
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
# Public API for non-Python
# -----------------------------

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")
    loc = _count_nonempty_lines(code_clean)
    filename = os.path.basename(file_path) if file_path else "pasted_code"

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
