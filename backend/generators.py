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
    Remove previously generated headers so they don't stack.
    """
    lines = code.splitlines()
    out: List[str] = []
    skipping = False

    for line in lines:
        if any(m in line for m in AUTO_MARKERS):
            skipping = True
            continue

        if skipping:
            # stop skipping when we hit a blank line
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
    Structure:
    1) Title
    2) What it does
    3) Requirements
    4) How to run
    5) Explanation of logic
    7) Example input/output
    8) Edge cases / notes
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
# PYTHON: accurate commenting using AST
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _py_expr_to_text(node: ast.AST) -> str:
    """
    Convert common AST expressions to a readable phrase.
    Not perfect, but better than vague statements.
    """
    if isinstance(node, ast.BinOp):
        op_map = {
            ast.Add: "adds",
            ast.Sub: "subtracts",
            ast.Mult: "multiplies",
            ast.Div: "divides",
            ast.Mod: "takes modulo of",
            ast.Pow: "raises to the power of",
        }
        verb = op_map.get(type(node.op), "combines")
        return f"{verb} two values"
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            return f"calls `{node.func.attr}()`"
        if isinstance(node.func, ast.Name):
            return f"calls `{node.func.id}()`"
        return "calls a function"
    if isinstance(node, ast.Compare):
        return "compares values"
    if isinstance(node, ast.Subscript):
        return "indexes into a collection"
    if isinstance(node, ast.Attribute):
        return "accesses an attribute"
    return "computes a value"


def _py_return_summary(fn: ast.FunctionDef) -> Optional[str]:
    """
    Analyze return statements to describe what a function returns.
    """
    returns: List[str] = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            returns.append(_py_expr_to_text(n.value))

    if not returns:
        return None

    # If many return types, summarize generally
    unique = sorted(set(returns))
    if len(unique) == 1:
        return f"Returns a value that {unique[0]}."
    return "Returns a value depending on logic paths (multiple return forms detected)."


def _py_side_effects_summary(fn: ast.FunctionDef) -> List[str]:
    """
    Describe visible side effects like printing, writing files, pandas usage, etc.
    """
    notes: List[str] = []
    calls = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                calls.append(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                calls.append(n.func.attr)

    calls_set = set(calls)

    if "print" in calls_set:
        notes.append("Prints output to the terminal.")
    if "input" in calls_set:
        notes.append("Reads input from the user in the terminal.")
    if "open" in calls_set:
        notes.append("Reads from or writes to files using `open()`.")
    if "read_csv" in calls_set:
        notes.append("Reads a CSV file (likely using pandas).")
    if "to_csv" in calls_set:
        notes.append("Writes data to a CSV file.")
    if "plot" in calls_set:
        notes.append("Creates a plot/graph.")
    return notes


def _python_docs_and_comments(code: str, file_path: str) -> Dict[str, Any]:
    code = _clean_existing_auto_headers(code)
    tree, err = _safe_parse_python(code)

    # Documentation (structured)
    title = _filename_title(file_path, "python")
    what: List[str] = []
    req: List[str] = ["Python 3.10+ recommended"]
    run: List[str] = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'script.py'}`",
    ]
    logic: List[str] = []
    examples: List[str] = []
    edges: List[str] = []

    if tree is None:
        what.append("This Python file could not be parsed due to a syntax/indentation issue.")
        logic.append("Fix the syntax error and try again for accurate documentation.")
        edges.append(f"Parse error: {err}")
        return {
            "commented_code": code.rstrip() + "\n",
            "documentation": _doc_sectioned_no_code(
                title=title,
                what_it_does=what,
                requirements=req,
                how_to_run=run,
                logic=logic,
                examples=["Input/Output depends on what the script does."],
                edge_cases=edges,
            ),
        }

    # Summaries from AST
    fn_defs: List[ast.FunctionDef] = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    has_main_guard = 'if __name__ == "__main__"' in code or "if __name__ == '__main__'" in code

    if imports:
        what.append("Loads required libraries using import statements.")
    if class_defs:
        what.append(f"Defines {len(class_defs)} class(es) to organize related data and behavior.")
    if fn_defs:
        what.append(f"Defines {len(fn_defs)} function(s) to split the program into reusable steps.")
    if has_main_guard:
        what.append('Runs an entry point when executed directly (`if __name__ == "__main__"`).')

    logic.append("Python reads the file top-to-bottom, defining imports, classes, and functions first.")
    if has_main_guard:
        logic.append("The main guard prevents code from running when the file is imported as a module.")
    if fn_defs:
        logic.append("Functions are called later to perform specific tasks like calculations, file operations, or transformations.")

    examples.append("Input: depends on the script (function arguments, files, or user input).")
    examples.append("Output: depends on the script (return values, printed text, or saved files).")

    edges.append("If input types are wrong (e.g., text where numbers are expected), the script may raise errors unless handled.")
    edges.append("If the script reads external files, the path must exist and be accessible.")

    # Create comments with real function descriptions
    out: List[str] = []
    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    # Keep original code, but inject function headers with accurate summary
    lines = code.splitlines()
    line_map = {i + 1: line for i, line in enumerate(lines)}

    # Find function start lines via AST (lineno)
    fn_by_line: Dict[int, ast.FunctionDef] = {}
    for fn in fn_defs:
        if getattr(fn, "lineno", None):
            fn_by_line[fn.lineno] = fn

    for i in range(1, len(lines) + 1):
        line = line_map[i]
        s = line.strip()

        if i in fn_by_line:
            fn = fn_by_line[i]
            args = [a.arg for a in fn.args.args] if fn.args else []
            out.append("")
            out.append("# ---------------------------------------")
            out.append(f"# Function: {fn.name}()")
            if args:
                out.append(f"# Inputs: {', '.join(args)}")
            else:
                out.append("# Inputs: (none)")

            ret_summary = _py_return_summary(fn)
            side = _py_side_effects_summary(fn)

            if side:
                for note in side:
                    out.append(f"# {note}")
            if ret_summary:
                out.append(f"# {ret_summary}")
            else:
                out.append("# Returns: (no explicit return detected; may return None).")
            out.append("# ---------------------------------------")

        # Add small loop/try notes only when they appear
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats this block until the loop condition ends.")
        if re.match(r"^\s*try\s*:\s*$", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Error handling: the code tries the block and handles failures in except.")
        out.append(line)

    documentation = _doc_sectioned_no_code(
        title=title,
        what_it_does=what or ["Runs Python code (imports, functions, and optional entry point)."],
        requirements=req,
        how_to_run=run,
        logic=logic,
        examples=examples,
        edge_cases=edges,
    )

    return {"commented_code": "\n".join(out).rstrip() + "\n", "documentation": documentation}


# ============================================================
# JAVASCRIPT: improved commenting with real hints (not spam)
# ============================================================

JS_FUNC_RE = re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*\{")
JS_ARROW_RE = re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*\((.*?)\)\s*=>")


def _js_guess_return(line_block: str) -> Optional[str]:
    if "return" not in line_block:
        return None
    if "+" in line_block and "return" in line_block:
        return "Returns a computed value (a calculation is returned)."
    return "Returns a value based on the function logic."


def _javascript_docs_and_comments(code: str, file_path: str) -> Dict[str, Any]:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()

    out: List[str] = []
    out.append("/* =======================================")
    out.append("   Professional beginner-friendly comments")
    out.append("   ======================================= */")
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("")

    # Add comments above functions only
    i = 0
    while i < len(lines):
        line = lines[i]
        m1 = JS_FUNC_RE.match(line)
        m2 = JS_ARROW_RE.match(line)

        if m1 or m2:
            name = (m1.group(1) if m1 else m2.group(1))
            args = (m1.group(2) if m1 else m2.group(2)).strip()

            # Collect a small block of following lines for return guess
            block = "\n".join(lines[i:i+20])
            ret = _js_guess_return(block)

            out.append("")
            out.append("/* --------------------------------------- */")
            out.append(f"/* Function: {name}() */")
            out.append(f"/* Inputs: {args if args else '(none)'} */")
            out.append(f"/* {ret or 'Returns: (no explicit return found in nearby lines).'} */")
            out.append("/* --------------------------------------- */")

        out.append(line)
        i += 1

    doc = _doc_sectioned_no_code(
        title=_filename_title(file_path, "javascript"),
        what_it_does=["Implements JavaScript logic (functions, events, calculations) used in a browser or Node.js."],
        requirements=["Browser for web scripts OR Node.js for server scripts."],
        how_to_run=[
            "Website:",
            "1. Link the file in HTML with `<script src='file.js'></script>`.",
            "2. Open the HTML file and check the console for output/errors.",
            "",
            "Node.js:",
            "1. Run: `node file.js`",
        ],
        logic=[
            "Functions group reusable steps like calculations or UI updates.",
            "If used in the browser, code may run based on user actions (click, input, page load).",
        ],
        examples=[
            "Input: function arguments or user actions (clicks/typing).",
            "Output: return values, console logs, alerts, or page changes.",
        ],
        edge_cases=[
            "If the script is not linked correctly in HTML, it won’t run in the browser.",
            "If using DOM elements, missing IDs/classes can cause errors.",
        ],
    )

    return {"commented_code": "\n".join(out).rstrip() + "\n", "documentation": doc}


# ============================================================
# HTML / CSS / JAVA (cleaner, still useful)
# ============================================================

def _html_docs_and_comments(code: str, file_path: str) -> Dict[str, Any]:
    code = _clean_existing_auto_headers(code)
    out = [
        "<!-- ======================================= -->",
        "<!-- Professional beginner-friendly comments -->",
        "<!-- ======================================= -->",
        f"<!-- File: {os.path.basename(file_path) if file_path else 'pasted_code'} -->",
        "",
        code.strip(),
        "",
    ]
    doc = _doc_sectioned_no_code(
        title=_filename_title(file_path, "html"),
        what_it_does=["Defines the structure and content of a web page (head + body)."],
        requirements=["A web browser."],
        how_to_run=[
            "1. Save as `index.html` (or any `.html` name).",
            "2. Double-click it to open in a browser.",
        ],
        logic=[
            "The browser parses HTML and builds the page structure (DOM).",
            "`<head>` holds metadata and links; `<body>` contains visible content.",
        ],
        examples=["Input: user interacts with page elements.", "Output: browser displays content and runs scripts (if linked)."],
        edge_cases=["Broken links in `<script>` or `<link>` may prevent JS/CSS from working."],
    )
    return {"commented_code": "\n".join(out).rstrip() + "\n", "documentation": doc}


def _css_docs_and_comments(code: str, file_path: str) -> Dict[str, Any]:
    code = _clean_existing_auto_headers(code)
    out = [
        "/* ======================================= */",
        "/* Professional beginner-friendly comments */",
        "/* ======================================= */",
        f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */",
        "/* CSS controls layout, colors, spacing, and typography. */",
        "",
        code.strip(),
        "",
    ]
    doc = _doc_sectioned_no_code(
        title=_filename_title(file_path, "css"),
        what_it_does=["Styles HTML elements by applying rules to selectors."],
        requirements=["A browser + an HTML file that links this CSS."],
        how_to_run=[
            "1. Link in HTML: `<link rel='stylesheet' href='styles.css'>` inside `<head>`.",
            "2. Open the HTML file in a browser.",
            "3. Refresh to see style updates.",
        ],
        logic=[
            "Selectors choose elements to style (`body`, `.class`, `#id`).",
            "Properties define how elements should look (color, spacing, display).",
        ],
        examples=["Input: none directly.", "Output: page appearance changes."],
        edge_cases=["Wrong file path in `<link>` means styles won’t load."],
    )
    return {"commented_code": "\n".join(out).rstrip() + "\n", "documentation": doc}


def _java_docs_and_comments(code: str, file_path: str) -> Dict[str, Any]:
    code = _clean_existing_auto_headers(code)
    out = [
        "// =======================================",
        "// Professional beginner-friendly comments",
        "// =======================================",
        f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}",
        "",
        code.strip(),
        "",
    ]
    doc = _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines Java classes and methods. If a `main()` method exists, the program can run directly."],
        requirements=["Java JDK (17+ recommended)."],
        how_to_run=[
            "1. Open a terminal in the folder containing the `.java` file.",
            "2. Compile: `javac FileName.java`",
            "3. Run (if it has `main`): `java FileName`",
        ],
        logic=[
            "A Java file usually contains one public class.",
            "`main()` (if present) is the entry point that starts execution.",
        ],
        examples=["Input: depends on program (args/user input).", "Output: console prints or program actions."],
        edge_cases=["The public class name should match the filename for compilation to succeed."],
    )
    return {"commented_code": "\n".join(out).rstrip() + "\n", "documentation": doc}


# ============================================================
# Public API
# ============================================================

def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    return _python_docs_and_comments(code.replace("\r\n", "\n"), file_path)


def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")

    if language == "python":
        return _python_docs_and_comments(code_clean, file_path)
    if language == "javascript":
        return _javascript_docs_and_comments(code_clean, file_path)
    if language == "html":
        return _html_docs_and_comments(code_clean, file_path)
    if language == "css":
        return _css_docs_and_comments(code_clean, file_path)
    if language == "java":
        return _java_docs_and_comments(code_clean, file_path)

    # fallback
    doc = _doc_sectioned_no_code(
        title=_filename_title(file_path, language or "unknown"),
        what_it_does=["Part of a software project."],
        requirements=["Depends on project setup."],
        how_to_run=["Run steps depend on project setup."],
        logic=["Logic depends on the file contents."],
        examples=["Input/output depends on the program."],
        edge_cases=["No additional notes."],
    )
    return {"commented_code": code_clean.rstrip() + "\n", "documentation": doc}