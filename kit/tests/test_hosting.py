"""`status --remote`: whether the published copy and the hosted app are current. Nothing here reaches MotherDuck or
Cloud Run: the published copy is a file, and `gcloud` and `git` are stand-ins."""

import duckdb
import pytest

from duckkit import hosting
from duckkit.cli import remote_lines
from duckkit.publish import publish

ANSWERS = "_commit: v0.6.1\nproject_name: shopviz\ncloud_run: true\ngcp_project: shop-123\ngcp_region: europe-west2\n"


def fake_tools(monkeypatch, label: str = "abc1234", behind: str | None = "0"):
    """`gcloud` answers with `label`; `git rev-list` with `behind` (None: the commit is not in this clone)."""
    calls = []

    def run(command, spec, tool):
        calls.append(command)
        if tool == "gcloud":
            return label
        if behind is None:
            raise hosting.HostingError("`git` failed: bad revision")
        return behind

    monkeypatch.setattr(hosting, "_run", run)
    return calls


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


@pytest.mark.parametrize("behind, line", [
    ("0", "Deployed:     abc1234, the same as origin/main"),
    ("3", "Deployed:     abc1234, 3 commits behind origin/main: `/hosting deploy`"),
    (None, "Deployed:     abc1234, a commit this clone lacks: `git fetch`, then ask again"),
])
def test_the_deployed_line_compares_the_hosted_commit_with_main(spec, monkeypatch, behind, line):
    (spec.root / ".copier-answers.yml").write_text(ANSWERS)
    calls = fake_tools(monkeypatch, behind=behind)
    assert remote_lines(spec, publishing=False) == [line]
    assert calls[0] == ["gcloud", "run", "services", "describe", "shopviz", "--project=shop-123",
                        "--region=europe-west2", "--format=value(spec.template.metadata.labels.commit)"]


def test_a_service_without_a_commit_label_says_how_to_get_one(spec, monkeypatch):
    (spec.root / ".copier-answers.yml").write_text(ANSWERS)
    fake_tools(monkeypatch, label="")
    assert remote_lines(spec, publishing=False) == [
        "Deployed:     can't tell: the service has no commit label: deploy it with `/hosting deploy`"]


def test_a_missing_tool_is_reported_not_raised(spec, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("gcloud")

    (spec.root / ".copier-answers.yml").write_text(ANSWERS)
    monkeypatch.setattr(hosting.subprocess, "run", missing)
    assert remote_lines(spec, publishing=False) == ["Deployed:     can't tell: `gcloud` is not installed"]
