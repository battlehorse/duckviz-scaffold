"""The hard stops of docs/working.md, as a Claude Code hook (PreToolUse, on Bash).

Claude Code sends each Bash command as JSON on stdin, and runs it only after this hook answers:
- **deny**: never, in any permission mode. Pushing to main, force-pushing, moving or deleting a tag, a hard reset on
  main, and a merge that is not a merge commit.
- **ask**: the user must confirm in a prompt. Publishing, deploying, changing who can open the hosted app, a paid
  classification, deleting or moving the data, and merging a PR that changes the spec.
- **no answer**: the normal permission rules decide.

The hook reads the command as a shell would, closely enough for a command written in good faith: `cd`, `git -C`,
`gh -R`, `bash -c`, `env`, `xargs`, `eval` and `uv run` are followed. It finds the repo and the app (its
`.copier-answers.yml`) from the folder each command runs in. In the scaffold repo, which has no answers file, the
app rules are off. docs/working.md names what the hook does not catch.

It is plain Python with no dependencies, so it runs before `uv sync` and outside the app's environment. It runs on
the system's `python3`, which can be old (3.9 on macOS): keep to Python 3.9.
"""

from __future__ import annotations  # annotations such as `str | None` on Python 3.9

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

DENY, ASK = "deny", "ask"
PROTECTED_DIRS = ("data", "backups", "curated")
PROTECTED_SUFFIXES = (".duckdb", ".duckdb.wal")
MAIN_BRANCHES = ("main", "master")
RELEASE_TAG = re.compile(r"v\d+(\.\d+)*")
WRAPPERS = {"sudo", "command", "time", "env", "nohup", "exec", "{", "}"}
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
UV_OPTIONS_WITH_A_VALUE = {"--project", "--directory", "--with", "--with-editable", "--with-requirements", "--python",
                           "--package", "-p", "--env-file", "--extra", "--group", "--only-group", "--no-group",
                           "--index", "--default-index", "--index-url", "--extra-index-url", "--find-links"}
XARGS_OPTIONS_WITH_A_VALUE = {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"}


@dataclass
class Command:
    """A simple command: its words, the folder it runs in, and the variables set before it."""

    words: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)


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
    hard stop applies. `root` is the session's project folder, and `cwd` the folder the command starts in."""
    found = []
    for cmd in simple_commands(command, cwd):
        found += [result for rule in RULES if (result := rule(cmd, root))]
    denied = [r for r in found if r[0] == DENY]
    return (denied or found or [None])[0]


# ─── Reading the command ───

def simple_commands(command: str, cwd: Path) -> list[Command]:
    """Each simple command in a shell command line, with the folder it runs in (`cd` changes it for the commands
    after it). The text of a heredoc is not a command, so it is left out."""
    text = unquoted_newlines_to_semicolons(strip_heredocs(command.replace("\\\n", " ")))
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # an unclosed quote: look at the words, unparsed
        tokens = text.split()
    commands: list[Command] = []
    words: list[str] = []
    for token in tokens + [";"]:
        if token not in OPERATORS:
            words.append(token)
            continue
        for cmd in expand(unwrap(Command(words, cwd))):
            if cmd.words[0] == "cd":
                cwd = changed_dir(cmd.cwd, cmd.words[1:])
            else:
                commands.append(cmd)
        words = []
    return commands


def strip_heredocs(command: str) -> str:
    """`command` without the body of each heredoc (`<<EOF` … `EOF`)."""
    return re.sub(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n.*?\n\s*\2[ \t]*(?=\n|$)", r"\3", command, flags=re.DOTALL)


def unquoted_newlines_to_semicolons(text: str) -> str:
    """`text` with each newline outside quotes made a `;`, so that each line is a command of its own."""
    out, quote = [], None
    for i, char in enumerate(text):
        if quote:
            if char == quote and (quote == "'" or text[i - 1] != "\\"):
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "\n":
            char = ";"
        out.append(char)
    return "".join(out)


def changed_dir(cwd: Path, args: list[str]) -> Path:
    """The folder after `cd <args>`."""
    target = next((a for a in args if not a.startswith("-")), "~")
    return Path(os.path.normpath(cwd / os.path.expanduser(target)))


def unwrap(cmd: Command) -> Command:
    """The command itself, past the variable assignments, the wrappers (`sudo`, `env`, `xargs`, …) and `uv run`
    before it. `python -m <package>` counts as the app's command."""
    words, env = list(cmd.words), dict(cmd.env)
    while words:
        first = words[0]
        if re.fullmatch(r"\w+=.*", first):
            name, value = first.split("=", 1)
            env[name] = value
            words = words[1:]
        elif first in WRAPPERS:
            words = words[1:]
        elif first == "xargs":
            words = skip_options(words[1:], XARGS_OPTIONS_WITH_A_VALUE)
        elif first == "uv" and len(words) > 1 and words[1] == "run":
            words = skip_options(words[2:], UV_OPTIONS_WITH_A_VALUE)
        elif Path(first).name.startswith("python") and len(words) > 2 and words[1] == "-m":
            words = [package_command(cmd.cwd, words[2]), *words[3:]]
        else:
            break
    return Command(words, cmd.cwd, env)


def skip_options(words: list[str], with_a_value: set[str]) -> list[str]:
    """`words` past the leading options, and the values of those that take one."""
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in with_a_value else words[1:]
    return words


def expand(cmd: Command) -> list[Command]:
    """A command, or the commands inside `bash -c "…"` (sh, zsh, `-lc` and the like) and `eval "…"`."""
    words = cmd.words
    if not words:
        return []
    if Path(words[0]).name in ("bash", "sh", "zsh"):
        for i, word in enumerate(words[1:-1], start=1):
            if re.fullmatch(r"-[a-z]*c[a-z]*", word):
                return simple_commands(words[i + 1], cmd.cwd)
    if words[0] == "eval":
        return simple_commands(" ".join(words[1:]), cmd.cwd)
    return [cmd]


# ─── The repo and the app a command works on ───

@cache
def repo_root(directory: Path) -> Path | None:
    done = subprocess.run(["git", "-C", str(directory), "rev-parse", "--show-toplevel"], capture_output=True,
                          text=True, check=False)
    return Path(done.stdout.strip()) if done.returncode == 0 else None


def answers(directory: Path) -> str:
    """The text of the `.copier-answers.yml` of the repo `directory` is in, or "" outside an app."""
    top = repo_root(directory) or directory
    path = top / ".copier-answers.yml"
    return path.read_text() if path.exists() else ""


def answer(directory: Path, key: str) -> str | None:
    match = re.search(rf"^{key}:\s*['\"]?([\w.-]+)", answers(directory), flags=re.MULTILINE)
    return match.group(1) if match else None


def package_command(directory: Path, module: str) -> str:
    """`python -m <module>`: the app's command when `module` is the app's package (or its cli)."""
    package = answer(directory, "package")
    if package and module.split(".")[0] == package:
        return answer(directory, "project_name") or module
    return f"python -m {module}"


def is_tag(directory: Path, name: str) -> bool:
    done = subprocess.run(["git", "-C", str(directory), "rev-parse", "-q", "--verify", f"refs/tags/{name}"],
                          capture_output=True, check=False)
    return done.returncode == 0


def current_branch(directory: Path) -> str:
    done = subprocess.run(["git", "-C", str(directory), "branch", "--show-current"], capture_output=True, text=True,
                          check=False)
    return done.stdout.strip()


def git_args(cmd: Command, subcommand: str) -> tuple[Path, list[str]] | None:
    """The folder git works in (`-C` changes it) and the arguments after `git <subcommand>`. None if `cmd` is
    another command."""
    if not cmd.words or cmd.words[0] != "git":
        return None
    directory, rest = cmd.cwd, cmd.words[1:]
    while rest and rest[0].startswith("-"):
        if rest[0] == "-C" and len(rest) > 1:
            directory = Path(os.path.normpath(directory / os.path.expanduser(rest[1])))
        rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
    return (directory, rest[1:]) if rest and rest[0] == subcommand else None


# ─── The rules: each returns (decision, reason) or None ───

def git_push(cmd, root):
    found = git_args(cmd, "push")
    if found is None:
        return None
    directory, args = found
    options = [a for a in args if a.startswith("-")]
    refspecs = [a for a in args if not a.startswith("-")][1:]  # the first one is the remote
    if any(o in ("-f", "--force", "--mirror") or o.startswith(("--force-with-lease", "--force-if-includes"))
           for o in options) or any(r.startswith("+") for r in refspecs):
        return DENY, "Force-pushing is a hard stop. Push a new commit instead, or ask the user."
    if "--all" in options:
        return DENY, "`git push --all` can push main. Push one branch, and open a PR."
    deleting = "-d" in options or "--delete" in options
    for refspec in refspecs:
        target = refspec.split(":")[-1]
        if refspec.startswith(":") or deleting:
            if target.startswith("refs/tags/") or is_tag(directory, target) or RELEASE_TAG.fullmatch(target):
                return DENY, "Deleting a pushed tag is a hard stop: apps depend on it. Ask the user."
            continue
        target = target.removeprefix("refs/heads/")
        if target == "HEAD":
            target = current_branch(directory)
        if target in MAIN_BRANCHES:
            return DENY, "Pushing to main is a hard stop. Push a branch and open a PR."
    if not refspecs and current_branch(directory) in MAIN_BRANCHES:
        return DENY, "Pushing to main is a hard stop. Push a branch and open a PR."
    return None


def git_tag(cmd, root):
    found = git_args(cmd, "tag")
    if found and ({"-f", "--force"} & set(found[1])):
        return DENY, "Moving a tag is a hard stop: apps depend on it. Make a new tag."
    return None


def git_reset_hard_on_main(cmd, root):
    found = git_args(cmd, "reset")
    if found and "--hard" in found[1] and current_branch(found[0]) in MAIN_BRANCHES:
        return DENY, "A hard reset on main is a hard stop. Work on a branch."
    return None


def merge_pr(cmd, root):
    """`gh pr merge`: only as a merge commit, and only for a PR whose spec check passed with no spec change."""
    words = cmd.words
    if words[:3] != ["gh", "pr", "merge"]:
        return None
    args = words[3:]
    if not {"--merge", "-m"} & set(args):
        return DENY, "Merge with `--merge`: a merge commit reverts on its own (docs/working.md)."
    repo = cmd.env.get("GH_REPO")
    positional, i = [], 0
    while i < len(args):
        if args[i] in ("-R", "--repo") and i + 1 < len(args):
            repo, i = args[i + 1], i + 2
            continue
        if args[i].startswith("--repo="):
            repo = args[i].split("=", 1)[1]
        elif not args[i].startswith("-"):
            positional.append(args[i])
        i += 1
    if not positional:
        return ASK, "Name the PR to merge (`gh pr merge <number> --merge`), so its spec check can be read."
    state = pr_spec_state(cmd.cwd, positional[0], repo)
    if state == "unchanged":
        return None
    if state == "changed":
        return ASK, "This PR changes the spec (label spec-change). Only the user approves a spec change."
    return ASK, "The spec check of this PR has not passed yet, so it may change the spec. Ask the user."


def pr_spec_state(directory: Path, pr: str, repo: str | None) -> str:
    """"changed" (the PR has the spec-change label), "unchanged" (the spec check passed without it) or "unknown"."""
    command = ["gh", "pr", "view", pr, "--json", "labels,statusCheckRollup", *(["-R", repo] if repo else [])]
    done = subprocess.run(command, cwd=directory, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return "unknown"
    found = json.loads(done.stdout)
    if any(label["name"] == "spec-change" for label in found.get("labels", [])):
        return "changed"
    checks = {c.get("name"): c.get("conclusion") for c in found.get("statusCheckRollup", [])}
    return "unchanged" if checks.get("spec") == "SUCCESS" else "unknown"


def app_commands(cmd, root):
    """The app's commands that send data out or cost money."""
    cli = answer(cmd.cwd, "project_name")
    if not cli or len(cmd.words) < 2 or cmd.words[0] != cli:
        return None
    name, options = cmd.words[1], cmd.words[2:]
    if name == "publish" and not {"--check", "--dry-run"} & set(options):
        return ASK, "Publishing sends personal data to MotherDuck. Only the user starts it (/publish)."
    if name == "classify" and "--dry-run" not in options:
        return ASK, "Classification costs money. Show the estimate (--dry-run) and ask the user."
    return None


def gcloud(cmd, root):
    """Deploys, traffic, and who can open the hosted app."""
    words = cmd.words
    if not words or words[0] != "gcloud":
        return None
    if "deploy" in words or "update-traffic" in words or ("services" in words and "delete" in words):
        return ASK, "A deploy changes the hosted app. Only the user approves it (/hosting)."
    if any(re.fullmatch(r"(add|remove|set)-iam-policy(-binding)?", w) for w in words):
        return ASK, "This changes who can open the hosted app. Only the user approves it (/hosting)."
    return None


def data_removal(cmd, root):
    """Deleting or moving the database, the backups or the curated decisions."""
    words = cmd.words
    if not words:
        return None
    if words[0] in ("rm", "rmdir", "mv", "trash", "unlink", "shred"):
        paths = [w for w in words[1:] if not w.startswith("-")]
        if words[0] == "mv":
            paths = paths[:-1]  # the destination
    elif words[:2] == ["git", "rm"]:
        paths = [w for w in words[2:] if not w.startswith("-")]
    elif words[:2] == ["git", "clean"] and any(o.startswith("-") and ("x" in o or "X" in o) for o in words[2:]):
        return ASK, "git clean -x deletes ignored files, the data and the backups too. Ask the user."
    elif words[0] == "find" and "-delete" in words:
        starts = []
        for word in words[1:]:
            if word.startswith(("-", "(", "!")):
                break
            starts.append(word)
        patterns = [w for w in words if any(name in w for name in ("duckdb", *PROTECTED_DIRS))]
        if patterns or any(is_protected(cmd.cwd, start, whole_dir=False) for start in starts or ["."]):
            return ASK, "This find deletes files in the data, the backups or the curated decisions. Ask the user."
        return None
    else:
        return None
    if any(is_protected(cmd.cwd, path) for path in paths):
        return ASK, "This deletes or moves the data, the backups or the curated decisions. Ask the user first."
    return None


def is_protected(cwd: Path, path: str, whole_dir: bool = True) -> bool:
    """Whether `path` (from `cwd`) can hold the database, data/, backups/ or curated/ of its repo. With `whole_dir`,
    the repo's folder itself (or a folder above it, or a glob in it) counts too: deleting it deletes them."""
    if "$" in path or "`" in path or path.endswith(PROTECTED_SUFFIXES):
        return True  # a variable may be anything
    full = Path(os.path.normpath(cwd / os.path.expanduser(path)))
    glob = any(c in path for c in "*?[")
    if glob:
        full = full.parent
    top = repo_root(cwd) or cwd
    if (whole_dir or glob) and (top == full or full in top.parents):
        return True
    try:
        parts = full.relative_to(top).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in PROTECTED_DIRS


RULES = [git_push, git_tag, git_reset_hard_on_main, merge_pr, app_commands, gcloud, data_removal]

if __name__ == "__main__":
    main()
