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
    "Professional beginner-friendly Java notes",
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
            # stop skipping after a blank line
            if line.strip() == "":
                skipping = False
            continue

        out.append(line)

    cleaned = "\n".join(out).strip()
    return cleaned + ("\n" if code.endswith("\n") else "")


# -----------------------------
# Python analysis (accurate)
# -----------------------------

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
# Python comment inference (NO guessing, only observable intent)
# -----------------------------

def _op_name(op: ast.operator) -> Optional[str]:
    if isinstance(op, ast.Add):
        return "adds"
    if isinstance(op, ast.Sub):
        return "subtracts"
    if isinstance(op, ast.Mult):
        return "multiplies"
    if isinstance(op, ast.Div):
        return "divides"
    if isinstance(op, ast.FloorDiv):
        return "floor-divides"
    if isinstance(op, ast.Mod):
        return "takes the remainder of"
    if isinstance(op, ast.Pow):
        return "raises to the power of"
    return None


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return "a function"


def _describe_return_expr(expr: ast.AST) -> str:
    """
    Describe what a RETURN does in a beginner-friendly way,
    based only on the returned expression.
    """
    # return a + b
    if isinstance(expr, ast.BinOp):
        op = _op_name(expr.op)
        if op:
            # Very common: a+b, price*quantity, etc.
            return f"Returns a value that {op} two values."

        # fallback
        return "Returns the result of a calculation."

    # return f"...{x}..."
    if isinstance(expr, ast.JoinedStr):
        return "Returns a formatted text string (an f-string)."

    # return "text"
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return "Returns a text string."

    # return 123 / 12.3 / True / None
    if isinstance(expr, ast.Constant):
        return "Returns a constant value."

    # return some_variable
    if isinstance(expr, ast.Name):
        return "Returns a previously computed value."

    # return [ ... ] or ( ... )
    if isinstance(expr, ast.List):
        return "Returns a list."
    if isinstance(expr, ast.Tuple):
        return "Returns multiple values as a tuple."

    # return { ... }
    if isinstance(expr, ast.Dict):
        return "Returns a dictionary (key/value mapping)."

    # return [x for x in items if ...]
    if isinstance(expr, ast.ListComp):
        if expr.generators and any(g.ifs for g in expr.generators):
            return "Returns a filtered list (keeps only items that match a condition)."
        return "Returns a new list built from another sequence."

    # return {k: v for ...}
    if isinstance(expr, ast.DictComp):
        return "Returns a dictionary built from another sequence."

    # return max(...), json.dumps(...), str(...), etc.
    if isinstance(expr, ast.Call):
        fn = _call_name(expr)
        if fn == "max":
            return "Returns the largest item based on a rule."
        if fn == "min":
            return "Returns the smallest item based on a rule."
        if fn == "sorted":
            return "Returns a sorted version of the data."
        if fn in ("str", "int", "float"):
            return f"Returns the value converted to {fn}."
        if fn == "join":
            return "Returns one string made by joining many strings together."
        if fn == "dumps":
            return "Returns JSON text."
        if fn == "loads":
            return "Returns data parsed from JSON text."
        return "Returns the result of calling a function."

    # return something.attr
    if isinstance(expr, ast.Attribute):
        return "Returns a value stored on an object."

    return "Returns a result value."


def _describe_side_effects(body: List[ast.stmt]) -> List[str]:
    """
    Look for clear side effects (append/pop/write/print/input) without guessing.
    """
    effects: List[str] = []

    class Finder(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> Any:
            # print(...)
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                if "Prints information to the screen." not in effects:
                    effects.append("Prints information to the screen.")
            # input(...)
            if isinstance(node.func, ast.Name) and node.func.id == "input":
                if "Reads input from the user." not in effects:
                    effects.append("Reads input from the user.")
            # obj.append(...)
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "append":
                    if "Adds an item to a list." not in effects:
                        effects.append("Adds an item to a list.")
                if node.func.attr == "pop":
                    if "Removes an item from a list." not in effects:
                        effects.append("Removes an item from a list.")
                if node.func.attr in ("write_text", "write", "writelines"):
                    if "Writes output to a file." not in effects:
                        effects.append("Writes output to a file.")
                if node.func.attr in ("read_text", "read", "readlines"):
                    if "Reads data from a file." not in effects:
                        effects.append("Reads data from a file.")
            self.generic_visit(node)

        def visit_Try(self, node: ast.Try) -> Any:
            if "Handles errors using try/except." not in effects:
                effects.append("Handles errors using try/except.")
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> Any:
            if "Uses a loop to repeat steps." not in effects:
                effects.append("Uses a loop to repeat steps.")
            self.generic_visit(node)

        def visit_While(self, node: ast.While) -> Any:
            if "Uses a loop to repeat steps." not in effects:
                effects.append("Uses a loop to repeat steps.")
            self.generic_visit(node)

    for st in body:
        Finder().visit(st)

    return effects


def _infer_function_comment(node: ast.FunctionDef, in_class: Optional[str]) -> str:
    """
    Build a single, accurate summary line for a function/method.
    - Uses return description if returns exist
    - Adds side-effects if found
    - Tries to use the function name ONLY as mild context (not guessing behavior)
    """
    # Special-case: __init__
    if node.name == "__init__" and in_class:
        return f"Initializes a new `{in_class}` object (sets up starting values)."

    # Find returns
    returns: List[ast.Return] = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    return_descs: List[str] = []
    for r in returns:
        if r.value is None:
            # `return` without value: exits early
            return_descs.append("May exit early to stop the function.")
        else:
            return_descs.append(_describe_return_expr(r.value))

    # Side effects
    effects = _describe_side_effects(node.body)

    # If we have a strong return description, use the best one
    summary = ""
    if return_descs:
        # choose the most informative (prefer ones mentioning lists/dicts/formatting)
        priority = [
            "filtered list",
            "dictionary",
            "formatted",
            "JSON",
            "calculation",
            "converted",
            "largest",
            "smallest",
        ]
        chosen = return_descs[0]
        for p in priority:
            for d in return_descs:
                if p.lower() in d.lower():
                    chosen = d
                    break
        summary = chosen
    elif effects:
        # no return -> describe side-effect-based function
        summary = effects[0]
    else:
        summary = "Performs one step of the program."

    # Make summary read like “This function …”
    # (No “returns the result of calling x” wording.)
    if summary.startswith("Returns"):
        return summary.replace("Returns", "Returns", 1)
    return summary


def _add_python_comments(code: str) -> str:
    """
    Python commenting rules (professional + accurate):
    - One header at top
    - Explain clear blocks (imports / loops / try/except) lightly
    - For each function/method: add a summary that matches observable behavior
    - NEVER insert comments between decorators and def
    - Avoid “What this program does” block (user requested)
    """
    code = _clean_existing_auto_headers(code)
    tree, _err = _safe_parse_python(code)

    lines = code.splitlines()
    out: List[str] = []

    out.append("# =======================================")
    out.append("# Professional beginner-friendly comments")
    out.append("# =======================================")
    out.append("")

    # If AST parse fails, we must be conservative (no structure-based insertion)
    if not tree:
        out.append("# Note: This file could not be fully parsed (possible indentation/syntax issue).")
        out.append("# Comments below are minimal to avoid breaking the code.")
        out.append("")
        # Minimal pass: only comment imports and top-level loops/try blocks by regex
        for line in lines:
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                out.append("# Imports: libraries used by this file.")
                out.append(line)
                continue
            if re.match(r"^\s*(for|while)\b", line):
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}# Loop: repeats the block below.")
                out.append(line)
                continue
            if re.match(r"^\s*try\s*:", line):
                indent = re.match(r"^\s*", line).group(0)
                out.append(f"{indent}# Error handling: try this block and catch errors instead of crashing.")
                out.append(line)
                continue
            out.append(line)
        return "\n".join(out).rstrip() + "\n"

    # Build a map: line number -> comment lines to insert BEFORE that line
    insert_before: Dict[int, List[str]] = {}

    # Helper to schedule insertion
    def add_before(lineno_1based: int, comment_lines: List[str]) -> None:
        idx = max(0, lineno_1based - 1)
        insert_before.setdefault(idx, [])
        # avoid duplicates
        for c in comment_lines:
            if c not in insert_before[idx]:
                insert_before[idx].append(c)

    # Walk AST: comment functions and classes
    class Stack(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            # comment class
            add_before(
                node.lineno,
                [
                    "",
                    "# ---------------------------------------",
                    f"# Class: {node.name}",
                    "# A class groups related data (attributes) and behavior (methods).",
                    "# ---------------------------------------",
                ],
            )
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            in_class = self.class_stack[-1] if self.class_stack else None

            # IMPORTANT: decorators must stay directly above def.
            # So we insert comments BEFORE the FIRST decorator if present,
            # otherwise before the def line.
            target_line = node.lineno
            if node.decorator_list:
                # decorator lineno is available in Python 3.8+ nodes
                dlines = [getattr(d, "lineno", node.lineno) for d in node.decorator_list]
                target_line = min(dlines)

            # Build accurate summary line
            summary = _infer_function_comment(node, in_class)

            header = [
                "",
                "# ---------------------------------------",
                f"# Function: {node.name}()",
                f"# {summary}",
                "# ---------------------------------------",
            ]

            add_before(target_line, header)
            self.generic_visit(node)

    Stack().visit(tree)

    # Also: comment imports once (top-of-file scan)
    for idx, line in enumerate(lines):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            add_before(idx + 1, ["# Imports: libraries used by this file."])
            break

    # Render with insertions
    for idx, line in enumerate(lines):
        if idx in insert_before:
            out.extend(insert_before[idx])
        # Add loop / try comments lightly (but don’t spam every loop inside list comps)
        if re.match(r"^\s*(for|while)\b", line):
            indent = re.match(r"^\s*", line).group(0)
            # avoid duplicates if already inserted a function header right above
            if not (out and out[-1].strip().startswith("# Loop:")):
                out.append(f"{indent}# Loop: repeats the block below.")
        if re.match(r"^\s*try\s*:", line):
            indent = re.match(r"^\s*", line).group(0)
            if not (out and out[-1].strip().startswith("# Error handling:")):
                out.append(f"{indent}# Error handling: try this block and catch errors instead of crashing.")
        out.append(line)

    return "\n".join(out).rstrip() + "\n"


def generate_python_docs(code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    """
    Produces:
    - commented_code
    - documentation (beginner-friendly, specific)
    """
    code_clean = code.replace("\r\n", "\n")
    info = _summarize_python_code(code_clean)
    loc = _count_nonempty_lines(code_clean)

    parse_note = ""
    if not info.get("parse_ok", True):
        parse_note = (
            "## Important Note\n"
            "This Python file has a syntax/indentation issue, so some deep analysis is limited.\n"
            "Fix indentation (usually 4 spaces) and try again.\n\n"
        )

    documentation = (
        f"# File Documentation - `{os.path.basename(file_path)}`\n\n"
        f"{parse_note}"
        f"## Key Components\n"
        f"- Lines of code (non-empty): **{loc}**\n"
        f"- Imports detected: **{len(info.get('imports', []))}**\n"
        f"- Loops detected: **{info.get('loops', 0)}**\n"
        f"- Functions detected: **{len(info.get('functions', []))}**\n"
        f"- Classes detected: **{len(info.get('classes', []))}**\n\n"
        f"## Inputs / Outputs\n"
        f"- **Inputs:** {'Uses terminal input (`input(...)`).' if info.get('has_input') else 'Function parameters or events.'}\n"
        f"- **Outputs:** printed text, returned values, saved files, or UI changes (depends on the code).\n\n"
        f"## How to run (step-by-step)\n"
        f"1. Open a terminal in the file folder.\n"
        f"2. Run: `python {os.path.basename(file_path)}`\n"
        f"3. Follow any prompts or UI windows.\n"
    )

    commented_code = _add_python_comments(code_clean)
    return {"commented_code": commented_code, "documentation": documentation}


# -----------------------------
# HTML (professional + accurate)
# -----------------------------

def _comment_html(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("<!-- ======================================= -->")
    out.append("<!-- Professional beginner-friendly comments -->")
    out.append("<!-- ======================================= -->")
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
            add_once("html", "<!-- <html>: the root element of the page -->")
        if s.startswith("<head"):
            add_once("head", "<!-- <head>: page settings (title, CSS links, meta tags) -->")
        if s.startswith("<title"):
            add_once("title", "<!-- <title>: text shown on the browser tab -->")
        if s.startswith("<body"):
            add_once("body", "<!-- <body>: everything the user can see on the page -->")
        if s.startswith("<header"):
            add_once("header", "<!-- <header>: top section (usually logo/title/menu) -->")
        if s.startswith("<main"):
            add_once("main", "<!-- <main>: the main content area -->")
        if s.startswith("<footer"):
            add_once("footer", "<!-- <footer>: bottom section (copyright/links) -->")
        if s.startswith("<script"):
            add_once("script", "<!-- <script>: JavaScript code that adds behavior -->")
        if "<link" in s and "href=" in s:
            add_once("csslink", "<!-- <link>: connects this HTML to a CSS file -->")

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# CSS (professional + accurate)
# -----------------------------

def _explain_css_selector(selector: str) -> str:
    sel = selector.strip()
    if sel.startswith("."):
        return f"Targets elements with class `{sel[1:]}`."
    if sel.startswith("#"):
        return f"Targets the element with id `{sel[1:]}`."
    # element selector
    return f"Targets all `<{sel}>` elements."


def _comment_css(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    text = code.strip()

    out: List[str] = []
    out.append("/* ======================================= */")
    out.append("/* Professional beginner-friendly comments */")
    out.append("/* ======================================= */")
    out.append("/* CSS controls how the page LOOKS (layout, colors, spacing, fonts). */")
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

        out.append(f"/* {_explain_css_selector(selector)} */")
        out.append(f"{selector} {{")
        for line in body.splitlines():
            t = line.strip()
            if not t:
                continue
            # small, helpful inline notes (not spam)
            if t.startswith("display:"):
                out.append(f"  {t} /* layout mode */")
            elif t.startswith("gap:"):
                out.append(f"  {t} /* space between items */")
            elif t.startswith("background"):
                out.append(f"  {t} /* background color */")
            elif t.startswith("color:"):
                out.append(f"  {t} /* text color */")
            elif t.startswith("font-family"):
                out.append(f"  {t} /* font */")
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


# -----------------------------
# Java (professional + accurate)
# -----------------------------

def _comment_java(code: str) -> str:
    code = _clean_existing_auto_headers(code)
    lines = code.splitlines()
    out: List[str] = []

    out.append("// =======================================")
    out.append("// Professional beginner-friendly comments")
    out.append("// =======================================")
    out.append("")

    for line in lines:
        s = line.strip()

        if re.match(r"^public\s+class\s+\w+", s):
            out.append("// Class: groups related methods (functions) and data.")
            out.append(line)
            continue

        if re.match(r"^public\s+static\s+void\s+main\s*\(", s):
            out.append("// main(): program entry point (starts running here).")
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
            out.append("// Return: sends a result back to whoever called this method.")
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out).rstrip() + "\n"


# -----------------------------
# JavaScript (you said it's OK)
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
# Public API: generate_simple_docs
# -----------------------------

def generate_simple_docs(language: str, code: str, file_path: str = "pasted_code") -> Dict[str, Any]:
    language = (language or "").lower().strip()
    code_clean = code.replace("\r\n", "\n")
    loc = _count_nonempty_lines(code_clean)
    filename = os.path.basename(file_path) if file_path else "pasted_code"

    # Commenting
    commented = code_clean
    if language == "html":
        commented = _comment_html(code_clean)
    elif language == "css":
        commented = _comment_css(code_clean)
    elif language == "javascript":
        commented = _comment_js(code_clean)
    elif language == "java":
        commented = _comment_java(code_clean)

    # Documentation
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