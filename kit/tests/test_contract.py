"""The reference schema, its descriptions, and the conformance check."""

from tests.conftest import make_contract


def test_descriptions_from_comments():
    views = make_contract().descriptions()
    assert list(views) == ["v_contract", "v_items"]
    about, columns = views["v_items"]
    assert about == "One row per item. Items never repeat."
    assert columns == {"item": "the item's name", "kind": "fruit or veg", "price": "in pounds; NULL when unknown"}


def test_the_views_conform(db):
    assert make_contract().check(db) == []


def test_the_check_catches_breakage(db):
    contract = make_contract()
    db.execute("INSERT INTO items VALUES ('apple2', 'rock', 1, '')")
    assert contract.check(db) == ["v_items.kind: 1 rows outside fruit, veg"]
    db.execute("CREATE OR REPLACE VIEW v_items AS SELECT name AS item, kind, price FROM items"
               " UNION ALL SELECT 'apple', 'fruit', 1")
    assert "v_items: 1 duplicate keys (item)" in contract.check(db)
    db.execute("CREATE OR REPLACE VIEW v_items AS SELECT name AS item, kind FROM items")
    assert contract.check(db) == ["v_items.price: missing"]


def test_versions():
    contract = make_contract("1.0")
    assert contract.accepts("shop", "1.7") and not contract.accepts("shop", "2.0")
    assert not contract.accepts("other", "1.0")
