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
# Python (HARD MODE: AST + condition-aware comments)
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _py_expr_to_text(node: ast.AST) -> str:
    """
    Convert a Python AST expression into simple English-ish text.
    Not perfect, but designed to be safe and generally helpful.
    """
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        return f"{_py_expr_to_text(node.value)}.{node.attr}"

    if isinstance(node, ast.Constant):
        # strings with quotes to reduce confusion
        if isinstance(node.value, str):
            return f'"{node.value}"'
        return str(node.value)

    if isinstance(node, ast.Call):
        # common calls
        fn = _py_expr_to_text(node.func)
        if fn.endswith("len") or fn == "len":
            if node.args:
                return f"length of {_py_expr_to_text(node.args[0])}"
        if fn.endswith("isalpha") or fn.endswith("isdigit"):
            return f"{fn}() check"
        if fn.endswith("strptime"):
            return "parse a datetime"
        if fn.endswith("split"):
            return "split text"
        if fn.endswith("lower"):
            return "lowercase text"
        if fn.endswith("upper"):
            return "uppercase text"
        if fn.endswith("float") or fn == "float":
            return "convert to float"
        if fn.endswith("int") or fn == "int":
            return "convert to int"
        if fn.endswith("str") or fn == "str":
            return "convert to string"
        return f"{fn}(...)"

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return f"not ({_py_expr_to_text(node.operand)})"
        return f"unary-op({ _py_expr_to_text(node.operand) })"

    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        parts = [_py_expr_to_text(v) for v in node.values]
        return f" {op} ".join(parts)

    if isinstance(node, ast.Compare):
        left = _py_expr_to_text(node.left)
        # only first comparator for readable text
        if not node.ops or not node.comparators:
            return left

        op = node.ops[0]
        right = _py_expr_to_text(node.comparators[0])

        op_map = {
            ast.Eq: "equals",
            ast.NotEq: "does not equal",
            ast.Lt: "is less than",
            ast.LtE: "is less than or equal to",
            ast.Gt: "is greater than",
            ast.GtE: "is greater than or equal to",
            ast.Is: "is",
            ast.IsNot: "is not",
            ast.In: "is in",
            ast.NotIn: "is not in",
        }
        op_text = op_map.get(type(op), "compares to")
        return f"{left} {op_text} {right}"

    if isinstance(node, ast.BinOp):
        # keep it safe and light
        return "a calculated value"

    # fallback
    return "a value"


def _py_condition_to_reason(test: ast.AST) -> str:
    """
    Turn a condition into a beginner-friendly reason sentence.
    Example: if len(parts) < 3 -> "because the number of parts is less than 3"
    """
    t = _py_expr_to_text(test)
    return f"because {t}"


def _python_func_one_liner(fn: ast.FunctionDef) -> Optional[str]:
    """
    Short helpful line for the function based on visible patterns.
    """
    body = fn.body
    if not body:
        return None

    # skip docstring
    if (
        isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    if not body:
        return None

    # single return
    if len(body) == 1 and isinstance(body[0], ast.Return):
        return "Computes and returns a result."

    # file reading detection
    for node in ast.walk(fn):
        if isinstance(node, ast.With):
            for item in node.items:
                if (
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(item.context_expr.func, ast.Name)
                    and item.context_expr.func.id == "open"
                ):
                    return "Reads a file and processes its contents."

    # parsing detection
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "strptime":
                return "Parses text into datetime values."
    return None


def _python_build_comment_maps(code: str) -> Tuple[Dict[int, str], Dict[int, str]]:
    """
    Build AST-based maps:
    - def/class comments (line -> comment)
    - early-return reasons (line -> comment)
    """
    tree, _ = _safe_parse_python(code)
    if not tree:
        return {}, {}

    def_map: Dict[int, str] = {}
    return_reason_map: Dict[int, str] = {}

    # def/class comments
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            def_map[node.lineno] = f"# Class `{node.name}`: a blueprint that groups data and behavior."
        elif isinstance(node, ast.FunctionDef):
            hint = _python_func_one_liner(node)
            if hint:
                def_map[node.lineno] = f"# Function `{node.name}()`: {hint}"
            else:
                def_map[node.lineno] = f"# Function `{node.name}()`: runs a reusable set of steps."

    # reason-aware early returns inside if-blocks:
    # if <cond>: return <value>
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # only handle the common beginner pattern: single early return in the body
            if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                ret = node.body[0]
                reason = _py_condition_to_reason(node.test)
                # comment should be near the return line, not the if line
                return_reason_map[ret.lineno] = f"# Stop here {reason}."

    return def_map, return_reason_map


def _py_should_comment_line(s: str) -> bool:
    """
    Comment only lines beginners usually struggle with (avoid spam).
    """
    if not s or s.startswith("#"):
        return False

    # structure / blocks
    if s.startswith(("def ", "class ", "if __name__", "for ", "while ", "try:", "except", "with ")):
        return True

    # imports: comment as a group, not each line (handled separately)
    if s.startswith(("import ", "from ")):
        return True

    # hard patterns
    if "lambda " in s:
        return True
    if " for " in s and ("[" in s and "]" in s):
        return True
    if "join(" in s and " for " in s:
        return True

    # parsing / validation helpers
    if ".split(" in s and re.search(r"\.split\([^)]*,\s*\d+\s*\)", s):
        return True
    if "datetime.strptime" in s:
        return True
    if s.startswith("@dataclass") or "dataclass(" in s:
        return True

    # common beginner-pain builtins
    if "enumerate(" in s:
        return True
    if "zip(" in s:
        return True
    if "sorted(" in s or ".sort(" in s:
        return True
    if s.startswith("return"):
        return True

    # container helpers
    if any(x in s for x in (".append(", ".get(", ".setdefault(", ".update(")):
        return True

    # conversions
    if re.search(r"\b(int|float|str|bool)\s*\(", s):
        return True

    return False


def _py_comment_for_line(s: str) -> Optional[str]:
    st = s.strip()

    if st.startswith("@dataclass"):
        if "frozen=True" in st.replace(" ", ""):
            return "# dataclass(frozen=True): makes objects immutable (fields cannot be changed)."
        return "# dataclass: auto-creates __init__ and other helper methods for a data class."

    if st.startswith("if __name__"):
        return "# This part runs only when the file is executed directly."

    if st.startswith("for "):
        return "# Loop: repeat the indented block for each item."

    if st.startswith("while "):
        return "# Loop: keep repeating while the condition stays true."

    if st == "try:":
        return "# Try: run code that might fail; handle errors in `except`."

    if st.startswith("except"):
        return "# Except: handle a specific error so the program doesn't crash."

    if st.startswith("with ") and "open(" in st:
        return "# Open a file safely. It auto-closes when this block ends."

    if ".split(" in st and re.search(r"\.split\([^)]*,\s*\d+\s*\)", st):
        m = re.search(r"\.split\([^)]*,\s*(\d+)\s*\)", st)
        if m:
            n = int(m.group(1))
            return f"# split(..., {n}): split into at most {n + 1} parts (keeps the remaining text together)."

    if "datetime.strptime" in st:
        return "# Convert a timestamp string into a real datetime value."

    if ("[" in st and "]" in st) and " for " in st:
        return "# List comprehension: build a list by looping in one line."

    if "join(" in st and " for " in st:
        return "# Build one string by joining many pieces."

    if "lambda " in st:
        return "# lambda: a tiny one-line function (often used for sorting)."

    if "enumerate(" in st:
        return "# enumerate(...): loop while also getting the index number."

    if "zip(" in st:
        return "# zip(...): pair items from multiple lists together."

    if "sorted(" in st:
        return "# sorted(...): create a new sorted list."
    if ".sort(" in st:
        if "key=" in st:
            return "# sort(key=...): reorder items using a rule (the key chooses what to sort by)."
        return "# sort(): reorder the list in place."

    if ".append(" in st:
        return "# append(): add an item to the end of the list."
    if ".get(" in st:
        return "# dict.get(...): read a value safely (uses a default if missing)."
    if ".setdefault(" in st:
        return "# setdefault(...): get a value, or create it if it doesn't exist."

    if re.search(r"\bint\s*\(", st):
        return "# int(...): convert to a whole number."
    if re.search(r"\bfloat\s*\(", st):
        return "# float(...): convert to a decimal number."
    if re.search(r"\bstr\s*\(", st):
        return "# str(...): convert to text."

    if st.startswith("return "):
        return "# Return: send the result back to whoever called this function."

    return None


def _python_add_comments(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()

    def_map, return_reason_map = _python_build_comment_maps(code)

    out: List[str] = []
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    # one comment for import block(s)
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith(("import ", "from ")):
            start = i
            while i < len(lines) and lines[i].strip().startswith(("import ", "from ")):
                i += 1
            out.append("# Imports: bring in libraries this file depends on.")
            for j in range(start, i):
                out.append(lines[j])
            out.append("")
            continue

        out.append(lines[i])
        i += 1

    rebuilt = "\n".join(out).splitlines()

    final: List[str] = []
    for idx, line in enumerate(rebuilt, start=1):
        s = line.strip()

        # def/class comment from AST
        if idx in def_map and s.startswith(("def ", "class ")):
            indent = re.match(r"^\s*", line).group(0)
            final.append(f"{indent}{def_map[idx]}")
            final.append(line)
            continue

        # reason-aware early return (from AST if-pattern)
        if idx in return_reason_map and s.startswith("return"):
            indent = re.match(r"^\s*", line).group(0)
            final.append(f"{indent}{return_reason_map[idx]}")
            final.append(line)
            continue

        # general targeted comment
        if _py_should_comment_line(s):
            c = _py_comment_for_line(s)
            if c:
                indent = re.match(r"^\s*", line).group(0)
                final.append(f"{indent}{c}")

        final.append(line)

    return "\n".join(final).rstrip() + "\n"


def _python_docs(code: str, file_path: str) -> str:
    tree, err = _safe_parse_python(code)
    has_input = "input(" in code.lower()

    what: List[str] = []
    if has_input:
        what.append("Runs in the terminal and asks the user for input.")
    else:
        what.append("Defines functions/classes and runs logic when executed.")

    requirements = ["Python 3 installed"]

    how = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'main.py'}`",
        "3. Follow any prompts (if the script asks for input).",
    ]

    logic = [
        "Python reads the file from top to bottom.",
        "Imports load first, then functions/classes are defined.",
        "The `if __name__ == '__main__'` block runs only when executed directly.",
        "Many scripts validate inputs early and return/exit when data is invalid.",
    ]

    examples = [
        "Input: user input (if used) or function arguments.",
        "Output: printed text or returned values depending on the code.",
    ]

    edge = []
    if not tree:
        edge.append(f"Syntax/indentation error: {err}")
    edge.append("If the code reads files, the file must exist (unless handled).")
    edge.append("Bad formats (dates/numbers) can cause errors unless handled with try/except.")

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
        return f"// {name}({args}) — arrow function (short function syntax)."

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
# HTML (go harder: teach attributes + accessibility)
# ============================================================

_HTML_TAG_HINTS = {
    "form": "Form: collects user input and submits it.",
    "input": "Input: where the user types a value.",
    "button": "Button: user clicks to trigger an action.",
    "script": "Script: loads/runs JavaScript.",
    "link": "Link: connects external files (like CSS).",
    "meta": "Meta: page configuration (charset, viewport).",
    "label": "Label: describes what an input field is for.",
    "table": "Table: displays rows and columns of data.",
    "thead": "Table head: column titles.",
    "tbody": "Table body: table rows go here.",
    "section": "Section: groups related content.",
    "header": "Header: top area of the page.",
    "main": "Main: primary content of the page.",
    "footer": "Footer: bottom area of the page.",
}


def _html_attribute_notes(line: str) -> List[str]:
    s = line.strip()
    low = s.lower()
    notes: List[str] = []

    if "required" in low:
        notes.append("required: user must fill this before submitting.")
    if "minlength" in low:
        notes.append("minlength: minimum number of characters allowed.")
    if 'type="number"' in low or "type='number'" in low:
        notes.append("type=number: input expects numeric values.")
    if "step=" in low:
        notes.append("step: allowed increments (e.g., 0.01 for money).")
    if re.search(r"\bmin\s*=", low):
        notes.append("min: smallest allowed value.")
    if "aria-" in low:
        notes.append("aria-*: helps screen readers understand the page (accessibility).")
    if "aria-labelledby" in low:
        notes.append("aria-labelledby: connects this section to a heading for accessibility.")
    if re.search(r"\bfor\s*=", low) and re.search(r"\bid\s*=", low):
        notes.append("for/id: links <label> to <input> (clicking label focuses input).")
    if re.search(r"\bname\s*=", low):
        notes.append("name: key used when reading form values in JavaScript.")
    if re.search(r"\bid\s*=", low):
        notes.append("id: unique identifier (used for selecting the element in JS/CSS).")
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
            if hint:
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}<!-- {hint} -->")

        notes = _html_attribute_notes(line)
        if notes:
            indent = re.match(r"^\s*", line).group(0)
            for n in notes:
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
            "ARIA attributes improve accessibility for screen readers.",
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
# Java (go harder: condition-aware “why” on validations)
# ============================================================

_JAVA_CLASS_RE = re.compile(r"^\s*(public\s+)?class\s+([A-Za-z_]\w*)")
_JAVA_METHOD_RE = re.compile(r"^\s*(public|private|protected)\s+(static\s+)?([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z_]\w*)\s*\(")
_JAVA_CTOR_RE = re.compile(r"^\s*(public|private|protected)\s+([A-Za-z_]\w*)\s*\(")
_JAVA_IF_RETURN_RE = re.compile(r"^\s*if\s*\((.+)\)\s*return\s+(true|false|null)\s*;")


def _java_should_comment(s: str) -> bool:
    if not s or s.startswith("//"):
        return False

    if s.startswith("import "):
        return True
    if _JAVA_CLASS_RE.match(s):
        return True
    if "public static void main" in s:
        return True
    if _JAVA_METHOD_RE.match(s) or _JAVA_CTOR_RE.match(s):
        return True
    if s.startswith(("private ", "public ", "protected ")) and s.endswith(";") and "(" not in s:
        return True
    if "this." in s:
        return True
    if s.startswith(("if", "for", "while", "try", "catch", "return ")):
        return True

    return False


def _java_simple_condition_reason(cond: str) -> str:
    """
    Turn Java condition text into a simple reason phrase.
    Example: "amount <= 0" -> "because amount is not positive"
    """
    c = cond.strip()

    # quick common patterns
    if "<= 0" in c:
        left = c.split("<= 0")[0].strip()
        return f"because {left} is not positive"
    if "== null" in c:
        left = c.split("== null")[0].strip()
        return f"because {left} is missing (null)"
    if "!= null" in c:
        left = c.split("!= null")[0].strip()
        return f"because {left} exists (not null)"
    if "< 0" in c:
        left = c.split("< 0")[0].strip()
        return f"because {left} is negative"
    if "> balance" in c:
        return "because the requested amount is more than the available balance"
    return f"because the condition ({cond.strip()}) is true"


def _java_comment_for_line(s: str) -> Optional[str]:
    st = s.strip()

    if st.startswith("import "):
        return "// Import: bring in classes from Java libraries."

    m = _JAVA_CLASS_RE.match(st)
    if m:
        name = m.group(2)
        return f"// Class `{name}`: groups data (fields) and actions (methods)."

    if "public static void main" in st:
        return "// main(): Java starts running here."

    if st.startswith(("private ", "public ", "protected ")) and st.endswith(";") and "(" not in st:
        return "// Field: stores information inside each object."

    mctor = _JAVA_CTOR_RE.match(st)
    if mctor and "class" not in st and "void" not in st and "(" in st:
        name = mctor.group(2)
        return f"// Constructor `{name}(...)`: runs when creating a new object."

    mm = _JAVA_METHOD_RE.match(st)
    if mm and "main" not in st:
        ret_type = mm.group(3)
        name = mm.group(4)
        if ret_type == "void":
            return f"// Method `{name}(...)`: performs an action (no returned value)."
        return f"// Method `{name}(...)`: returns a `{ret_type}` result."

    # condition-aware early return
    m_if_ret = _JAVA_IF_RETURN_RE.match(st)
    if m_if_ret:
        cond = m_if_ret.group(1)
        reason = _java_simple_condition_reason(cond)
        return f"// Stop here {reason}."

    if "this." in st:
        return "// this.field = ... means: set a value on the current object."

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
        return "// Return: send a result back to the caller."

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
            "`main()` is the entry point for running a program.",
            "Constructors run when you create objects using `new`.",
            "Validation checks often stop early when inputs are invalid.",
        ],
        examples=["Input: user input if coded, or method parameters.", "Output: console text or returned values."],
        edge_cases=["Public class name often must match the file name to compile."],
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