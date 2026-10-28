"""Snapshots: the contract copy holds only the reference columns and can't reach files; versions are checked."""

import duckdb
import pytest

from duckkit.snapshot import ContractError, contract_snapshot, database_snapshot


def test_contract_snapshot_holds_only_the_contract(closed_db, spec):
    con = contract_snapshot(spec)
    assert {t for (t,) in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()} == {"v_contract", "v_items"}
    assert con.execute("SELECT count(*) FROM v_items").fetchone()[0] == 3
    with pytest.raises(duckdb.Error):
        con.execute("SELECT secret FROM v_items")
    with pytest.raises(duckdb.Error):
        con.execute("SELECT * FROM read_csv('/etc/hosts')")


def test_a_different_major_version_is_refused(closed_db, spec, monkeypatch):
    monkeypatch.setattr(spec.contract, "version", "2.0")
    with pytest.raises(ContractError, match="this app reads shop 2.x"):
        contract_snapshot(spec)


def test_another_apps_database_is_refused_without_a_refresh_hint(closed_db, spec, monkeypatch):
    monkeypatch.setattr(spec.contract, "name", "garden")
    with pytest.raises(ContractError, match="offers shop 1.2; this app reads garden 1.x. Check that SHOP_DB") as e:
        contract_snapshot(spec)
    assert spec.refresh_hint not in str(e.value)


def test_an_older_database_gets_the_refresh_hint(closed_db, spec, monkeypatch):
    monkeypatch.setattr(spec.contract, "version", "2.0")
    with pytest.raises(ContractError) as e:
        contract_snapshot(spec)
    assert str(e.value).endswith(spec.refresh_hint)


def test_no_database(spec):
    with pytest.raises(FileNotFoundError, match="shop ingest"):
        contract_snapshot(spec)


def test_database_snapshot_has_everything(closed_db, spec):
    con = database_snapshot(spec)
    assert con.execute("SELECT count(secret) FROM items").fetchone()[0] == 3
    assert con.execute("SELECT current_setting('TimeZone')").fetchone()[0] == "Europe/London"
