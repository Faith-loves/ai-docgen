from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# Helpers (general)
# ============================================================

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

    lines = code.splitlines()
    buf: List[str] = []
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
    return out if len(out) >= 20 else ""


# ============================================================
# Remove old auto comment blocks (prevents duplication forever)
# ============================================================

def _clean_existing_auto_headers(code: str) -> str:
    """
    Remove our previous repeated auto-comment blocks so we don't stack them forever.
    """
    lines = code.splitlines()
    cleaned: List[str] = []

    skipping = False
    for line in lines:
        if "Beginner-friendly comments (auto-added)" in line:
            skipping = True
            continue
        if skipping and line.strip() == "":
            skipping = False
            continue
        if "This file was automatically commented to help beginners" in line:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip() + ("\n" if code.endswith("\n") else "")


# ============================================================
# Python analysis (safe)
# ============================================================

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


# ============================================================
# Better Python purpose detection (real description)
# ============================================================

def _guess_python_program_type(code: str) -> str:
    c = code.lower()

    if "tkinter" in c:
        if "dice" in c or (("randint" in c) and (".png" in c)):
            return (
                "This Python program creates a dice rolling simulator with a Tkinter window. "
                "When the user clicks a button, it randomly chooses a dice number and shows the matching image."
            )
        return (
            "This Python program builds a graphical window (GUI) using Tkinter so the user can interact with it."
        )

    if "turtle" in c:
        if "heart" in c:
            return (
                "This Python program uses Turtle graphics to draw a heart-like shape by calculating points "
                "with math formulas and drawing lines between them."
            )
        return "This Python program uses Turtle graphics to draw shapes/patterns on the screen."

    if ("todo" in c and "task" in c) or ("to-do" in c) or ("to do" in c):
        if "input(" in c:
            return (
                "This Python program is a simple To-Do List app in the terminal. "
                "It lets the user view tasks, add new tasks, and remove tasks using a menu."
            )

    if "input(" in c:
        return (
            "This Python program runs in the terminal, asks the user questions, and performs actions based on the answers."
        )

    return (
        "This Python file contains code that performs tasks when the script runs or when its functions are called."
    )


def _python_how_to_run(code: str, file_path: str) -> str:
    filename = os.path.basename(file_path) if file_path else "main.py"
    c = code.lower()

    steps: List[str] = []
    steps.append("### Option A: Run with Python (recommended)")
    steps.append("1. Make sure Python is installed (Python 3).")
    steps.append("2. Open a terminal in the folder containing the file.")
    steps.append(f"3. Run: `python {filename}`")

    if "tkinter" in c:
        steps.append("4. A window will open. Use the buttons/fields to interact with the app.")
    elif "turtle" in c:
        steps.append("4. A drawing window will open. Wait for the drawing to finish.")
        steps.append("5. Close the window to stop the program.")
    else:
        if "input(" in c:
            steps.append("4. Follow the menu/prompts and type your choices in the terminal.")
        else:
            steps.append("4. If nothing prints, the file may only contain helper functions used by another file.")

    return "\n".join(steps)


# ============================================================
# NEW: Function meaning detector (so comments are not generic)
# ============================================================

def _explain_function_name(fn_name: str) -> str:
    """
    Give a simple, beginner-friendly explanation based on common function names.
    """
    n = (fn_name or "").lower().strip()

    # Todo app patterns
    if n in ("show_tasks", "show_task", "list_tasks", "display_tasks"):
        return "Shows the current tasks in the to-do list (prints them out)."
    if n in ("add_task", "create_task", "insert_task"):
        return "Adds a new task to the to-do list."
    if n in ("remove_task", "delete_task", "pop_task"):
        return "Removes one task from the to-do list using its number/index."
    if n in ("main", "run", "start"):
        return "Starts the program and keeps the menu running until the user exits."

    # Generic patterns
    if n.startswith("get_"):
        return "Gets or collects some information and returns it."
    if n.startswith("set_"):
        return "Updates or changes a value in the program."
    if "calc" in n or "compute" in n:
        return "Calculates something and returns the result."
    if "print" in n or "display" in n or "show" in n:
        return "Shows information to the user."
    if "load" in n:
        return "Loads data (for example from a file) into the program."
    if "save" in n:
        return "Saves data (for example into a file)."

    return "Does one specific job in the program."


# ============================================================
# Better Python commenting (minimal + meaningful)
# ============================================================

def _add_python_comments(code: str) -> str:
    """
    Beginner-friendly comments (not spam):
    - One header at top
    - Explains important top-level variables (lists/dicts)
    - Specific comment before each function (based on function name)
    - Comment for loops and menu patterns
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Beginner-friendly comments (auto-added)")
    out.append("# =======================================")
    out.append("")
    out.append("# This file was automatically commented to help beginners understand it.")
    out.append("")

    in_imports = False

    for line in lines:
        stripped = line.strip()

        # Imports
        if stripped.startswith("import ") or stripped.startswith("from "):
            if not in_imports:
                out.append("# ✅ Imports: these bring extra tools/libraries into the program.")
                in_imports = True
            out.append(line)
            continue
        else:
            in_imports = False

        # Explain a simple global list/dict at top-level (very common for beginners)
        # Example: todo_list = []
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*\[\s*\]\s*$", line) and (line.startswith(" ") is False):
            var = line.split("=")[0].strip()
            out.append(f"# ✅ `{var}` is an empty list. The program will store items inside it.")
            out.append(line)
            continue

        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*\{\s*\}\s*$", line) and (line.startswith(" ") is False):
            var = line.split("=")[0].strip()
            out.append(f"# ✅ `{var}` is an empty dictionary (key/value storage).")
            out.append(line)
            continue

        # Function defs
        m = re.match(r"^(\s*)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
        if m:
            indent = m.group(1)
            fn_name = m.group(2)
            expl = _explain_function_name(fn_name)

            out.append("")
            out.append(f"{indent}# ✅ Function: {fn_name}()")
            out.append(f"{indent}# {expl}")
            out.append(line)
            continue

        # Loops
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            if "while True" in line.replace(" ", ""):
                out.append(f"{indent}# ✅ Main loop: keeps the program running until the user chooses to exit.")
            else:
                out.append(f"{indent}# ✅ Loop: repeats the following block multiple times.")
            out.append(line)
            continue

        # Menu printing pattern
        if stripped.startswith("print(") and "choose an option" in stripped.lower():
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# ✅ Menu: show the user what they can do next.")
            out.append(line)
            continue

        # input() explanation
        if "input(" in line:
            indent = re.match(r"^\s*", line).group(0)
            if "choice" in stripped.lower():
                out.append(f"{indent}# ✅ Ask the user to pick a menu option.")
            else:
                out.append(f"{indent}# ✅ Ask the user to type something into the terminal.")
            out.append(line)
            continue

        # Slicing explanation
        if "[:3]" in line.replace(" ", ""):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# ✅ Slicing: `list[:3]` means “take the first 3 items”.")
            out.append(line)
            continue

        # Combining lists explanation
        if re.search(r"\s=\s.*\+\s.*", line) and "list" in line.lower():
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# ✅ Combine lists: `a + b` joins two lists together.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# ============================================================
# Main generator: Python
# ============================================================

def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")

    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    top_desc = _first_meaningful_comment_or_doc(code_clean)
    purpose_guess = _guess_python_program_type(code_clean)

    purpose_lines: List[str] = []
    if top_desc:
        purpose_lines.append(top_desc.splitlines()[0].strip())
        if len(top_desc) > 120:
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
            "Even with errors, we still generate beginner-friendly docs and light comments.\n"
        )

    doc_lines: List[str] = []
    doc_lines.append(f"# File Documentation - `{os.path.basename(file_path)}`")
    doc_lines.append("")

    if parse_note:
        doc_lines.append(parse_note)
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
            doc_lines.append(f"- `{fn}()` – {_explain_function_name(fn)}")
        doc_lines.append("")

    doc_lines.append("## Inputs / Outputs")
    if "input(" in code_clean.lower():
        doc_lines.append("- **Input:** the user types input in the terminal (menu choices, task text, etc.).")
    else:
        doc_lines.append("- **Input:** values passed into functions, or events like clicks (for GUI programs).")
    doc_lines.append("- **Output:** printed text, returned values, or a window/drawing on screen.")
    doc_lines.append("")

    doc_lines.append("## How it fits into a larger project")
    doc_lines.append("- This file can run alone as a small program.")
    doc_lines.append("- It can also be imported so other Python files can reuse its functions.")
    doc_lines.append("")

    doc_lines.append("## How to run (step-by-step)")
    doc_lines.append(how_to)
    doc_lines.append("")

    doc_lines.append("## Edge cases / important notes")
    doc_lines.append("- If the user enters the wrong type (example: letters instead of numbers), the program may show an error message.")
    doc_lines.append("- If you get an error, read the line number in the error message and check spacing/typos.")
    doc_lines.append("")

    documentation = "\n".join(doc_lines).strip() + "\n"
    commented_code = _add_python_comments(code_clean)

    return {"commented_code": commented_code, "documentation": documentation}


# ============================================================
# Simple docs for JS/HTML/CSS/Java
# ============================================================

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")
    loc = _count_nonempty_lines(code_clean)
    filename = os.path.basename(file_path) if file_path else "pasted_code"

    purpose = "This file is part of a software project."

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
        how_to_lines.append("2. Open the HTML file in a browser, OR use a local server.")
        how_to_lines.append("3. CSS applies automatically if linked in the HTML.")
        how_to_lines.append("4. JavaScript runs automatically if linked in the HTML.")
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
        f"- **Inputs:** user actions (clicks), function parameters, or data in the page.\n"
        f"- **Outputs:** updated page content/styles, console output, or returned values.\n\n"
        f"## How it fits into a larger project\n"
        f"- This file works together with other files (HTML/CSS/JS) or other Java classes.\n\n"
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


def _comment_js(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("/* =======================================")
    out.append("   Beginner-friendly JS notes (auto-added)")
    out.append("   ======================================= */")
    out.append("")
    out.append(code.strip())
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