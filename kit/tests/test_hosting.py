"""`status --remote`: whether the published copy and the hosted app are current. Nothing here reaches MotherDuck or
Cloud Run: the published copy is a file, and `gcloud` and `git` are stand-ins for `subprocess.run`."""

import json
import subprocess

import duckdb
import pytest
import typer
from typer.testing import CliRunner

from duckkit import hosting
from duckkit.cli import add_standard_commands, remote_lines
from duckkit.publish import publish

ANSWERS = "_commit: v0.6.1\nproject_name: shopviz\ncloud_run: true\ngcp_project: shop-123\ngcp_region: europe-west2\n"
SERVICE = {"status": {"traffic": [{"revisionName": "shopviz-00007", "percent": 0, "latestRevision": True},
                                  {"revisionName": "shopviz-00006", "percent": 100}]}}


class Tools:
    """Answers `gcloud` and `git` as a hosted app with `label` on its serving revision would. Keeps the commands."""

    def __init__(self, label="abc1234", known=True, on_main=True, behind="0", fail=None, has_main=True):
        self.label, self.known, self.on_main, self.behind, self.fail = label, known, on_main, behind, fail
        self.has_main = has_main
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if self.fail and command[0] == self.fail:
            return subprocess.CompletedProcess(command, 1, "", "ERROR: (gcloud) you do not have permission\n")
        if command[:4] == ["gcloud", "run", "services", "describe"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(SERVICE), "")
        if command[:4] == ["gcloud", "run", "revisions", "describe"]:
            return subprocess.CompletedProcess(command, 0, self.label + "\n", "")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0 if self.has_main else 1)
        if command[:2] == ["git", "cat-file"]:
            return subprocess.CompletedProcess(command, 0 if self.known else 128)
        if command[:2] == ["git", "merge-base"]:
            return subprocess.CompletedProcess(command, 0 if self.on_main else 1)
        return subprocess.CompletedProcess(command, 0, self.behind + "\n", "")


@pytest.fixture
def cloud_run(spec, monkeypatch):
    (spec.root / ".copier-answers.yml").write_text(ANSWERS)

    def use(tools):
        monkeypatch.setattr(hosting.subprocess, "run", tools)
        return tools
    return use


def test_a_published_copy_like_the_database_is_up_to_date(closed_db, spec, tmp_path):
    spec.motherduck_target = str(tmp_path / "published.duckdb")
    publish(spec)
    assert remote_lines(spec, publishing=True) == [f"Published:    {spec.motherduck_target} is up to date"]


def test_a_published_copy_older_than_the_database_names_the_views_that_differ(db, spec, tmp_path):
    spec.motherduck_target = str(tmp_path / "published.duckdb")
    db.close()
    publish(spec)
    with duckdb.connect(str(spec.db_path)) as con:
        con.execute("UPDATE items SET price = 9 WHERE name = 'apple'")
    assert remote_lines(spec, publishing=True) == [
        "Published:    1 view differs from the database (v_items): `shop publish` sends them"]


def test_without_a_token_the_published_line_says_why(closed_db, spec):
    (line,) = remote_lines(spec, publishing=True)
    assert line.startswith("Published:    can't tell: no MotherDuck token")


def test_an_app_without_cloud_run_has_no_deployed_line(closed_db, spec):
    (spec.root / ".copier-answers.yml").write_text(ANSWERS.replace("cloud_run: true", "cloud_run: false"))
    assert remote_lines(spec, publishing=False) == []


def test_the_deployed_commit_is_the_serving_revisions_not_the_latest(spec, cloud_run):
    tools = cloud_run(Tools(behind="3"))
    assert remote_lines(spec, publishing=False) == [
        "Deployed:     abc1234, 3 commits behind origin/main: `/hosting deploy`"]
    where = ["--project=shop-123", "--region=europe-west2"]
    assert tools.commands == [
        ["gcloud", "run", "services", "describe", "shopviz", *where, "--format=json"],
        ["gcloud", "run", "revisions", "describe", "shopviz-00006", *where, "--format=value(metadata.labels.commit)"],
        ["git", "rev-parse", "--verify", "-q", "origin/main"],
        ["git", "cat-file", "-e", "abc1234^{commit}"],
        ["git", "merge-base", "--is-ancestor", "abc1234", "origin/main"],
        ["git", "rev-list", "--count", "abc1234..origin/main"],
    ]


@pytest.mark.parametrize("tools, state", [
    (Tools(behind="0"), "the same as origin/main"),
    (Tools(behind="1"), "1 commit behind origin/main: `/hosting deploy`"),
    (Tools(known=False), "a commit this clone lacks: `git fetch`, then ask again"),
    (Tools(on_main=False), "not on origin/main (a branch, or a commit not pushed, was deployed)"),
])
def test_the_deployed_line_says_where_the_commit_stands(spec, cloud_run, tools, state):
    cloud_run(tools)
    assert remote_lines(spec, publishing=False) == [f"Deployed:     abc1234, {state}"]


@pytest.mark.parametrize("answers, tools, reason", [
    (ANSWERS, Tools(label=""), "the serving revision shopviz-00006 has no commit label: deploy with `/hosting deploy`"),
    (ANSWERS, Tools(fail="gcloud"), "`gcloud` failed: ERROR: (gcloud) you do not have permission"),
    (ANSWERS, Tools(behind="fatal"), "`git rev-list` gave 'fatal', not a count"),
    (ANSWERS, Tools(has_main=False), "this clone has no origin/main: `git fetch`, then ask again"),
    (ANSWERS.replace("gcp_region: europe-west2\n", ""), Tools(), ".copier-answers.yml has no gcp_region"),
    ("cloud_run: [true\n", Tools(), ".copier-answers.yml can't be read"),
])
def test_a_check_that_cant_run_says_why_in_its_line(spec, cloud_run, answers, tools, reason):
    cloud_run(tools)
    (spec.root / ".copier-answers.yml").write_text(answers)
    (line,) = remote_lines(spec, publishing=False)
    assert line.startswith(f"Deployed:     can't tell: {reason}")


def test_a_missing_gcloud_is_reported_not_raised(spec, cloud_run):
    def missing(*args, **kwargs):
        raise FileNotFoundError("gcloud")

    cloud_run(missing)
    assert remote_lines(spec, publishing=False) == ["Deployed:     can't tell: `gcloud` is not installed"]


def test_status_prints_the_remote_lines_only_with_remote(closed_db, spec, cloud_run):
    cloud_run(Tools())
    app = typer.Typer()
    add_standard_commands(app, spec, backups=False, publishing=False)
    plain = CliRunner().invoke(app, ["status"]).output
    remote = CliRunner().invoke(app, ["status", "--remote"]).output
    assert "Deployed:" not in plain
    assert remote == plain + "Deployed:     abc1234, the same as origin/main\n"


def test_without_a_database_status_still_checks_the_hosted_app(spec, cloud_run):
    cloud_run(Tools())
    app = typer.Typer()
    add_standard_commands(app, spec, backups=False, publishing=False)
    assert CliRunner().invoke(app, ["status", "--remote"]).output.endswith(
        "Deployed:     abc1234, the same as origin/main\n")
