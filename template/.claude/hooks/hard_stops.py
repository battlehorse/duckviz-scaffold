"""The hard stops of docs/working.md, as a Claude Code hook (PreToolUse, on Bash).

Claude Code sends each Bash command as JSON on stdin, and runs it only after this hook answers:
- **deny**: never, in any permission mode. Pushing to main, force-pushing, moving a tag, a hard reset on main.
- **ask**: the user must confirm in a prompt. Publishing, deploying, changing who can open the hosted app, a paid
  classification, deleting or moving the data, and merging a PR that changes the spec.
- **no answer**: the normal permission rules decide.

The hook is plain Python with no dependencies, so it runs before `uv sync` and outside the app's environment. It
reads the app's command name from `.copier-answers.yml`. In the scaffold repo, which has none, the app rules are off.
It runs on the system's `python3`, which can be old (3.9 on macOS): keep to Python 3.9.
"""

from __future__ import annotations  # annotations such as `str | None` on Python 3.9

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

DENY, ASK = "deny", "ask"
PROTECTED_DIRS = ("data", "backups", "curated")
PROTECTED_SUFFIXES = (".duckdb", ".duckdb.wal")
MAIN_BRANCHES = ("main", "master")
WRAPPERS = {"sudo", "command", "time", "env", "nohup", "exec"}
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}


def main() -> None:
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command", "")
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
    cwd = Path(event.get("cwd") or root)
    found = decide(command, root, cwd)
    if found:
        decision, reason = found
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                 "permissionDecisionReason": reason}}))


def decide(command: str, root: Path, cwd: Path) -> tuple[str, str] | None:
    """The strongest decision for any simple command in `command` (deny before ask), with its reason. None: no
    hard stop applies."""
    cli = app_command(root)
    found = []
    for words in simple_commands(command):
        found += [result for rule in RULES if (result := rule(words, root, cwd, cli))]
    denied = [r for r in found if r[0] == DENY]
    return (denied or found or [None])[0]


# ─── Parsing the command ───

def simple_commands(command: str) -> list[list[str]]:
    """The words of each simple command in a shell command line. The text of a heredoc is not a command, so it is
    left out. `bash -c "…"` counts as the commands in its string."""
    lines = []
    for line in strip_heredocs(command).splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        try:
            lines.append(list(lexer))
        except ValueError:  # an unclosed quote: look at the words, unparsed
            lines.append(line.split())
    commands = []
    for tokens in lines:
        words: list[str] = []
        for token in tokens + [";"]:
            if token in OPERATORS:
                if words:
                    commands += expand(unwrap(words))
                words = []
            else:
                words.append(token)
    return commands


def strip_heredocs(command: str) -> str:
    """`command` without the body of each heredoc (`<<EOF` … `EOF`)."""
    return re.sub(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n.*?\n\s*\2[ \t]*(?=\n|$)", r"\3", command, flags=re.DOTALL)


def unwrap(words: list[str]) -> list[str]:
    """The command itself, without the variable assignments, the wrappers (`sudo`, `env`, …) and `uv run` before
    it."""
    while words:
        first = words[0]
        if re.fullmatch(r"\w+=.*", first) or first in WRAPPERS:
            words = words[1:]
        elif first == "uv" and len(words) > 1 and words[1] == "run":
            words = words[2:]
            while words and words[0].startswith("-"):  # uv's own options, and the value of --project and the like
                takes_value = words[0] in ("--project", "--directory", "--with", "--python", "--package", "-p")
                words = words[2:] if takes_value else words[1:]
        else:
            return words
    return words


def expand(words: list[str]) -> list[list[str]]:
    """A command, or the commands inside `bash -c "…"` (and sh, zsh)."""
    if words and Path(words[0]).name in ("bash", "sh", "zsh") and "-c" in words[1:-1]:
        return simple_commands(words[words.index("-c") + 1])
    return [words] if words else []


def app_command(root: Path) -> str | None:
    """The app's command name (`project_name` in .copier-answers.yml), or None outside an app."""
    answers = root / ".copier-answers.yml"
    if not answers.exists():
        return None
    match = re.search(r"^project_name:\s*['\"]?([\w.-]+)", answers.read_text(), flags=re.MULTILINE)
    return match.group(1) if match else None


def is_tag(root: Path, name: str) -> bool:
    done = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{name}"], cwd=root, capture_output=True,
                          check=False)
    return done.returncode == 0


def current_branch(root: Path) -> str:
    done = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, check=False)
    return done.stdout.strip()


# ─── The rules: each returns (decision, reason) or None ───

def git_push(words, root, cwd, cli):
    args = git_args(words, "push")
    if args is None:
        return None
    options = [a for a in args if a.startswith("-")]
    refspecs = [a for a in args if not a.startswith("-")][1:]  # the first one is the remote
    if any(o in ("-f", "--force", "--mirror") or o.startswith(("--force-with-lease", "--force-if-includes"))
           for o in options) or any(r.startswith("+") for r in refspecs):
        return DENY, "Force-pushing is a hard stop. Push a new commit instead, or ask the user."
    deleting = "-d" in options or "--delete" in options
    for refspec in refspecs:
        target = refspec.split(":")[-1].removeprefix("refs/heads/")
        if refspec.startswith(":") or deleting:
            if target.startswith("refs/tags/") or is_tag(root, target):
                return DENY, "Deleting a pushed tag is a hard stop: apps depend on it. Ask the user."
            continue
        if target == "HEAD":
            target = current_branch(root)
        if target in MAIN_BRANCHES:
            return DENY, "Pushing to main is a hard stop. Push a branch and open a PR."
    if not refspecs and current_branch(root) in MAIN_BRANCHES:
        return DENY, "Pushing to main is a hard stop. Push a branch and open a PR."
    return None


def git_tag_force(words, root, cwd, cli):
    args = git_args(words, "tag")
    if args is not None and ("-f" in args or "--force" in args):
        return DENY, "Moving a tag is a hard stop: apps depend on it. Make a new tag."
    return None


def git_reset_hard_on_main(words, root, cwd, cli):
    args = git_args(words, "reset")
    if args is not None and "--hard" in args and current_branch(root) in MAIN_BRANCHES:
        return DENY, "A hard reset on main is a hard stop. Work on a branch."
    return None


def merge_spec_pr(words, root, cwd, cli):
    """`gh pr merge` on a PR that changes the spec, or whose spec check has not passed yet."""
    if words[:3] != ["gh", "pr", "merge"]:
        return None
    target = [w for w in words[3:] if not w.startswith("-")][:1]
    state = pr_spec_state(root, target)
    if state == "unchanged":
        return None
    if state == "changed":
        return ASK, "This PR changes the spec (label spec-change). Only the user approves a spec change."
    return ASK, "The spec check of this PR has not passed yet, so it may change the spec. Ask the user."


def pr_spec_state(root: Path, target: list[str]) -> str:
    """"changed" (the PR has the spec-change label), "unchanged" (the spec check passed without it) or "unknown"."""
    done = subprocess.run(["gh", "pr", "view", *target, "--json", "labels,statusCheckRollup"], cwd=root,
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return "unknown"
    pr = json.loads(done.stdout)
    if any(label["name"] == "spec-change" for label in pr.get("labels", [])):
        return "changed"
    checks = {c.get("name"): c.get("conclusion") for c in pr.get("statusCheckRollup", [])}
    return "unchanged" if checks.get("spec") == "SUCCESS" else "unknown"


def app_commands(words, root, cwd, cli):
    """The app's commands that send data out or cost money."""
    if not cli or not words or words[0] != cli or len(words) < 2:
        return None
    name, options = words[1], words[2:]
    if name == "publish" and not {"--check", "--dry-run"} & set(options):
        return ASK, "Publishing sends personal data to MotherDuck. Only the user starts it (/publish)."
    if name == "classify" and "--dry-run" not in options:
        return ASK, "Classification costs money. Show the estimate (--dry-run) and ask the user."
    return None


def gcloud(words, root, cwd, cli):
    """Deploys, traffic, and who can open the hosted app."""
    if not words or words[0] != "gcloud":
        return None
    if "deploy" in words or "update-traffic" in words or ("services" in words and "delete" in words):
        return ASK, "A deploy changes the hosted app. Only the user approves it (/hosting)."
    if any(re.fullmatch(r"(add|remove|set)-iam-policy(-binding)?", w) for w in words):
        return ASK, "This changes who can open the hosted app. Only the user approves it (/hosting)."
    return None


def data_removal(words, root, cwd, cli):
    """Deleting or moving the database, the backups or the curated decisions."""
    if not words:
        return None
    if words[0] in ("rm", "rmdir", "mv", "trash", "unlink", "shred"):
        paths = [w for w in words[1:] if not w.startswith("-")]
    elif words[:2] == ["git", "rm"]:
        paths = [w for w in words[2:] if not w.startswith("-")]
    elif words[:2] == ["git", "clean"] and any(o.startswith("-") and ("x" in o or "X" in o) for o in words[2:]):
        return ASK, "git clean -x deletes ignored files, the data and the backups too. Ask the user."
    elif words[0] == "find" and "-delete" in words:
        paths = [w for w in words[1:] if not w.startswith("-")][:1]
    else:
        return None
    if words[0] == "mv":
        paths = paths[:-1]  # the destination
    if any(is_protected(root, cwd, p) for p in paths):
        return ASK, "This deletes or moves the data, the backups or the curated decisions. Ask the user first."
    return None


def is_protected(root: Path, cwd: Path, path: str) -> bool:
    """Whether `path` is the database, or in data/, backups/ or curated/ of the repo at `root`."""
    if path.endswith(PROTECTED_SUFFIXES):
        return True
    full = Path(os.path.normpath(cwd / os.path.expanduser(path)))
    try:
        parts = full.relative_to(os.path.normpath(root)).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in PROTECTED_DIRS


def git_args(words: list[str], subcommand: str) -> list[str] | None:
    """The arguments after `git <subcommand>`, past git's own options (`-C <dir>`, `-c <key=value>`). None if
    `words` is another command."""
    if not words or words[0] != "git":
        return None
    rest = words[1:]
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
    return rest[1:] if rest and rest[0] == subcommand else None


RULES = [git_push, git_tag_force, git_reset_hard_on_main, merge_spec_pr, app_commands, gcloud, data_removal]

if __name__ == "__main__":
    main()
