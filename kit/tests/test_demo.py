"""build_demo: a demo database with the marker, never over the real database or another file, never half-built."""

import duckdb
import pytest

from duckkit.demo import build_demo, is_demo, params
from duckkit.store import connect
from tests.conftest import DB_SCHEMA


def _connect(spec):
    return lambda path: connect(spec, DB_SCHEMA, path=path)


def _fill(con):
    con.execute("INSERT INTO items VALUES ('plum', 'fruit', 0.3, NULL)")


def test_build_demo_writes_the_data_and_the_marker(spec):
    path = build_demo(spec, _connect(spec), _fill, "seed = 7\n")
    assert path == spec.demo_db_path and is_demo(spec, path)
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute("SELECT name FROM items").fetchall() == [("plum",)]
        assert params(con) == "seed = 7\n"


def test_build_demo_replaces_an_earlier_demo(spec):
    build_demo(spec, _connect(spec), _fill, "seed = 1\n")
    build_demo(spec, _connect(spec), lambda con: None, "seed = 2\n")
    with duckdb.connect(str(spec.demo_db_path), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM items").fetchone()[0] == 0
        assert params(con) == "seed = 2\n"


def test_build_demo_never_writes_over_the_real_database(spec, db):
    db.close()
    with pytest.raises(ValueError, match="is your database"):
        build_demo(spec, _connect(spec), _fill, "", path=spec.db_path)
    assert spec.db_path.exists() and not is_demo(spec, spec.db_path)


def test_build_demo_never_writes_over_another_file(spec, tmp_path):
    other = tmp_path / "other.duckdb"
    with duckdb.connect(str(other)) as con:
        con.execute("CREATE TABLE notes (text VARCHAR)")
    with pytest.raises(ValueError, match="isn't a demo database"):
        build_demo(spec, _connect(spec), _fill, "", path=other)
    with duckdb.connect(str(other), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM notes").fetchone()[0] == 0


def test_build_demo_never_replaces_a_file_without_the_marker_at_the_demo_path(spec):
    """The demo path alone doesn't make a file a demo database: replacing one needs the marker."""
    spec.demo_db_path.parent.mkdir(parents=True, exist_ok=True)
    spec.demo_db_path.write_text("not a database")
    with pytest.raises(ValueError, match="isn't a demo database"):
        build_demo(spec, _connect(spec), _fill, "")
    assert spec.demo_db_path.read_text() == "not a database"


def test_a_failed_build_leaves_no_file(spec):
    def broken(con):
        _fill(con)
        raise RuntimeError("generator failed")

    with pytest.raises(RuntimeError):
        build_demo(spec, _connect(spec), broken, "")
    assert not spec.demo_db_path.exists()
    assert not spec.demo_db_path.with_name(spec.demo_db_path.name + ".wal").exists()


def test_params_of_a_real_database(db):
    assert params(db) is None
