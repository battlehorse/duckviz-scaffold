"""`spec-diff`: the parts of the spec that a change touches (docs/how-we-work.md).

The spec is what the app must keep doing: the docs that say what the app is for and how it is built,
the contracts and schemas, the browser checks, the guardrails, and some of the tests. `.claude/spec-paths` lists it,
in groups:

    [data]
    contract/**
    docs/contract.md

A change is a spec change when it changes a file that a pattern matches, or a **spec test**: a test marked
`@pytest.mark.spec` (or in a class or a module whose `pytestmark` holds that mark). A new spec test is not a spec
change. A spec test that changed, was removed or lost its mark is. A spec test's code includes the module-level names
it uses (helpers, constants, the lists that `parametrize` reads). A change to the pytest settings
(`[tool.pytest.ini_options]`) is a spec change too: they choose which tests run. Dependency changes are reported, not
counted.

`spec-diff` lists the files and tests that a change touches. It does not tell an extension (it adds to the spec and
keeps each promise) from a revision (it alters or removes one): the reviewer judges that.

The diff runs from the merge base with `base` to the working tree, so it covers commits and uncommitted changes.
"""

import ast
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SPEC_PATHS = ".claude/spec-paths"


@dataclass(frozen=True)
class SpecPaths:
    """The spec's files: each group, with its glob patterns (relative to the repo root, `**` for any depth)."""

    groups: dict[str, list[str]]

    def group_of(self, path: str) -> str | None:
        """The first group with a pattern that matches `path`, or None."""
        for group, patterns in self.groups.items():
            if any(PurePosixPath(path).full_match(pattern) for pattern in patterns):
                return group
        return None


@dataclass
class SpecDiff:
    """What a change does to the spec."""

    base: str
    files: dict[str, list[str]] = field(default_factory=dict)  # group → the changed files ("M docs/contract.md")
    spec_tests: list[str] = field(default_factory=list)  # "tests/test_x.py::test_y: changed"
    new_spec_tests: list[str] = field(default_factory=list)  # not a spec change
    dependencies: list[str] = field(default_factory=list)  # reported, not a spec change

    @property
    def changed(self) -> bool:
        return bool(self.files or self.spec_tests)

    def lines(self) -> list[str]:
        out = [f"Spec changes since {self.base}:" if self.changed else f"✓ no spec changes since {self.base}"]
        for group, files in self.files.items():
            out.append(f"  [{group}]")
            out += [f"    {f}" for f in files]
        if self.spec_tests:
            out.append("  [spec tests]")
            out += [f"    {t}" for t in self.spec_tests]
        if self.new_spec_tests:
            out.append("New spec tests (not a spec change):")
            out += [f"  {t}" for t in self.new_spec_tests]
        if self.dependencies:
            out.append("Dependencies (reported, not a spec change):")
            out += [f"  {d}" for d in self.dependencies]
        return out


def read_spec_paths(root: Path) -> SpecPaths:
    """Read `.claude/spec-paths`: `[group]` lines, then one pattern a line. `#` starts a comment."""
    path = root / SPEC_PATHS
    if not path.exists():
        raise ValueError(f"no {SPEC_PATHS}: it lists the spec's files (docs/spec.md)")
    groups: dict[str, list[str]] = {}
    group = None
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1].strip()
            groups.setdefault(group, [])
        elif group is None:
            raise ValueError(f"{SPEC_PATHS}:{number}: a pattern before the first [group]")
        else:
            groups[group].append(line)
    return SpecPaths(groups)


def spec_diff(root: Path, base: str = "origin/main") -> SpecDiff:
    """Compare the working tree of the repo at `root` with its merge base with `base`."""
    paths = read_spec_paths(root)
    try:
        merge_base = _git(root, "merge-base", base, "HEAD").strip()
    except ValueError as e:
        raise ValueError(f"no common commit of {base} and HEAD ({e}): fetch the base branch, or pass another --base"
                         ) from e
    result = SpecDiff(base=base)
    changes, renamed_from = _changed_files(root, merge_base)
    renamed = set(renamed_from.values())
    for status, path in changes:
        group = paths.group_of(path)
        if group:
            result.files.setdefault(group, []).append(f"{status} {path}")
        if PurePosixPath(path).name.startswith("test_") and path.endswith(".py") and path not in renamed:
            changed, new = _spec_test_changes(root, merge_base, renamed_from.get(path, path), path)
            result.spec_tests += changed
            result.new_spec_tests += new
    before, after = _read_at(root, merge_base, "pyproject.toml"), _read_now(root, "pyproject.toml")
    if _pytest_settings(before) != _pytest_settings(after):
        result.spec_tests.append("pyproject.toml [tool.pytest.ini_options]: changed")
    result.dependencies = _dependency_changes(before, after)
    return result


def _git(root: Path, *args: str) -> str:
    """git's output. A failure raises ValueError, so that spec-diff says it can't tell (exit 2)."""
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _changed_files(root: Path, merge_base: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """(status, path) for each file changed since `merge_base`: committed, uncommitted and untracked. A renamed file
    counts under both its old and its new path. Also: each renamed file's old path, by its new one."""
    changes, renamed_from = [], {}
    for line in _git(root, "diff", "--name-status", "-M", merge_base).splitlines():
        status, *names = line.split("\t")
        changes += [(status[0], name) for name in names]
        if status.startswith("R"):
            renamed_from[names[1]] = names[0]
    changes += [("A", name) for name in _git(root, "ls-files", "--others", "--exclude-standard").splitlines()]
    return changes, renamed_from


def _read_at(root: Path, commit: str, path: str) -> str | None:
    """The file's text at `commit`, or None if it didn't exist there."""
    done = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, text=True, check=False)
    return done.stdout if done.returncode == 0 else None


def _read_now(root: Path, path: str) -> str | None:
    file = root / path
    return file.read_text() if file.exists() else None


# ─── Spec tests ───

def _spec_test_changes(root: Path, merge_base: str, old_path: str, path: str) -> tuple[list[str], list[str]]:
    """The spec tests of one test file (at `old_path` before a rename) that changed, were removed or lost their
    mark; and the new ones."""
    try:
        before_marked, _ = _tests(_read_at(root, merge_base, old_path))
        after_marked, after_all = _tests(_read_now(root, path))
    except SyntaxError as e:  # spec-diff can't tell what changed: exit 2, not 1
        raise ValueError(f"{path} does not parse: {e}") from e
    changed = []
    for name, body in before_marked.items():
        if name not in after_marked:
            changed.append(f"{path}::{name}: {'unmarked' if name in after_all else 'removed'}")
        elif after_marked[name] != body:
            changed.append(f"{path}::{name}: changed")
    new = [f"{path}::{name}" for name in after_marked if name not in before_marked]
    return changed, new


def _tests(source: str | None) -> tuple[dict[str, str], set[str]]:
    """The spec tests in a test module (name → its code, with the module-level code it uses, without line numbers),
    and the names of all its tests."""
    if source is None:
        return {}, set()
    module = ast.parse(source)
    definitions = _module_definitions(module)
    module_marked = any(_holds_spec_mark(node.value) for node in module.body
                        if isinstance(node, ast.Assign) and any(_is_name(t, "pytestmark") for t in node.targets))
    marked, names = {}, set()
    for node, owner, prefix in _test_functions(module):
        name = prefix + node.name
        names.add(name)
        class_marked = owner is not None and _class_marked(owner)
        if module_marked or class_marked or any(_holds_spec_mark(d) for d in node.decorator_list):
            known = definitions | (_class_definitions(owner) if owner else {})  # a class's own names come first
            used = sorted(_uses(node, known) - {node.name})
            marked[name] = ast.dump(node) + "".join(ast.dump(known[n]) for n in used)
    return marked, names


def _class_marked(cls: ast.ClassDef) -> bool:
    """Whether a test class holds the spec mark: as a decorator, or in a `pytestmark` of its body."""
    return any(_holds_spec_mark(d) for d in cls.decorator_list) or any(
        _holds_spec_mark(node.value) for node in cls.body
        if isinstance(node, ast.Assign) and any(_is_name(t, "pytestmark") for t in node.targets))


def _class_definitions(cls: ast.ClassDef) -> dict[str, ast.AST]:
    """The names a test class defines in its body: its attributes (a list that `parametrize` reads) and its methods
    (a helper the tests call as `self.helper`)."""
    return _module_definitions(ast.Module(body=cls.body, type_ignores=[]))


def _module_definitions(module: ast.Module) -> dict[str, ast.AST]:
    """The node of each name the module defines at its top level: functions, classes, assignments and imports."""
    found: dict[str, ast.AST] = {}
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found[node.name] = node
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                found |= {name.id: node for name in ast.walk(target) if isinstance(name, ast.Name)}
        elif isinstance(node, ast.Import | ast.ImportFrom):
            found |= {(alias.asname or alias.name).split(".")[0]: node for alias in node.names}
    return found


def _uses(node: ast.AST, definitions: dict[str, ast.AST]) -> set[str]:
    """The names of `definitions` that `node` uses, and the names those use in turn. A function's arguments count: a
    fixture defined in the module is a function of that name. So does `self.<name>`: a method or an attribute of
    the test's class."""
    def direct(of: ast.AST) -> set[str]:
        names = {n.id for n in ast.walk(of) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(of) if isinstance(n, ast.Attribute) and _is_name(n.value, "self")}
        if isinstance(of, ast.FunctionDef | ast.AsyncFunctionDef):
            names |= {a.arg for a in of.args.args}
        return names & definitions.keys()

    found: set[str] = set()
    todo = direct(node)
    while todo:
        name = todo.pop()
        found.add(name)
        todo |= direct(definitions[name]) - found
    return found


def _test_functions(module: ast.Module):
    """Each test function: (its node, its class or None, its class prefix)."""
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            yield node, None, ""
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name.startswith("test"):
                    yield item, node, f"{node.name}::"


def _holds_spec_mark(expr: ast.expr) -> bool:
    """Whether `expr` is `pytest.mark.spec` (or `mark.spec`, called or not), or a list or tuple that holds it."""
    if isinstance(expr, ast.List | ast.Tuple):
        return any(_holds_spec_mark(e) for e in expr.elts)
    if isinstance(expr, ast.Call):
        expr = expr.func
    if not (isinstance(expr, ast.Attribute) and expr.attr == "spec"):
        return False
    parent = expr.value
    return _is_name(parent, "mark") or (isinstance(parent, ast.Attribute) and parent.attr == "mark")


def _is_name(expr: ast.expr, name: str) -> bool:
    return isinstance(expr, ast.Name) and expr.id == name


# ─── pytest settings and dependencies ───

def _pytest_settings(pyproject: str | None) -> dict:
    """The `[tool.pytest.ini_options]` table: it chooses which tests run (markers, `addopts`, paths)."""
    if pyproject is None:
        return {}
    return tomllib.loads(pyproject).get("tool", {}).get("pytest", {}).get("ini_options", {})


def _dependency_changes(before: str | None, after: str | None) -> list[str]:
    """The dependencies added, removed or changed in pyproject.toml, in every list (the project's, its extras, its
    dependency groups)."""
    old, new = _dependencies(before), _dependencies(after)
    changes = [f"{where}: added {new[where, package]}" for where, package in new if (where, package) not in old]
    changes += [f"{where}: removed {old[where, package]}" for where, package in old if (where, package) not in new]
    changes += [f"{where}: {old[where, package]} → {new[where, package]}" for where, package in new
                if (where, package) in old and old[where, package] != new[where, package]]
    return changes


def _dependencies(pyproject: str | None) -> dict[tuple[str, str], str]:
    """Each dependency's requirement, by its list and its package name: ("group dev", "pytest") → "pytest>=9"."""
    if pyproject is None:
        return {}
    data = tomllib.loads(pyproject)
    lists = {"project": data.get("project", {}).get("dependencies", [])}
    lists |= {f"extra {k}": v for k, v in data.get("project", {}).get("optional-dependencies", {}).items()}
    lists |= {f"group {k}": v for k, v in data.get("dependency-groups", {}).items()}
    found = {}
    for list_name, requirements in lists.items():
        for requirement in requirements:
            if isinstance(requirement, str):  # a dependency group can include another group: a table, skipped
                package = re.split(r"[\s<>=!~;\[@]", requirement, maxsplit=1)[0].lower()
                found[list_name, package] = requirement
    return found


if __name__ == "__main__":  # a repo without an app CLI (the scaffold itself): python -m duckkit.specdiff [--base X]
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="python -m duckkit.specdiff", description="What a branch changes in the spec.")
    parser.add_argument("--base", default="origin/main", help="The branch to compare with (from its merge base).")
    try:
        found = spec_diff(Path.cwd(), parser.parse_args().base)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(2)
    print("\n".join(found.lines()))
    sys.exit(1 if found.changed else 0)
