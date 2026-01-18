from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers (general)
# -----------------------------

def _safe_strip(s: str) -> str:
    return (s or "").strip()


def _count_nonempty_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def _first_meaningful_comment_or_doc(code: str) -> str:
    """
    Try to extract top-of-file docstring or leading comment that describes purpose.
    Works even if code has indentation issues (no AST needed).
    """
    text = code.lstrip()
    if text.startswith(('"""', "'''")):
        q = text[:3]
        end = text.find(q, 3)
        if end != -1:
            return _safe_strip(text[3:end])

    # Try leading block of comments (# ...)
    lines = code.splitlines()
    buf = []
    for line in lines[:25]:
        t = line.strip()
        if t.startswith("#"):
            buf.append(t.lstrip("#").strip())
        elif t == "":
            if buf:
                buf.append("")
        else:
            break

    out = "\n".join(buf).strip()
    if len(out) >= 20:
        return out
    return ""


def _guess_python_program_type(code: str) -> Tuple[str, List[str]]:
    """
    Heuristics to describe purpose in plain English.
    Returns: (purpose_sentence, extra_notes)
    """
    c = code.lower()
    notes: List[str] = []

    if "tkinter" in c or "from tkinter" in c:
        return (
            "This Python program builds a simple graphical user interface (GUI) using Tkinter so a user can interact with the app by clicking buttons and typing input.",
            notes,
        )

    if "turtle" in c or "from turtle" in c or "import turtle" in c:
        return (
            "This Python program uses Turtle graphics to draw shapes/patterns on the screen by moving a cursor (the 'turtle') around and drawing lines.",
            notes,
        )

    if "input(" in c:
        return (
            "This Python program runs in the terminal and asks the user for input, then performs actions based on what the user enters.",
            notes,
        )

    if "random" in c and ("guess" in c or "randint" in c):
        return (
            "This Python program uses random numbers to create a small game or simulation where results change each time you run it.",
            notes,
        )

    return (
        "This Python file contains Python code (functions and instructions) that performs some tasks when the script runs or when its functions are called.",
        notes,
    )


def _python_how_to_run(code: str, file_path: str) -> str:
    filename = os.path.basename(file_path) if file_path else "main.py"
    c = code.lower()

    steps: List[str] = []
    steps.append("### Option A: Run with Python (recommended)")
    steps.append("1. Make sure Python is installed (Python 3).")
    steps.append("2. Open a terminal in the folder containing the file.")
    steps.append(f"3. Run: `python {filename}`")

    if "tkinter" in c or "from tkinter" in c:
        steps.append("4. A window should open. Use the buttons/fields in the window.")
    elif "turtle" in c or "from turtle" in c or "import turtle" in c:
        steps.append("4. A drawing window should open. Wait for it to finish drawing.")
        steps.append("5. Close the window to end the program.")
    else:
        if "input(" in c:
            steps.append("4. Follow the prompts in the terminal and type your input.")
        else:
            steps.append("4. If nothing prints, the code may be a library of functions used by other files.")

    return "\n".join(steps)


def _clean_existing_auto_headers(code: str) -> str:
    """
    Remove previous auto-header blocks so we don't stack them forever.
    Works for Python (#), JS/CSS (/* */), HTML (<!-- -->), Java (//).
    """
    lines = code.splitlines()
    out: List[str] = []

    skip = False
    for line in lines:
        low = line.lower()

        if "beginner-friendly" in low and "auto" in low:
            skip = True
            continue

        if skip:
            if line.strip() == "":
                skip = False
            continue

        out.append(line)

    return "\n".join(out).strip() + ("\n" if code.endswith("\n") else "")


# -----------------------------
# Python analysis (safe)
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
    }

    if not tree:
        summary["loops"] = len(re.findall(r"\b(for|while)\b", code))
        summary["functions"] = re.findall(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code, flags=re.M)
        summary["classes"] = re.findall(r"^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]", code, flags=re.M)
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


def _add_python_comments(code: str) -> str:
    code = _clean_existing_auto_headers(code)

    lines = code.splitlines()
    out: List[str] = []
    out.append("# =======================================")
    out.append("# Beginner-friendly comments (auto-added)")
    out.append("# =======================================")
    out.append("")
    out.append("# This file was automatically commented to help beginners understand it.")
    out.append("")

    for line in lines:
        s = line.strip()

        if s.startswith("import ") or s.startswith("from "):
            if not out or not out[-1].startswith("# Import"):
                out.append("# Import libraries needed for this program.")
            out.append(line)
            continue

        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Repeat the following block multiple times (a loop).")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")

    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    top_desc = _first_meaningful_comment_or_doc(code_clean)
    purpose_guess, notes = _guess_python_program_type(code_clean)

    purpose_lines: List[str] = []
    if top_desc:
        purpose_lines.append(top_desc.splitlines()[0].strip())
        if len(top_desc) > 120 and purpose_guess:
            purpose_lines.append(purpose_guess)
    else:
        purpose_lines.append(purpose_guess)

    how_to = _python_how_to_run(code_clean, file_path)

    functions = info.get("functions", [])
    classes = info.get("classes", [])
    imports = info.get("imports", [])
    loops = info.get("loops", 0)

    parse_note = ""
    if not info.get("parse_ok", True):
        parse_note = (
            "## Important Note\n"
            "This code has a syntax/indentation issue, so full analysis may be limited.\n"
            "If you see `IndentationError`, fix spacing inside functions (usually 4 spaces).\n"
            "Even with errors, we still generate beginner-friendly docs and light comments.\n\n"
        )

    doc_lines: List[str] = []
    doc_lines.append(f"# File Documentation - `{os.path.basename(file_path)}`")
    doc_lines.append("")
    if parse_note:
        doc_lines.append(parse_note.strip())
        doc_lines.append("")

    doc_lines.append("## Purpose")
    for pl in purpose_lines:
        doc_lines.append(f"- {pl}")
    doc_lines.append("")

    doc_lines.append("## Key Components")
    doc_lines.append(f"- Lines of code (non-empty): **{loc}**")
    doc_lines.append(f"- Imports detected: **{len(imports)}**")
    doc_lines.append(f"- Loops detected: **{loops}**")
    doc_lines.append(f"- Functions detected: **{len(functions)}**")
    doc_lines.append(f"- Classes detected: **{len(classes)}**")
    doc_lines.append("")

    if imports:
        doc_lines.append("### Imports")
        for imp in imports:
            doc_lines.append(f"- `{imp}`")
        doc_lines.append("")

    if classes:
        doc_lines.append("### Classes")
        for c in classes:
            doc_lines.append(f"- `{c}`")
        doc_lines.append("")

    if functions:
        doc_lines.append("### Functions (what they are for)")
        for fn in functions:
            doc_lines.append(f"- `{fn}()` – a helper function used by the program.")
        doc_lines.append("")

    doc_lines.append("## Inputs / Outputs")
    if "input(" in code_clean.lower():
        doc_lines.append("- **Input:** the user types input in the terminal (because `input(...)` is used).")
    else:
        doc_lines.append("- **Input:** values passed into functions, or events like clicks (for GUI programs).")
    doc_lines.append("- **Output:** printed text, returned values, or a window/drawing on screen.")
    doc_lines.append("")

    doc_lines.append("## How it fits into a larger project")
    doc_lines.append("- If this is the only file, it can run as a standalone script.")
    doc_lines.append("- If there are multiple files, other files may import and use functions from this file.")
    doc_lines.append("")

    doc_lines.append("## How to run (step-by-step)")
    doc_lines.append(how_to)
    doc_lines.append("")

    doc_lines.append("## Edge cases / important notes")
    doc_lines.append("- If the program loads files (images/data), those files must be in the correct folder.")
    doc_lines.append("- If you get an error, read the line number in the error message and check spacing/typos.")
    if notes:
        for n in notes:
            doc_lines.append(f"- {n}")
    doc_lines.append("")

    documentation = "\n".join(doc_lines).strip() + "\n"
    commented_code = _add_python_comments(code_clean)

    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# Simple docs for JS/HTML/CSS/Java
# -----------------------------

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")
    loc = _count_nonempty_lines(code_clean)
    filename = os.path.basename(file_path) if file_path else "pasted_code"

    purpose = "This file is part of a software project."
    lc = code_clean.lower()

    if language == "html":
        purpose = "This HTML file defines the structure/content of a web page (what users see)."
    elif language == "css":
        purpose = "This CSS file defines the visual style of a web page (colors, layout, spacing, fonts)."
    elif language == "javascript":
        purpose = "This JavaScript file adds behavior/logic to a website (clicks, calculations, dynamic changes)."
    elif language == "java":
        purpose = "This Java file defines a class (and methods) used in a Java application."

    how_to_lines: List[str] = []
    if language in ("html", "css", "javascript"):
        how_to_lines.append("1. Find the main `.html` file in the project.")
        how_to_lines.append("2. Open the HTML file in a browser (double-click it).")
        how_to_lines.append("3. CSS will style the page if it is linked in the HTML.")
        how_to_lines.append("4. JavaScript will run if it is linked in the HTML.")
    elif language == "java":
        how_to_lines.append("1. Install Java (JDK).")
        how_to_lines.append("2. Open a terminal in the folder containing the `.java` file(s).")
        how_to_lines.append("3. Compile: `javac FileName.java`")
        how_to_lines.append("4. Run (if it has a main method): `java FileName`")
    else:
        how_to_lines.append("Run steps depend on the project setup.")

    commented = code_clean
    if language == "html":
        commented = _comment_html(code_clean)
    elif language == "css":
        commented = _comment_css(code_clean)
    elif language == "javascript":
        commented = _comment_js(code_clean)
    elif language == "java":
        commented = _comment_java(code_clean)

    documentation = (
        f"# File Documentation - `{filename}`\n\n"
        f"## Purpose\n- {purpose}\n\n"
        f"## Key Components\n- Lines of code (non-empty): **{loc}**\n\n"
        f"## Inputs / Outputs\n"
        f"- **Inputs:** user actions (clicks), function parameters, or data.\n"
        f"- **Outputs:** updated page content/styles, console output, or returned values.\n\n"
        f"## How it fits into a larger project\n"
        f"- This file works together with other files in the project.\n\n"
        f"## How to run / use (step-by-step)\n"
        + "\n".join(how_to_lines)
        + "\n"
    )

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation}


def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append("<!-- ======================================= -->")
    out.append("<!-- Beginner-friendly notes (auto-added)     -->")
    out.append("<!-- ======================================= -->")
    out.append("")
    for line in lines:
        s = line.strip().lower()
        if s.startswith("<head"):
            out.append("<!-- HEAD: page settings (title, CSS links, meta tags) -->")
        if s.startswith("<body"):
            out.append("<!-- BODY: what the user sees on the page -->")
        if s.startswith("<header"):
            out.append("<!-- HEADER: top section (title/logo/menu) -->")
        if s.startswith("<main"):
            out.append("<!-- MAIN: the main content area -->")
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _comment_css(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Beginner-friendly CSS notes (auto-added) */")
    out.append("/* ======================================= */")
    out.append("")
    out.append("/* Tip: CSS changes how the page LOOKS (colors, layout, spacing). */")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


# ✅✅✅ THIS IS THE FIX: REAL JS COMMENTS (BEGINNER-FRIENDLY, NOT SPAM)
def _comment_js(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()

    out: List[str] = []
    out.append("/* =======================================")
    out.append("   Beginner-friendly JS comments (auto-added)")
    out.append("   ======================================= */")
    out.append("")
    out.append("/* This file contains JavaScript logic (functions that do things). */")
    out.append("")

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect function declarations: function name(args) { ...
        m = re.match(r"^(\s*)function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{?\s*$", line)
        if m:
            indent = m.group(1)
            fname = m.group(2)
            args = m.group(3).strip()

            out.append(f"{indent}// Function: {fname}()")
            out.append(f"{indent}// Purpose: A reusable piece of code you can call to do one job.")
            if args:
                out.append(f"{indent}// Input(s): {args}")
            else:
                out.append(f"{indent}// Input(s): none")
            out.append(line)
            i += 1
            continue

        # Comment common patterns inside functions (light, not spam)
        if re.match(r"^\s*if\s*\(", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}// Check a condition. If it's true, run the next line/block.")
            out.append(line)
            i += 1
            continue

        if "return " in stripped:
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}// Return the final result back to whoever called this function.")
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


def _comment_java(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("// =======================================")
    out.append("// Beginner-friendly Java notes (auto-added)")
    out.append("// =======================================")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"