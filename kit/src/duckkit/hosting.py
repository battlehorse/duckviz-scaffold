"""`hosting`: what the hosted app (the template's `cloud_run` option) runs, for `status --remote`.

The deploy of `/hosting` labels the Cloud Run service with the commit it built (`--update-labels=commit=<commit>`).
This module reads that label with `gcloud`, and counts the commits of `origin/main` that the hosted app does not run
yet. The project, region and service come from `.copier-answers.yml` (`gcp_project`, `gcp_region`, `project_name`).
Nothing here changes the service or the repo.
"""

import subprocess
from dataclasses import dataclass

from duckkit.doctor import answers
from duckkit.spec import AppSpec


@dataclass
class Deployed:
    """The hosted app's commit, and how many commits of `origin/main` it lacks (None: git can't tell)."""

    commit: str
    behind: int | None


class HostingError(RuntimeError):
    """The hosted app can't be read: the message says why."""


def service(spec: AppSpec) -> tuple[str, str, str] | None:
    """(service, project, region) of the hosted app; None when the app has no `cloud_run`."""
    found = answers(spec) or {}
    if not found.get("cloud_run"):
        return None
    return found["project_name"], found["gcp_project"], found["gcp_region"]


def deployed(spec: AppSpec) -> Deployed | None:
    """What the hosted app runs; None when the app has no `cloud_run`. Raises HostingError."""
    hosted = service(spec)
    if hosted is None:
        return None
    name, project, region = hosted
    commit = _run(["gcloud", "run", "services", "describe", name, f"--project={project}", f"--region={region}",
                   "--format=value(spec.template.metadata.labels.commit)"], spec, "gcloud")
    if not commit:
        raise HostingError("the service has no commit label: deploy it with `/hosting deploy`")
    try:
        behind = int(_run(["git", "rev-list", "--count", f"{commit}..origin/main"], spec, "git"))
    except HostingError:
        behind = None  # the commit is not in this clone: fetch first
    return Deployed(commit, behind)


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
