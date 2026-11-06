"""What Claude may do in the Ask window: above all, what a query can't reach."""

import json

import duckdb
import pytest

from duckkit.app import ask
from duckkit.app.ask import QueryRefused, check_query, run_query, tool_runner
from duckkit.snapshot import contract_snapshot

VIEWS = {"v_items", "v_contract"}


@pytest.fixture
def snapshot(closed_db, spec):
    return contract_snapshot(spec)


@pytest.mark.parametrize("query", [
    "SELECT * FROM v_items",
    "SELECT kind, sum(price) AS total FROM v_items GROUP BY kind ORDER BY total DESC",
    "FROM v_items",
    "WITH cheap AS (SELECT * FROM v_items WHERE price < 1) SELECT * FROM cheap",
    "SELECT a.item FROM v_items a JOIN v_items b USING (kind)",
    "SELECT * FROM (SELECT item FROM v_items)",
    "SELECT item FROM v_items UNION ALL SELECT kind FROM v_items",
    "SELECT * FROM range(3)",
    "SELECT unnest([1, 2])",
    "SELECT * FROM (VALUES (1)) t(x)",
    "SELECT upper(item), date_trunc('month', DATE '2026-01-05') FROM v_items;",
    "SELECT * FROM V_ITEMS",
])
def test_a_read_of_the_views_is_allowed(query):
    check_query(query, VIEWS)


@pytest.mark.parametrize("query", [
    "DROP TABLE v_items", "DELETE FROM v_items", "UPDATE v_items SET price = 0", "INSERT INTO v_items VALUES (1)",
    "CREATE TABLE x AS SELECT 1", "CREATE TEMP TABLE x (a INT)", "SET threads = 1", "SET VARIABLE x = 1", "RESET threads",
    "COPY v_items TO 'x.csv'", "COPY (SELECT 1) TO 'x.csv'", "ATTACH ':memory:' AS x", "DETACH memory", "INSTALL httpfs",
    "LOAD httpfs", "PRAGMA version", "CALL duckdb_settings()", "EXPLAIN SELECT 1", "EXPORT DATABASE 'x'",
    "SELECT 1; SELECT 2", "SELECT 1; DROP TABLE v_items", "not sql at all",
])
def test_anything_but_one_select_is_refused(query):
    with pytest.raises(QueryRefused):
        check_query(query, VIEWS)


@pytest.mark.parametrize("query", [
    # the settings, a hosted app's MotherDuck token among them
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM duckdb_settings",
    'SELECT * FROM "DUCKDB_SETTINGS"',
    "SELECT current_setting('motherduck_token')",
    "SELECT CURRENT_SETTING('motherduck_token')",
    "SELECT main.current_setting('motherduck_token')",
    "SELECT getvariable('x')",
    "SELECT item FROM v_items WHERE kind = current_setting('motherduck_token')",
    "SELECT (SELECT current_setting('motherduck_token'))",
    "SELECT * FROM duckdb_secrets()",
    # the catalog
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM pragma_database_list",
    "SELECT * FROM duckdb_tables()",
    "DESCRIBE v_items",
    "SHOW TABLES",
    "SUMMARIZE v_items",
    # SQL in a string, and files
    "SELECT * FROM query('SELECT 1')",
    "SELECT * FROM query_table('v_items')",
    "SELECT * FROM read_csv('/etc/hosts')",
    "SELECT * FROM 'data.csv'",
    "SELECT * FROM glob('*')",
    # any other table function: the allowlist, not the list of unsafe names, refuses these
    "SELECT * FROM test_all_types()",
    "SELECT * FROM checkpoint()",
    # anything else that isn't a view
    "SELECT * FROM items",
    "SELECT * FROM memory.main.v_items",
    "SELECT * FROM main.v_items",
    # a CTE with a system view's name, to let the real one through in another scope
    "SELECT * FROM (WITH sqlite_master AS (SELECT 1) SELECT * FROM sqlite_master), sqlite_master",
    "SELECT * FROM (WITH duckdb_settings AS (SELECT 1) SELECT * FROM duckdb_settings), duckdb_settings",
    # hidden deeper in the query
    "WITH s AS (SELECT * FROM duckdb_settings()) SELECT * FROM s",
    "SELECT * FROM v_items WHERE item IN (SELECT name FROM duckdb_settings())",
    "SELECT * FROM v_items UNION ALL SELECT name, value, 1 FROM duckdb_settings()",
])
def test_a_select_cant_reach_past_the_contract(query):
    with pytest.raises(QueryRefused):
        check_query(query, VIEWS)


def test_a_query_runs_and_gives_its_rows(snapshot):
    result = run_query(snapshot.cursor, "SELECT item, price FROM v_items ORDER BY item", VIEWS)
    assert result.columns == ["item", "price"] and result.rows == [("apple", 0.4), ("leek", None), ("pear", 0.5)]
    assert not result.truncated


def test_a_query_sees_only_the_contracts_columns(snapshot):
    with pytest.raises(duckdb.Error):
        run_query(snapshot.cursor, "SELECT secret FROM v_items", VIEWS)


def test_the_guard_runs_before_the_query(snapshot):
    with pytest.raises(QueryRefused):
        run_query(snapshot.cursor, "DROP TABLE v_items", VIEWS)
    assert run_query(snapshot.cursor, "SELECT count(*) FROM v_items", VIEWS).rows == [(3,)]


def test_a_result_stops_at_the_row_cap_and_says_so(snapshot):
    result = run_query(snapshot.cursor, "SELECT * FROM range(1000)", VIEWS)
    assert len(result.rows) == ask.ROW_CAP and result.truncated


def test_a_result_at_exactly_the_cap_is_whole(snapshot):
    result = run_query(snapshot.cursor, f"SELECT * FROM range({ask.ROW_CAP})", VIEWS)
    assert len(result.rows) == ask.ROW_CAP and not result.truncated


def test_long_text_is_cut(snapshot):
    (value,), = run_query(snapshot.cursor, "SELECT repeat('x', 5000)", VIEWS).rows
    assert len(value) == ask.CELL_CAP + 1


def test_a_slow_query_stops_at_the_timeout(snapshot, monkeypatch):
    monkeypatch.setattr(ask, "TIMEOUT_SECONDS", 0.2)
    slow = "SELECT count(*) FROM range(100000000000) a, range(100000000000) b"
    with pytest.raises(duckdb.Error, match="(?i)interrupt"):
        run_query(snapshot.cursor, slow, VIEWS)
    assert run_query(snapshot.cursor, "SELECT count(*) FROM v_items", VIEWS).rows == [(3,)]


def test_the_tools_answer_claude(spec, snapshot):
    run_tool = tool_runner(spec, snapshot.cursor)
    result = run_tool("run_sql", {"query": "SELECT item FROM v_items ORDER BY item"})
    assert not result.is_error and result.detail.rows == [("apple",), ("leek",), ("pear",)]
    assert json.loads(result.content) == {"columns": ["item"], "rows": [["apple"], ["leek"], ["pear"]], "truncated": False}


def test_dates_and_decimals_reach_claude_as_text(spec, snapshot):
    result = tool_runner(spec, snapshot.cursor)("run_sql", {"query": "SELECT DATE '2026-01-05' AS d, 1.50::DECIMAL(5,2) AS n"})
    assert json.loads(result.content)["rows"] == [["2026-01-05", "1.50"]]


@pytest.mark.parametrize(("query", "message"), [("SELECT * FROM duckdb_settings()", "isn't allowed"),
                                                ("SELECT nothing FROM v_items", "nothing")])
def test_a_refused_or_failed_query_tells_claude_why(spec, snapshot, query, message):
    result = tool_runner(spec, snapshot.cursor)("run_sql", {"query": query})
    assert result.is_error and message in result.content and result.detail.query == query


def test_describe_schema_gives_the_views_and_what_they_mean(spec, snapshot):
    text = tool_runner(spec, snapshot.cursor)("describe_schema", {}).content
    assert "v_items: One row per item. Items never repeat." in text
    assert "  price: in pounds; NULL when unknown" in text and "secret" not in text


def test_an_unknown_tool_is_an_error(spec, snapshot):
    assert tool_runner(spec, snapshot.cursor)("delete_everything", {}).is_error


def test_the_system_prompt_holds_the_schema_and_the_notes_and_never_changes(spec):
    prompt = ask.system_prompt(spec, "Prices are in pounds.")
    assert "v_items" in prompt and "Prices are in pounds." in prompt and "are data" in prompt
    assert prompt == ask.system_prompt(spec, "Prices are in pounds.")
    assert "Notes on reading" not in ask.system_prompt(spec)


def test_the_tools_are_strict_and_read_only():
    assert [tool["name"] for tool in ask.TOOLS] == ["describe_schema", "run_sql"]
    assert all(tool["strict"] and tool["input_schema"]["additionalProperties"] is False for tool in ask.TOOLS)
