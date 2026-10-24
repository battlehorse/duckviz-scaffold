"""The guard's parsing: tables, CTEs, table functions, f-strings and imports."""

from pathlib import Path

from duckkit.contract import Contract
from duckkit.testing import guard
from tests.conftest import make_contract


def test_tables_ctes_and_functions():
    assert guard.tables("WITH x AS (SELECT * FROM raw) SELECT * FROM x JOIN v_items USING (item)") == {"raw", "v_items"}
    assert guard.tables("SELECT (SELECT count(*) FROM a) FROM b") == {"a", "b"}
    assert guard.tables("SELECT * FROM read_csv('x.csv')") == {"read_csv()"}


def test_sql_strings_skip_docstrings_and_fill_constants(tmp_path):
    path = tmp_path / "m.py"
    path.write_text('"""SELECT x FROM docstring"""\nVIEW = "v_items"\nQ = f"SELECT item FROM {VIEW}"\n'
                    'R = f"SELECT * FROM {other}"\n')
    assert guard.sql_strings(path) == [(3, "SELECT item FROM v_items"), (4, "SELECT * FROM {?}")]


def test_check_sql(spec):
    reference = make_contract().reference()
    assert not guard.check_sql(spec, "x", "SELECT price FROM v_items WHERE item = ?", reference)
    assert "isn't one of the contract's views" in guard.check_sql(spec, "x", "SELECT * FROM items", reference)[0]
    assert "reference schema" in guard.check_sql(spec, "x", "SELECT secret FROM v_items", reference)[0]


def test_forbidden_modules(spec):
    banned = guard.forbidden_modules(spec)
    assert guard.forbidden("shop.db.store", banned) and guard.forbidden("duckkit.publish", banned)
    assert not guard.forbidden("duckkit.snapshot", banned) and not guard.forbidden("shop.dbx", banned)


def test_doc_problems(spec, tmp_path):
    doc = tmp_path / "contract.md"
    doc.write_text("## Views\n### `v_contract`\n| `contract` | |\n| `version` | |\n### `v_items`\n| `item` | |\n")
    assert guard.doc_problems(spec, doc) == [
        "v_items: contract.md lists ['item'], the schema has ['item', 'kind', 'price']"]
    assert isinstance(spec.contract, Contract) and Path(doc).exists()
