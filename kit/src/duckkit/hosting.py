"""`hosting`: what the hosted app (the template's `cloud_run` option) runs, for `status --remote`.

The deploy of `/hosting` labels the Cloud Run revision with the commit it built (`--update-labels=commit=<commit>`).
This module finds the revision that serves the traffic (after a rollback, an older one), reads its label with
`gcloud`, and compares that commit with `origin/main`, as of the last fetch. The project, region and service come
from `.copier-answers.yml` (`gcp_project`, `gcp_region`, `project_name`). Nothing here changes the service or the
repo.
"""

import json
import subprocess
from dataclasses import dataclass

import yaml

from duckkit.doctor import ANSWERS, answers
from duckkit.spec import AppSpec


@dataclass
class Deployed:
    """The commit that the hosted app serves, and where it stands against `origin/main`.

    `behind` counts the commits of `origin/main` that it lacks. `on_main` is False for a commit that is not on
    `origin/main` (a branch deployed for a test). `known` is False when this clone does not have the commit."""

    commit: str
    behind: int = 0
    on_main: bool = True
    known: bool = True


class HostingError(RuntimeError):
    """The hosted app can't be read: the message says why."""


def service(spec: AppSpec) -> tuple[str, str, str] | None:
    """(service, project, region) of the hosted app; None when the app has no `cloud_run`. Raises HostingError."""
    try:
        found = answers(spec) or {}
    except yaml.YAMLError as e:
        raise HostingError(f"{ANSWERS} can't be read: {str(e).splitlines()[0]}") from e
    if not found.get("cloud_run"):
        return None
    missing = [key for key in ("project_name", "gcp_project", "gcp_region") if not found.get(key)]
    if missing:
        raise HostingError(f"{ANSWERS} has no {', '.join(missing)}")
    return found["project_name"], found["gcp_project"], found["gcp_region"]


def deployed(spec: AppSpec) -> Deployed | None:
    """What the hosted app serves; None when the app has no `cloud_run`. Raises HostingError."""
    hosted = service(spec)
    if hosted is None:
        return None
    name, project, region = hosted
    where = [f"--project={project}", f"--region={region}"]
    described = _run(["gcloud", "run", "services", "describe", name, *where, "--format=json"], spec, "gcloud")
    try:
        traffic = json.loads(described).get("status", {}).get("traffic") or []
    except json.JSONDecodeError as e:
        raise HostingError("`gcloud` gave an answer that is not JSON") from e
    serving = max(traffic, key=lambda t: t.get("percent", 0), default={}).get("revisionName")
    if not serving:
        raise HostingError("the service serves no revision")
    commit = _run(["gcloud", "run", "revisions", "describe", serving, *where,
                   "--format=value(metadata.labels.commit)"], spec, "gcloud")
    if not commit:
        raise HostingError(f"the serving revision {serving} has no commit label: deploy with `/hosting deploy`")
    if not _succeeds(["git", "cat-file", "-e", f"{commit}^{{commit}}"], spec):
        return Deployed(commit, known=False)
    if not _succeeds(["git", "merge-base", "--is-ancestor", commit, "origin/main"], spec):
        return Deployed(commit, on_main=False)
    count = _run(["git", "rev-list", "--count", f"{commit}..origin/main"], spec, "git")
    try:
        return Deployed(commit, behind=int(count))
    except ValueError as e:
        raise HostingError(f"`git rev-list` gave {count!r}, not a count") from e


def _succeeds(command: list[str], spec: AppSpec) -> bool:
    """Whether a `git` check holds. Raises HostingError when git itself can't run."""
    try:
        return subprocess.run(command, cwd=spec.root, capture_output=True, check=False, timeout=60).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise HostingError(f"`{command[0]}` could not run: {e}") from e


def _run(command: list[str], spec: AppSpec, tool: str) -> str:
    try:
        out = subprocess.run(command, cwd=spec.root, capture_output=True, text=True, check=False, timeout=60)
    except FileNotFoundError as e:
        raise HostingError(f"`{tool}` is not installed") from e
    except subprocess.TimeoutExpired as e:
        raise HostingError(f"`{tool}` did not answer in 60 s") from e
    if out.returncode != 0:
        raise HostingError(f"`{tool}` failed: {(out.stderr.strip().splitlines() or ['no message'])[-1]}")
    return out.stdout.strip()
