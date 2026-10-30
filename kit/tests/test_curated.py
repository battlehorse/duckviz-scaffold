"""Curated decisions: exported sorted and atomically, restored into a rebuilt database in one transaction, never
wiped by a database without decisions, and kept apart from a demo database."""

from datetime import date

import duckdb
import pytest

from duckkit.curated import (
    CuratedTable,
    Difference,
    FileChange,
    Refused,
    align,
    compare,
    curating,
    export,
    file_changes,
    holds_decisions,
    not_manual,
    restore,
)
from duckkit.demo import build_demo
from duckkit.store import connect
from tests.conftest import DB_SCHEMA, git

SCHEMA = DB_SCHEMA + """
CREATE TABLE IF NOT EXISTS labels (day DATE PRIMARY KEY, label VARCHAR NOT NULL, classified_by VARCHAR,
                                   classified_at TIMESTAMP);
"""
LABELS = CuratedTable("labels", ("day", "label", "classified_by", "classified_at"), "day")
KINDS = CuratedTable("items", ("name", "kind"), "name", where="kind IS NOT NULL", key="name")
TABLES = [LABELS, KINDS]


@pytest.fixture
def con(spec):
    """The app's database: three items from the ingestion, two of them with a kind decided, and two labels."""
    con = connect(spec, SCHEMA)
    con.execute("INSERT INTO items VALUES ('pear', 'fruit', 0.5, 'z'), ('apple', 'fruit', 0.4, 'x'),"
                " ('leek', NULL, 0.9, 'y')")
    con.execute("INSERT INTO labels VALUES ('2026-03-02', 'party, with \"guests\"', 'manual', '2026-03-03 10:00'),"
                " ('2026-01-05', 'away', 'llm', NULL)")
    yield con
    con.close()


def rebuilt(spec):
    """A new database with the ingestion's rows and no decisions."""
    spec.db_path.unlink()
    con = connect(spec, SCHEMA)
    con.execute("INSERT INTO items VALUES ('apple', NULL, 0.4, 'x'), ('leek', NULL, 0.9, 'y'),"
                " ('pear', NULL, 0.5, 'z')")
    return con


def test_export_writes_sorted_decisions_only(con, spec):
    assert export(con, spec.curated_dir, TABLES)
    assert (spec.curated_dir / "labels.csv").read_text().splitlines() == [
        "day,label,classified_by,classified_at",
        "2026-01-05,away,llm,",
        '2026-03-02,"party, with ""guests""",manual,2026-03-03 10:00:00',
    ]
    assert (spec.curated_dir / "items.csv").read_text().splitlines() == ["name,kind", "apple,fruit", "pear,fruit"]
    assert sorted(p.name for p in spec.curated_dir.iterdir()) == ["items.csv", "labels.csv"]  # no temporary file


def test_restore_brings_back_every_decision(con, spec):
    export(con, spec.curated_dir, TABLES)
    before = {t.name: con.execute(f"FROM {t.name} ORDER BY ALL").fetchall() for t in TABLES}
    con.close()
    con = rebuilt(spec)
    assert restore(con, spec.curated_dir, TABLES) == {"labels": 2, "items": 2}
    assert {t.name: con.execute(f"FROM {t.name} ORDER BY ALL").fetchall() for t in TABLES} == before


def test_restore_keeps_an_empty_text_apart_from_a_null(con, spec):
    con.execute("UPDATE labels SET classified_by = CASE WHEN day = '2026-03-02' THEN '' END")
    export(con, spec.curated_dir, TABLES)
    con.close()
    con = rebuilt(spec)
    restore(con, spec.curated_dir, TABLES)
    assert con.execute("SELECT classified_by FROM labels ORDER BY day").fetchall() == [(None,), ("",)]


def test_restore_reads_an_empty_value_of_another_type_as_null(con, spec):
    con.close()
    con = rebuilt(spec)
    spec.curated_dir.mkdir(parents=True, exist_ok=True)
    (spec.curated_dir / "labels.csv").write_text('day,label,classified_by,classified_at\n2026-01-05,away,llm,""\n')
    restore(con, spec.curated_dir, [LABELS])
    assert con.execute("SELECT classified_at FROM labels").fetchall() == [(None,)]


def test_restore_only_into_a_database_without_decisions(con, spec):
    export(con, spec.curated_dir, TABLES)
    assert restore(con, spec.curated_dir, TABLES) is None
    con.close()
    con = rebuilt(spec)
    assert restore(con, spec.curated_dir / "none", TABLES) is None  # no files
    assert not holds_decisions(con, TABLES)


def test_restore_skips_keys_not_ingested_yet_and_files_without_a_column(con, spec):
    spec.curated_dir.mkdir()
    (spec.curated_dir / "labels.csv").write_text("day,label\n2026-02-01,old file\n")  # no classified_by yet
    (spec.curated_dir / "items.csv").write_text("name,kind\napple,fruit\nquince,fruit\n")
    con.close()
    con = rebuilt(spec)
    assert restore(con, spec.curated_dir, TABLES) == {"labels": 1, "items": 1}
    assert con.execute("FROM labels").fetchall() == [(date(2026, 2, 1), "old file", None, None)]
    assert con.execute("SELECT name FROM items WHERE kind IS NOT NULL").fetchall() == [("apple",)]


def test_restore_is_one_transaction(con, spec):
    export(con, spec.curated_dir, TABLES)
    (spec.curated_dir / "items.csv").write_text("kind\nfruit\n")  # no key column: fails after labels loaded
    con.close()
    con = rebuilt(spec)
    with pytest.raises(ValueError, match="no name column"):
        restore(con, spec.curated_dir, TABLES)
    assert not holds_decisions(con, TABLES)


def test_restore_runs_the_apps_step_inside_the_transaction(con, spec):
    export(con, spec.curated_dir, TABLES)
    con.close()
    con = rebuilt(spec)

    def after(c):
        c.execute("UPDATE items SET secret = 'derived' WHERE kind IS NOT NULL")
        raise RuntimeError("the app's step failed")

    with pytest.raises(RuntimeError):
        restore(con, spec.curated_dir, TABLES, after=after)
    assert not holds_decisions(con, TABLES) and con.execute("SELECT count(*) FROM items WHERE secret = 'derived'"
                                                            ).fetchone()[0] == 0


def test_a_database_without_decisions_never_wipes_the_files(con, spec):
    export(con, spec.curated_dir, TABLES)
    saved = (spec.curated_dir / "labels.csv").read_text()
    con.close()
    con = rebuilt(spec)
    assert not export(con, spec.curated_dir, TABLES)
    assert (spec.curated_dir / "labels.csv").read_text() == saved


def test_a_table_emptied_on_purpose_is_written(con, spec):
    export(con, spec.curated_dir, TABLES)
    con.execute("DELETE FROM labels")
    assert export(con, spec.curated_dir, TABLES)
    assert (spec.curated_dir / "labels.csv").read_text().splitlines() == ["day,label,classified_by,classified_at"]


def test_curating_exports_after_the_command(con, spec):
    con.close()
    with curating(spec, lambda: connect(spec, SCHEMA), TABLES) as c:
        c.execute("UPDATE items SET kind = 'veg' WHERE name = 'leek'")
    assert "leek,veg" in (spec.curated_dir / "items.csv").read_text()


def test_curating_exports_what_was_committed_when_the_command_fails(con, spec):
    con.close()
    with pytest.raises(RuntimeError), curating(spec, lambda: connect(spec, SCHEMA), TABLES) as c:
        c.execute("UPDATE items SET kind = 'veg' WHERE name = 'leek'")  # committed: a batch done
        c.begin()
        c.execute("DELETE FROM labels")  # the half-finished batch
        raise RuntimeError("the model refused")
    assert "away" in (spec.curated_dir / "labels.csv").read_text() and "leek,veg" in (spec.curated_dir / "items.csv").read_text()


def test_curating_writes_the_removal_of_the_last_decision(con, spec):
    con.execute("DELETE FROM labels WHERE label = 'away'")
    con.execute("UPDATE items SET kind = NULL")
    export(con, spec.curated_dir, TABLES)
    con.close()
    with curating(spec, lambda: connect(spec, SCHEMA), TABLES) as c:
        c.execute("DELETE FROM labels")
    assert (spec.curated_dir / "labels.csv").read_text().splitlines() == ["day,label,classified_by,classified_at"]


def test_curating_on_a_database_without_decisions_keeps_the_files(con, spec):
    export(con, spec.curated_dir, TABLES)
    saved = (spec.curated_dir / "labels.csv").read_text()
    con.close()
    rebuilt(spec).close()
    with curating(spec, lambda: connect(spec, SCHEMA), TABLES):
        pass  # a command run before `ingest` restored the decisions
    assert (spec.curated_dir / "labels.csv").read_text() == saved


def test_curating_refuses_a_demo_database(con, spec):
    con.close()
    build_demo(spec, lambda path: connect(spec, SCHEMA, path=path), lambda c: None, "", path=spec.demo_db_path)
    spec.db_path.unlink()
    spec.demo_db_path.rename(spec.db_path)
    with pytest.raises(Refused, match="is a demo database"), curating(spec, lambda: connect(spec, SCHEMA), TABLES):
        pass
    assert not spec.curated_dir.exists()


def test_a_key_must_be_a_column():
    with pytest.raises(ValueError, match="must be one of the columns"):
        CuratedTable("items", ("kind",), "kind", key="name")


def test_not_manual():
    with duckdb.connect() as c:
        rows = c.execute(f"SELECT x FROM (VALUES ('llm'), ('manual'), (NULL)) t(x) WHERE {not_manual('x')}").fetchall()
    assert sorted(rows, key=str) == [("llm",), (None,)]


# ─── The git guard ───

@pytest.fixture
def committed(con, spec):
    """The decisions exported and committed: 2 labels, 2 items."""
    export(con, spec.curated_dir, TABLES)
    git(spec.root, "init", "-q", "-b", "main")
    git(spec.root, "add", "curated")
    git(spec.root, "commit", "-q", "-m", "decisions")
    return con


def test_the_guard_lists_what_the_next_commit_does_to_each_file(committed, spec):
    committed.execute("UPDATE items SET kind = 'veg' WHERE name = 'pear'")
    committed.execute("INSERT INTO labels VALUES ('2026-04-01', 'new', 'manual', NULL)")
    export(committed, spec.curated_dir, TABLES)
    git(spec.root, "add", "curated")
    changes = {c.name: c for c in file_changes(spec)}
    assert changes["items.csv"] == FileChange("items.csv", 2, 2, added=1, removed=1)  # a changed row
    assert changes["labels.csv"] == FileChange("labels.csv", 2, 3, added=1, removed=0)
    assert not any(c.loses_many for c in changes.values())


def test_an_emptied_file_is_a_loss_to_confirm(committed, spec):
    (spec.curated_dir / "labels.csv").write_text("day,label,classified_by,classified_at\n")
    git(spec.root, "add", "curated")
    (change,) = file_changes(spec)
    assert change.loses_many and change.line() == "labels.csv: 2 → 0 rows (+0, −2)"


def test_losing_a_few_rows_of_many_is_not_flagged():
    assert not FileChange("skus.csv", 2000, 1995, added=0, removed=5).loses_many
    assert FileChange("skus.csv", 2000, 1700, added=0, removed=300).loses_many
    assert not FileChange("skus.csv", 2000, 2000, added=300, removed=300).loses_many  # a reclassification


def test_against_a_branch_the_guard_reads_the_working_tree(committed, spec):
    (spec.curated_dir / "items.csv").write_text("name,kind\n")  # not staged
    assert file_changes(spec) == []
    assert [c.line() for c in file_changes(spec, base="main")] == ["items.csv: 2 → 0 rows (+0, −2)"]


def test_a_note_with_line_breaks_is_one_row(committed, spec):
    committed.execute("UPDATE labels SET label = 'away\nfor a week\nin the hills' WHERE label = 'away'")
    export(committed, spec.curated_dir, TABLES)
    git(spec.root, "add", "curated")
    (change,) = file_changes(spec)
    assert change.line() == "labels.csv: 2 → 2 rows (+1, −1)"


def test_a_branch_is_compared_from_where_it_left_its_base(committed, spec):
    git(spec.root, "switch", "-q", "-c", "work")
    git(spec.root, "switch", "-q", "main")
    committed.execute("INSERT INTO labels VALUES ('2026-04-01', 'new on main', 'manual', NULL)")
    export(committed, spec.curated_dir, TABLES)
    git(spec.root, "commit", "-q", "-am", "main gains a decision")
    git(spec.root, "switch", "-q", "work")  # never touched curated/
    assert file_changes(spec, base="main") == []


def test_an_unknown_base_is_an_error(committed, spec):
    with pytest.raises(ValueError, match="nosuch is not a branch"):
        file_changes(spec, base="nosuch")


def test_the_first_commit_has_nothing_before_it(con, spec):
    export(con, spec.curated_dir, TABLES)
    git(spec.root, "init", "-q", "-b", "main")
    git(spec.root, "add", "curated")
    assert {c.name: (c.before, c.after) for c in file_changes(spec)} == {"labels.csv": (0, 2), "items.csv": (0, 2)}


# ─── A restored backup against the files ───

def test_equal_decisions_compare_equal(con, spec):
    export(con, spec.curated_dir, TABLES)
    assert compare(con, spec.curated_dir, TABLES) == []


def test_a_snapshot_older_than_the_files_shows_changed_and_missing_decisions(con, spec):
    export(con, spec.curated_dir, TABLES)  # the files hold the decisions of now
    con.execute("UPDATE labels SET label = 'home' WHERE day = '2026-01-05'")  # the snapshot had older ones
    con.execute("DELETE FROM labels WHERE day = '2026-03-02'")
    con.execute("UPDATE items SET kind = NULL WHERE name = 'pear'")
    assert compare(con, spec.curated_dir, TABLES) == [Difference("labels", 0, 1, 1), Difference("items", 0, 1, 0)]
    assert Difference("labels", 0, 1, 1).line() == "labels: 1 changed, 0 only in the database, 1 only in curated/"


def test_a_snapshot_newer_than_the_files_shows_its_own_decisions(con, spec):
    export(con, spec.curated_dir, TABLES)
    con.execute("UPDATE items SET kind = 'veg' WHERE name = 'leek'")  # a decision never committed
    assert compare(con, spec.curated_dir, TABLES) == [Difference("items", 1, 0, 0)]
    (spec.curated_dir / "items.csv").unlink()  # no file: no decisions in git
    assert compare(con, spec.curated_dir, TABLES) == [Difference("items", 3, 0, 0)]


def test_an_older_file_without_a_column_compares_it_as_empty(con, spec):
    con.execute("UPDATE labels SET classified_by = NULL, classified_at = NULL")
    spec.curated_dir.mkdir()
    (spec.curated_dir / "labels.csv").write_text('day,label\n2026-01-05,away\n2026-03-02,"party, with ""guests"""\n')
    assert compare(con, spec.curated_dir, [LABELS]) == []


def test_align_gives_the_database_the_files_decisions(con, spec):
    export(con, spec.curated_dir, TABLES)
    files = {p.name: p.read_text() for p in spec.curated_dir.iterdir()}
    con.execute("UPDATE labels SET label = 'home' WHERE day = '2026-01-05'")
    con.execute("INSERT INTO labels VALUES ('2026-04-01', 'only here', 'manual', NULL)")
    con.execute("UPDATE items SET kind = 'veg' WHERE name = 'pear'")  # a keyed row the snapshot has
    con.execute("UPDATE items SET kind = 'veg' WHERE name = 'leek'")
    assert align(con, spec.curated_dir, TABLES) == {"labels": 2, "items": 2}
    assert compare(con, spec.curated_dir, TABLES) == []
    assert con.execute("SELECT name, kind FROM items ORDER BY name").fetchall() == [
        ("apple", "fruit"), ("leek", None), ("pear", "fruit")]
    assert con.execute("SELECT count(*) FROM items").fetchone() == (3,)  # the ingestion's rows stay
    assert {p.name: p.read_text() for p in spec.curated_dir.iterdir()} == files  # the files are only read


def test_align_refuses_and_changes_nothing_without_files_or_when_decisions_stay(con, spec):
    before = con.execute("SELECT * FROM labels ORDER BY day").fetchall()
    with pytest.raises(ValueError, match="no curated files"):
        align(con, spec.curated_dir, TABLES)
    export(con, spec.curated_dir, TABLES)
    stuck = CuratedTable("items", ("name", "kind"), "name", where="price > 0", key="name")  # true with kind NULL
    with pytest.raises(ValueError, match="clearing the decisions left some"):
        align(con, spec.curated_dir, [LABELS, stuck])
    assert con.execute("SELECT * FROM labels ORDER BY day").fetchall() == before
    assert con.execute("SELECT count(*) FROM items WHERE kind IS NOT NULL").fetchone() == (2,)
