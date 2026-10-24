"""The standard commands: app on localhost (and the tailnet), publish, backups, status, sql, doctor."""

import json
import subprocess

import pytest
import typer
from typer.testing import CliRunner

from duckkit.cli import add_standard_commands
from duckkit.store import connect
from tests.conftest import DB_SCHEMA

runner = CliRunner()


@pytest.fixture
def cli(spec):
    app = typer.Typer()
    add_standard_commands(app, spec, connect=lambda: connect(spec, DB_SCHEMA),
                          status=lambda con: [f"Items: {con.execute('SELECT count(*) FROM items').fetchone()[0]}"])
    return app


class FakeServe:
    """Stands in for the `tailscale serve` process: it keeps running and records the signals it gets."""

    def __init__(self, args):
        self.args, self.signals = args, []

    def poll(self):
        return None

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def launched(monkeypatch):
    calls = {"serve": []}
    monkeypatch.setattr("subprocess.call", lambda args, **kw: calls.update(streamlit=args, env=kw.get("env")) or 0)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tailscale")

    def run(args, **kw):
        state = {"BackendState": calls.get("backend", "Running"), "Self": {"DNSName": "mac.tail1234.ts.net."}}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(state), stderr="")

    def popen(args, **kw):
        calls["serve"].append(FakeServe(args))
        return calls["serve"][-1]

    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr("subprocess.Popen", popen)
    return calls


def test_app_on_localhost_only(cli, launched):
    result = runner.invoke(cli, ["app"])
    assert result.exit_code == 0
    args = launched["streamlit"]
    assert args[args.index("--server.address") + 1] == "localhost"
    assert args[args.index("--server.port") + 1] == "8600"
    assert launched["serve"] == []


def test_tailnet_forwards_while_the_app_runs(cli, launched):
    result = runner.invoke(cli, ["app", "--tailnet"])
    assert result.exit_code == 0 and "https://mac.tail1234.ts.net:8600" in result.output
    (serve,) = launched["serve"]
    assert serve.args == ["/usr/bin/tailscale", "serve", "--https=8600", "8600"]  # never `funnel`
    assert serve.signals


def test_tailnet_needs_a_connected_tailscale(cli, launched):
    launched["backend"] = "Stopped"
    assert runner.invoke(cli, ["app", "--tailnet"]).exit_code == 1
    assert "streamlit" not in launched


def test_demo_needs_a_demo_database(cli, launched, spec):
    assert runner.invoke(cli, ["app", "--demo"]).exit_code == 1
    spec.demo_db_path.parent.mkdir(parents=True, exist_ok=True)
    spec.demo_db_path.write_text("")
    assert runner.invoke(cli, ["app", "--demo"]).exit_code == 0
    assert launched["env"]["SHOP_DB"] == str(spec.demo_db_path)


def test_status_sql_publish_and_backups(cli, closed_db, spec, tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "b"))
    result = runner.invoke(cli, ["status"])
    assert "Items: 3" in result.output and "the app's views conform" in result.output
    assert "apple" in runner.invoke(cli, ["sql", "SELECT item FROM v_items"]).output
    assert runner.invoke(cli, ["sql", "DELETE FROM items"]).exit_code == 1
    assert "v_items: 3 rows" in runner.invoke(cli, ["publish", "--dry-run"]).output
    target = str(tmp_path / "p.duckdb")
    assert runner.invoke(cli, ["publish", "--to", target]).exit_code == 0
    assert "up to date" in runner.invoke(cli, ["publish", "--to", target, "--check"]).output
    assert "Backups:      none yet" in runner.invoke(cli, ["status"]).output
    assert runner.invoke(cli, ["backup"]).exit_code == 0
    assert "1 snapshots" in runner.invoke(cli, ["backups"]).output
    assert "Backups:      1, the newest 0 hours old" in runner.invoke(cli, ["status"]).output


def test_publish_refuses_the_demo_database(cli, spec, monkeypatch):
    monkeypatch.setattr(spec, "db_path", spec.demo_db_path)
    result = runner.invoke(cli, ["publish", "--to", "x.duckdb"])
    assert result.exit_code == 1 and "demo" in result.output


def test_doctor(cli, spec):
    assert "wasn't made from the scaffold" in runner.invoke(cli, ["doctor"]).output
    (spec.root / ".copier-answers.yml").write_text("_commit: v0.1.0\nmotherduck: true\nopt_out: [docs/dashboard.md]\n")
    output = runner.invoke(cli, ["doctor"]).output
    assert "CLAUDE.md is missing" in output
    assert ".claude/skills/publish/SKILL.md is missing" in output and "Dockerfile" not in output
    assert "docs/dashboard.md is opted out but docs/deviations.md doesn't say why" in output


def test_doctor_versions(cli, spec, monkeypatch):
    monkeypatch.setattr("duckkit.doctor.kit_version", lambda: "0.2.0")
    answers = spec.root / ".copier-answers.yml"
    answers.write_text("_commit: v0.1.0\n")
    assert "the files come from scaffold v0.1.0 but duckkit is 0.2.0" in runner.invoke(cli, ["doctor"]).output
    answers.write_text("_commit: v0.2.0\n")
    assert "but duckkit is" not in runner.invoke(cli, ["doctor"]).output
    answers.write_text("_commit: 31bae11\n")
    assert "not a release" in runner.invoke(cli, ["doctor"]).output
