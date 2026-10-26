"""The hard-stops hook (template/.claude/hooks/hard_stops.py): each rule denies, asks, or lets a command through."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "template" / ".claude" / "hooks" / "hard_stops.py"
sys.dont_write_bytecode = True  # no __pycache__ in template/: copier would copy it into every app
spec = importlib.util.spec_from_file_location("hard_stops", HOOK)
hard_stops = importlib.util.module_from_spec(spec)
sys.modules["hard_stops"] = hard_stops  # a dataclass looks its module up
spec.loader.exec_module(hard_stops)
sys.dont_write_bytecode = False


@pytest.fixture
def repo(tmp_path):
    """An app's repo on a branch called `work`, with the command `shopviz`."""
    subprocess.run(["git", "init", "-q", "-b", "work"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty",
                    "-m", "start"], cwd=tmp_path, check=True)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp_path, check=True)
    (tmp_path / ".copier-answers.yml").write_text("_commit: v1.0.0\nproject_name: shopviz\npackage: shopviz\n")
    return tmp_path


def decision(repo, command, cwd=None):
    found = hard_stops.decide(command, cwd or repo)
    return found[0] if found else None


@pytest.mark.parametrize("command", [
    "git push origin main",
    "git push origin HEAD:main",
    "git push -u origin work:refs/heads/main",
    "git push --force origin work",
    "git push -f",
    "git push --force-with-lease origin work",
    "git push origin +work",
    "git push origin :refs/tags/v1.0.0",
    "git push --delete origin v1.0.0",
    "git tag -f v1.0.0",
    "git -C . push origin main",
    "git add . && git commit -m x && git push origin main",
    "bash -c 'git push origin main'",
    "bash -lc 'git push origin main'",
    "echo x | xargs -n 1 git push origin main",
    "eval 'git push origin main'",
    "{ git push origin main; }",
    "git push \\\n  origin main",
    "git push --all origin",
    "git push --delete origin v2",
    "git push origin :v2.1",
    "gh pr merge 12 --squash",
    "gh pr merge 12",
    "# push the branch\ngit push origin main",
    "git push -fu origin work",
    "git push -uf origin work",
    "git tag -fa v1.2.3 -m again",
    "git tag -af v1.2.3 -m again",
])
def test_these_are_denied(repo, command):
    assert decision(repo, command) == "deny"


def test_pushing_on_main_without_a_refspec_is_denied(repo):
    subprocess.run(["git", "checkout", "-q", "-b", "main"], cwd=repo, check=True)
    assert decision(repo, "git push") == "deny"
    assert decision(repo, "git push -u origin HEAD") == "deny"
    assert decision(repo, "git reset --hard origin/main") == "deny"


@pytest.mark.parametrize("command", [
    "uv run shopviz publish",
    "uv run --project . shopviz publish --to md:shop",
    "shopviz classify --limit 10",
    "gcloud run deploy shopviz --source . --quiet",
    "gcloud run services update-traffic shopviz --to-revisions=r1=100",
    "gcloud iap web add-iam-policy-binding --member=user:someone@example.com",
    "rm data/shop.duckdb",
    "rm -rf backups",
    "mv data/shop.duckdb data/shop.duckdb.old",
    "cd data && rm shop.duckdb",
    "git rm -r curated",
    "git clean -fdx",
    "find curated -name '*.csv' -delete",
    "find . -name '*.duckdb' -delete",
    "rm -rf *",
    "rm -rf .",
    'rm -rf "$CLAUDE_PROJECT_DIR/data"',
    "uv run --env-file .env shopviz publish",
    "uv run python -m shopviz publish",
    "uv run python -m shopviz.cli classify",
    "gh pr merge --merge",
    "find . -name '*.parquet' -delete",
    "find . -path '*/backups/*' -delete",
])
def test_these_ask_the_user(repo, command):
    assert decision(repo, command) == "ask"


@pytest.mark.parametrize("command", [
    "git push -u origin work",
    "git push origin v1.0.1",
    "git push --tags",
    "git push origin --delete old-branch",
    "git push origin --delete v2-redesign",
    "git tag v1.0.1",
    "git reset --hard HEAD~1",
    "uv run shopviz publish --check",
    "uv run shopviz publish --dry-run",
    "uv run shopviz classify --dry-run",
    "uv run shopviz status",
    "uv add pandas",
    "rm -rf build .pytest_cache",
    "mv notes.txt data/notes.txt",
    "gcloud run services describe shopviz",
    "cat > body.md <<'EOF'\nThen run git push origin main and rm -rf data.\nEOF\ngh pr create --body-file body.md",
    "git commit -m 'do not git push --force'",
    "git commit -m 'Fix it\n\ngit push origin main is refused now'",
    "find . -name '*.pyc' -delete",
    "find . -name __pycache__ -delete",
    "find . -path ./data -prune -o -path ./backups -prune -o -path ./curated -prune -o -name '*.tmp' -delete",
    "find src/metadata -name '*.json' -delete",
    "rm -rf tmp/*",
    "echo '# not a comment' && ls",
])
def test_these_pass(repo, command):
    assert decision(repo, command) is None


def test_merging_a_pr_asks_unless_its_spec_check_passed_without_a_spec_change(repo, monkeypatch):
    for state, expected in [("changed", "ask"), ("unknown", "ask"), ("unchanged", None)]:
        monkeypatch.setattr(hard_stops, "pr_spec_state", lambda directory, pr, repo, state=state: state)
        assert decision(repo, "gh pr merge 12 --merge") == expected


def test_outside_an_app_the_app_rules_are_off(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "work"], cwd=tmp_path, check=True)
    assert hard_stops.decide("shopviz publish", tmp_path) is None
    assert hard_stops.decide("git push origin main", tmp_path)[0] == "deny"


def test_the_hook_answers_claude_code_in_its_format(repo):
    event = {"tool_input": {"command": "git push origin main"}, "cwd": str(repo)}
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                          env={"CLAUDE_PROJECT_DIR": str(repo), "PATH": "/usr/bin:/bin"}, check=True)
    answer = json.loads(done.stdout)["hookSpecificOutput"]
    assert answer["hookEventName"] == "PreToolUse" and answer["permissionDecision"] == "deny"
    quiet = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_input": {"command": "ls"}}),
                           capture_output=True, text=True, env={"CLAUDE_PROJECT_DIR": str(repo), "PATH": "/usr/bin:/bin"},
                           check=True)
    assert quiet.stdout == ""


def test_the_hook_runs_on_the_systems_old_python():
    """Claude Code runs it with the system's `python3`, which is 3.9 on macOS."""
    import ast

    ast.parse(HOOK.read_text(), feature_version=(3, 9))


def test_the_branch_is_read_where_the_command_runs(repo, tmp_path_factory):
    """A worktree on main, inside a session that started on another branch."""
    worktree = tmp_path_factory.mktemp("wt") / "main-checkout"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "main", str(worktree)], cwd=repo, check=True)
    assert decision(repo, "git push", cwd=worktree) == "deny"
    assert decision(repo, "git reset --hard HEAD~1", cwd=worktree) == "deny"
    assert decision(repo, f"cd {worktree} && git push") == "deny"
    assert decision(repo, f"git -C {worktree} push") == "deny"
    assert decision(repo, "git push") is None  # the session's own branch is `work`


def test_the_app_is_found_from_the_folder_the_command_runs_in(repo, tmp_path):
    parent = repo.parent
    assert hard_stops.decide("uv run shopviz publish", repo)[0] == "ask"
    assert hard_stops.decide(f"cd {repo.name} && uv run shopviz publish", parent)[0] == "ask"


def test_a_merge_reads_the_spec_check_of_the_named_repo(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(hard_stops, "pr_spec_state", lambda directory, pr, repo: seen.append((pr, repo)) or "unchanged")
    decision(repo, "gh pr merge 25 --merge -R someone/other")
    decision(repo, "GH_REPO=someone/else gh pr merge 26 --merge")
    assert seen == [("25", "someone/other"), ("26", "someone/else")]


def test_a_merge_option_value_is_not_the_pr(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(hard_stops, "pr_spec_state", lambda directory, pr, repo: seen.append(pr) or "unchanged")
    assert decision(repo, "gh pr merge --merge --subject 'Merge it' 12") is None
    assert seen == ["12"]


def run(conclusion, started, status="COMPLETED"):
    return {"name": "spec", "status": status, "conclusion": conclusion, "startedAt": started}


@pytest.mark.parametrize("runs, expected", [
    ([run("SKIPPED", "10:55:32"), run("SUCCESS", "10:55:10")], "unchanged"),  # an edit that didn't change the base
    ([run("SUCCESS", "10:55:10"), run("FAILURE", "11:00:00")], "unknown"),  # the newest run is the one that counts
    ([run("SUCCESS", "10:55:10"), run(None, "11:00:00", status="IN_PROGRESS")], "unknown"),  # a new base, still going
    ([run("SKIPPED", "10:55:32")], "unknown"),
])
def test_the_newest_spec_run_that_ran_decides(repo, monkeypatch, runs, expected):
    done = subprocess.CompletedProcess([], 0, stdout=json.dumps({"labels": [], "statusCheckRollup": runs}))
    monkeypatch.setattr(hard_stops.subprocess, "run", lambda *a, **k: done)
    assert hard_stops.pr_spec_state(repo, "12", None) == expected
