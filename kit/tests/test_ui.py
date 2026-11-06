"""The shared widgets: each renders, keeps to its keys, and takes its colours from the tokens."""

import pytest
from streamlit.testing.v1 import AppTest

from duckkit.app import theme, ui


def run(script) -> AppTest:
    at = AppTest.from_function(script).run()
    assert not at.exception
    return at


def test_sections_and_cards_render_with_their_text():
    def page():
        from duckkit.app import ui
        ui.section("Spend over time", "By aisle")
        ui.subsection("By week")
        with ui.card("spend", "Top items", "Select a row"):
            import streamlit as st
            st.write("inside")

    at = run(page)
    assert [h.value for h in at.subheader] == ["Spend over time", "By week", "Top items"]
    assert [c.value for c in at.caption] == ["By aisle", "Select a row"]
    assert "inside" in [m.value for m in at.markdown]


def test_two_sections_with_one_title_need_a_key():
    def page():
        from duckkit.app import ui
        ui.section("Totals", key="first")
        ui.section("Totals", key="second")

    assert [h.value for h in run(page).subheader] == ["Totals", "Totals"]


def test_a_status_always_has_an_icon_and_a_word():
    assert set(ui.STATUS) == {"good", "info", "warning", "error"}
    assert all(icon.startswith(":material/") for icon, _ in ui.STATUS.values())


def test_an_unknown_status_is_refused():
    with pytest.raises(KeyError):
        ui.status("fine", "text")


def test_the_stylesheet_takes_its_colours_from_the_tokens():
    css = ui.stylesheet()
    for m in ("light", "dark"):
        assert theme.SELECTED[m] in css and theme.BORDER[m] in css and theme.INK[m]["surface"] in css


def test_every_test_id_in_the_stylesheet_says_why():
    """A key can't change under us, but a test id can: each one comes with a comment."""
    css = ui.stylesheet()
    assert css.count('data-testid="stButtonGroup"') == 2 and "A key can't reach inside these widgets" in css
    assert css.count("data-testid") == 2
