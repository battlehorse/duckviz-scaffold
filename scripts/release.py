"""Release the scaffold: one version for the template and duckkit, then a tag.

    uv run --project kit scripts/release.py 0.2.0

Sets kit/pyproject.toml's version and copier.yml's kit_ref, checks that CHANGELOG.md has an entry, commits, and tags
vX.Y.Z. Push with `git push origin main vX.Y.Z`: apps see the release from then on (`doctor --remote`, the weekly
scaffold-update workflow).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("usage: release.py X.Y.Z")
    tag = f"v{version}"
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        sys.exit("the working tree isn't clean: commit first")
    if f"## {tag}" not in (ROOT / "CHANGELOG.md").read_text():
        sys.exit(f"CHANGELOG.md has no '## {tag}' entry")
    kit = ROOT / "kit" / "pyproject.toml"
    kit.write_text(re.sub(r'^version = ".*"$', f'version = "{version}"', kit.read_text(), count=1, flags=re.M))
    copier = ROOT / "copier.yml"
    copier.write_text(re.sub(r"(kit_ref:\n  type: str\n  default: )v\S+", rf"\g<1>{tag}", copier.read_text()))
    subprocess.run(["uv", "lock", "--project", "kit"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-qam", f"Release {tag}"], cwd=ROOT, check=True)
    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=ROOT, check=True)
    print(f"Tagged {tag}. Push: git push origin main {tag}")


if __name__ == "__main__":
    main(*sys.argv[1:2] or [""])
