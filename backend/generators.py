from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# Shared helpers
# ============================================================

AUTO_MARKERS = [
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


def _clean_existing_auto_headers(code: str) -> str:
    """
    Remove previously generated headers so we do not stack them forever.
    """
    lines = code.splitlines()
    out: List[str] = []
    skipping = False

    for line in lines:
        if any(m.lower() in line.lower() for m in AUTO_MARKERS):
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
# Python (better + more accurate + less spam)
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _python_func_one_liner(fn: ast.FunctionDef) -> Optional[str]:
    """
    Try to produce a short helpful line for the function *based on visible body patterns*.
    No guessing beyond what the code literally does.
    """
    # If the function is only "return something", we can describe that something safely.
    body = fn.body
    if not body:
        return None

    # If first statement is a docstring, skip it
    if isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]

    if len(body) == 1 and isinstance(body[0], ast.Return):
        ret = body[0].value

        # return "".join(...) patterns
        if isinstance(ret, ast.Call) and isinstance(ret.func, ast.Attribute) and ret.func.attr == "join":
            return "Returns a single string created by joining many pieces together."

        # return Counter(...).most_common(...)
        if isinstance(ret, ast.Call) and isinstance(ret.func, ast.Attribute) and ret.func.attr == "most_common":
            return "Returns the most common items with their counts."

        # return something simple
        return "Returns a computed result."

    # if the function opens a file (with open)
    for node in ast.walk(fn):
        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call) and isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == "open":
                    return "Reads a file and processes its contents."

    return None


def _python_build_def_comment_map(code: str) -> Dict[int, str]:
    """
    Map line numbers -> comments for def/class lines using AST when possible.
    This makes function comments less generic.
    """
    tree, _ = _safe_parse_python(code)
    if not tree:
        return {}

    m: Dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            m[node.lineno] = f"# Define class `{node.name}` (a blueprint for creating objects)."
        if isinstance(node, ast.FunctionDef):
            hint = _python_func_one_liner(node)
            if hint:
                m[node.lineno] = f"# Function `{node.name}()`: {hint}"
            else:
                m[node.lineno] = f"# Function `{node.name}()`: a reusable block of steps."
    return m


def _py_should_comment_line(s: str) -> bool:
    """
    Comment only lines that beginners usually struggle with.
    (We avoid spamming obvious simple assignments.)
    """
    if not s or s.startswith("#"):
        return False

    # always comment "structure" lines
    if s.startswith(("import ", "from ", "def ", "class ", "if __name__")):
        return True

    # common confusing blocks
    if s.startswith(("for ", "while ", "try:", "except", "with ")):
        return True

    # tricky one-liners and helpers
    if "lambda " in s:
        return True
    if " for " in s and ("[" in s and "]" in s):  # list comprehension
        return True
    if " for " in s and ("(" in s and ")") and "join(" in s:  # generator within join
        return True

    # key library patterns beginners ask about
    if "Counter(" in s or ".most_common(" in s:
        return True

    # dict/list methods
    if ".append(" in s or ".pop(" in s or ".get(" in s:
        return True

    # conversions (ONLY if actually converting)
    if re.search(r"\b(int|float|str|bool)\s*\(", s):
        return True

    # return lines
    if s.startswith("return "):
        return True

    return False


def _py_comment_for_line(s: str) -> Optional[str]:
    st = s.strip()

    if st.startswith(("import ", "from ")):
        return "# Import: bring in code from another library/module."

    if st.startswith("if __name__"):
        return "# This block runs only when you execute this file directly."

    if st.startswith("for "):
        return "# Loop: repeat the block below for each item."

    if st.startswith("while "):
        return "# Loop: keep repeating while the condition stays true."

    if st.startswith("try:"):
        return "# Error handling: try this; if it fails, Python jumps to `except`."

    if st.startswith("except"):
        return "# Handle the error instead of crashing."

    if st.startswith("with ") and "open(" in st:
        return "# Open the file safely; it will auto-close when the block ends."

    if st.startswith("return "):
        return "# Return: send the result back to the caller."

    if "Counter(" in st:
        return "# Counter: counts how many times each item appears."

    if ".most_common(" in st:
        return "# most_common(): returns the top items with the highest counts."

    if ".append(" in st:
        return "# append(): add an item to the end of the list."

    if ".pop(" in st:
        return "# pop(): remove and return an item from the list."

    if ".get(" in st:
        return "# dict.get(): read a value safely (returns a default if missing)."

    if re.search(r"\bint\s*\(", st):
        return "# Convert a value to an integer (whole number)."
    if re.search(r"\bfloat\s*\(", st):
        return "# Convert a value to a float (number with decimals)."
    if re.search(r"\bstr\s*\(", st):
        return "# Convert a value to text (string)."

    if ("[" in st and "]" in st) and " for " in st:
        return "# List comprehension: build a new list in one line."

    if "lambda " in st:
        return "# lambda: a small one-line function used as a quick helper."

    if "join(" in st and " for " in st:
        return "# Build a string by joining many pieces together."

    return None


def _python_add_comments(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()

    # AST-based map gives better function/class comments
    def_comment_map = _python_build_def_comment_map(code)

    out: List[str] = []
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for idx, line in enumerate(lines, start=1):
        s = line.strip()

        # Put higher-quality comment for def/class lines from AST if available
        if idx in def_comment_map and s.startswith(("def ", "class ")):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}{def_comment_map[idx]}")
            out.append(line)
            continue

        if _py_should_comment_line(s):
            c = _py_comment_for_line(s)
            if c:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}{c}")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _python_docs(code: str, file_path: str) -> str:
    info_tree, parse_err = _safe_parse_python(code)
    has_input = "input(" in code.lower()
    what: List[str] = []
    if has_input:
        what.append("Runs in the terminal and asks the user for input.")
    else:
        what.append("Runs a Python script / defines functions and classes.")

    requirements = ["Python 3 installed"]

    how = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'main.py'}`",
        "3. Follow any prompts (if the script asks for input).",
    ]

    logic = [
        "Python reads the file from top to bottom.",
        "Imports run first, then functions/classes are defined.",
        "If there is an `if __name__ == '__main__'` block, that part runs last.",
    ]

    examples = [
        "Input: user input (if used) or function arguments.",
        "Output: printed text or returned values depending on the code.",
    ]

    edge = []
    if not info_tree:
        edge.append(f"Syntax/indentation error: {parse_err}")
    edge.append("If the script reads a file, the file must exist (unless handled).")
    edge.append("If the code converts text to numbers, invalid text can cause errors unless handled.")

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
    return {
        "commented_code": _python_add_comments(code_clean, file_path),
        "documentation": _python_docs(code_clean, file_path),
    }


# ============================================================
# JavaScript (retain)
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
# HTML (improved: comment confusing attributes too)
# ============================================================

_HTML_TAG_HINTS = {
    "form": "Form: collects input and triggers submit logic.",
    "input": "Input: user types a value here.",
    "button": "Button: user clicks to trigger an action.",
    "script": "Script: loads/runs JavaScript.",
    "link": "Link: connects external files (like CSS).",
    "meta": "Meta: page configuration (charset, viewport).",
    "table": "Table: displays data in rows and columns.",
    "thead": "Table head: column titles.",
    "tbody": "Table body: rows of data.",
    "label": "Label: describes an input field.",
    "section": "Section: groups related content.",
    "header": "Header: top area of the page.",
    "main": "Main: primary page content.",
    "footer": "Footer: bottom area of the page.",
}


def _html_attribute_comments(line: str) -> List[str]:
    """
    Add small comments for confusing attributes.
    """
    s = line.strip().lower()
    notes: List[str] = []

    if "required" in s:
        notes.append("required: user must fill this before submitting.")
    if "minlength" in s:
        notes.append("minlength: minimum number of characters allowed.")
    if 'type="number"' in s or "type='number'" in s:
        notes.append("type=number: input expects a numeric value.")
    if "step=" in s:
        notes.append("step: allowed increments (e.g., 0.01 for money).")
    if "min=" in s:
        notes.append("min: smallest allowed value.")
    if "aria-" in s:
        notes.append("aria-*: accessibility hint for screen readers.")
    if "id=" in s and "name=" in s:
        notes.append("id connects label ↔ input; name is the key used when reading form values.")
    return notes


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
            if hint and "<!--" not in line:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}<!-- {hint} -->")

        # attribute-level hints for lines that have them
        attr_notes = _html_attribute_comments(line)
        if attr_notes:
            indent = re.match(r"^\s*", line).group(0)
            for n in attr_notes:
                out.append(f"{indent}<!-- {n} -->")

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
# CSS (retain)
# ============================================================

def _comment_css(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("")

    for line in lines:
        s = line.strip()

        if s.startswith(":root"):
            out.append("/* :root holds global CSS variables (reusable values). */")

        if s.startswith("@media"):
            out.append("/* Responsive design: rules apply only on certain screen sizes. */")

        if "display: flex" in s:
            out.append("/* Flex layout: helps align items in a row/column. */")

        if "display: grid" in s:
            out.append("/* Grid layout: helps build rows/columns layout. */")

        if s.startswith("padding:"):
            out.append("/* Padding = space inside the element. */")

        if s.startswith("margin:"):
            out.append("/* Margin = space outside the element. */")

        if s.startswith("gap:"):
            out.append("/* Gap = space between items in flex/grid layouts. */")

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
# Java (improved: constructor/this/fields/returns/indent)
# ============================================================

_JAVA_CLASS_RE = re.compile(r"^\s*(public\s+)?class\s+([A-Za-z_]\w*)")
_JAVA_METHOD_RE = re.compile(r"^\s*(public|private|protected)\s+(static\s+)?([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z_]\w*)\s*\(")
_JAVA_CTOR_RE = re.compile(r"^\s*(public|private|protected)\s+([A-Za-z_]\w*)\s*\(")


def _java_should_comment(s: str) -> bool:
    if not s or s.startswith("//"):
        return False

    if s.startswith("import "):
        return True
    if _JAVA_CLASS_RE.match(s):
        return True
    if "public static void main" in s:
        return True
    if _JAVA_METHOD_RE.match(s):
        return True
    if _JAVA_CTOR_RE.match(s) and "class" not in s and "void" not in s:
        return True

    if s.startswith(("private ", "public ", "protected ")):
        # fields also confuse beginners
        if s.endswith(";") and "(" not in s:
            return True

    if s.startswith("this."):
        return True
    if "Math.max" in s:
        return True
    if s.startswith(("if", "for", "while", "try", "catch", "return ")):
        return True

    return False


def _java_comment_for_line(s: str) -> Optional[str]:
    st = s.strip()

    if st.startswith("import "):
        return "// Import: use classes from another Java package."

    m = _JAVA_CLASS_RE.match(st)
    if m:
        name = m.group(2)
        return f"// Class `{name}`: groups related data (fields) and behavior (methods)."

    if "public static void main" in st:
        return "// main(): program entry point (Java starts running here)."

    # fields
    if st.startswith(("private ", "public ", "protected ")) and st.endswith(";") and "(" not in st:
        return "// Field: stores data inside the object."

    # constructor
    mctor = _JAVA_CTOR_RE.match(st)
    if mctor and "class" not in st and "void" not in st and "(" in st and ")" in st:
        name = mctor.group(2)
        return f"// Constructor `{name}(...)`: runs when you create a new object."

    # method signature
    mm = _JAVA_METHOD_RE.match(st)
    if mm and "main" not in st:
        ret_type = mm.group(3)
        name = mm.group(4)
        if ret_type == "void":
            return f"// Method `{name}(...)`: performs an action (no returned value)."
        return f"// Method `{name}(...)`: returns a `{ret_type}` result."

    if st.startswith("this."):
        return "// `this.` means “this current object’s field/value”."

    if "Math.max" in st:
        return "// Math.max(a,b): picks the larger value (used to prevent negatives)."

    if st.startswith("if"):
        return "// If-statement: run the next block only when the condition is true."

    if st.startswith("for"):
        return "// Loop: repeat the next block multiple times."

    if st.startswith("while"):
        return "// Loop: keep repeating while the condition stays true."

    if st.startswith("try"):
        return "// Try: run code that might throw an exception."

    if st.startswith("catch"):
        return "// Catch: handle the error so the program does not crash."

    if st.startswith("return "):
        return "// Return: send a value back to the caller."

    return None


def _comment_java(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        s = line.strip()
        if _java_should_comment(s):
            c = _java_comment_for_line(s)
            if c:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}{c}")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _java_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines Java classes and methods; may run from `main()`."],
        requirements=["Java JDK installed."],
        how_to_run=[
            "1. Open terminal in the folder.",
            "2. Compile: `javac FileName.java`",
            "3. Run: `java FileName` (without .java)",
        ],
        logic=[
            "Java code is organized into classes.",
            "`main()` is the entry point.",
            "Methods return values using `return` (unless they are void).",
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
        return {"commented_code": _comment_js(code_clean, file_path), "documentation": _js_docs(file_path)}

    if language == "html":
        return {"commented_code": _comment_html(code_clean, file_path), "documentation": _html_docs(file_path)}

    if language == "css":
        return {"commented_code": _comment_css(code_clean, file_path), "documentation": _css_docs(file_path)}

    if language == "java":
        return {"commented_code": _comment_java(code_clean, file_path), "documentation": _java_docs(file_path)}

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