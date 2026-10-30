"""The standard commands: app on localhost (and the tailnet), publish, backups, status, sql, doctor."""

import json
import shutil
import subprocess

import duckdb
import pytest
import typer
from typer.testing import CliRunner

from duckkit.cli import add_standard_commands
from duckkit.curated import CuratedTable, export
from duckkit.demo import MARKER
from duckkit.store import connect
from tests.conftest import DB_SCHEMA, git

runner = CliRunner()


@pytest.fixture
def cli(spec):
    app = typer.Typer()
    add_standard_commands(app, spec, connect=lambda: connect(spec, DB_SCHEMA),
                          status=lambda con: [f"Items: {con.execute('SELECT count(*) FROM items').fetchone()[0]}"],
                          curations=True)
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
    assert "up to date: v_contract 1 rows, v_items 3 rows" in runner.invoke(cli, ["publish", "--to", target, "--check"]).output
    with duckdb.connect(target) as con:
        con.execute("UPDATE v_items SET price = price + 1 WHERE item = 'apple'")  # same rows, new price
    stale = runner.invoke(cli, ["publish", "--to", target, "--check"])
    assert stale.exit_code == 1 and "differs from this database (run `shop publish`" in stale.output
    assert "v_items: 3 rows on both sides, with different contents" in stale.output
    assert "v_contract" not in stale.output  # unchanged tables aren't listed
    assert "Backups:      none yet" in runner.invoke(cli, ["status"]).output
    assert runner.invoke(cli, ["backup"]).exit_code == 0
    assert "1 snapshots" in runner.invoke(cli, ["backups"]).output
    assert "Backups:      1, the newest 0 hours old" in runner.invoke(cli, ["status"]).output


def test_backup_copies_off_the_machine_and_fetch_backup_brings_it_back(cli, closed_db, spec, gcs, tmp_path,
                                                                       monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "b"))
    result = runner.invoke(cli, ["backup"])
    assert result.exit_code == 0 and "Copied to gs://shop-backups/shop/shop-" in result.output
    name = next((tmp_path / "b").iterdir()).name
    listed = runner.invoke(cli, ["backups"]).output
    assert f"{name}" in listed and "here and in Cloud Storage" in listed
    assert "1 snapshots in" in listed and "1 in gs://shop-backups/shop" in listed
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "new"))  # a new machine: no local snapshot
    assert "Cloud Storage only" in runner.invoke(cli, ["backups"]).output
    fetched = runner.invoke(cli, ["fetch-backup"])
    assert fetched.exit_code == 0 and f"Fetched {tmp_path / 'new' / name}" in fetched.output
    assert runner.invoke(cli, ["fetch-backup"]).exit_code == 1  # it is here already


def test_a_failed_upload_exits_1_and_keeps_the_local_snapshot(cli, closed_db, spec, gcs, tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "b"))
    gcs.fail = "cp"
    result = runner.invoke(cli, ["backup"])
    assert result.exit_code == 1 and "Backed up to" in result.output
    assert "the copy to Cloud Storage failed" in result.output and "is only on this machine" in result.output
    assert len(list((tmp_path / "b").iterdir())) == 1
    gcs.fail = "objects"
    listed = runner.invoke(cli, ["backups"])
    assert listed.exit_code == 0 and "Cloud Storage can't be read" in listed.output
    assert "here; Cloud Storage unknown" in listed.output and "here only" not in listed.output


def test_publish_refuses_a_demo_database_anywhere(cli, spec, monkeypatch, tmp_path):
    """A database holding the demo marker table is a demo one, whatever its path."""
    path = tmp_path / "elsewhere.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE demo_params (seed INTEGER)")
    monkeypatch.setattr(spec, "db_path", path)
    result = runner.invoke(cli, ["publish", "--to", str(tmp_path / "published.duckdb")])
    assert result.exit_code == 1 and "is a demo database" in result.output
    assert not (tmp_path / "published.duckdb").exists()


def test_is_demo(spec, tmp_path):
    from duckkit.demo import is_demo

    assert not is_demo(spec, tmp_path / "missing.duckdb")
    (tmp_path / "junk.duckdb").write_text("not a database")
    assert not is_demo(spec, tmp_path / "junk.duckdb")
    spec.demo_db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(spec.demo_db_path)) as con:  # the demo path without the marker: not a demo database
        con.execute("CREATE TABLE items (name VARCHAR)")
    assert not is_demo(spec, spec.demo_db_path)
    with duckdb.connect(str(spec.demo_db_path)) as con:
        con.execute("CREATE TABLE demo_params (params VARCHAR)")
    assert is_demo(spec, spec.demo_db_path)


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


def test_doctor_remote_refuses_curated_decisions_in_a_public_repo(cli, spec, monkeypatch):
    (spec.root / ".copier-answers.yml").write_text("_commit: v0.1.0\n")
    subprocess.run(["git", "init", "-q"], cwd=spec.root, check=True)
    (spec.root / "curated").mkdir()
    (spec.root / "curated" / "labels.csv").write_text("day,label\n")
    seen = {"visibility": "PUBLIC"}
    monkeypatch.setattr("duckkit.doctor.visibility", lambda _spec: seen["visibility"])
    assert "curated" not in runner.invoke(cli, ["doctor", "--remote"]).output  # not in git
    subprocess.run(["git", "add", "curated"], cwd=spec.root, check=True)
    assert "the GitHub repo is public: make the repo private" in runner.invoke(cli, ["doctor", "--remote"]).output
    assert "curated" not in runner.invoke(cli, ["doctor"]).output  # only with --remote
    seen["visibility"] = "PRIVATE"
    assert "curated" not in runner.invoke(cli, ["doctor", "--remote"]).output
    seen["visibility"] = None
    assert "couldn't check that the GitHub repo is private" in runner.invoke(cli, ["doctor", "--remote"]).output


def test_doctor_remote_refuses_a_backup_bucket_that_isnt_private(cli, spec, gcs, monkeypatch):
    (spec.root / ".copier-answers.yml").write_text("_commit: v0.1.0\n")
    monkeypatch.setattr("duckkit.doctor.newest_release", lambda _source: None)
    private = runner.invoke(cli, ["doctor", "--remote"])
    assert "gs://shop-backups" not in private.output  # (the test repo lacks the expected files: doctor exits 1)
    assert ["gcloud", "storage", "buckets", "describe", "gs://shop-backups", "--raw", "--format=json"] in gcs.commands
    gcs.bucket = {"iamConfiguration": {"publicAccessPrevention": "inherited"}}
    out = runner.invoke(cli, ["doctor", "--remote"])
    assert "gs://shop-backups holds the whole database and doesn't prevent public access" in out.output
    assert "gs://shop-backups has no uniform bucket-level access" in out.output
    assert "gs://shop-backups" not in runner.invoke(cli, ["doctor"]).output  # only with --remote
    gcs.bucket = {}  # an answer without iamConfiguration: a note, not a problem
    unknown = runner.invoke(cli, ["doctor", "--remote"])
    assert "couldn't check that the backup bucket is private" in unknown.output and "public access" not in unknown.output
    assert "gave no iamConfiguration" in unknown.output
    gcs.fail = "buckets"
    assert "couldn't check that the backup bucket is private" in runner.invoke(cli, ["doctor", "--remote"]).output
    monkeypatch.delenv("SHOP_BACKUP_REMOTE")
    gcs.commands.clear()
    runner.invoke(cli, ["doctor", "--remote"])
    assert gcs.commands == []  # no remote: no gcloud


def test_status_remote_says_how_old_the_newest_off_machine_backup_is(cli, closed_db, spec, gcs, tmp_path,
                                                                     monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "b"))
    monkeypatch.setattr("duckkit.hosting.deployed", lambda _spec: None)
    assert "Off-machine:  none yet in gs://shop-backups/shop" in runner.invoke(cli, ["status", "--remote"]).output
    assert runner.invoke(cli, ["backup"]).exit_code == 0
    out = runner.invoke(cli, ["status", "--remote"]).output
    assert "Off-machine:  1, the newest 0 hours old (gs://shop-backups/shop)" in out
    assert "Off-machine" not in runner.invoke(cli, ["status"]).output  # only with --remote: no network
    gcs.fail = "objects"
    assert "Off-machine:  can't tell:" in runner.invoke(cli, ["status", "--remote"]).output
    monkeypatch.delenv("SHOP_BACKUP_REMOTE")
    assert "Off-machine:  none: the backups are only on this machine" in runner.invoke(cli, ["status", "--remote"]).output


def test_status_says_how_to_bring_stale_views_up_to_date(cli, closed_db, spec):
    with duckdb.connect(str(spec.db_path)) as con:  # as if made by an older version
        con.execute("DROP VIEW v_items")
    out = runner.invoke(cli, ["status"]).output
    assert "1 problems for the app → `shop ingest` recreates the views" in out and "  ✗ v_items: missing" in out


def test_status_says_a_demo_database_is_made_up(cli, closed_db, spec):
    assert "Demo:" not in runner.invoke(cli, ["status"]).output
    with duckdb.connect(str(spec.db_path)) as con:
        con.execute("CREATE TABLE demo_params (params VARCHAR)")
    assert "Demo:         made-up data (`shop demo`), not your own" in runner.invoke(cli, ["status"]).output


def test_status_warns_when_the_demo_database_no_longer_fits_the_contract(cli, closed_db, spec):
    """A demo built by an older version of the app would show only an error in `app --demo`: status says so."""
    assert "Demo file:" not in runner.invoke(cli, ["status"]).output  # no demo database
    shutil.copy(closed_db, spec.demo_db_path)
    assert "Demo file:" not in runner.invoke(cli, ["status"]).output  # one that fits
    with duckdb.connect(str(spec.demo_db_path)) as con:  # as if built by an older version
        con.execute("DROP VIEW v_items")
    out = runner.invoke(cli, ["status"]).output
    line = next(ln for ln in out.splitlines() if ln.startswith("Demo file:"))
    assert "demo.duckdb" in line and "(1 problem)" in line and "`shop demo`" in line
    assert "Contract:     shop 1.0, the app's views conform" in out  # the real database is fine
    spec.db_path.unlink()  # a fresh clone with only the demo: still warned
    assert "Demo file:" in runner.invoke(cli, ["status"]).output


def test_status_says_when_it_cant_read_the_demo_and_skips_it_when_it_is_the_database(cli, closed_db, spec,
                                                                                     monkeypatch):
    spec.demo_db_path.write_bytes(b"not a database")
    line = next(ln for ln in runner.invoke(cli, ["status"]).output.splitlines() if ln.startswith("Demo file:"))
    assert "can't read demo.duckdb" in line and "rebuild" not in line  # no rebuild advice for a read error
    shutil.copy(closed_db, spec.demo_db_path)
    with duckdb.connect(str(spec.demo_db_path)) as con:
        con.execute("DROP VIEW v_items")
    monkeypatch.setattr(spec, "db_path", spec.demo_db_path)  # SHOP_DB names the demo: status checks it itself
    out = runner.invoke(cli, ["status"]).output
    assert "Demo file:" not in out and "1 problems for the app" in out  # once, in the contract line


def test_curated_check_refuses_an_emptied_file_unless_confirmed(cli, spec, monkeypatch):
    spec.curated_dir.mkdir()
    (spec.curated_dir / "labels.csv").write_text("day,label\n2026-01-01,away\n2026-01-02,home\n")
    git(spec.root, "init", "-q", "-b", "main")
    git(spec.root, "add", "curated")
    git(spec.root, "commit", "-q", "-m", "decisions")
    (spec.curated_dir / "labels.csv").write_text("day,label\n")
    git(spec.root, "add", "curated")
    result = runner.invoke(cli, ["curated-check"])
    assert result.exit_code == 1 and "labels.csv: 2 → 0 rows" in result.output
    monkeypatch.setenv("ALLOW_CURATED_LOSS", "1")
    assert runner.invoke(cli, ["curated-check"]).exit_code == 0


# ─── A restored backup and the curated decisions (curated=) ───

KINDS = CuratedTable("items", ("name", "kind"), "name", where="kind IS NOT NULL", key="name")


@pytest.fixture
def curated_cli(spec):
    app = typer.Typer()
    add_standard_commands(app, spec, connect=lambda: connect(spec, DB_SCHEMA), curations=True, curated=[KINDS])
    return app


def test_a_restore_older_than_curated_is_shown_and_git_can_win(curated_cli, db, spec, tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_DIR", str(tmp_path / "b"))
    db.close()
    assert runner.invoke(curated_cli, ["backup"]).exit_code == 0  # the snapshot: apple, leek, pear as made
    with duckdb.connect(str(spec.db_path)) as con:  # later decisions, committed to curated/
        con.execute("UPDATE items SET kind = 'veg' WHERE name = 'apple'")
        export(con, spec.curated_dir, [KINDS])
    assert "Curated:      in line with curated/" in runner.invoke(curated_cli, ["status"]).output
    snapshot = next((tmp_path / "b").iterdir())
    restored = tmp_path / "restored.duckdb"
    out = runner.invoke(curated_cli, ["restore", str(snapshot), "--to", str(restored)]).output
    assert "✗ the decisions in restored.duckdb differ from curated/:" in out
    assert "items: 1 changed, 0 only in the database, 0 only in curated/" in out and "For git to win:" in out
    assert runner.invoke(curated_cli, ["curated-diff", "--db", str(restored)]).exit_code == 1
    files = (spec.curated_dir / "items.csv").read_text()
    refused = runner.invoke(curated_cli, ["curated-align", "--db", str(spec.db_path)])
    assert refused.exit_code == 1 and "is the app's database" in refused.output
    aligned = runner.invoke(curated_cli, ["curated-align", "--db", str(restored)])
    assert aligned.exit_code == 0 and "Aligned" in aligned.output and "match curated/" in aligned.output
    assert runner.invoke(curated_cli, ["curated-diff", "--db", str(restored)]).exit_code == 0
    assert (spec.curated_dir / "items.csv").read_text() == files  # curated/ is only read
    with duckdb.connect(str(restored)) as con:
        assert con.execute("SELECT kind FROM items WHERE name = 'apple'").fetchone() == ("veg",)


def test_status_says_when_the_decisions_differ(curated_cli, db, spec):
    export(db, spec.curated_dir, [KINDS])
    db.execute("UPDATE items SET kind = 'veg' WHERE name = 'pear'")  # never exported: the database is newer
    db.close()
    out = runner.invoke(curated_cli, ["status"]).output
    assert "Curated:      1 decisions differ from curated/ (`shop curated-diff`)" in out
    assert runner.invoke(curated_cli, ["curated-diff"]).exit_code == 1


def test_curated_align_refuses_a_demo_database(curated_cli, db, spec, tmp_path):
    export(db, spec.curated_dir, [KINDS])
    db.close()
    demo = tmp_path / "copy.duckdb"
    shutil.copy(spec.db_path, demo)
    with duckdb.connect(str(demo)) as con:
        con.execute(f"CREATE TABLE {MARKER} (params VARCHAR)")
    out = runner.invoke(curated_cli, ["curated-align", "--db", str(demo)])
    assert out.exit_code == 1 and "is a demo database" in out.output
    assert runner.invoke(curated_cli, ["curated-diff", "--db", str(demo)]).exit_code == 1
    spec.db_path.unlink()
    shutil.copy(demo, spec.db_path)  # the demo as the app's database
    assert "Curated:      a demo database" in runner.invoke(curated_cli, ["status"]).output


def test_curated_align_reports_a_failure_and_leaves_the_file(curated_cli, db, spec, tmp_path):
    export(db, spec.curated_dir, [KINDS])
    db.close()
    other = tmp_path / "other.duckdb"
    with duckdb.connect(str(other)) as con:  # an older schema: no items table
        con.execute("CREATE TABLE labels (day DATE)")
    out = runner.invoke(curated_cli, ["curated-align", "--db", str(other)])
    assert out.exit_code == 1 and "is unchanged (the transaction rolled back)" in out.output


def test_without_curated_tables_there_are_no_curated_commands(cli, closed_db):
    assert "Curated:" not in runner.invoke(cli, ["status"]).output
    assert runner.invoke(cli, ["curated-diff"]).exit_code == 2


# ─── doctor: the docs' paths ───

def test_doctor_finds_broken_doc_links_and_backticked_paths(spec):
    from duckkit.doctor import broken_links

    (spec.root / "docs" / "design").mkdir(parents=True)
    (spec.root / "docs" / "design" / "contract.md").write_text("# Contract\n")
    (spec.root / "docs" / "README.md").write_text(
        "[ok](design/contract.md) [anchor](design/contract.md#views) [gone](design/gone.md) [web](https://x.org/a.md)"
        " [here](#top) [placeholder](<file>.md)\nSee `docs/design/contract.md` and `docs/contract.md`.\n")
    (spec.root / ".claude" / "skills" / "x").mkdir(parents=True)
    (spec.root / ".claude" / "skills" / "x" / "SKILL.md").write_text("Read [the contract](../../../docs/contract.md).\n")
    (spec.root / "CHANGELOG.md").write_text("Moved `docs/contract.md`.\n")  # names old paths on purpose
    assert sorted(broken_links(spec)) == [(".claude/skills/x/SKILL.md", "../../../docs/contract.md"),
                                          ("docs/README.md", "design/gone.md"), ("docs/README.md", "docs/contract.md")]


def test_doctor_finds_spec_paths_that_match_no_file(spec):
    from duckkit.doctor import stale_spec_paths

    (spec.root / ".claude").mkdir()
    (spec.root / ".claude" / "spec-paths").write_text(
        "[shape]\ndocs/design/architecture.md\ndocs/architecture.md   # moved\n[behaviour]\ntests/**/conftest.py\n")
    (spec.root / "docs" / "design").mkdir(parents=True)
    (spec.root / "docs" / "design" / "architecture.md").write_text("")
    (spec.root / "tests" / "app").mkdir(parents=True)
    (spec.root / "tests" / "app" / "conftest.py").write_text("")
    assert stale_spec_paths(spec) == ["docs/architecture.md"]


def test_doctor_notes_docs_missing_from_the_index(spec):
    from duckkit.doctor import unindexed_docs

    (spec.root / "docs" / "guides").mkdir(parents=True)
    for name in ("guides/cli.md", "guides/data.md", "extra.md"):
        (spec.root / "docs" / name).write_text("")
    assert unindexed_docs(spec) == []  # no index yet: nothing to compare
    (spec.root / "docs" / "README.md").write_text("| [Commands](guides/cli.md) | … |\n")
    assert unindexed_docs(spec) == ["docs/extra.md", "docs/guides/data.md"]


def test_doctor_reports_the_docs_paths(cli, spec):
    (spec.root / ".copier-answers.yml").write_text("_commit: v0.1.0\n")
    (spec.root / "docs").mkdir()
    (spec.root / "docs" / "README.md").write_text("[gone](gone.md)\n")
    (spec.root / "docs" / "extra.md").write_text("")
    out = runner.invoke(cli, ["doctor"]).output
    assert "✗ docs/README.md names gone.md, which doesn't exist" in out
    assert "· docs/extra.md is not in docs/README.md, the index" in out
