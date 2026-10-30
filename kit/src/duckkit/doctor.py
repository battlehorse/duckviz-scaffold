"""`doctor`: how an app's repo compares with the scaffold it was made from.

It reads `.copier-answers.yml` (written by `copier copy` / `copier update`: the scaffold version and the answers,
including the options and `opt_out`) and checks:

- the scaffold version the files come from, against the installed duckkit (they should be the same release);
- with `--remote`, the newest release of the scaffold (`git ls-remote --tags`), that a repo whose git holds
  curated/ (the user's decisions, duckkit.curated) isn't public (`gh repo view`), and that the Cloud Storage bucket
  of the off-machine backups (`[backup] remote`) is private (`gcloud storage buckets describe`);
- that the files every app has are there, unless an option turns them off or `opt_out` lists them;
- that every opted-out file is explained in docs/deviations.md (the app's own list of where it differs);
- that the docs' paths hold: no Markdown file (docs, skills, agents) links to a missing file or names a missing
  `docs/….md`, and every line of `.claude/spec-paths` matches a file (else `spec-diff` misses its changes). A doc
  that `docs/README.md` (the index) doesn't list is a note.

Problems make `doctor` fail; notes don't.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path, PurePosixPath

import yaml

from duckkit.spec import AppSpec

ANSWERS = ".copier-answers.yml"

# Files every app has: (path, the option that must be on for it, or None)
EXPECTED = [
    ("CLAUDE.md", None),
    ("README.md", None),
    ("docs/architecture.md", None),
    ("docs/contract.md", None),
    ("docs/dashboard.md", None),
    ("docs/getting-started.md", None),
    ("docs/scaffold.md", None),
    ("docs/deviations.md", None),
    ("tests/app/test_contract_only.py", None),
    (".github/workflows/tests.yml", None),
    (".streamlit/config.toml", None),
    (".claude/skills/app/SKILL.md", None),
    (".claude/skills/catch-up/SKILL.md", None),
    (".claude/skills/scaffold-update/SKILL.md", None),
    (".claude/skills/publish/SKILL.md", "motherduck"),
    (".claude/skills/backup/SKILL.md", "backup"),
    (".claude/skills/restore-backup/SKILL.md", "backup"),
    (".claude/skills/hosting/SKILL.md", "cloud_run"),
    ("docs/hosting.md", "cloud_run"),
    ("Dockerfile", "cloud_run"),
    (".gcloudignore", "cloud_run"),
    ("curated/README.md", "curations"),
    (".claude/skills/rebuild-database/SKILL.md", "curations"),
    (".githooks/pre-commit", None),
    (".github/pull_request_template.md", None),
    ("docs/spec.md", None),
    ("docs/how-we-work.md", None),
    ("docs/review.md", None),
    (".claude/spec-paths", None),
    (".claude/settings.json", None),
    (".claude/agents/reviewer.md", None),
    (".claude/skills/deliver-outcome/SKILL.md", None),
    ("config.example.toml", None),
]


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"  · {n}" for n in self.notes] + [f"  ✗ {p}" for p in self.problems]
        out.append("✗ " + f"{len(self.problems)} problems" if self.problems else "✓ in step with the scaffold")
        return out


def answers(spec: AppSpec) -> dict | None:
    """The scaffold answers of the repo, or None when it wasn't made from the scaffold."""
    path = spec.root / ANSWERS
    return yaml.safe_load(path.read_text()) or {} if path.exists() else None


def kit_version() -> str | None:
    try:
        return installed_version("duckkit")
    except PackageNotFoundError:
        return None


def newest_release(source: str) -> str | None:
    """The highest vX.Y.Z tag of the scaffold's repo; None when it can't be reached."""
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs", source], capture_output=True, text=True,
                         check=False, timeout=30)
    tags = re.findall(r"refs/tags/(v\d+\.\d+\.\d+)$", out.stdout, re.MULTILINE)
    return max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else None


def tracks_curated(spec: AppSpec) -> bool:
    """Whether git holds files under curated/."""
    out = subprocess.run(["git", "ls-files", "--", "curated"], cwd=spec.root, capture_output=True, text=True,
                         check=False, timeout=30)
    return bool(out.stdout.strip())


def visibility(spec: AppSpec) -> str | None:
    """The GitHub repo's visibility ("PUBLIC", "PRIVATE", "INTERNAL"); None when `gh` can't tell."""
    try:
        out = subprocess.run(["gh", "repo", "view", "--json", "visibility", "--jq", ".visibility"], cwd=spec.root,
                             capture_output=True, text=True, check=False, timeout=30)
    except FileNotFoundError:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def diagnose(spec: AppSpec, remote: bool = False) -> Report:
    report = Report()
    found = answers(spec)
    if found is None:
        report.problems.append(f"no {ANSWERS}: this repo wasn't made from the scaffold (see the scaffold's "
                               "docs/upgrading.md, \"Adopting the scaffold\")")
        return report
    commit = str(found.get("_commit", "?"))
    kit = kit_version()
    report.notes.append(f"scaffold files from {commit}, duckkit {kit or 'not installed'}")
    if not re.match(r"v\d+\.\d+\.\d+$", commit):
        report.notes.append(f"{commit} is not a release: made from a working copy of the scaffold (its own CI)")
    elif kit and commit.lstrip("v") != kit:
        report.problems.append(f"the files come from scaffold {commit} but duckkit is {kit}: run `/scaffold-update` "
                               "(or `copier update`), which moves both together")
    if remote and (source := found.get("_src_path")):
        newest = newest_release(source)
        if newest and newest != commit.split("-")[0]:
            report.notes.append(f"scaffold {newest} is out: `/scaffold-update` brings it in")
    if remote and tracks_curated(spec):
        seen = visibility(spec)
        if seen == "PUBLIC":
            report.problems.append("git holds curated/, your decisions, and the GitHub repo is public: make the repo "
                                   "private")
        elif seen is None:
            report.notes.append("git holds curated/: couldn't check that the GitHub repo is private (`gh repo view`)")
    if remote:
        _check_backup_bucket(spec, report)
    opt_out = set(found.get("opt_out") or [])
    for path, flag in EXPECTED:
        if flag and not found.get(flag):
            continue
        if path in opt_out:
            continue
        if not (spec.root / path).exists():
            report.problems.append(f"{path} is missing (restore it with `copier update`, or add it to opt_out and "
                                   "explain why in docs/deviations.md)")
    doc = spec.root / "docs" / "deviations.md"
    deviations = doc.read_text() if doc.exists() else ""
    for path in sorted(opt_out):
        if path not in deviations:
            report.problems.append(f"{path} is opted out but docs/deviations.md doesn't say why")
    report.problems += [f"{source} names {target}, which doesn't exist" for source, target in broken_links(spec)]
    report.problems += [f".claude/spec-paths: {pattern} matches no file, so `spec-diff` can't see it change (a file "
                        "that moved, or a stale line)" for pattern in stale_spec_paths(spec)]
    report.notes += [f"{path} is not in docs/README.md, the index: add a line for it" for path in unindexed_docs(spec)]
    return report


# ─── The docs' paths ───

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "data", "backups",
             "build", "dist"}
LINK = re.compile(r"\]\(([^)\s]+)\)")  # [text](target)
CODE_PATH = re.compile(r"`(docs/[\w./-]+\.md)`")  # `docs/contract.md`, a path from the repo root


def repo_files(spec: AppSpec) -> list[str]:
    """Every file of the repo, as a path from the root; without .git, the virtualenv, caches and the data."""
    found = []
    for folder, dirs, files in os.walk(spec.root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = Path(folder).relative_to(spec.root)
        found += [(rel / f).as_posix() for f in files]
    return sorted(found)


def broken_links(spec: AppSpec) -> list[tuple[str, str]]:
    """(file, target) for each relative link in a Markdown file to a file that doesn't exist, and each `docs/….md` in
    backticks that doesn't. A link resolves from its file's folder, a backticked path from the repo root."""
    broken = []
    for name in repo_files(spec):
        if not name.endswith(".md") or name == "CHANGELOG.md":  # the changelog names old paths on purpose
            continue
        text = (spec.root / name).read_text(errors="replace")
        for target in LINK.findall(text):
            path = target.split("#", 1)[0]
            if not path or re.match(r"[a-z][a-z0-9+.-]*:", path) or any(c in path for c in "<>{}*$"):
                continue  # an anchor, a URL, a placeholder
            if not os.path.exists(os.path.normpath(spec.root / PurePosixPath(name).parent / path)):
                broken.append((name, target))
        for path in CODE_PATH.findall(text):
            if not (spec.root / path).exists():
                broken.append((name, path))
    return broken


def stale_spec_paths(spec: AppSpec) -> list[str]:
    """The patterns of `.claude/spec-paths` that match no file of the repo."""
    from duckkit.specdiff import read_spec_paths

    try:
        groups = read_spec_paths(spec.root).groups
    except ValueError:
        return []  # no file: EXPECTED reports it
    files = [PurePosixPath(f) for f in repo_files(spec)]
    return [pattern for patterns in groups.values() for pattern in patterns
            if not any(f.full_match(pattern) for f in files)]


def unindexed_docs(spec: AppSpec) -> list[str]:
    """The docs that `docs/README.md` doesn't link to; empty when there is no index."""
    index = spec.root / "docs" / "README.md"
    if not index.exists():
        return []
    linked = {os.path.normpath(index.parent / t.split("#", 1)[0]) for t in LINK.findall(index.read_text())}
    return [name for name in repo_files(spec) if name.startswith("docs/") and name.endswith(".md")
            and name != "docs/README.md" and os.path.normpath(spec.root / name) not in linked]


def _check_backup_bucket(spec: AppSpec, report: Report) -> None:
    """The bucket of the off-machine backups holds the whole database: it must be private."""
    from duckkit.backup import OffsiteError, bucket_problems

    try:
        if spec.backup_remote() is None:
            return
        report.problems.extend(bucket_problems(spec))
    except ValueError as e:
        report.problems.append(str(e))
    except OffsiteError as e:
        report.notes.append(f"couldn't check that the backup bucket is private: {e}")
