"""Guard rails: the browser app reads the contract's views and nothing else, and never loads the ingestion.

Every SQL string in the app's code (spec.app_code) is parsed by DuckDB (json_serialize_sql) to list the tables it
names, then run against the reference schema, so it also fails on a column the contract doesn't have. Imports are
checked twice: in the source (`import_problems`), and by loading everything in a fresh interpreter
(`loaded_problems`), since imports can be indirect.

An app's tests/app/test_contract_only.py calls these (the template writes it).
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb

from duckkit.spec import AppSpec

# duckkit's ingestion side: the browser app never needs it
KIT_SERVICE = {f"duckkit.{m}" for m in ("store", "backup", "privacy", "publish", "cli", "doctor", "serve", "demo")}


def src(spec: AppSpec) -> Path:
    return spec.root / "src" / spec.package


def app_files(spec: AppSpec) -> list[Path]:
    """The browser app's Python files: spec.app_code, relative to src/<package> (folders or files)."""
    found = []
    for entry in spec.app_code:
        path = src(spec) / entry
        found += sorted(path.rglob("*.py")) if path.is_dir() else [path] if path.exists() else []
    return found


def app_tests(spec: AppSpec) -> list[Path]:
    """The browser app's tests: tests/app/*.py."""
    return sorted((spec.root / "tests" / "app").glob("*.py"))


def forbidden_modules(spec: AppSpec) -> set[str]:
    """The modules the browser app must not import: the app's ingestion side, and duckkit's."""
    return {f"{spec.package}.{m}" for m in spec.forbidden} | KIT_SERVICE


def name(spec: AppSpec, path: Path) -> str:
    """`path` relative to the repo root, for messages and test ids."""
    return str(path.relative_to(spec.root))


# ─── Finding SQL in the code ───

def sql_strings(path: Path, skip_functions: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    """(line, text) of every string literal that looks like SQL (SELECT … FROM, in capitals), docstrings
    excepted. An f-string's {NAME} placeholders are filled from the module's string constants; any other
    placeholder makes the string uncheckable, so it is returned as it is and fails to parse."""
    tree = ast.parse(path.read_text())
    constants = {t.id: node.value.value for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                 for t in node.targets if isinstance(t, ast.Name)}
    skipped, docstrings = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in skip_functions:
            skipped |= {id(n) for n in ast.walk(node)}
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef) and ast.get_docstring(node) is not None:
            docstrings.add(id(node.body[0].value))
        if isinstance(node, ast.JoinedStr):  # its pieces are checked as part of the whole
            skipped |= {id(n) for n in node.values}
    found = []
    for node in ast.walk(tree):
        if id(node) in skipped or id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else
                           constants.get(v.value.id, "{?}") if isinstance(v.value, ast.Name) else "{?}"
                           for v in node.values)
        else:
            continue
        if re.search(r"\bSELECT\b", text) and re.search(r"\bFROM\b", text):
            found.append((node.lineno, text))
    return found


def tables(sql: str) -> set[str]:
    """The tables (and table functions) a statement reads, CTEs left out, as DuckDB's parser sees them."""
    tree = json.loads(duckdb.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    if tree.get("error"):
        raise ValueError(tree.get("error_message", "unparseable"))
    names, ctes = set(), set()

    def walk(node):
        """Collect table names and CTE names from every node of the parse tree."""
        if isinstance(node, dict):
            if node.get("type") == "BASE_TABLE":
                names.add(".".join(p for p in (node.get("catalog_name"), node.get("schema_name"),
                                               node["table_name"]) if p))
            elif node.get("type") == "TABLE_FUNCTION":
                names.add(f"{node['function'].get('function_name', '?')}()")
            for entry in node.get("cte_map", {}).get("map", []):
                ctes.add(entry["key"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tree)
    return names - ctes


def check_sql(spec: AppSpec, where: str, sql: str, reference: duckdb.DuckDBPyConnection) -> list[str]:
    """The problems with one SQL string of the app: it can't be parsed, reads a non-view, or doesn't run on the
    reference schema. Empty: it is fine."""
    try:
        outside = tables(sql) - set(spec.contract.views())
    except ValueError as e:
        return [f"{where}: can't parse its SQL to check it ({e})"]
    if outside:
        return [f"{where}: reads {', '.join(sorted(outside))}, which isn't one of the contract's views"]
    params = [None] * len(reference.extract_statements(sql)[0].named_parameters)
    try:
        reference.execute(sql, params)  # binds every column: only the reference schema's exist
    except duckdb.Error as e:
        return [f"{where}: doesn't run on the reference schema: {str(e).splitlines()[0]}"]
    return []


def sql_problems(spec: AppSpec) -> tuple[int, list[str]]:
    """(SQL strings checked, problems) over the whole browser app."""
    reference = spec.contract.reference()
    checked, problems = 0, []
    for path in app_files(spec):
        for line, sql in sql_strings(path):
            checked += 1
            problems += check_sql(spec, f"{name(spec, path)}:{line}", sql, reference)
    return checked, problems


# ─── Imports ───

def imports(path: Path) -> set[str]:
    """Every module that `path` imports, and every `module.name` it imports from one."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def forbidden(module: str, banned: set[str]) -> bool:
    """Whether `module` is one of `banned` or inside one."""
    return any(module == b or module.startswith(b + ".") for b in banned)


def import_problems(spec: AppSpec, path: Path) -> set[str]:
    """The forbidden modules `path` imports. The app's tests also may not import spec.forbidden_in_tests."""
    banned = forbidden_modules(spec) | (set(spec.forbidden_in_tests) if path in app_tests(spec) else set())
    return {m for m in imports(path) if forbidden(m, banned)}


def loaded_problems(spec: AppSpec, extra: tuple[str, ...] = ("tests.conftest",),
                    page_only: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """(modules loaded, forbidden ones among them) when a fresh interpreter imports the app's code, its tests and
    `extra`. Pages (`<app>.views`, `<app>.main`, and `page_only`) are left out: they run in a Streamlit session."""
    root = spec.root
    modules = [*(".".join(p.relative_to(root / "src").with_suffix("").parts) for p in app_files(spec)),
               *(".".join(p.relative_to(root).with_suffix("").parts) for p in app_tests(spec)),
               *extra]
    pages = tuple(f"{spec.package}.{a.name}.{p}" for a in spec.apps for p in ("views", "main")) + page_only
    modules = [m.removesuffix(".__init__") for m in modules if not m.startswith(pages)]
    prefixes = (spec.package, "tests", "duckkit")
    script = (f"import importlib, sys\nfor m in {modules!r}: importlib.import_module(m)\n"
              f"print(sorted(m for m in sys.modules if m.startswith({prefixes!r})))")
    out = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True, check=True).stdout
    loaded = ast.literal_eval(out)
    banned = (forbidden_modules(spec) | set(spec.forbidden_in_tests)) - set(extra)
    return loaded, [m for m in loaded if forbidden(m, banned)]


# ─── The contract's documentation ───

def doc_problems(spec: AppSpec, doc: Path) -> list[str]:
    """docs/contract.md has a `### \\`view\\`` section for every view, whose table lists its columns in order."""
    sections = dict(re.findall(r"^### `(\w+)`.*?\n(.*?)(?=^### |^## |\Z)", doc.read_text(), re.MULTILINE | re.DOTALL))
    problems = []
    for view, (_, columns) in spec.contract.descriptions().items():
        if view not in sections:
            problems.append(f"{view}: no section in {doc.name}")
            continue
        documented = re.findall(r"^\| `(\w+)`", sections[view], re.MULTILINE)
        if documented != list(columns):
            problems.append(f"{view}: {doc.name} lists {documented}, the schema has {list(columns)}")
    return problems
