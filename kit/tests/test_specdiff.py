"""spec-diff: which changes touch the spec (the files in .claude/spec-paths, and the spec tests), and which are
only reported (dependencies)."""

import subprocess
from textwrap import dedent

import pytest

from duckkit.specdiff import read_spec_paths, spec_diff

SPEC_PATHS = """\
# The spec of a test app
[purpose]
docs/dashboard.md

[data]
contract/**   # every file of the contract
"""

TESTS = '''\
import pytest


@pytest.mark.spec
def test_totals_reconcile():
    assert 1 + 1 == 2


@pytest.mark.spec
def test_a_merge_moves_the_spend():
    assert True


def test_a_helper():
    assert "a".upper() == "A"
'''

PYPROJECT = """\
[project]
name = "shop"
dependencies = ["duckdb>=1.5.6,<2", "typer>=0.27"]

[dependency-groups]
dev = ["pytest>=9"]
"""


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repo whose `main` holds the spec paths, a doc, the contract, two spec tests and a pyproject, with a branch
    `work` checked out."""
    files = {".claude/spec-paths": SPEC_PATHS, "docs/dashboard.md": "# Questions\n", "contract/schema.sql": "-- v1\n",
             "docs/notes.md": "notes\n", "tests/test_logic.py": TESTS, "pyproject.toml": PYPROJECT}
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "start")
    git(tmp_path, "switch", "-q", "-c", "work")
    return tmp_path


def edit(repo, path, old, new):
    file = repo / path
    file.write_text(file.read_text().replace(old, new))


def test_no_change_is_no_spec_change(repo):
    diff = spec_diff(repo, "main")
    assert not diff.changed and diff.lines() == ["✓ no spec changes since main"]


def test_a_change_outside_the_spec_is_not_a_spec_change(repo):
    edit(repo, "docs/notes.md", "notes", "more notes")
    edit(repo, "tests/test_logic.py", '"a".upper() == "A"', '"b".upper() == "B"')  # an unmarked test
    (repo / "tests" / "test_new.py").write_text("def test_more():\n    assert True\n")
    assert not spec_diff(repo, "main").changed


def test_changed_spec_files_are_grouped(repo):
    edit(repo, "docs/dashboard.md", "Questions", "The questions")
    (repo / "contract" / "rules.sql").write_text("-- new\n")  # untracked
    git(repo, "commit", "-q", "-am", "doc")  # committed and uncommitted changes both count
    diff = spec_diff(repo, "main")
    assert diff.changed and diff.files == {"purpose": ["M docs/dashboard.md"], "data": ["A contract/rules.sql"]}


def test_a_spec_test_that_changed_was_removed_or_lost_its_mark_is_a_spec_change(repo):
    edit(repo, "tests/test_logic.py", "1 + 1 == 2", "2 + 2 == 4")
    edit(repo, "tests/test_logic.py", "@pytest.mark.spec\ndef test_a_merge", "def test_a_merge")
    diff = spec_diff(repo, "main")
    assert diff.spec_tests == ["tests/test_logic.py::test_totals_reconcile: changed",
                               "tests/test_logic.py::test_a_merge_moves_the_spend: unmarked"]
    (repo / "tests" / "test_logic.py").unlink()
    assert len(spec_diff(repo, "main").spec_tests) == 2  # both removed


def test_moving_a_spec_test_down_the_file_is_not_a_change(repo):
    edit(repo, "tests/test_logic.py", "import pytest\n", "import pytest\n\n\nCONSTANT = 1\n")
    assert not spec_diff(repo, "main").changed


def test_a_new_spec_test_is_listed_but_is_not_a_spec_change(repo):
    (repo / "tests" / "test_more.py").write_text(dedent('''\
        import pytest

        pytestmark = [pytest.mark.spec]


        class TestRestore:
            def test_every_decision_comes_back(self):
                assert True
        '''))
    diff = spec_diff(repo, "main")
    assert not diff.changed
    assert diff.new_spec_tests == ["tests/test_more.py::TestRestore::test_every_decision_comes_back"]


def test_dependency_changes_are_reported_not_counted(repo):
    edit(repo, "pyproject.toml", '"typer>=0.27"', '"typer>=0.28", "pandas>=2"')
    edit(repo, "pyproject.toml", 'dev = ["pytest>=9"]', "dev = []")
    diff = spec_diff(repo, "main")
    assert not diff.changed
    assert diff.dependencies == ["project: added pandas>=2", "group dev: removed pytest>=9",
                                 "project: typer>=0.27 → typer>=0.28"]


def test_spec_paths_must_start_with_a_group(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "spec-paths").write_text("docs/**\n")
    with pytest.raises(ValueError, match="before the first"):
        read_spec_paths(tmp_path)


def test_a_repo_without_spec_paths_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no .claude/spec-paths"):
        read_spec_paths(tmp_path)


def test_a_test_file_that_does_not_parse_is_an_error_not_a_change(repo):
    edit(repo, "tests/test_logic.py", "1 + 1 == 2", "1 + 1 ==")
    with pytest.raises(ValueError, match="tests/test_logic.py does not parse"):
        spec_diff(repo, "main")


def test_an_unknown_base_is_an_error(repo):
    with pytest.raises(ValueError, match="no common commit of nowhere and HEAD"):
        spec_diff(repo, "nowhere")


def test_a_change_to_what_a_spec_test_uses_is_a_spec_change(repo):
    (repo / "tests" / "test_cases.py").write_text(dedent('''\
        import pytest

        CASES = [(1, 2), (2, 3)]


        def plus_one(x):
            return x + 1


        @pytest.mark.spec
        @pytest.mark.parametrize("x, y", CASES)
        def test_plus_one(x, y):
            assert plus_one(x) == y
        '''))
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "cases")
    git(repo, "switch", "-q", "-c", "later")
    edit(repo, "tests/test_cases.py", "CASES = [(1, 2), (2, 3)]", "CASES = []")  # the test now runs nothing
    assert spec_diff(repo, "work").spec_tests == ["tests/test_cases.py::test_plus_one: changed"]
    edit(repo, "tests/test_cases.py", "CASES = []", "CASES = [(1, 2), (2, 3)]")
    edit(repo, "tests/test_cases.py", "return x + 1", "return 2 * x")
    assert spec_diff(repo, "work").spec_tests == ["tests/test_cases.py::test_plus_one: changed"]


def test_a_renamed_test_file_compares_with_its_old_path(repo):
    git(repo, "mv", "tests/test_logic.py", "tests/test_rules.py")
    diff = spec_diff(repo, "main")
    assert diff.spec_tests == [] and diff.new_spec_tests == []


def test_a_change_to_the_pytest_settings_is_a_spec_change(repo):
    edit(repo, "pyproject.toml", "[dependency-groups]", '[tool.pytest.ini_options]\naddopts = "-m \'not spec\'"\n\n[dependency-groups]')
    assert spec_diff(repo, "main").spec_tests == ["pyproject.toml [tool.pytest.ini_options]: changed"]


def test_the_scaffold_spec_holds_every_file_that_defines_a_spec_or_a_guardrail():
    """A PR that weakens the spec of every app must itself be a spec change of the scaffold."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    paths = read_spec_paths(root)
    guardrails = [
        "CLAUDE.md", "docs/spec.md", ".claude/settings.json", ".claude/spec-paths", "copier.yml", "scripts/render.sh",
        ".github/workflows/ci.yml", "kit/src/duckkit/specdiff.py", "kit/src/duckkit/spec.py",
        "template/CLAUDE.md.jinja", "template/docs/how-we-work.md", "template/docs/review.md",
        "template/docs/spec.md.jinja", "template/.claude/spec-paths.jinja", "template/.claude/settings.json.jinja",
        "template/.claude/agents/reviewer.md",
        "template/.claude/skills/deliver-outcome/SKILL.md.jinja", "template/.github/workflows/tests.yml.jinja",
        "template/.github/pull_request_template.md",
    ]
    assert all((root / path).exists() for path in guardrails)
    assert [path for path in guardrails if paths.group_of(path) is None] == []


def test_a_nested_conftest_matches_its_pattern():
    from duckkit.specdiff import SpecPaths

    paths = SpecPaths({"behaviour": ["tests/**/conftest.py"]})
    assert paths.group_of("tests/conftest.py") == paths.group_of("tests/app/conftest.py") == "behaviour"


def test_a_class_of_spec_tests_counts_its_own_names(repo):
    (repo / "tests" / "test_class.py").write_text(dedent('''\
        import pytest


        class TestRules:
            pytestmark = pytest.mark.spec
            CASES = [1, 2]

            def double(self, x):
                return 2 * x

            @pytest.mark.parametrize("x", CASES)
            def test_double_is_even(self, x):
                assert self.double(x) % 2 == 0
        '''))
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "class")
    git(repo, "switch", "-q", "-c", "later")
    edit(repo, "tests/test_class.py", "CASES = [1, 2]", "CASES = []")
    assert spec_diff(repo, "work").spec_tests == ["tests/test_class.py::TestRules::test_double_is_even: changed"]
    edit(repo, "tests/test_class.py", "CASES = []", "CASES = [1, 2]")
    edit(repo, "tests/test_class.py", "return 2 * x", "return 2 * x + 0")
    assert spec_diff(repo, "work").spec_tests == ["tests/test_class.py::TestRules::test_double_is_even: changed"]


def test_a_name_added_to_a_shared_import_line_is_not_a_change_of_a_spec_test(repo):
    """A spec test counts the imported names it uses, not the whole line they share with other tests' names."""
    (repo / "tests" / "test_imports.py").write_text(dedent('''\
        import pytest
        from math import ceil, floor


        @pytest.mark.spec
        def test_ceil():
            assert ceil(1.5) == 2
        '''))
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "imports")
    git(repo, "switch", "-q", "-c", "later")
    edit(repo, "tests/test_imports.py", "from math import ceil, floor", "from math import ceil, floor, sqrt")
    assert spec_diff(repo, "work").spec_tests == []
    edit(repo, "tests/test_imports.py", "from math import ceil, floor, sqrt", "from math import floor as ceil, sqrt")
    assert spec_diff(repo, "work").spec_tests == ["tests/test_imports.py::test_ceil: changed"]


@pytest.mark.parametrize("before, after", [
    ("from .m import f", "from ..m import f"),  # the level
    ("from .m import f", "from .n import f"),  # the module
    ("import os.path, os.sep", "import os.sep"),  # one of two dotted names of the same root
    ("import os.path, os.sep", "import os.curdir, os.sep"),
])
def test_a_change_of_where_an_imported_name_comes_from_is_a_change(repo, before, after):
    """Each import a spec test uses counts, whatever its form."""
    name = "f" if "from" in before else "os"
    (repo / "tests" / "test_where.py").write_text(f"import pytest\n{before}\n\n\n@pytest.mark.spec\ndef test_it():\n"
                                                  f"    assert {name}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "where")
    git(repo, "switch", "-q", "-c", "later")
    edit(repo, "tests/test_where.py", before, after)
    assert spec_diff(repo, "work").spec_tests == ["tests/test_where.py::test_it: changed"]
