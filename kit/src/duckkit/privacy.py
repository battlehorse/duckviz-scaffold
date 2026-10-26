"""Keep personal data out of git: the repo is meant to be safe to make public.

`check` scans every file git would commit (tracked, plus untracked files that aren't ignored) for this machine's
personal values: the settings the spec lists as private (`private_settings`), the MotherDuck token, extra terms
from `[privacy] terms` in config.toml (or <PREFIX>_PRIVACY_TERMS, comma-separated), and whatever the app's own
`extra` function finds (names in its database, say). The pre-commit hook (`<cli> privacy-check`) runs it before
every commit. A finding names the kind of term, never the term itself.
"""

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from duckkit.spec import AppSpec

# An app's own personal terms: {term: what it is}
Terms = Callable[[AppSpec], dict[str, str]]


@dataclass
class Finding:
    """A personal term on one line of a file. `what` names the kind of term, never the term itself."""

    path: str
    line: int
    what: str


def personal_terms(spec: AppSpec, extra: Terms | None = None) -> dict[str, str]:
    """{term: what it is} for every personal value known on this machine."""
    terms = {}
    settings = [*spec.private_settings, ("motherduck", "token", "MOTHERDUCK_TOKEN", "MotherDuck token"),
                ("anthropic", "api_key", "ANTHROPIC_API_KEY", "Anthropic API key")]
    for section, key, env, what in settings:
        if value := spec.setting(section, key, env):
            terms[str(value)] = what
    listed = spec.setting("privacy", "terms", f"{spec.env_prefix}_PRIVACY_TERMS", default=[])
    for term in listed.split(",") if isinstance(listed, str) else listed:
        if str(term).strip():
            terms[str(term).strip()] = "a [privacy] term"
    if extra:
        terms.update(extra(spec))
    return terms


def committable_files(root: Path) -> list[Path]:
    """The files git tracks, and the untracked files that .gitignore doesn't exclude."""
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                         capture_output=True, check=True).stdout.decode()
    return [root / p for p in out.split("\0") if p and (root / p).is_file()]


def scan(files: list[Path], terms: dict[str, str], root: Path) -> list[Finding]:
    """Every line of `files` that contains a term (any case). Terms shorter than 3 characters are skipped:
    they match too much."""
    patterns = [(re.compile(re.escape(t), re.IGNORECASE), what) for t, what in terms.items() if len(t) >= 3]
    found = []
    for path in files:
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue  # binary: nothing personal is ever written as one
        for number, line in enumerate(text.splitlines(), 1):
            for pattern, what in patterns:
                if pattern.search(line):
                    found.append(Finding(str(path.relative_to(root)), number, what))
    return found


def check(spec: AppSpec, extra: Terms | None = None) -> list[Finding]:
    """Scan the committable files for this machine's personal terms. Empty: safe to commit."""
    return scan(committable_files(spec.root), personal_terms(spec, extra), spec.root)
