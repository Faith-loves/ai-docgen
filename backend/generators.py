from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# Shared helpers
# ============================================================

AUTO_MARKERS = [
    # Old headers you want removed
    "Professional beginner-friendly comments",
    "Beginner-friendly comments (auto-added)",
    "Beginner-friendly notes (auto-added)",
    "Beginner-friendly CSS notes (auto-added)",
    "Beginner-friendly JS notes (auto-added)",
    "Beginner-friendly Java notes (auto-added)",
    "Professional beginner-friendly notes",
    "Professional beginner-friendly CSS notes",
    "Professional beginner-friendly JS notes",
    "Professional beginner-friendly Java notes",
]


def _count_nonempty_lines(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.strip())


def _clean_existing_auto_headers(code: str) -> str:
    """
    Removes previously generated header blocks so they don't stack.
    We keep it simple: if we detect marker lines, we skip until a blank line.
    """
    lines = code.splitlines()
    out: List[str] = []
    skipping = False

    for line in lines:
        if any(m.lower() in line.lower() for m in AUTO_MARKERS):
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
    Docs structure WITHOUT code section (as you requested).
    """
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## What it does")
    for x in what_it_does:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Requirements")
    for x in requirements:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## How to run")
    for x in how_to_run:
        lines.append(x)
    lines.append("")
    lines.append("## Explanation of logic")
    for x in logic:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Example input/output")
    for x in examples:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Edge cases / notes")
    for x in edge_cases:
        lines.append(f"- {x}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


# ============================================================
# Python: comment "confusing lines" only
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _python_summarize(code: str) -> Dict[str, Any]:
    tree, err = _safe_parse_python(code)
    info: Dict[str, Any] = {
        "parse_ok": tree is not None,
        "parse_error": err,
        "imports": [],
        "functions": [],  # [{"name":..., "args":[...], "returns":bool}]
        "classes": [],
        "has_input": "input(" in code.lower(),
        "has_print": "print(" in code.lower(),
        "loops": 0,
    }

    if not tree:
        info["imports"] = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", code, flags=re.M)
        info["classes"] = re.findall(r"^\s*class\s+([a-zA-Z_]\w*)", code, flags=re.M)
        info["loops"] = len(re.findall(r"\b(for|while)\b", code))
        fn_names = re.findall(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(", code, flags=re.M)
        info["functions"] = [{"name": n, "args": [], "returns": True} for n in fn_names]
        return info

    imports: List[str] = []
    classes: List[str] = []
    functions: List[Dict[str, Any]] = []
    loops = 0

    class V(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> Any:
            for n in node.names:
                imports.append(n.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
            if node.module:
                imports.append(node.module)

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            classes.append(node.name)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            args = [a.arg for a in node.args.args]
            returns = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
            functions.append({"name": node.name, "args": args, "returns": returns})
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
    info["imports"] = sorted(set(imports))
    info["classes"] = classes
    info["functions"] = functions
    info["loops"] = loops
    return info


def _py_should_comment_line(s: str) -> bool:
    """
    Decide which lines beginners usually struggle with.
    We avoid commenting every simple line.
    """
    if not s:
        return False
    if s.startswith("#"):
        return False

    confusing_tokens = [
        "lambda ",
        " with ",
        " as ",
        "try:",
        "except",
        "raise ",
        "yield ",
        "async ",
        "await ",
        "import ",
        "from ",
        "return ",
        "for ",
        "while ",
        "if ",
        "elif ",
        "else:",
        "class ",
        "def ",
    ]
    if any(s.startswith(t.strip()) for t in confusing_tokens):
        return True

    # patterns that confuse beginners
    if "{" in s and "}" in s:  # dict literals
        return True
    if "[" in s and "]" in s and " for " in s:  # list comprehension
        return True
    if "sum(" in s or "sorted(" in s or "max(" in s or "min(" in s:
        return True
    if ".get(" in s or ".append(" in s or ".pop(" in s:
        return True
    if "int(" in s or "float(" in s or "str(" in s:
        return True
    if "__name__" in s:
        return True

    return False


def _py_comment_for_line(s: str) -> Optional[str]:
    """
    Safe explanations based on visible syntax.
    No guessing business logic.
    """
    st = s.strip()

    if st.startswith("import ") or st.startswith("from "):
        return "# Bring in code from another library/file."

    if st.startswith("class "):
        return "# Define a class (a blueprint for creating objects)."

    if st.startswith("def "):
        return "# Define a function (a reusable block of steps)."

    if st.startswith("if __name__"):
        return "# Run the code below only when this file is executed directly."

    if st.startswith("for "):
        return "# Loop through items one by one."

    if st.startswith("while "):
        return "# Keep looping while the condition stays true."

    if st.startswith("try:"):
        return "# Try running the code below; if it fails, handle it in `except`."

    if st.startswith("except"):
        return "# Handle an error so the program does not crash."

    if st.startswith("return "):
        return "# Send a result back to whoever called this function."

    if "lambda " in st:
        return "# A small one-line function (lambda) used as a quick helper."

    if " with " in st and ":" in st:
        return "# Open/use something safely; it will close/clean up automatically."

    if "int(" in st or "float(" in st:
        return "# Convert a value into a number type."

    if ".append(" in st:
        return "# Add a new item to a list."

    if ".pop(" in st:
        return "# Remove and return an item from a list."

    if ".get(" in st:
        return "# Read a value from a dictionary safely (with a default if missing)."

    if "sum(" in st:
        return "# Add up many numbers to get a total."

    if "sorted(" in st:
        return "# Sort items into a new ordered list."

    if "[" in st and "]" in st and " for " in st:
        return "# Build a new list in one line (list comprehension)."

    if "{" in st and "}" in st:
        return "# Create a dictionary (key → value mapping)."

    return None


def _python_add_comments(code: str, file_path: str, info: Dict[str, Any]) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    # No annoying headers. Just a simple file label (optional).
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        s = line.strip()
        if _py_should_comment_line(s):
            c = _py_comment_for_line(s)
            if c:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}{c}")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _python_docs(code: str, file_path: str, info: Dict[str, Any]) -> str:
    what: List[str] = []
    if info.get("has_input"):
        what.append("Runs in the terminal and asks the user for input.")
    else:
        what.append("Defines functions/classes that run when executed or imported.")
    if info.get("functions"):
        what.append(f"Contains {len(info['functions'])} function(s).")
    if info.get("classes"):
        what.append(f"Contains {len(info['classes'])} class(es).")

    requirements = ["Python 3 installed"]

    how = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'main.py'}`",
        "3. Follow any prompts (if the code asks for input).",
    ]

    logic = [
        "Python reads the file top-to-bottom.",
        "Imports load first, then functions/classes are defined.",
        "If present, the `if __name__ == '__main__'` block runs last.",
    ]
    if info.get("loops"):
        logic.append("Loops repeat parts of the code multiple times.")

    examples = [
        "Input: values typed by the user (if input is used) or function arguments.",
        "Output: printed text, saved files, or returned values depending on the code.",
    ]

    edge = []
    if not info.get("parse_ok"):
        edge.append(f"Syntax/indentation error: {info.get('parse_error')}")
    edge.append("If the code converts strings to numbers, invalid input can cause errors.")
    edge.append("If the code reads files, missing files will cause errors unless handled.")

    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "python"),
        what_it_does=what,
        requirements=requirements,
        how_to_run=how,
        logic=logic,
        examples=examples,
        edge_cases=edge,
    )


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")
    info = _python_summarize(code_clean)
    documentation = _python_docs(code_clean, file_path, info)
    commented_code = _python_add_comments(code_clean, file_path, info)
    return {"commented_code": commented_code, "documentation": documentation}


# ============================================================
# JavaScript: ALWAYS produce valid JS comments, line-aware
# ============================================================

_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\((.*?)\)")
_JS_ARROW_RE = re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>")
_JS_EVENT_RE = re.compile(r"\.addEventListener\s*\(")

def _js_should_comment(s: str) -> bool:
    if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return False

    starts = (
        "import ", "export ",
        "function ", "async function ",
        "class ",
        "if (", "for (", "while (",
        "try", "catch",
        "return ",
        "const ", "let ", "var ",
    )
    if any(s.startswith(x) for x in starts):
        return True

    if "await " in s or "fetch(" in s:
        return True
    if "document." in s or "querySelector" in s or "getElementById" in s or "createElement" in s:
        return True
    if _JS_EVENT_RE.search(s):
        return True
    if "map(" in s or "filter(" in s or "reduce(" in s or "sort(" in s:
        return True
    if "JSON.parse" in s or "JSON.stringify" in s:
        return True
    if "console.log" in s or "alert(" in s or "prompt(" in s:
        return True

    return False


def _js_comment_for_line(s: str) -> Optional[str]:
    st = s.strip()

    if st.startswith("import "):
        return "// Import code from another module."
    if st.startswith("export "):
        return "// Export this so other files can use it."

    m = _JS_FUNC_RE.match(st)
    if m:
        name, args = m.group(1), m.group(2)
        if st.startswith("async"):
            return f"// Define async function {name}({args}) — can wait for promises using await."
        return f"// Define function {name}({args}) — reusable block of steps."

    m2 = _JS_ARROW_RE.match(st)
    if m2:
        name, args = m2.group(1), m2.group(2)
        if "async" in st:
            return f"// {name}({args}) — async arrow function."
        return f"// {name}({args}) — arrow function (a short way to write a function)."

    if st.startswith(("const ", "let ", "var ")):
        if "document.getElementById" in st or "querySelector" in st:
            return "// Get an element from the page so we can read or update it."
        if "createElement" in st:
            return "// Create a new HTML element in JavaScript."
        if "fetch(" in st:
            return "// Start an API request (fetch)."
        return "// Create a variable to store a value."

    if st.startswith("if ("):
        return "// Only run the next block when the condition is true."
    if st.startswith("for ("):
        return "// Loop: repeat the next block multiple times."
    if st.startswith("while ("):
        return "// Loop: keep repeating while the condition stays true."
    if st.startswith("try"):
        return "// Try running code that might fail; errors go to catch."
    if st.startswith("catch"):
        return "// Handle an error so the app does not crash."
    if st.startswith("return"):
        return "// Return a result back to the caller."

    if "await " in st:
        return "// Wait for an async operation to finish before continuing."
    if "fetch(" in st:
        return "// Send an HTTP request to an API."
    if _JS_EVENT_RE.search(st):
        return "// Run this code when the user triggers an event (e.g., submit, click)."
    if "map(" in st:
        return "// Transform each item into a new value (map)."
    if "filter(" in st:
        return "// Keep only items that match a condition (filter)."
    if "reduce(" in st:
        return "// Combine many items into one result (reduce)."
    if "sort(" in st:
        return "// Sort the list into a new order."
    if "console.log" in st:
        return "// Print a message to the console (for debugging)."
    if "alert(" in st:
        return "// Show a popup message in the browser."
    if "prompt(" in st:
        return "// Ask the user for input in a popup prompt."

    return None


def _comment_js(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        s = line.strip()
        if _js_should_comment(s):
            c = _js_comment_for_line(s)
            if c:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}{c}")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _js_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "javascript"),
        what_it_does=["Adds logic to a web page (or runs as a Node.js script)."],
        requirements=["Browser (web) or Node.js (backend)."],
        how_to_run=[
            "Web:",
            "1. Link the file in HTML: `<script src='file.js'></script>`",
            "2. Open the HTML in a browser and check DevTools Console.",
            "",
            "Node:",
            "1. Run: `node file.js`",
        ],
        logic=[
            "Variables store values.",
            "Functions group reusable steps.",
            "Events run code when the user interacts (click/submit).",
            "Async code can call APIs using fetch + await.",
        ],
        examples=[
            "Input: user clicks, submits form, or types data.",
            "Output: DOM updates, console logs, alerts, returned values.",
        ],
        edge_cases=[
            "If the script file path is wrong in HTML, it will not run.",
            "API requests can fail if the server is down or URL is wrong.",
        ],
    )


# ============================================================
# HTML: comment confusing tags/attributes
# ============================================================

_HTML_TAG_HINTS = {
    "form": "Collects user input and sends it when submitted.",
    "input": "Input field where the user types a value.",
    "button": "Clickable button to trigger an action.",
    "script": "Loads or runs JavaScript code.",
    "link": "Links external resources like CSS files.",
    "meta": "Page configuration (charset, viewport, etc.).",
    "table": "Displays data in rows and columns.",
    "thead": "Table header section.",
    "tbody": "Table body section.",
    "label": "Text label for an input field.",
}


def _comment_html(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append(f"<!-- File: {os.path.basename(file_path) if file_path else 'pasted_code'} -->")
    out.append("")

    tag_re = re.compile(r"^\s*<\s*([a-zA-Z0-9]+)\b")
    for line in lines:
        m = tag_re.match(line)
        if m:
            tag = m.group(1).lower()
            hint = _HTML_TAG_HINTS.get(tag)
            # comment only for tags beginners struggle with
            if hint and "<!--" not in line:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}<!-- {hint} -->")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _html_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "html"),
        what_it_does=["Defines the structure and content of a web page."],
        requirements=["A web browser."],
        how_to_run=["1. Save as `.html`", "2. Open in a browser."],
        logic=[
            "The browser reads HTML and builds the page structure (DOM).",
            "CSS (if linked) controls appearance; JS (if linked) controls behavior.",
        ],
        examples=["Input: user clicks/types.", "Output: page shows content or runs JS."],
        edge_cases=["Broken `<link>` / `<script src>` paths stop CSS/JS from loading."],
    )


# ============================================================
# CSS: comment confusing selectors/properties without breaking nesting
# ============================================================

def _comment_css(code: str, file_path: str) -> str:
    """
    We do NOT restructure CSS (regex parsing breaks media queries).
    We add safe comments when we see:
    - :root variables
    - @media blocks
    - display:flex/grid
    - important layout properties
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("")

    for line in lines:
        s = line.strip()

        if s.startswith(":root"):
            out.append("/* :root holds global CSS variables (reusable colors/sizes). */")

        if s.startswith("@media"):
            out.append("/* Responsive design: styles inside apply only on certain screen sizes. */")

        if "display: flex" in s:
            out.append("/* Flex layout: helps align items in a row/column. */")

        if "display: grid" in s:
            out.append("/* Grid layout: helps build columns/rows layouts. */")

        if s.startswith("padding:"):
            out.append("/* Padding = space inside the element. */")

        if s.startswith("margin:"):
            out.append("/* Margin = space outside the element. */")

        if s.startswith("gap:"):
            out.append("/* Gap = space between items in flex/grid layout. */")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _css_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "css"),
        what_it_does=["Controls how a web page looks (layout, spacing, fonts, colors)."],
        requirements=["A browser + an HTML file that links this CSS."],
        how_to_run=[
            "1. Link it in HTML: `<link rel='stylesheet' href='styles.css'>`",
            "2. Refresh the browser after edits.",
        ],
        logic=[
            "Selectors choose which elements to style.",
            "Properties define how those elements should look.",
            "@media blocks apply different styles for different screen sizes.",
        ],
        examples=["Input: none directly.", "Output: page appearance changes."],
        edge_cases=["If the CSS file path is wrong, styles will not load."],
    )


# ============================================================
# Java: comment confusing constructs
# ============================================================

def _comment_java(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        s = line.strip()

        if re.match(r"^import\s+", s):
            out.append("// Import a Java library so we can use its classes.")
            out.append(line)
            continue

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Define a class (container for methods and data).")
            out.append(line)
            continue

        if "public static void main" in s:
            out.append("// Program starts running from main().")
            out.append(line)
            continue

        if re.match(r"^\s*(public|private|protected)\s+static\s+\w+\s+\w+\s*\(", s) and "main" not in s:
            out.append("// Define a method (reusable block). It can take inputs and return a result.")
            out.append(line)
            continue

        if s.startswith("for") and "(" in s:
            out.append("// Loop: repeat the next block multiple times.")
            out.append(line)
            continue

        if s.startswith("try"):
            out.append("// Try running code that might throw an exception.")
            out.append(line)
            continue

        if s.startswith("catch"):
            out.append("// Handle the error so the program does not crash.")
            out.append(line)
            continue

        if s.startswith("return "):
            out.append("// Return a value back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _java_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines Java classes/methods and may run from `main()`."],
        requirements=["Java JDK installed."],
        how_to_run=[
            "1. Open terminal in the folder.",
            "2. Compile: `javac FileName.java`",
            "3. Run: `java FileName` (without .java)",
        ],
        logic=[
            "Java code is organized into classes.",
            "`main()` is the entry point.",
            "Methods may return values using `return`.",
        ],
        examples=["Input: user input if coded, or method parameters.", "Output: printed console text or returned values."],
        edge_cases=["Class name often must match the file name to compile."],
    )


# ============================================================
# Public API: generate_simple_docs
# ============================================================

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")

    if language == "python":
        return generate_python_docs(code_clean, file_path=file_path)

    if language == "javascript":
        commented = _comment_js(code_clean, file_path)
        documentation = _js_docs(file_path)
        return {"commented_code": commented, "documentation": documentation}

    if language == "html":
        commented = _comment_html(code_clean, file_path)
        documentation = _html_docs(file_path)
        return {"commented_code": commented, "documentation": documentation}

    if language == "css":
        commented = _comment_css(code_clean, file_path)
        documentation = _css_docs(file_path)
        return {"commented_code": commented, "documentation": documentation}

    if language == "java":
        commented = _comment_java(code_clean, file_path)
        documentation = _java_docs(file_path)
        return {"commented_code": commented, "documentation": documentation}

    # fallback
    documentation = _doc_sectioned_no_code(
        title=_filename_title(file_path, language or "unknown"),
        what_it_does=["Part of a software project."],
        requirements=["Depends on the project."],
        how_to_run=["Depends on the project."],
        logic=["Depends on the code."],
        examples=["Depends on the code."],
        edge_cases=["No extra notes."],
    )
    return {"commented_code": code_clean.rstrip() + "\n", "documentation": documentation}
