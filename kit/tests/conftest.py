"""A small app for duckkit's tests: a two-view contract, its tables and views, in a temporary project."""

from pathlib import Path

import pytest

from duckkit import AppEntry, AppSpec, Contract
from duckkit.contract import enum_rule
from duckkit.store import connect

SCHEMA = Path(__file__).parent / "schema.sql"

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (name VARCHAR PRIMARY KEY, kind VARCHAR, price DOUBLE, secret VARCHAR);
CREATE OR REPLACE VIEW v_contract AS SELECT 'shop' AS contract, '1.2' AS version;
CREATE OR REPLACE VIEW v_items AS SELECT name AS item, kind, price FROM items;
"""


def make_contract(version: str = "1.0") -> Contract:
    return Contract(name="shop", version=version, schema=SCHEMA,
                    rules=[enum_rule("v_items", "kind", ["fruit", "veg"])])


@pytest.fixture
def spec(tmp_path, monkeypatch) -> AppSpec:
    for name in ("MOTHERDUCK_TOKEN", "ANTHROPIC_API_KEY", "SHOP_DB", "SHOP_APP_DB", "SHOP_BACKUP_DIR"):
        monkeypatch.delenv(name, raising=False)
    return AppSpec(package="shop", root=tmp_path, contract=make_contract(), apps=[AppEntry("app", port=8600)],
                   timezone="Europe/London", motherduck_target="md:shop", demo_file="demo.duckdb",
                   private_settings=(("shop", "account", "SHOP_ACCOUNT", "account number"),))


@pytest.fixture
def db(spec):
    """The app's database with three items, open for writing."""
    con = connect(spec, DB_SCHEMA)
    con.execute("INSERT INTO items VALUES ('apple', 'fruit', 0.4, 'x'), ('leek', 'veg', NULL, 'y'),"
                " ('pear', 'fruit', 0.5, 'z')")
    yield con
    con.close()


@pytest.fixture
def closed_db(db, spec):
    """`db`, closed so a snapshot can attach it. Returns its path."""
    db.close()
    return spec.db_path
