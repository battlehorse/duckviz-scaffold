"""The gallery draws every block with no error, so a change to duckkit that breaks one fails here."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

GALLERY = Path(__file__).parent.parent


@pytest.fixture
def at(monkeypatch) -> AppTest:
    monkeypatch.chdir(GALLERY)  # the theme file's path in .streamlit/config.toml is relative to gallery/
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppTest.from_file(str(GALLERY / "app.py"), default_timeout=30).run()


def blocks(at: AppTest) -> list[str]:
    return [h.value for h in at.subheader]


def test_every_block_draws(at):
    assert not at.exception
    import app

    for group, items in app.GROUPS.items():
        assert group in blocks(at)
        for item in items:
            assert item.title in blocks(at), f"{group}: {item.title} is missing"


def test_every_block_shows_its_own_code(at):
    import app

    shown = [code.value for code in at.code]
    for items in app.GROUPS.values():
        for item in items:
            assert app.source(item.draw) in shown
            assert "@block" not in app.source(item.draw)


def test_the_answer_shows_its_rows_query_and_cost(at):
    assert any("spent most in February" in m.value for m in at.markdown)
    assert any("select shop, sum(spend)" in code.value for code in at.code)
    assert any("This answer ≈ \\$0.03" in c.value for c in at.caption)


def test_the_drawer_never_reaches_claude(at, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key")
    at.button(key="ui-ask-button").click().run()
    assert not at.exception
    assert any("the gallery has no Claude" in i.value for i in at.info)


def test_the_theme_is_the_template_file():
    config = (GALLERY / ".streamlit" / "config.toml").read_text()
    assert 'base = "../template/.streamlit/theme.toml"' in config
    assert (GALLERY / "../template/.streamlit/theme.toml").is_file()


def test_the_drawer_sees_the_page(at):
    at.button(key="ui-ask-button").click().run()
    assert any("the duckkit gallery" in t.value for t in at.text)
