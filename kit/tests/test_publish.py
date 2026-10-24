"""Publishing copies only the contract views, described; --check and --dry-run change nothing."""

import duckdb
import pytest

from duckkit.publish import compare, plan, publish


def test_publish_to_a_file(closed_db, spec, tmp_path):
    target = str(tmp_path / "published.duckdb")
    assert plan(spec) == {"v_contract": (1, ["contract", "version"]), "v_items": (3, ["item", "kind", "price"])}
    assert publish(spec, target) == {"v_contract": 1, "v_items": 3}
    with duckdb.connect(target, read_only=True) as con:
        assert {t for (t,) in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()} == {
            "v_contract", "v_items"}  # no raw tables, no secrets
        assert con.execute("SELECT comment FROM duckdb_columns() WHERE column_name = 'price'").fetchone()[0] == (
            "in pounds; NULL when unknown")
    assert all(same for _, _, same in compare(spec, target).values())


def test_check_sees_a_change(db, spec, tmp_path):
    target = str(tmp_path / "published.duckdb")
    db.close()
    publish(spec, target)
    with duckdb.connect(str(spec.db_path)) as con:
        con.execute("UPDATE items SET price = 9 WHERE name = 'apple'")
    result = compare(spec, target)
    assert result["v_items"] == (3, 3, False) and result["v_contract"][2]


def test_motherduck_needs_a_token(closed_db, spec):
    with pytest.raises(ValueError, match="MOTHERDUCK_TOKEN"):
        publish(spec)
