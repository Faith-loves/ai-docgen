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
# Python (professional, specific)
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _summarize_python(code: str) -> Dict[str, Any]:
    tree, err = _safe_parse_python(code)
    info: Dict[str, Any] = {
        "parse_ok": tree is not None,
        "parse_error": err,
        "imports": [],
        "functions": [],  # list of dicts: {"name":..., "args":[...], "returns":bool}
        "classes": [],
        "loops": 0,
        "has_input": "input(" in code.lower(),
        "has_print": "print(" in code.lower(),
    }

    if not tree:
        # fallback regex
        info["imports"] = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", code, flags=re.M)
        info["classes"] = re.findall(r"^\s*class\s+([a-zA-Z_]\w*)", code, flags=re.M)
        info["loops"] = len(re.findall(r"\b(for|while)\b", code))
        fn_names = re.findall(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(", code, flags=re.M)
        info["functions"] = [{"name": n, "args": [], "returns": True} for n in fn_names]
        return info

    imports: List[str] = []
    functions: List[Dict[str, Any]] = []
    classes: List[str] = []
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
            arg_names = [a.arg for a in node.args.args]
            returns = any(isinstance(n, ast.Return) for n in ast.walk(node))
            functions.append({"name": node.name, "args": arg_names, "returns": returns})
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
    info["functions"] = functions
    info["classes"] = classes
    info["loops"] = loops
    return info


def _python_docs(code: str, file_path: str, info: Dict[str, Any]) -> str:
    title = _filename_title(file_path, "python")
    what: List[str] = []
    if info.get("has_input"):
        what.append("Runs in the terminal and reads user input with `input(...)`.")
    else:
        what.append("Defines functions/classes that run when executed or imported.")
    if info.get("functions"):
        what.append(f"Defines {len(info['functions'])} function(s).")
    if info.get("classes"):
        what.append(f"Defines {len(info['classes'])} class(es).")

    req = ["Python 3.10+ recommended"]

    how = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'main.py'}`",
        "3. Follow any prompts printed in the terminal (if any).",
    ]

    logic: List[str] = [
        "Imports load first (if any).",
        "Functions/classes define reusable behavior.",
        "If present, `if __name__ == '__main__'` runs the entry point.",
    ]
    if info.get("loops"):
        logic.append("Loops repeat logic until the loop condition ends.")

    examples: List[str] = []
    if info.get("has_input"):
        examples = ["Input: user types values at prompts.", "Output: text printed in the terminal."]
    else:
        examples = ["Input: function arguments when called.", "Output: return values or printed output."]

    edge: List[str] = ["User input must match expected types (numbers where numbers are required)."]
    if not info.get("parse_ok"):
        edge.insert(0, f"⚠ Python parse error: {info.get('parse_error')}")

    return _doc_sectioned_no_code(
        title=title,
        what_it_does=what,
        requirements=req,
        how_to_run=how,
        logic=logic,
        examples=examples,
        edge_cases=edge,
    )


def _python_add_comments(code: str, file_path: str, info: Dict[str, Any]) -> str:
    """
    Add comments that match the code lines:
    - Imports explained once
    - Each function gets a clear explanation based on name and return usage
    - Loops/try/except/return lines explained
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if s.startswith("import ") or s.startswith("from "):
            if not any(x.strip() == "# Imports: libraries this file needs." for x in out[-6:]):
                out.append("# Imports: libraries this file needs.")
            out.append(line)
            i += 1
            continue

        m_class = re.match(r"^(\s*)class\s+([A-Za-z_]\w*)\b", line)
        if m_class:
            indent = m_class.group(1)
            cname = m_class.group(2)
            out.append("")
            out.append(f"{indent}# Class: {cname} — groups related data and methods.")
            out.append(line)
            i += 1
            continue

        m_fn = re.match(r"^(\s*)def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:", line)
        if m_fn:
            indent = m_fn.group(1)
            fname = m_fn.group(2)
            args = m_fn.group(3).strip()

            # try to find if this function returns something from summary
            returns = True
            for f in info.get("functions", []):
                if f.get("name") == fname:
                    returns = bool(f.get("returns"))
                    break

            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# Function: {fname}()")
            if args:
                out.append(f"{indent}# Inputs: {args}")
            else:
                out.append(f"{indent}# Inputs: (none)")
            if returns:
                out.append(f"{indent}# Output: returns a value to the caller (or prints results).")
            else:
                out.append(f"{indent}# Output: performs an action (may print) and does not return a value.")
            out.append(f"{indent}# ---------------------------------------")
            out.append(line)
            i += 1
            continue

        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Loop: repeats the block below.")
            out.append(line)
            i += 1
            continue

        if re.match(r"^\s*try\s*:\s*$", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Error handling: try this block; if it fails, jump to `except`.")
            out.append(line)
            i += 1
            continue

        if re.match(r"^\s*except\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# If an error happened in `try`, this code runs instead of crashing.")
            out.append(line)
            i += 1
            continue

        if re.match(r"^\s*return\b", line):
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}# Return: send a result back to the code that called this function.")
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python(code_clean)
    documentation = _python_docs(code_clean, file_path, info)
    commented_code = _python_add_comments(code_clean, file_path, info)
    return {"commented_code": commented_code, "documentation": documentation}


# ============================================================
# JavaScript (LINE-AWARE comments)
# ============================================================

_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*\{?")
_JS_ARROW_RE = re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>")
_JS_RETURN_RE = re.compile(r"^\s*return\b")
_JS_IF_RE = re.compile(r"^\s*if\s*\(")
_JS_FOR_RE = re.compile(r"^\s*for\s*\(")
_JS_WHILE_RE = re.compile(r"^\s*while\s*\(")
_JS_TRY_RE = re.compile(r"^\s*try\s*\{?\s*$")
_JS_CATCH_RE = re.compile(r"^\s*catch\s*\(")
_JS_AWAIT_RE = re.compile(r"\bawait\b")
_JS_FETCH_RE = re.compile(r"\bfetch\s*\(")
_JS_DOM_GET_RE = re.compile(r"\b(document\.getElementById|querySelector|querySelectorAll)\b")


def _js_line_comment(line: str) -> Optional[str]:
    """
    Returns a short comment for a single JS line (when we can).
    We avoid lying: only explain obvious syntax patterns.
    """
    s = line.strip()
    if not s:
        return None

    # declarations
    if s.startswith("import "):
        return "// Import: bring in code from another file/package."
    if s.startswith("export "):
        return "// Export: make this available to other modules."

    # function declarations
    m = _JS_FUNC_RE.match(line)
    if m:
        name = m.group(1)
        args = m.group(2).strip()
        if "async" in s.split():
            return f"// Function {name}({args}): async function (can use await inside)."
        return f"// Function {name}({args}): reusable block of logic."

    m2 = _JS_ARROW_RE.match(line)
    if m2:
        name = m2.group(1)
        args = m2.group(2).strip()
        if "async" in s:
            return f"// {name}({args}): async arrow function."
        return f"// {name}({args}): arrow function."

    if s.startswith("const ") or s.startswith("let ") or s.startswith("var "):
        if "fetch(" in s:
            return "// Create a variable holding the result of an HTTP request (fetch)."
        return "// Variable: stores a value for later use."

    # control flow
    if _JS_IF_RE.match(line):
        return "// If-statement: run the next block only when the condition is true."
    if _JS_FOR_RE.match(line):
        return "// For-loop: repeat the next block for each iteration."
    if _JS_WHILE_RE.match(line):
        return "// While-loop: keep repeating while the condition stays true."
    if _JS_TRY_RE.match(line):
        return "// Try: run code that might fail; errors go to catch."
    if _JS_CATCH_RE.match(line):
        return "// Catch: runs if an error happened in try."

    # async/network/dom patterns
    if _JS_FETCH_RE.search(line):
        return "// Fetch: send an HTTP request to an API."
    if _JS_AWAIT_RE.search(line):
        return "// Await: wait for an async operation to finish before continuing."
    if _JS_DOM_GET_RE.search(line):
        return "// DOM: select an element from the page (HTML)."

    # return
    if _JS_RETURN_RE.match(line):
        return "// Return: send a value back to the caller."

    # common tiny patterns
    if "console.log" in s:
        return "// Debug: print a message to the browser/Node console."
    if "alert(" in s:
        return "// UI: show a popup message in the browser."

    return None


def _comment_js(code: str, file_path: str) -> str:
    """
    Produces per-line comments so a beginner can see what each line does.
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("/* =======================================")
    out.append("   Professional beginner-friendly comments")
    out.append("   ======================================= */")
    out.append(f"/* File: {os.path.basename(file_path) if file_path else 'pasted_code'} */")
    out.append("")

    for line in lines:
        comment = _js_line_comment(line)
        if comment:
            # keep indentation: comment at same indent level as the line
            indent = re.match(r"^\s*", line).group(0)
            out.append(f"{indent}{comment}")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _js_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "javascript"),
        what_it_does=[
            "Adds logic/behavior to a webpage (or runs as a Node.js script).",
            "Functions organize reusable logic; async code can call APIs using fetch().",
        ],
        requirements=[
            "Browser (for web JavaScript) OR Node.js (for backend scripts).",
        ],
        how_to_run=[
            "Website:",
            "1. Link the JS file in HTML: `<script src='file.js'></script>`.",
            "2. Open the HTML file in a browser and check DevTools Console.",
            "",
            "Node.js:",
            "1. Run: `node file.js`",
        ],
        logic=[
            "Variables store values used later.",
            "Functions wrap logic so it can be reused.",
            "If async/await is used, the code waits for promises to resolve.",
        ],
        examples=[
            "Input: user clicks a button / calls a function.",
            "Output: console messages, page updates, or return values.",
        ],
        edge_cases=[
            "If the script is not linked correctly in HTML, it will not run.",
            "API calls can fail if the URL is wrong or the server is down.",
        ],
    )


# ============================================================
# HTML (clean + useful)
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
            add_once("head", "<!-- <head>: metadata, title, CSS links -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: visible page content -->")
        if "<link" in s and "stylesheet" in s:
            add_once("css", "<!-- <link rel='stylesheet'>: connects CSS styling to this page -->")
        if s.startswith("<script") or "<script" in s:
            add_once("script", "<!-- <script>: loads/runs JavaScript for page behavior -->")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _html_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "html"),
        what_it_does=["Defines the page structure and content that the browser displays."],
        requirements=["A web browser (Chrome/Edge/Firefox/Safari)."],
        how_to_run=[
            "1. Save the file with a `.html` extension.",
            "2. Open it in a browser.",
        ],
        logic=[
            "HTML is parsed from top to bottom to build the page structure (DOM).",
            "`<head>` contains configuration; `<body>` contains what the user sees.",
        ],
        examples=[
            "Input: user clicks links/buttons.",
            "Output: page updates or JavaScript runs (if included).",
        ],
        edge_cases=[
            "Broken `<script src>` or `<link href>` paths can break JS/CSS.",
        ],
    )


# ============================================================
# CSS (selector-aware)
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

    # comment per rule block
    pattern = re.compile(r"([^{]+)\{([^}]*)\}", re.S)
    pos = 0
    for m in pattern.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            out.append(before)
            out.append("")
        selector = m.group(1).strip()
        body = m.group(2).strip()

        out.append(f"/* {_explain_css_selector(selector)} */")
        out.append(f"{selector} {{")
        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue
            # small inline explanations for common properties
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* spacing between items */")
            elif t.startswith("background"):
                out.append(f"  {t} /* background styling */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font-family"):
                out.append(f"  {t} /* font choice */")
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


def _css_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "css"),
        what_it_does=["Styles a webpage by changing layout, colors, spacing, and fonts."],
        requirements=["A browser + an HTML file that links this CSS using `<link rel='stylesheet'>`."],
        how_to_run=[
            "1. Link the CSS file inside the HTML `<head>`.",
            "2. Open the HTML in a browser and refresh after changes.",
        ],
        logic=[
            "Selectors choose which elements to style (`body`, `.class`, `#id`).",
            "Properties control how those elements look.",
        ],
        examples=[
            "Input: none directly.",
            "Output: the webpage appearance changes.",
        ],
        edge_cases=[
            "If the CSS file path is wrong, the browser won’t load styles.",
        ],
    )


# ============================================================
# Java (basic but accurate)
# ============================================================

def _comment_java(code: str, file_path: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        s = line.strip()

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: container for methods and data.")
            out.append(line)
            continue

        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): program entry point.")
            out.append(line)
            continue

        if re.match(r"^\s*(public|private|protected)\s+static\s+\w+\s+\w+\s*\(", s) and "main" not in s:
            out.append("// Method: reusable block of logic (takes inputs and may return a result).")
            out.append(line)
            continue

        if s.startswith("return "):
            out.append("// Return: send a value back to the caller.")
            out.append(line)
            continue

        if s.startswith("for(") or s.startswith("for ("):
            out.append("// Loop: repeat code for each iteration.")
            out.append(line)
            continue

        if s.startswith("try"):
            out.append("// Try: run code that might throw an exception.")
            out.append(line)
            continue

        if s.startswith("catch"):
            out.append("// Catch: handles errors from the try block.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _java_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines Java classes and methods; may run via `main()`."],
        requirements=["Java JDK installed (Java 17+ recommended)."],
        how_to_run=[
            "1. Open a terminal in the folder containing the `.java` file.",
            "2. Compile: `javac FileName.java`",
            "3. Run: `java FileName` (without .java)",
        ],
        logic=[
            "A class groups methods (functions).",
            "`main()` is where execution starts.",
            "Methods can return results with `return`.",
        ],
        examples=[
            "Input: running the program in the terminal.",
            "Output: console messages printed with `System.out.println`.",
        ],
        edge_cases=[
            "The public class name usually must match the filename.",
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