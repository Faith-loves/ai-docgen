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

    Strategy:
    - If we see any known marker, we skip lines until we hit the first blank line.
    - This removes the whole header block cleanly.
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
    Docs structure WITHOUT the "code" section (as requested).
    """
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")

    # Your requested structure (without code section)
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


def _indent_of(line: str) -> str:
    return re.match(r"^\s*", line).group(0)


# ============================================================
# PYTHON (universal, AST-based meaning)
# ============================================================

def _safe_parse_python(code: str) -> Tuple[Optional[ast.AST], Optional[str]]:
    try:
        return ast.parse(code), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _py_expr_to_english(expr: ast.AST) -> str:
    """
    Convert a Python expression into a beginner-friendly description.
    IMPORTANT: We do not guess; we describe visible operations only.
    """
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, str):
            return "a text value"
        if expr.value is None:
            return "None"
        return "a constant value"

    if isinstance(expr, ast.Name):
        return f"the value of `{expr.id}`"

    if isinstance(expr, ast.Attribute):
        base = _py_expr_to_english(expr.value)
        return f"{base}.{expr.attr}"

    if isinstance(expr, ast.Call):
        fn = expr.func
        fn_name = ""
        if isinstance(fn, ast.Name):
            fn_name = fn.id
        elif isinstance(fn, ast.Attribute):
            fn_name = fn.attr
        else:
            fn_name = "a function"

        return f"the result of calling `{fn_name}(...)`"

    if isinstance(expr, ast.BinOp):
        left = _py_expr_to_english(expr.left)
        right = _py_expr_to_english(expr.right)

        if isinstance(expr.op, ast.Add):
            return f"the sum of {left} and {right}"
        if isinstance(expr.op, ast.Sub):
            return f"the difference between {left} and {right}"
        if isinstance(expr.op, ast.Mult):
            return f"the product of {left} and {right}"
        if isinstance(expr.op, ast.Div):
            return f"{left} divided by {right}"
        return "a computed value"

    if isinstance(expr, ast.Compare):
        return "a true/false comparison result"

    if isinstance(expr, ast.Dict):
        return "a dictionary (key-value mapping)"

    if isinstance(expr, ast.List):
        return "a list of values"

    if isinstance(expr, ast.Tuple):
        return "a tuple of values"

    if isinstance(expr, ast.JoinedStr):
        return "a formatted text (f-string)"

    return "a computed value"


def _summarize_python(code: str) -> Dict[str, Any]:
    tree, err = _safe_parse_python(code)
    info: Dict[str, Any] = {
        "parse_ok": tree is not None,
        "parse_error": err,
        "imports": [],
        "classes": [],
        "loops": 0,
        "has_input": "input(" in code.lower(),
        "has_print": "print(" in code.lower(),
        # functions: list of dicts:
        # {name, args, returns_value(bool), return_desc(str|None)}
        "functions": [],
    }

    if not tree:
        # fallback regex (limited)
        info["imports"] = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", code, flags=re.M)
        info["classes"] = re.findall(r"^\s*class\s+([a-zA-Z_]\w*)", code, flags=re.M)
        info["loops"] = len(re.findall(r"\b(for|while)\b", code))
        fn_names = re.findall(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(", code, flags=re.M)
        info["functions"] = [{"name": n, "args": [], "returns_value": True, "return_desc": None} for n in fn_names]
        return info

    imports: List[str] = []
    classes: List[str] = []
    loops = 0
    functions: List[Dict[str, Any]] = []

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

        def visit_For(self, node: ast.For) -> Any:
            nonlocal loops
            loops += 1
            self.generic_visit(node)

        def visit_While(self, node: ast.While) -> Any:
            nonlocal loops
            loops += 1
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            arg_names = [a.arg for a in node.args.args]

            # Find return statements and describe the most informative one
            return_nodes = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
            returns_value = any(r.value is not None for r in return_nodes)

            return_desc: Optional[str] = None
            for r in return_nodes:
                if r.value is not None:
                    return_desc = _py_expr_to_english(r.value)
                    break

            functions.append(
                {
                    "name": node.name,
                    "args": arg_names,
                    "returns_value": returns_value,
                    "return_desc": return_desc,
                }
            )
            self.generic_visit(node)

    V().visit(tree)

    info["imports"] = sorted(set(imports))
    info["classes"] = classes
    info["loops"] = loops
    info["functions"] = functions
    return info


def _python_docs(code: str, file_path: str, info: Dict[str, Any]) -> str:
    title = _filename_title(file_path, "python")

    what: List[str] = []
    if info.get("has_input"):
        what.append("Runs in the terminal and reads user input using `input(...)`.")
    else:
        what.append("Defines functions/classes and runs code when executed (or when functions are called).")

    if info.get("functions"):
        what.append(f"Defines {len(info['functions'])} function(s) to organize logic.")
    if info.get("classes"):
        what.append(f"Defines {len(info['classes'])} class(es) for structure.")

    req = ["Python 3.10+ recommended"]

    how = [
        "1. Open a terminal in the folder containing the file.",
        f"2. Run: `python {os.path.basename(file_path) if file_path else 'main.py'}`",
        "3. Follow any prompts printed in the terminal (if any).",
    ]

    logic: List[str] = [
        "Imports run first (if any).",
        "Function/class definitions set up reusable parts of the program.",
        "If present, `if __name__ == '__main__'` runs the entry point.",
    ]
    if info.get("loops"):
        logic.append("Loops repeat blocks of code until the loop ends or the program exits.")

    examples: List[str] = []
    if info.get("has_input"):
        examples = [
            "Input: user types values when prompted.",
            "Output: messages or results printed in the terminal.",
        ]
    else:
        examples = [
            "Input: function arguments (when functions are called).",
            "Output: return values and/or printed output depending on the code.",
        ]

    edge: List[str] = []
    if not info.get("parse_ok"):
        edge.append(f"⚠ Python parse error: {info.get('parse_error')}")
        edge.append("Fix indentation/syntax to improve comment accuracy.")
    edge.append("If a function expects numbers, passing text may cause errors unless handled.")
    edge.append("If the script reads files, the file path must exist.")

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
    Universal Python comments that are:
    - line-aware (placed directly above relevant lines)
    - specific (return descriptions describe actual operations)
    - not spammy (no useless repeated blocks)
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append(f"# File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    fn_map: Dict[str, Dict[str, Any]] = {f["name"]: f for f in info.get("functions", []) if isinstance(f, dict)}

    for line in lines:
        s = line.strip()
        indent = _indent_of(line)

        # imports
        if s.startswith("import ") or s.startswith("from "):
            out.append(f"{indent}# Import: bring in libraries this file needs.")
            out.append(line)
            continue

        # class
        m_class = re.match(r"^(\s*)class\s+([A-Za-z_]\w*)\b", line)
        if m_class:
            cname = m_class.group(2)
            out.append("")
            out.append(f"{indent}# Class: `{cname}` groups related data and methods.")
            out.append(line)
            continue

        # function
        m_fn = re.match(r"^(\s*)def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:", line)
        if m_fn:
            fname = m_fn.group(2)
            args_raw = m_fn.group(3).strip()

            meta = fn_map.get(fname, {})
            returns_value = bool(meta.get("returns_value", True))
            return_desc = meta.get("return_desc")

            out.append("")
            out.append(f"{indent}# ---------------------------------------")
            out.append(f"{indent}# Function: {fname}()")
            if args_raw:
                out.append(f"{indent}# Inputs: {args_raw}")
            else:
                out.append(f"{indent}# Inputs: (none)")

            if returns_value:
                if return_desc:
                    out.append(f"{indent}# Output: returns {return_desc}.")
                else:
                    out.append(f"{indent}# Output: returns a value to the caller.")
            else:
                out.append(f"{indent}# Output: performs an action (side effects) and returns nothing.")
            out.append(f"{indent}# ---------------------------------------")

            out.append(line)
            continue

        # try/except
        if re.match(r"^\s*try\s*:\s*$", line):
            out.append(f"{indent}# Error handling: run code that might fail; errors go to `except`.")
            out.append(line)
            continue

        if re.match(r"^\s*except\b", line):
            out.append(f"{indent}# If an error happened above, handle it here instead of crashing.")
            out.append(line)
            continue

        # loops
        if re.match(r"^\s*(for|while)\b", line):
            out.append(f"{indent}# Loop: repeat the next block multiple times.")
            out.append(line)
            continue

        # return
        if re.match(r"^\s*return\b", line):
            out.append(f"{indent}# Return: send a result back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python(code_clean)
    documentation = _python_docs(code_clean, file_path, info)
    commented_code = _python_add_comments(code_clean, file_path, info)
    return {"commented_code": commented_code, "documentation": documentation}


# ============================================================
# JAVASCRIPT (universal, line-aware, less ugly)
# ============================================================

_JS_FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*\{?")
_JS_ARROW_RE = re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(?(.+?)\)?\s*=>")
_JS_RETURN_RE = re.compile(r"^\s*return\b")
_JS_IF_RE = re.compile(r"^\s*if\s*\(")
_JS_FOR_RE = re.compile(r"^\s*for\s*\(")
_JS_WHILE_RE = re.compile(r"^\s*while\s*\(")
_JS_TRY_RE = re.compile(r"^\s*try\s*\{?\s*$")
_JS_CATCH_RE = re.compile(r"^\s*catch\s*\(")


def _js_return_desc(line: str) -> Optional[str]:
    """
    Try to describe what is being returned, based only on visible syntax.
    """
    s = line.strip()
    if not s.startswith("return"):
        return None

    # return a + b
    if re.search(r"return\s+.+\s*\+\s*.+", s):
        return "Return: send back the result of an addition/concatenation."

    # return `Hello ${name}`
    if "`" in s and "${" in s:
        return "Return: send back a formatted text (template string)."

    # return someFunction(...)
    if re.search(r"return\s+[A-Za-z_]\w*\s*\(", s):
        return "Return: send back the result of calling a function."

    # return object/array literal
    if re.search(r"return\s+\{", s):
        return "Return: send back an object (key-value data)."
    if re.search(r"return\s+\[", s):
        return "Return: send back an array (list of values)."

    return "Return: send a value back to the caller."


def _js_line_comment(line: str) -> Optional[str]:
    """
    Returns a short comment for a single JS line when we can.
    Universal rules:
    - explain syntax patterns without guessing behavior
    - comments should match the exact next line
    """
    s = line.strip()
    if not s:
        return None

    # obvious broken line like: aler
    if re.fullmatch(r"[A-Za-z_]\w*", s) and s not in ("true", "false", "null", "undefined"):
        return f"// ⚠ Possible typo or incomplete statement: `{s}`"

    # import/export
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
            return f"// Function: {name}({args}) — async function (can use await)."
        return f"// Function: {name}({args}) — reusable block of logic."

    # arrow functions
    m2 = _JS_ARROW_RE.match(line)
    if m2:
        name = m2.group(1)
        args = (m2.group(2) or "").strip()
        if "async" in s:
            return f"// Function: {name}({args}) — async arrow function."
        return f"// Function: {name}({args}) — arrow function."

    # variables
    if s.startswith("const ") or s.startswith("let ") or s.startswith("var "):
        if "prompt(" in s:
            return "// Input: ask the user for a value (browser prompt)."
        if "fetch(" in s:
            return "// Network: start an HTTP request using fetch()."
        return "// Variable: store a value for later use."

    # control flow
    if _JS_IF_RE.match(line):
        return "// If: run the next block only when the condition is true."
    if _JS_FOR_RE.match(line):
        return "// For-loop: repeat the next block for each iteration."
    if _JS_WHILE_RE.match(line):
        return "// While-loop: keep repeating while the condition stays true."
    if _JS_TRY_RE.match(line):
        return "// Try: run code that might throw an error."
    if _JS_CATCH_RE.match(line):
        return "// Catch: handle errors from the try block."

    # return
    if _JS_RETURN_RE.match(line):
        return _js_return_desc(line)

    # common browser/node patterns
    if "console.log" in s:
        return "// Debug: print a message to the console."
    if "alert(" in s:
        return "// UI: show a popup message in the browser."
    if "fetch(" in s:
        return "// Fetch: send an HTTP request to an API."
    if "await " in s:
        return "// Await: wait for an async operation to finish."

    if any(x in s for x in ["document.querySelector", "document.getElementById", "querySelectorAll"]):
        return "// DOM: select an element from the page."
    if ".addEventListener" in s:
        return "// Event: run code when a user interaction happens (click, input, etc.)."

    return None


def _comment_js(code: str, file_path: str) -> str:
    """
    Produces line-aware comments:
    - comment is placed directly above the line it describes
    - avoids big ugly block comment spam
    """
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append(f"// File: {os.path.basename(file_path) if file_path else 'pasted_code'}")
    out.append("")

    for line in lines:
        comment = _js_line_comment(line)
        if comment:
            out.append(f"{_indent_of(line)}{comment}")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _js_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "javascript"),
        what_it_does=[
            "Adds logic/behavior to a webpage (or runs as a Node.js script).",
            "Functions organize reusable logic; async code can call APIs using fetch().",
        ],
        requirements=["Browser (web) OR Node.js (backend scripts)."],
        how_to_run=[
            "Website:",
            "1. Link the JS file in HTML: `<script src='file.js'></script>`.",
            "2. Open the HTML file in a browser and check DevTools Console.",
            "",
            "Node.js:",
            "1. Run: `node file.js`",
        ],
        logic=[
            "Variables store values for later use.",
            "Functions group steps into reusable blocks.",
            "If async/await is used, the code waits for promises to resolve before continuing.",
        ],
        examples=[
            "Input: user clicks a button / enters text / calls a function.",
            "Output: console messages, popups, DOM updates, or return values.",
        ],
        edge_cases=[
            "If the script is not linked correctly in HTML, it will not run.",
            "API calls can fail if the URL is wrong or the server is down.",
        ],
    )


# ============================================================
# HTML (universal, line-aware but not spammy)
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

    def add_once(key: str, text: str):
        if key not in seen:
            out.append(text)
            seen.add(key)

    for line in lines:
        s = line.strip().lower()

        if s.startswith("<!doctype"):
            add_once("doctype", "<!-- DOCTYPE: tells the browser this is HTML5 -->")

        if s.startswith("<html"):
            add_once("html", "<!-- <html>: root element wrapping the whole page -->")

        if s.startswith("<head"):
            add_once("head", "<!-- <head>: metadata, title, and links to CSS/JS -->")

        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")

        if "<meta" in s:
            add_once("meta", "<!-- <meta>: page configuration (charset, viewport, etc.) -->")

        if "<link" in s and "stylesheet" in s:
            add_once("css", "<!-- <link rel='stylesheet'>: loads a CSS file for styling -->")

        if s.startswith("<body"):
            add_once("body", "<!-- <body>: visible page content -->")

        if "<form" in s:
            add_once("form", "<!-- <form>: collects user input -->")

        if "<input" in s:
            add_once("input", "<!-- <input>: user data entry field -->")

        if "<button" in s:
            add_once("button", "<!-- <button>: clickable action element -->")

        if "<script" in s:
            add_once("script", "<!-- <script>: loads/runs JavaScript for behavior -->")

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
            "HTML is parsed top-to-bottom to build the page structure (DOM).",
            "`<head>` contains setup; `<body>` contains visible content.",
        ],
        examples=[
            "Input: user clicks links/buttons or types into form fields.",
            "Output: the page updates or JavaScript runs (if included).",
        ],
        edge_cases=[
            "Broken `<script src>` or `<link href>` paths can prevent JS/CSS from loading.",
        ],
    )


# ============================================================
# CSS (selector-aware + inline property hints)
# ============================================================

def _explain_css_selector(selector: str) -> str:
    sel = selector.strip()
    if sel.startswith("."):
        return f"Targets elements with class `{sel[1:]}`."
    if sel.startswith("#"):
        return f"Targets the element with id `{sel[1:]}`."
    if sel.startswith("@media"):
        return "Applies styles only under certain screen conditions (responsive design)."
    return f"Targets elements matching `{sel}`."


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
    # NOTE: This is a best-effort parser; it handles typical CSS blocks well.
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

        for raw_line in body.splitlines():
            t = raw_line.strip()
            if not t:
                continue

            # Small, universal inline hints for common properties
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("flex"):
                out.append(f"  {t} /* flexbox layout setting */")
            elif t.startswith("grid"):
                out.append(f"  {t} /* grid layout setting */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* spacing between items */")
            elif t.startswith("background"):
                out.append(f"  {t} /* background styling */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font"):
                out.append(f"  {t} /* font styling */")
            elif t.startswith("padding"):
                out.append(f"  {t} /* inner spacing */")
            elif t.startswith("margin"):
                out.append(f"  {t} /* outer spacing */")
            elif t.startswith("width") or t.startswith("max-width") or t.startswith("min-width"):
                out.append(f"  {t} /* sizing */")
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
            "Media queries (`@media`) apply styles conditionally for responsive design.",
        ],
        examples=[
            "Input: none directly.",
            "Output: the webpage appearance changes.",
        ],
        edge_cases=[
            "If the CSS file path is wrong, the browser won’t load styles.",
            "Some properties override others depending on selector specificity.",
        ],
    )


# ============================================================
# JAVA (more structured + line-aware)
# ============================================================

_JAVA_CLASS_RE = re.compile(r"^\s*public\s+class\s+([A-Za-z_]\w*)")
_JAVA_MAIN_RE = re.compile(r"^\s*public\s+static\s+void\s+main\s*\(")
_JAVA_METHOD_RE = re.compile(
    r"^\s*(public|private|protected)\s+(static\s+)?([A-Za-z_]\w*(?:<.*?>)?)\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*\{?"
)
_JAVA_RETURN_RE = re.compile(r"^\s*return\b")
_JAVA_FOR_RE = re.compile(r"^\s*for\s*\(")
_JAVA_WHILE_RE = re.compile(r"^\s*while\s*\(")
_JAVA_TRY_RE = re.compile(r"^\s*try\s*\{?")
_JAVA_CATCH_RE = re.compile(r"^\s*catch\s*\(")


def _java_method_comment(ret_type: str, name: str, args: str) -> str:
    # Explain method signature without guessing its deeper intent.
    a = args.strip() if args.strip() else "(none)"
    if ret_type == "void":
        return f"// Method: {name}({a}) — performs an action (no return value)."
    return f"// Method: {name}({a}) — returns a `{ret_type}` result."


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
        indent = _indent_of(line)

        m_cls = _JAVA_CLASS_RE.match(line)
        if m_cls:
            out.append(f"{indent}// Class: `{m_cls.group(1)}` groups methods and data.")
            out.append(line)
            continue

        if _JAVA_MAIN_RE.match(line):
            out.append(f"{indent}// main(): program entry point (execution starts here).")
            out.append(line)
            continue

        m_m = _JAVA_METHOD_RE.match(line)
        if m_m and " main" not in line:
            ret_type = m_m.group(3)
            name = m_m.group(4)
            args = m_m.group(5)
            out.append(f"{indent}{_java_method_comment(ret_type, name, args)}")
            out.append(line)
            continue

        if _JAVA_FOR_RE.match(line):
            out.append(f"{indent}// Loop: repeat the next block for each iteration.")
            out.append(line)
            continue

        if _JAVA_WHILE_RE.match(line):
            out.append(f"{indent}// Loop: keep repeating while the condition stays true.")
            out.append(line)
            continue

        if _JAVA_TRY_RE.match(line):
            out.append(f"{indent}// Try: run code that might throw an exception.")
            out.append(line)
            continue

        if _JAVA_CATCH_RE.match(line):
            out.append(f"{indent}// Catch: handle exceptions from the try block.")
            out.append(line)
            continue

        if _JAVA_RETURN_RE.match(line):
            out.append(f"{indent}// Return: send a result back to the caller.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def _java_docs(file_path: str) -> str:
    return _doc_sectioned_no_code(
        title=_filename_title(file_path, "java"),
        what_it_does=["Defines Java classes and methods; may run via `main()` if present."],
        requirements=["Java JDK installed (Java 17+ recommended)."],
        how_to_run=[
            "1. Open a terminal in the folder containing the `.java` file.",
            "2. Compile: `javac FileName.java`",
            "3. Run: `java FileName` (without .java)",
        ],
        logic=[
            "A class groups methods (functions) and fields (data).",
            "`main()` is where execution starts.",
            "Methods can return results using `return` (unless return type is `void`).",
        ],
        examples=[
            "Input: running the program in the terminal.",
            "Output: console messages printed using `System.out.println`.",
        ],
        edge_cases=[
            "The public class name usually must match the filename for compilation.",
            "If the code reads files, the file must exist and path must be correct.",
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

    return {"commented_code": commented.rstrip() + "\n", "documentation": documentation
}