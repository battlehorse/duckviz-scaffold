"""The schema version is recorded, older databases migrate in order, newer ones and gaps stop."""

import pytest

from duckkit.store import connect, tables


def test_new_database_gets_the_version(spec):
    con = connect(spec, "CREATE TABLE IF NOT EXISTS t (a INT)", version=3)
    assert con.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    assert tables(con) == ["schema_version", "t"]


def test_migrations_run_in_order(spec):
    connect(spec, "CREATE TABLE IF NOT EXISTS t (a INT)", version=1).close()
    con = connect(spec, "SELECT 1", version=3, migrations={
        1: "ALTER TABLE t ADD COLUMN b INT",
        2: lambda c: c.execute("ALTER TABLE t ADD COLUMN c INT"),
    })
    assert [c for (c,) in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='t'")
            .fetchall()] == ["a", "b", "c"]
    assert con.execute("SELECT version FROM schema_version").fetchone()[0] == 3


def test_gaps_and_newer_databases_stop(spec):
    connect(spec, "SELECT 1", version=1).close()
    with pytest.raises(RuntimeError, match="no migration from schema version 1"):
        connect(spec, "SELECT 1", version=2)
    connect(spec, "SELECT 1", version=1, path=spec.root / "b.duckdb").close()
    con = connect(spec, "SELECT 1", version=1, path=spec.root / "b.duckdb")
    con.execute("UPDATE schema_version SET version = 5")
    con.close()
    with pytest.raises(RuntimeError, match="newer than this code"):
        connect(spec, "SELECT 1", version=1, path=spec.root / "b.duckdb")
