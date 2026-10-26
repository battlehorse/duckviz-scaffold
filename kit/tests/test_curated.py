"""Curated decisions: exported sorted and atomically, restored into a rebuilt database in one transaction, never
wiped by a database without decisions, and kept apart from a demo database."""

from datetime import date

import duckdb
import pytest

from duckkit.curated import CuratedTable, Refused, curating, export, holds_decisions, not_manual, restore
from duckkit.demo import build_demo
from duckkit.store import connect
from tests.conftest import DB_SCHEMA

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


def test_curating_refuses_a_database_not_restored_yet(con, spec):
    export(con, spec.curated_dir, TABLES)
    saved = {t.name: (spec.curated_dir / f"{t.name}.csv").read_text() for t in TABLES}
    con.close()
    rebuilt(spec).close()
    with pytest.raises(Refused, match="run `shop ingest` first"), curating(spec, lambda: connect(spec, SCHEMA),
                                                                          TABLES) as c:
        c.execute("INSERT INTO labels VALUES ('2026-04-01', 'new', 'manual', NULL)")  # would export this row only
    assert {t.name: (spec.curated_dir / f"{t.name}.csv").read_text() for t in TABLES} == saved


def test_ingest_curates_a_database_not_restored_yet_and_restores_it(con, spec):
    export(con, spec.curated_dir, TABLES)
    saved = {t.name: (spec.curated_dir / f"{t.name}.csv").read_text() for t in TABLES}
    con.close()
    rebuilt(spec).close()
    with curating(spec, lambda: connect(spec, SCHEMA), TABLES, restores=True) as c:
        assert restore(c, spec.curated_dir, TABLES)
    assert {t.name: (spec.curated_dir / f"{t.name}.csv").read_text() for t in TABLES} == saved


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
