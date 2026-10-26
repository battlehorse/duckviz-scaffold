"""`doctor`: how an app's repo compares with the scaffold it was made from.

It reads `.copier-answers.yml` (written by `copier copy` / `copier update`: the scaffold version and the answers,
including the options and `opt_out`) and checks:

- the scaffold version the files come from, against the installed duckkit (they should be the same release);
- with `--remote`, the newest release of the scaffold (`git ls-remote --tags`), and that a repo whose git holds
  curated/ (the user's decisions, duckkit.curated) isn't public (`gh repo view`);
- that the files every app has are there, unless an option turns them off or `opt_out` lists them;
- that every opted-out file is explained in docs/deviations.md (the app's own list of where it differs).

Problems make `doctor` fail; notes don't.
"""

import re
import subprocess
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

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
    (".claude/skills/hosting/SKILL.md", "cloud_run"),
    ("docs/hosting.md", "cloud_run"),
    ("Dockerfile", "cloud_run"),
    (".gcloudignore", "cloud_run"),
    ("curated/README.md", "curations"),
    (".claude/skills/classify/SKILL.md", "llm"),
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
    return report
