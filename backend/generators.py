from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Shared helpers
# ============================================================

AUTO_MARKERS = [
    "Beginner-friendly comments (auto-added)",
    "Beginner-friendly notes (auto-added)",
    "Beginner-friendly CSS notes (auto-added)",
    "Beginner-friendly JS notes (auto-added)",
    "Beginner-friendly Java notes (auto-added)",
    "Professional beginner-friendly comments",
    "Professional beginner-friendly notes",
    "Professional beginner-friendly CSS notes",
    "Professional beginner-friendly JS notes",
    "Professional beginner-friendly Java notes",
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
            if line.strip() == "":
                skipping = False
            continue

        out.append(line)

    cleaned = "\n".join(out).strip()
    return cleaned + ("\n" if code.endswith("\n") else "")


def _filename_title(file_path: str, language: str) -> str:
    base = os.path.basename(file_path) if file_path else "pasted_code"
    return f"{base} ({language})"


def _doc_sectioned_no_code(
    *,
    title: str,
    what_it_does: List[str],
    requirements: List[str],
    how_to_run: List[str],
    logic: List[str],
    examples: List[str],
    edge_cases: List[str],
) -> str:
    """
    Docs structure WITHOUT code section (as requested).
    """
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 2) What it does")
    for x in what_it_does:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 3) Requirements")
    for x in requirements:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 4) How to run")
    for x in how_to_run:
        lines.append(x)
    lines.append("")
    lines.append("## 5) Explanation of logic")
    for x in logic:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 6) Example input/output")
    for x in examples:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 7) Edge cases / notes")
    for x in edge_cases:
        lines.append(f"- {x}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


# ============================================================
# Python (Professional comments + structured docs)
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
        "has_input": "input(" in code.lower(),
        "has_print": "print(" in code.lower(),
        "uses_tkinter": ("tkinter" in code.lower() or "from tkinter" in code.lower()),
        "uses_turtle": ("turtle" in code.lower() or "from turtle" in code.lower()),
    }

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


def _python_guess_title(code: str, file_path: str) -> str:
    c = code.lower()
    name = os.path.basename(file_path) if file_path else "pasted_code"
    if "todo" in name.lower() or ("task" in c and "add" in c and "remove" in c):
        return "To-Do List (CLI)"
    if "turtle" in c:
        return "Turtle Drawing Program"
    if "tkinter" in c:
        return "Tkinter GUI Program"
    if "game" in c and "guess" in c:
        return "Small Guessing Game"
    return "Python Script"


def _python_what_it_does(code: str, info: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if info.get("uses_tkinter"):
        out.append("Creates a graphical interface using Tkinter.")
    elif info.get("uses_turtle"):
        out.append("Draws graphics on the screen using Turtle.")
    elif info.get("has_input"):
        out.append("Runs in the terminal and interacts with the user using input prompts.")
    else:
        out.append("Runs Python logic (functions, loops, calculations) when executed.")

    if info.get("functions"):
        out.append(f"Defines {len(info.get('functions', []))} function(s) to organize the program.")
    if info.get("classes"):
        out.append(f"Defines {len(info.get('classes', []))} class(es) to structure data/behavior.")
    if info.get("loops", 0):
        out.append(f"Uses {info.get('loops', 0)} loop(s) to repeat operations.")
    return out


def _python_requirements(info: Dict[str, Any]) -> List[str]:
    req = ["Python 3.10+ (recommended)"]
    if info.get("uses_tkinter"):
        req.append("Tkinter (usually included with Python)")
    if info.get("uses_turtle"):
        req.append("Turtle (included with Python)")
    return req


def _python_how_to_run(file_path: str, info: Dict[str, Any]) -> List[str]:
    fname = os.path.basename(file_path) if file_path else "main.py"
    lines: List[str] = []
    lines.append("1. Open a terminal in the folder containing the file.")
    lines.append(f"2. Run: `python {fname}`")
    if info.get("uses_turtle") or info.get("uses_tkinter"):
        lines.append("3. A window will open. Close it to end the program.")
    elif info.get("has_input"):
        lines.append("3. Follow the prompts shown in the terminal.")
    else:
        lines.append("3. If nothing prints, the file may be intended to be imported by other files.")
    return lines


def _python_logic(info: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append("Imports are loaded first (if any).")
    if info.get("classes"):
        lines.append("Classes define reusable structures (data + methods).")
    if info.get("functions"):
        lines.append("Functions group related steps into reusable blocks.")
    if info.get("loops", 0):
        lines.append("Loops repeat blocks of code until the loop ends or the program exits.")
    lines.append("If present, `if __name__ == \"__main__\"` runs the script entry point.")
    return lines


def _python_examples(info: Dict[str, Any]) -> List[str]:
    if info.get("has_input"):
        return [
            "Input: user types values at prompts.",
            "Output: program prints results/messages to the terminal.",
        ]
    if info.get("uses_turtle"):
        return [
            "Input: none (runs automatically).",
            "Output: a drawing window appears showing the graphics.",
        ]
    return [
        "Input: function arguments (if imported and called).",
        "Output: return values or printed output depending on the code.",
    ]


def _python_edge_cases(info: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if not info.get("parse_ok", True):
        notes.append("⚠ The file has a syntax/indentation issue; fix it to enable deeper analysis.")
        notes.append(f"Parse error: {info.get('parse_error')}")
    notes.append("User input must match expected types (numbers where numbers are required).")
    notes.append("External files must exist if the script tries to read them.")
    return notes


def _python_add_comments(code: str, file_path: str) -> str:
    """
    High-quality Python comments:
    - Explains what the code is doing
    - Avoids vague repeated text
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")
    out.append("# Notes:")
    out.append("# - Comments explain what the code does based on what is visible here.")
    out.append("")

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        # imports
        if s.startswith("import ") or s.startswith("from "):
            if not any("Imports:" in x for x in out[-6:]):
                out.append("# Imports: libraries used by this file.")
            out.append(line)
            i += 1
            continue

        # class
        m_class = re.match(r"^(\s*)class\s+([A-Za-z_]\w*)\b", line)
        if m_class:
            indent = m_class.group(1)
            cname = m_class.group(2)
            out.append("")
            out.append(f"{indent}# Class: {cname} — groups related data and methods.")
            out.append(line)
            i += 1
            continue

        # function
        m_fn = re.match(r"^(\s*)def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:", line)
        if m_fn:
            indent = m_fn.group(1)
            fname = m_fn.group(2)
            args = m_fn.group(3).strip()

            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# Function: {fname}()")
            out.append(f"{indent}# ---------------------------------------")

            if args:
                out.append(f"{indent}# Inputs: {args}")
            else:
                out.append(f"{indent}# Inputs: (none)")

            out.append(line)
            i += 1
            continue

        # loops
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below.")
            out.append(line)
            i += 1
            continue

        # try
        if re.match(r"^\s*try\s*:\s*$", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Error handling: prevents crashing if something goes wrong.")
            out.append(line)
            i += 1
            continue

        # return
        if re.match(r"^\s*return\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Return: send a value back to the caller.")
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python_code(code_clean)

    title = _python_guess_title(code_clean, file_path)
    doc = _doc_sectioned_no_code(
        title=title,
        what_it_does=_python_what_it_does(code_clean, info),
        requirements=_python_requirements(info),
        how_to_run=_python_how_to_run(file_path, info),
        logic=_python_logic(info),
        examples=_python_examples(info),
        edge_cases=_python_edge_cases(info),
    )

    commented_code = _python_add_comments(code_clean, file_path)
    return {"commented_code": commented_code, "documentation": doc}


# ============================================================
# HTML
# ============================================================

def _comment_html(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional beginner-friendly comments -->")
    out.append("<!-- ======================================= -->")
    out.append(f"<!-- File: {os.path.basename(file_path) if file_path else 'pasted_code'} -->")
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
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: metadata, title, CSS links -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: visible page content -->")
        if "<script" in s:
            add_once("script", "<!-- <script>: JavaScript for page behavior -->")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _html_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "html"),
        what_it_does=["Defines the structure and content of a webpage."],
        requirements=["A web browser (Chrome/Edge/Firefox/Safari)."],
        how_to_run=[
            "1. Save the file as `.html`.",
            "2. Double-click to open in your browser.",
        ],
        logic=[
            "The browser parses HTML and builds the page structure (DOM).",
            "`<head>` configures the page and `<body>` contains visible content.",
        ],
        examples=[
            "Input: user clicks buttons/links on the page.",
            "Output: browser shows content or runs JavaScript actions.",
        ],
        edge_cases=[
            "Incorrect file paths in `<link>` or `<script>` can break styling or functionality.",
        ],
    )


# ============================================================
# CSS
# ============================================================

def _comment_css(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional beginner-friendly comments */")
    out.append("/* ======================================= */")
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("/* CSS controls colors, layout, spacing, and fonts. */")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


def _css_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "css"),
        what_it_does=["Styles a webpage by changing layout, colors, spacing, and fonts."],
        requirements=["A browser + an HTML file that links this CSS with `<link rel='stylesheet'>`."],
        how_to_run=[
            "1. Link the CSS file inside the HTML `<head>`.",
            "2. Open the HTML in a browser and refresh after changes.",
        ],
        logic=[
            "Selectors choose which elements to style (e.g., `body`, `.class`, `#id`).",
            "Properties define how selected elements should look.",
        ],
        examples=[
            "Input: none directly.",
            "Output: the webpage appearance changes.",
        ],
        edge_cases=[
            "If the CSS file path is wrong in HTML, styles won’t load.",
        ],
    )


# ============================================================
# Java
# ============================================================

def _comment_java(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


def _java_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines a Java class and methods for a Java program."],
        requirements=["Java JDK installed (Java 17+ recommended)."],
        how_to_run=[
            "1. Open a terminal inside the folder containing the `.java` file.",
            "2. Compile: `javac FileName.java`",
            "3. Run (if it has main): `java FileName`",
        ],
        logic=[
            "A Java file usually contains a class.",
            "`main()` is the program entry point (starts execution).",
        ],
        examples=[
            "Input: running the program in terminal.",
            "Output: console messages printed with `System.out.println`.",
        ],
        edge_cases=[
            "Class name must match the filename for Java compilation to succeed.",
        ],
    )


# ============================================================
# JavaScript (commenting kept simple like you wanted)
# ============================================================

def _comment_js(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    out: List[str] = []
    out.append("/* =======================================")
    out.append("   Beginner-friendly JS notes (auto-added)")
    out.append("   ======================================= */")
    out.append("")
    out.append(code.strip())
    return "\n".join(out).rstrip() + "\n"


def _js_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "javascript"),
        what_it_does=["Adds interactive behavior and logic to a webpage (or runs in Node.js)."],
        requirements=["Browser (web) OR Node.js installed (backend scripts)."],
        how_to_run=[
            "Website:",
            "1. Link the file in HTML using `<script src='file.js'></script>`.",
            "2. Open the HTML file in a browser and check the console.",
            "",
            "Node.js:",
            "1. Run: `node file.js`",
        ],
        logic=[
            "Functions group reusable logic.",
            "Events run code when the user interacts (clicks, typing).",
        ],
        examples=[
            "Input: user clicks a button or calls a function.",
            "Output: alert/console output/page updates depending on code.",
        ],
        edge_cases=[
            "If not linked properly in HTML, JavaScript will not run.",
        ],
    )


# ============================================================
# Public API: generate_simple_docs (HTML/CSS/JS/Java)
# ============================================================

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")

    if language == "html":
        commented = _comment_html(code_clean, file_path)
        documentation = _html_docs(file_path)
    elif language == "css":
        commented = _comment_css(code_clean, file_path)
        documentation = _css_docs(file_path)
    elif language == "javascript":
        commented = _comment_js(code_clean, file_path)
        documentation = _js_docs(file_path)
    elif language == "java":
        commented = _comment_java(code_clean, file_path)
        documentation = _java_docs(file_path)
    else:
        commented = code_clean.strip() + "\n"
        documentation = _doc_sectioned_no_code(
            title=_filename_title(file_path, language or "unknown"),
            what_it_does=["Part of a software project."],
            requirements=["Depends on the project setup."],
            how_to_run=["Run steps depend on the project."],
            logic=["Logic depends on the file contents."],
            examples=["Input/output depends on the program."],
            edge_cases=["No extra notes."],
        )

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation}