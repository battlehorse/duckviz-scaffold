"""The shared widgets: each renders, keeps to its keys, and takes its colours from the tokens."""

import re

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


def test_each_status_shows_its_icon_and_its_word():
    def page():
        from duckkit.app import ui
        for kind in ui.STATUS:
            ui.status(kind, f"{kind} text")

    shown = " ".join(m.value for m in run(page).markdown)
    assert set(ui.STATUS) == {"good", "info", "warning", "error"}
    for kind, (icon, color) in ui.STATUS.items():
        assert icon in shown and f"{kind} text" in shown and f":{color}-badge[" in shown


def test_an_unknown_status_names_the_valid_ones():
    with pytest.raises(ValueError, match="good, info, warning, error"):
        ui.status("fine", "text")


def test_a_card_needs_no_title():
    def page():
        import streamlit as st

        from duckkit.app import ui
        with ui.card("plain"):
            st.write("inside")

    at = run(page)
    assert not at.subheader and "inside" in [m.value for m in at.markdown]


def test_a_card_and_a_subsection_can_share_a_name():
    def page():
        from duckkit.app import ui
        ui.subsection("Spend")
        ui.card("spend", "Top items")

    assert [h.value for h in run(page).subheader] == ["Spend", "Top items"]


def test_the_stylesheet_takes_its_colours_from_the_tokens():
    css = ui.stylesheet()
    for m in ("light", "dark"):
        assert theme.SELECTED[m] in css and theme.BORDER[m] in css and theme.INK[m]["surface"] in css


# Each test id in the stylesheet, and the word that the comment above its rule must use to explain it.
TEST_IDS = {"stButtonGroup": "button", "stLayoutWrapper": "wrapper", "stHorizontalBlock": "Columns", "stColumn": "Columns",
            "stMetricLabel": "label"}


def test_every_test_id_in_the_stylesheet_says_why():
    """A key can't change under us, but a test id can: the comment right above a rule explains each id that it uses."""
    before_any_comment, *parts = ui.stylesheet().split("/*")
    assert "data-testid" not in before_any_comment
    for part in parts:
        comment, rules = part.split("*/", 1)
        for test_id in re.findall(r'data-testid="(\w+)"', rules):
            assert "test id" in comment and TEST_IDS[test_id] in comment, test_id


def test_the_test_ids_in_use_are_the_known_ones():
    assert set(re.findall(r'data-testid="(\w+)"', ui.stylesheet())) == set(TEST_IDS)


def test_tiles_filters_and_chart_rows_render():
    def page():
        import streamlit as st

        from duckkit.app import ui
        with ui.filter_bar():
            st.segmented_control("Period", ["All"], key="period")
        a, b = ui.tile_row(2)
        ui.tile(a, "Spend", "£4,125", delta="+6%", delta_color="inverse")
        ui.tile(b, "Shops", "48", "no change")
        left, right = ui.chart_row([2, 1])
        left.write("chart")
        right.write("table")

    at = run(page)
    assert [(m.label, m.value) for m in at.metric] == [("Spend", "£4,125"), ("Shops", "48")]
    assert at.metric[1].delta == "no change"


def test_two_filter_bars_need_their_own_keys():
    def same_key():
        from duckkit.app import ui
        ui.filter_bar("a")
        ui.filter_bar("a")

    def own_keys():
        from duckkit.app import ui
        ui.filter_bar("a")
        ui.filter_bar("b")

    assert AppTest.from_function(same_key).run().exception
    run(own_keys)


def test_only_a_single_choice_is_solid():
    """A multi-select is often all on, and a row of solid pills shouts."""
    css = ui.stylesheet()
    assert 'aria-checked="true"' in css and 'aria-pressed="true"' not in css
