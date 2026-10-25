"""Release the scaffold: one version for the template and duckkit, then a tag. In two steps, around a PR:

    uv run --project kit scripts/release.py 0.3.0         # on a branch: set the versions and commit; open a PR
    uv run --project kit scripts/release.py --tag 0.3.0   # on main, after the PR is merged: tag the release

The first step sets kit/pyproject.toml's version and copier.yml's kit_ref, checks that CHANGELOG.md has an entry and
commits. The second checks that main has that version and tags vX.Y.Z. Push the tag with `git push origin vX.Y.Z`:
apps see the release from then on (`doctor --remote`, the weekly scaffold-update workflow). Never move a pushed tag.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "kit" / "pyproject.toml"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def prepare(version: str, tag: str) -> None:
    if git("branch", "--show-current") == "main":
        sys.exit(f"on main: make a branch first (git switch -c release/{tag})")
    if git("status", "--porcelain"):
        sys.exit("the working tree isn't clean: commit first")
    if f"## {tag}" not in (ROOT / "CHANGELOG.md").read_text():
        sys.exit(f"CHANGELOG.md has no '## {tag}' entry")
    KIT.write_text(re.sub(r'^version = ".*"$', f'version = "{version}"', KIT.read_text(), count=1,
                          flags=re.MULTILINE))
    copier = ROOT / "copier.yml"
    copier.write_text(re.sub(r"(kit_ref:\n  type: str\n  default: )v\S+", rf"\g<1>{tag}", copier.read_text()))
    subprocess.run(["uv", "lock", "--project", "kit"], cwd=ROOT, check=True)
    git("commit", "-qam", f"Release {tag}")
    print(f"Committed the release. Push the branch and open a PR; after it merges: release.py --tag {version}")


def tag_release(version: str, tag: str) -> None:
    if git("branch", "--show-current") != "main" or git("status", "--porcelain"):
        sys.exit("switch to a clean main first (git switch main && git pull)")
    if not re.search(rf'^version = "{re.escape(version)}"$', KIT.read_text(), flags=re.MULTILINE):
        sys.exit(f"main's duckkit isn't {version}: merge the release PR first")
    if git("tag", "--list", tag):
        sys.exit(f"{tag} exists already")
    git("tag", "-a", tag, "-m", f"Release {tag}")
    print(f"Tagged {tag}. Push: git push origin {tag}")


def main(args: list[str]) -> None:
    tagging = args[:1] == ["--tag"]
    version = (args[1:] if tagging else args)[:1]
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version[0]):
        sys.exit("usage: release.py [--tag] X.Y.Z")
    (tag_release if tagging else prepare)(version[0], f"v{version[0]}")


if __name__ == "__main__":
    main(sys.argv[1:])
