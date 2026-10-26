"""The guard's parsing: tables, CTEs, table functions, f-strings and imports."""

import re
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


def test_the_guard_refuses_every_ingestion_module_of_the_kit_docs():
    """docs/kit.md's "Which side may import what" is the list: each ingestion row is in KIT_SERVICE, and no other."""
    table = (Path(__file__).parents[2] / "docs" / "kit.md").read_text().split("## Which side may import what")[1]
    rows = re.findall(r"^\| \[`([\w.]+)`\]\(#[\w-]+\) \| (\w+) \|", table, re.M)
    assert rows, "no module rows found in docs/kit.md"
    assert {f"duckkit.{module}" for module, side in rows if side == "ingestion"} == guard.KIT_SERVICE


def test_doc_problems(spec, tmp_path):
    doc = tmp_path / "contract.md"
    doc.write_text("## Views\n### `v_contract`\n| `contract` | |\n| `version` | |\n### `v_items`\n| `item` | |\n")
    assert guard.doc_problems(spec, doc) == [
        "v_items: contract.md lists ['item'], the schema has ['item', 'kind', 'price']"]
    assert isinstance(spec.contract, Contract) and Path(doc).exists()


def test_loading_skips_page_modules(tmp_path, monkeypatch):
    """A module that runs only in a Streamlit session (spec.page_modules) isn't imported by the loading check."""
    from duckkit import AppEntry, AppSpec

    app = tmp_path / "src" / "pagepkg" / "app"
    app.mkdir(parents=True)
    (app.parent / "__init__.py").write_text("")
    (app / "__init__.py").write_text("")
    (app / "helper.py").write_text("X = 1\n")
    (app / "widget.py").write_text("raise RuntimeError('only inside Streamlit')\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "src"))
    spec = AppSpec(package="pagepkg", root=tmp_path, contract=make_contract(), apps=[AppEntry("app", 8600)],
                   app_code=("app",), page_modules=("app.widget",))
    loaded, problems = guard.loaded_problems(spec, extra=())
    assert "pagepkg.app.helper" in loaded and "pagepkg.app.widget" not in loaded and not problems
