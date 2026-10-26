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
