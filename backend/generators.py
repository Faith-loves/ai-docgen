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
            # Stop skipping after a blank line
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
        "functions": [],   # list[str]
        "classes": [],     # list[str]
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


# -----------------------------
# Python commenting (accurate per code)
# -----------------------------

def _op_to_words(op: ast.operator) -> Optional[str]:
    if isinstance(op, ast.Add):
        return "adds"
    if isinstance(op, ast.Sub):
        return "subtracts"
    if isinstance(op, ast.Mult):
        return "multiplies"
    if isinstance(op, ast.Div):
        return "divides"
    if isinstance(op, ast.Mod):
        return "takes the remainder of"
    if isinstance(op, ast.Pow):
        return "raises"
    return None


def _expr_to_name(expr: ast.AST) -> str:
    """
    Very small, safe stringifier for common expressions (no code-guessing).
    """
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Constant):
        return repr(expr.value)
    if isinstance(expr, ast.Attribute):
        base = _expr_to_name(expr.value)
        return f"{base}.{expr.attr}"
    if isinstance(expr, ast.Call):
        fn = _expr_to_name(expr.func)
        return f"{fn}(...)"
    if isinstance(expr, ast.Subscript):
        return f"{_expr_to_name(expr.value)}[...]"
    return "a value"


def _infer_function_summary(fn: ast.FunctionDef) -> List[str]:
    """
    Build 1–3 comment lines that match the function code.
    We do not invent behavior. We describe what we can see.
    """
    lines: List[str] = []
    fn_name = fn.name

    # Special-case "main"
    if fn_name.lower() == "main":
        lines.append("Main program entry point (controls the main flow).")

    # Detect returns
    returns: List[ast.Return] = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]

    # Detect input/print usage
    calls: List[ast.Call] = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    called_names = []
    for c in calls:
        called_names.append(_expr_to_name(c.func))

    uses_input = any(name.startswith("input") for name in called_names)
    uses_print = any(name.startswith("print") for name in called_names)

    # Detect list operations like append/pop/extend
    append_calls = []
    pop_calls = []
    for c in calls:
        if isinstance(c.func, ast.Attribute) and c.func.attr == "append":
            append_calls.append(c)
        if isinstance(c.func, ast.Attribute) and c.func.attr == "pop":
            pop_calls.append(c)

    # Detect simple arithmetic return: a + b, a - b, etc.
    if returns:
        # Try first return that has a value
        for r in returns:
            if r.value is None:
                continue

            v = r.value

            # return a + b / a - b etc.
            if isinstance(v, ast.BinOp):
                op_words = _op_to_words(v.op)
                left = _expr_to_name(v.left)
                right = _expr_to_name(v.right)
                if op_words:
                    # "adds a and b"
                    if op_words == "adds":
                        lines.append(f"Adds {left} and {right}.")
                        lines.append(f"Returns the result of {left} + {right}.")
                    elif op_words == "subtracts":
                        lines.append(f"Subtracts {right} from {left}.")
                        lines.append(f"Returns the result of {left} - {right}.")
                    elif op_words == "multiplies":
                        lines.append(f"Multiplies {left} by {right}.")
                        lines.append(f"Returns the result of {left} * {right}.")
                    elif op_words == "divides":
                        lines.append(f"Divides {left} by {right}.")
                        lines.append(f"Returns the result of {left} / {right}.")
                    elif op_words == "takes the remainder of":
                        lines.append(f"Computes the remainder of {left} divided by {right}.")
                        lines.append(f"Returns the result of {left} % {right}.")
                    elif op_words == "raises":
                        lines.append(f"Raises {left} to the power of {right}.")
                        lines.append(f"Returns the result of {left} ** {right}.")
                    break

            # return something(...) / return variable / return string
            if isinstance(v, ast.Call):
                lines.append(f"Returns the result of calling {_expr_to_name(v.func)}.")
                break

            if isinstance(v, ast.Name):
                lines.append(f"Returns {v.id}.")
                break

            if isinstance(v, ast.Constant):
                lines.append("Returns a constant value.")
                break

            # Fallback for other return expressions
            lines.append("Returns a value based on the function logic.")
            break

    # If no meaningful return message and we saw list modifications
    if append_calls and not any("Adds" in s or "append" in s.lower() for s in lines):
        # Mention first append target if available
        c0 = append_calls[0]
        if isinstance(c0.func, ast.Attribute):
            target = _expr_to_name(c0.func.value)
            lines.append(f"Appends an item to {target}.")

    if pop_calls and not any("Removes" in s or "pop" in s.lower() for s in lines):
        c0 = pop_calls[0]
        if isinstance(c0.func, ast.Attribute):
            target = _expr_to_name(c0.func.value)
            lines.append(f"Removes an item from {target}.")

    # Mention terminal interaction if we saw it
    if uses_input and not any("input" in s.lower() or "user" in s.lower() for s in lines):
        lines.append("Reads input from the user in the terminal.")
    if uses_print and not any("print" in s.lower() or "displays" in s.lower() for s in lines):
        lines.append("Prints output to the terminal.")

    # Trim duplicates / keep it short
    dedup: List[str] = []
    for s in lines:
        s2 = s.strip()
        if s2 and s2 not in dedup:
            dedup.append(s2)

    # If still empty, give a neutral statement
    if not dedup:
        dedup = ["Performs one specific job in the program."]

    # Keep at most 3 lines (clean, not spam)
    return dedup[:3]


def _add_python_comments(code: str, file_path: str = "pasted_code") -> str:
    """
    Professional Python commenting rules:
    - No "what this program does" block (as requested)
    - Clean header
    - Imports commented once
    - Each function gets an accurate summary based on its code
    - Loops and try/except get short comments
    - No spam / no repetition
    """
    code = _clean_existing_auto_headers(code)
    tree, err = _safe_parse_python(code)

    out: List[str] = []
    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    if tree is None:
        # If parsing fails, we still return a clean header + original code.
        out.append("# NOTE: This file has a syntax/indentation issue, so accurate auto-commenting is limited.")
        out.append("# Fix indentation (usually 4 spaces), then try again for better comments.")
        out.append("")
        out.append(code.strip())
        return "\n".join(out).rstrip() + "\n"

    # Collect function summaries
    fn_map: Dict[int, List[str]] = {}  # lineno -> [summary lines]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            fn_map[node.lineno] = _infer_function_summary(node)

    lines = code.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Imports
        if stripped.startswith("import ") or stripped.startswith("from "):
            # Add imports comment once
            if not any(x.strip() == "# Imports: libraries used by this file." for x in out):
                out.append("# Imports: libraries used by this file.")
            out.append(line)
            i += 1
            continue

        # Function def (insert accurate summary block)
        m = re.match(r"^(\s*)def\s+([a-zA-Z_]\w*)\s*\(", line)
        if m:
            indent = m.group(1)
            lineno = i + 1
            summary_lines = fn_map.get(lineno, ["Performs one specific job in the program."])

            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# Function: {m.group(2)}()")
            for s in summary_lines:
                out.append(f"{indent}# - {s}")
            out.append(f"{indent}# ---------------------------------------")
            out.append(line)
            i += 1
            continue

        # Loops
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below.")
            out.append(line)
            i += 1
            continue

        # try/except
        if re.match(r"^\s*try\s*:", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Error handling: catch errors instead of crashing.")
            out.append(line)
            i += 1
            continue

        if stripped.startswith("except "):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# If an error happens above, this block runs.")
            out.append(line)
            i += 1
            continue

        # main guard
        if stripped == 'if __name__ == "__main__":':
            out.append("")
            out.append("# Run the program only when this file is executed directly.")
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# Docs generation (Python)
# -----------------------------

def _python_how_to_run(code: str, file_path: str) -> str:
    filename = os.path.basename(file_path) if file_path else "main.py"
    c = code.lower()

    steps: List[str] = []
    steps.append("### Option A: Run with Python (recommended)")
    steps.append("1. Make sure Python is installed (Python 3).")
    steps.append("2. Open a terminal in the folder containing the file.")
    steps.append(f"3. Run: `python {filename}`")

    if "tkinter" in c:
        steps.append("4. A window should open. Use the window controls.")
    elif "turtle" in c:
        steps.append("4. A drawing window should open. Wait for it to finish drawing.")
        steps.append("5. Close the window to end the program.")
    elif "input(" in c:
        steps.append("4. Follow the prompts in the terminal and type your input.")
    else:
        steps.append("4. If nothing happens, the file may only define functions used by other files.")

    return "\n".join(steps)


def _guess_python_purpose(code: str) -> str:
    """
    Purpose for documentation (not comments).
    """
    c = code.lower()
    if "from tkinter" in c or "import tkinter" in c:
        return "Creates a desktop window (GUI) using Tkinter."
    if "from turtle" in c or "import turtle" in c:
        return "Draws graphics on the screen using the Turtle library."
    if "input(" in c:
        return "Runs in the terminal and interacts with the user through input prompts."
    if "random" in c and ("randint" in c or "choice" in c):
        return "Uses random numbers to create a small simulation or game."
    return "Contains Python logic that runs when the file is executed."


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    """
    Produces:
    - commented_code (professional + accurate per code)
    - documentation (beginner-friendly)
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