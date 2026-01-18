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
            # stop skipping after a blank line
            if line.strip() == "":
                skipping = False
            continue

        out.append(line)

    cleaned = "\n".join(out).strip()
    return cleaned + ("\n" if code.endswith("\n") else "")


def _md_escape_backticks(s: str) -> str:
    return (s or "").replace("`", "\\`")


def _filename_title(file_path: str, language: str) -> str:
    base = os.path.basename(file_path) if file_path else "pasted_code"
    return f"{base} ({language})"


def _doc_sectioned(
    *,
    title: str,
    what_it_does: List[str],
    requirements: List[str],
    how_to_run: List[str],
    logic: List[str],
    code_block: str,
    examples: List[str],
    edge_cases: List[str],
) -> str:
    """
    Produces documentation in the exact structure the user requested.
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
    lines.append("## 6) Code with docstrings/comments")
    lines.append(code_block.rstrip())
    lines.append("")
    lines.append("## 7) Example input/output")
    for x in examples:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 8) Edge cases / notes")
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
    c = code.lower()
    out: List[str] = []

    if info.get("uses_tkinter"):
        out.append("Creates a simple graphical user interface (GUI) using Tkinter.")
    elif info.get("uses_turtle"):
        out.append("Draws shapes/patterns on the screen using Turtle graphics.")
    elif info.get("has_input"):
        out.append("Runs in the terminal and interacts with the user using input prompts.")
    else:
        out.append("Runs Python logic (functions, loops, calculations) when executed.")

    # add a neutral “structure” line based on detection
    fns = info.get("functions", [])
    if fns:
        out.append(f"Defines {len(fns)} function(s) that organize the logic into reusable parts.")
    if info.get("loops", 0):
        out.append(f"Uses {info.get('loops', 0)} loop(s) to repeat operations.")
    return out


def _python_requirements(info: Dict[str, Any]) -> List[str]:
    req = ["Python 3.10+ (recommended)"]
    if info.get("uses_tkinter"):
        req.append("Tkinter (usually included with standard Python on Windows/macOS)")
    if info.get("uses_turtle"):
        req.append("Turtle (included with standard Python)")
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
        lines.append("3. If nothing prints, the file may only define functions for other files to import.")
    return lines


def _python_logic(info: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append("Imports are loaded first (if any).")
    if info.get("classes"):
        lines.append("Classes define reusable structures (data + methods).")
    if info.get("functions"):
        lines.append("Functions group related steps so the code is easier to read and reuse.")
    if info.get("loops", 0):
        lines.append("Loops repeat a block of code until the loop finishes or the program exits.")
    lines.append("When run as a script, the `if __name__ == \"__main__\"` block triggers the main flow.")
    return lines


def _python_examples(info: Dict[str, Any]) -> List[str]:
    ex: List[str] = []
    if info.get("has_input"):
        ex.append("Input: user types a menu option or text at the prompt.")
        ex.append("Output: the program prints results/messages back to the terminal.")
    elif info.get("uses_turtle"):
        ex.append("Input: none (script runs immediately).")
        ex.append("Output: a Turtle window drawing appears.")
    else:
        ex.append("Input: function parameters (if imported and called).")
        ex.append("Output: return values or printed output (depending on the code).")
    return ex


def _python_edge_cases(info: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if not info.get("parse_ok", True):
        notes.append("This file has an indentation/syntax error; fix it to enable full analysis.")
    notes.append("User input must match expected formats (numbers where numbers are required).")
    notes.append("If a file depends on other files/data not present, the script may fail at runtime.")
    return notes


def _python_add_comments(code: str, file_path: str, info: Dict[str, Any]) -> str:
    """
    Comments style matching what you liked:
    - strong header
    - explain intent + actual behavior where obvious (add/remove/return/etc.)
    - no vague "handles one part"
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
    out.append("# - Comments explain what the code is doing without guessing hidden behavior.")
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
            if args:
                out.append(f"{indent}# Inputs: {args}")
            else:
                out.append(f"{indent}# Inputs: (none)")
            out.append(f"{indent}# ---------------------------------------")
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
            out.append(f"{indent}# Error handling: try this block and catch errors instead of crashing.")
            out.append(line)
            i += 1
            continue

        # return
        if re.match(r"^\s*return\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Return: send a value back to whoever called this function.")
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

    title = _python_guess_title(code_clean, file_path)
    what_it_does = _python_what_it_does(code_clean, info)
    requirements = _python_requirements(info)
    how_to_run = _python_how_to_run(file_path, info)
    logic = _python_logic(info)
    examples = _python_examples(info)
    edge = _python_edge_cases(info)

    # structured docs includes the commented code block (so docs always match the structure)
    commented_code = _python_add_comments(code_clean, file_path, info)

    parse_warning = []
    if not info.get("parse_ok", True):
        parse_warning.append(f"⚠ Parse issue detected: {info.get('parse_error')}")

    # include key metrics inside logic or notes (kept clean)
    edge.append(f"Lines of code (non-empty): {loc}")
    edge.append(f"Functions detected: {len(info.get('functions', []))}")
    edge.append(f"Classes detected: {len(info.get('classes', []))}")
    edge.append(f"Loops detected: {info.get('loops', 0)}")
    edge.extend(parse_warning)

    doc = _doc_sectioned(
        title=f"{title}",
        what_it_does=what_it_does,
        requirements=requirements,
        how_to_run=how_to_run,
        logic=logic,
        code_block=f"```python\n{commented_code.rstrip()}\n```",
        examples=examples,
        edge_cases=edge,
    )

    return {"commented_code": commented_code, "documentation": doc}


# ============================================================
# HTML (Professional comments + structured docs)
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
        if s.startswith("<html"):
            add_once("html", "<!-- <html>: root element of the page -->")
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: metadata + links to CSS/JS -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown in the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: visible page content -->")
        if "<link" in s and "stylesheet" in s:
            add_once("csslink", "<!-- <link rel='stylesheet'>: attaches a CSS file -->")
        if s.startswith("<script"):
            add_once("script", "<!-- <script>: runs JavaScript on the page -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _html_docs(code: str, file_path: str) -> str:
    title = "HTML Page"
    what_it_does = [
        "Defines the structure and content of a web page using HTML elements.",
    ]
    requirements = [
        "A web browser (Chrome, Edge, Firefox, Safari)",
    ]
    how_to_run = [
        "1. Save the file with a `.html` extension.",
        "2. Double-click the file to open it in your browser.",
        "3. If the page links to CSS/JS files, keep them in the correct paths.",
    ]
    logic = [
        "The browser reads HTML top-to-bottom and builds the page structure (DOM).",
        "Elements inside `<head>` configure the page, while `<body>` contains visible content.",
    ]
    examples = [
        "Input: user clicks buttons/links on the page.",
        "Output: the browser shows updated content or navigates to another page (depending on the HTML/JS).",
    ]
    edge = [
        "Broken file paths in `<link>` or `<script>` tags will cause missing styles/behavior.",
        "Some HTML features behave differently across browsers if very old.",
    ]

    return _doc_sectioned(
        title=_filename_title(file_path, "html"),
        what_it_does=what_it_does,
        requirements=requirements,
        how_to_run=how_to_run,
        logic=logic,
        code_block=f"```html\n{_comment_html(code, file_path).rstrip()}\n```",
        examples=examples,
        edge_cases=edge,
    )


# ============================================================
# CSS (Professional comments + structured docs)
# ============================================================

def _explain_css_selector(selector: str) -> str:
    sel = selector.strip()
    if sel.startswith("."):
        return f"Targets elements with class `{sel[1:]}`."
    if sel.startswith("#"):
        return f"Targets the element with id `{sel[1:]}`."
    return f"Targets all `{sel}` elements."


def _comment_css(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    text = code.strip()

    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional beginner-friendly comments */")
    out.append("/* ======================================= */")
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("/* CSS controls layout, colors, spacing, and fonts. */")
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

        out.append(f"/* { _explain_css_selector(selector) } */")
        out.append(f"{selector} {{")
        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* spacing between items */")
            elif t.startswith("background"):
                out.append(f"  {t} /* background styling */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font-family"):
                out.append(f"  {t} /* font stack */")
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


def _css_docs(code: str, file_path: str) -> str:
    title = "CSS Stylesheet"
    what_it_does = [
        "Defines how HTML elements should look (colors, layout, spacing, typography).",
    ]
    requirements = [
        "A web browser (CSS is applied by the browser).",
        "An HTML file that links this CSS (via `<link rel='stylesheet' ...>`).",
    ]
    how_to_run = [
        "1. Ensure the CSS file is linked in your HTML `<head>`.",
        "2. Open the HTML file in a browser.",
        "3. Refresh the page after changes.",
    ]
    logic = [
        "Selectors choose which elements to style (e.g., `body`, `.class`, `#id`).",
        "Each `{ property: value; }` rule changes layout/appearance of matching elements.",
    ]
    examples = [
        "Input: none directly (styles apply automatically).",
        "Output: the page appearance changes in the browser.",
    ]
    edge = [
        "If the CSS file path is wrong in the HTML, styles won’t load.",
        "Some CSS properties depend on browser support.",
    ]

    return _doc_sectioned(
        title=_filename_title(file_path, "css"),
        what_it_does=what_it_does,
        requirements=requirements,
        how_to_run=how_to_run,
        logic=logic,
        code_block=f"```css\n{_comment_css(code, file_path).rstrip()}\n```",
        examples=examples,
        edge_cases=edge,
    )


# ============================================================
# JavaScript (Docs structured, comments kept simple as you wanted)
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


def _js_docs(code: str, file_path: str) -> str:
    title = "JavaScript File"
    what_it_does = [
        "Adds behavior and logic (functions, events, calculations) to a web page or Node.js script.",
    ]
    requirements = [
        "If used in a website: a browser + an HTML file that includes this script.",
        "If used in Node.js: Node.js installed.",
    ]
    how_to_run = [
        "Website:",
        "1. Link the JS file in HTML using `<script src='file.js'></script>`.",
        "2. Open the HTML file in a browser and check the console.",
        "",
        "Node.js:",
        "1. Open a terminal in the file folder.",
        "2. Run: `node file.js` (if it is a standalone script).",
    ]
    logic = [
        "Functions group reusable logic.",
        "Event handlers (e.g., click) run code when the user interacts.",
        "Return values provide results back to the caller.",
    ]
    examples = [
        "Input: user clicks a button or calls a function with a value.",
        "Output: the page updates, an alert appears, or a value is returned.",
    ]
    edge = [
        "If JS is not linked in HTML, nothing will run.",
        "Runtime errors appear in the browser console or terminal.",
    ]

    return _doc_sectioned(
        title=_filename_title(file_path, "javascript"),
        what_it_does=what_it_does,
        requirements=requirements,
        how_to_run=how_to_run,
        logic=logic,
        code_block=f"```javascript\n{_comment_js(code, file_path).rstrip()}\n```",
        examples=examples,
        edge_cases=edge,
    )


# ============================================================
# Java (Professional comments + structured docs)
# ============================================================

def _comment_java(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("// Java code is organized into classes containing methods.")
    out.append("")

    for line in lines:
        s = line.strip()

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: a container that groups methods and data.")
            out.append(line)
            continue

        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): program entry point (starts execution).")
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
            out.append("// Return: send a result back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _java_docs(code: str, file_path: str) -> str:
    title = "Java Class File"
    what_it_does = [
        "Defines a Java class and its methods for a Java application.",
    ]
    requirements = [
        "Java JDK installed (e.g., Java 17+ recommended).",
        "A terminal/command prompt.",
    ]
    how_to_run = [
        "1. Open a terminal in the folder containing the `.java` file(s).",
        "2. Compile: `javac FileName.java`",
        "3. Run (if it contains `main`): `java FileName`",
    ]
    logic = [
        "Classes group methods (functions) together.",
        "`main()` is where the program starts.",
        "Methods can return values to their callers using `return`.",
    ]
    examples = [
        "Input: command-line execution of the compiled class.",
        "Output: text printed to the console (if `System.out.println` is used).",
    ]
    edge = [
        "If the class name and filename do not match, Java compilation fails.",
        "If there is no `main` method, the class cannot be run directly (only imported/used).",
    ]

    return _doc_sectioned(
        title=_filename_title(file_path, "java"),
        what_it_does=what_it_does,
        requirements=requirements,
        how_to_run=how_to_run,
        logic=logic,
        code_block=f"```java\n{_comment_java(code, file_path).rstrip()}\n```",
        examples=examples,
        edge_cases=edge,
    )


# ============================================================
# Public API: generate_simple_docs (HTML/CSS/JS/Java)
# ============================================================

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")

    if language == "html":
        commented = _comment_html(code_clean, file_path)
        documentation = _html_docs(code_clean, file_path)
    elif language == "css":
        commented = _comment_css(code_clean, file_path)
        documentation = _css_docs(code_clean, file_path)
    elif language == "javascript":
        commented = _comment_js(code_clean, file_path)
        documentation = _js_docs(code_clean, file_path)
    elif language == "java":
        commented = _comment_java(code_clean, file_path)
        documentation = _java_docs(code_clean, file_path)
    else:
        # fallback
        commented = code_clean.strip() + "\n"
        documentation = _doc_sectioned(
            title=_filename_title(file_path, language or "unknown"),
            what_it_does=["Part of a software project."],
            requirements=["Depends on the project setup."],
            how_to_run=["Run steps depend on the project."],
            logic=["Logic depends on the file contents."],
            code_block=f"```text\n{commented.rstrip()}\n```",
            examples=["Input/output depends on the program."],
            edge_cases=["No extra notes."],
        )

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation}