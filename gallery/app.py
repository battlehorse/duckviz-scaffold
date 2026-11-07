"""The gallery: duckkit's look on one page, on synthetic data. A reference for this repo's docs (gallery/README.md).

Each block is a function that draws one thing. The page shows its source under it, read with `inspect`, so the code
shown is the code that ran. Run it from gallery/ (its `.streamlit/config.toml` takes the template's theme file):
`uv run streamlit run app.py`.
"""

import inspect
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts

from duckkit.app import ask_window, common, theme, ui
from duckkit.app.ask import QueryResult
from duckkit.app.claude import DEFAULT_MODEL, LLMError, ToolCall, ToolResult
from duckkit.contract import Contract
from duckkit.spec import AppEntry, AppSpec

HERE = Path(__file__).parent
SPEC = AppSpec(package="shopviz", root=HERE, contract=Contract("shop", "1.0", HERE / "contract" / "schema.sql"),
               apps=[AppEntry("app", port=8690)])
CAPTION = "Synthetic data, made up for this page"


def no_claude(spec: AppSpec):
    """The gallery never calls Claude, even with a key in the environment: a question would cost money."""
    raise LLMError("the gallery has no Claude. In an app, the drawer answers here")


ask_window.new_client = no_claude

# ─── Synthetic data ───

SHOPS = ["North", "South", "East"]
DAYS = [date(2026, 1, 1) + timedelta(days=i) for i in range(59)]


@st.cache_data
def daily() -> pd.DataFrame:
    """What each shop spent each day: a random walk, the same on every run."""
    rng = random.Random(7)
    rows = []
    for shop, start in zip(SHOPS, (60, 45, 30), strict=True):
        spend = start
        for day in DAYS:
            spend = max(5, spend + rng.uniform(-6, 6))
            rows.append({"day": pd.Timestamp(day), "shop": shop, "spend": round(spend, 2)})
    return pd.DataFrame(rows)


def by_day() -> pd.DataFrame:
    """One row per day, a column per shop."""
    return daily().pivot(index="day", columns="shop", values="spend")[SHOPS]


# ─── Blocks ───


@dataclass
class Block:
    title: str
    caption: str | None
    draw: Callable[[], None]


GROUPS: dict[str, list[Block]] = {}
# What each group shows, and the module it comes from: the docs page links each group to it.
INTRO = {
    "Palette": "The colours, in the mode on screen: duckkit.app.theme",
    "Type": "Hanken Grotesk, with tabular figures: duckkit.app.theme and the template's .streamlit/theme.toml",
    "Layout": "Sections, cards, the filter bar, tiles and status chips: duckkit.app.ui",
    "Controls": "Streamlit's own widgets, as the theme draws them",
    "Charts": "ECharts options built from duckkit.app.theme",
    "Tables": "common.table, and a selection shared with a chart: duckkit.app.common",
    "Ask window": "The button and an answer, drawn by duckkit.app.ask_window (no call to Claude)",
}


def block(group: str, title: str, caption: str | None = None):
    """Add the function below to `group`, as a block called `title`."""
    def add(draw):
        GROUPS.setdefault(group, []).append(Block(title, caption, draw))
        return draw
    return add


def source(draw: Callable) -> str:
    """The code of a block, without its @block line."""
    lines = inspect.getsource(draw).splitlines()
    return "\n".join(line for line in lines if not line.startswith("@block"))


def swatches(colors: dict[str, str]) -> None:
    """A chip for each colour, with its name and value."""
    m = theme.mode()
    chips = "".join(
        f'<div style="width:7.5rem"><div style="height:2.5rem;border-radius:6px;background:{color};'
        f'border:1px solid {theme.BORDER[m]}"></div><div style="font-size:0.8rem;margin-top:0.3rem">{name}</div>'
        f'<code style="font-size:0.75rem">{color}</code></div>'
        for name, color in colors.items())
    st.html(f'<div style="display:flex;flex-wrap:wrap;gap:0.75rem">{chips}</div>')


# Palette


@block("Palette", "Categorical", "One colour per entity, in this order, never cycled. Past eight: OTHER")
def categorical():
    m = theme.mode()
    swatches({f"CATEGORICAL[{i}]": c for i, c in enumerate(theme.CATEGORICAL[m])} | {"OTHER": theme.OTHER[m]})


@block("Palette", "Meaning", "A selection, and good or bad news. Never a series")
def meaning():
    m = theme.mode()
    swatches({"SELECTED": theme.SELECTED[m], "GOOD": theme.GOOD[m], "BAD": theme.BAD[m]})


@block("Palette", "Ink", "Text, axes and grid lines")
def ink():
    swatches({f"INK {name}": color for name, color in theme.INK[theme.mode()].items()})


@block("Palette", "Surfaces")
def surfaces():
    m = theme.mode()
    swatches({"PAGE": theme.PAGE[m], "SIDEBAR": theme.SIDEBAR[m], "BORDER": theme.BORDER[m],
              "TABLE_HEADER": theme.TABLE_HEADER[m]})


@block("Palette", "Shades", "The parts of one entity: theme.shades(colour, n, mode)")
def shade_steps():
    m = theme.mode()
    for color in theme.CATEGORICAL[m][:3]:
        swatches({f"shade {i}": shade for i, shade in enumerate(theme.shades(color, 4, m))})


# Type


@block("Type", "Headings and text")
def headings():
    st.header("A page's heading", anchor=False)
    st.subheader("A section's heading", anchor=False)
    st.markdown("Body text, with **bold**, *italic* and `code`. Figures are tabular, so columns of numbers line up:")
    st.markdown("£1,111.11  \n£8,888.88  \n£4,710.00")
    st.caption("A caption: what a number covers, or where it comes from.")


# Layout


@block("Layout", "Section and subsection", "ui.section and ui.subsection: a heading, a caption and a rule")
def sections():
    ui.section("Spend", "1 Jan to 28 Feb 2026", key="demo-section")
    ui.subsection("By shop", "Each shop's own total", key="demo-subsection")


@block("Layout", "Filter bar", "ui.filter_bar: it stays under the header as the page scrolls")
def filters():
    with ui.filter_bar("demo"):
        period, shops = st.columns([1, 2])
        period.segmented_control("Period", ["All", "30 days", "7 days"], default="All", key="demo-period")
        shops.pills("Shops", SHOPS, default=SHOPS, selection_mode="multi", key="demo-shops")


@block("Layout", "Tiles", "ui.tile_row, ui.tile and ui.delta: the colour and a word say what a change means")
def tiles():
    spend, visits, days, stock = ui.tile_row(4, key="demo")
    ui.tile(spend, "Spend", "£4,210", **ui.delta(-120, "£120 less than January", good="down"))
    ui.tile(visits, "Visits", "1,380", **ui.delta(-45, "45 fewer than January", good="up"))
    ui.tile(days, "Days", "59", "of 59")
    ui.tile(stock, "Lines in stock", "212", **ui.delta(3, "3 more than January"))


@block("Layout", "Card", "ui.card: a container that stands apart from the page")
def cards():
    left, right = st.columns(2)
    with left, ui.card("demo-top", "Top shop", "Over the period"):
        st.markdown(f"**North** spent £{by_day()['North'].sum():,.2f}.")
    with right, ui.card("demo-plain"):
        st.markdown("A card with no title.")


@block("Layout", "Status", "ui.status: an icon and a word, never colour alone")
def statuses():
    for column, kind in zip(st.columns(4), ui.STATUS, strict=True):
        with column:
            ui.status(kind, {"good": "No days missing", "info": "Demo data", "warning": "2 days missing",
                             "error": "No data"}[kind])


@block("Layout", "Messages", "Streamlit's own, in the theme's colours")
def messages():
    st.success("The data is up to date.", icon=":material/check_circle:")
    st.info("This page shows demo data.", icon=":material/info:")
    st.warning("2 days are missing.", icon=":material/warning:")
    st.error("The database has no contract views.", icon=":material/error:")


# Controls


@block("Controls", "Choices", "The selected segment is SELECTED. Pills stay light: a multi-select is often all on")
def choices():
    left, right = st.columns(2)
    left.segmented_control("Segmented control", ["Day", "Week", "Month"], default="Week", key="ctl-segment")
    right.pills("Pills", SHOPS, default=SHOPS[:2], selection_mode="multi", key="ctl-pills")
    left.selectbox("Select box", SHOPS, key="ctl-select")
    right.multiselect("Multiselect", SHOPS, default=SHOPS[:2], key="ctl-multi")


@block("Controls", "Inputs")
def inputs():
    left, right = st.columns(2)
    left.slider("Slider", 0, 100, (20, 80), key="ctl-slider")
    right.date_input("Date", (DAYS[0], DAYS[-1]), key="ctl-date")
    left.text_input("Text", placeholder="Search the shops", key="ctl-text")
    right.number_input("Number", value=12, key="ctl-number")
    left.toggle("Toggle", value=True, key="ctl-toggle")
    right.checkbox("Checkbox", value=True, key="ctl-check")


@block("Controls", "Buttons")
def buttons():
    primary, secondary, tertiary, _ = st.columns(4)
    primary.button("Primary", type="primary", key="ctl-primary")
    secondary.button("Secondary", icon=":material/refresh:", key="ctl-secondary")
    tertiary.button("Tertiary", type="tertiary", key="ctl-tertiary")


# Charts


@block("Charts", "Series by entity", "theme.entity_colors: pass the full list, so a filter never repaints a series")
def series_by_entity():
    m = theme.mode()
    frame = by_day()
    colors = theme.entity_colors(SHOPS, m)
    option = theme.base_option(m) | {
        "legend": {"data": SHOPS, "textStyle": {"color": theme.INK[m]["secondary"]}},
        "xAxis": {"type": "category", "data": [f"{d:%d %b}" for d in frame.index]},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": theme.INK[m]["grid"]}}},
        "series": [{"name": shop, "type": "line", "data": frame[shop].tolist(), "color": colors[shop],
                    "showSymbol": False, "lineStyle": {"width": 2}} for shop in SHOPS],
        "tooltip": theme.base_option(m)["tooltip"] | {"trigger": "axis"},
    }
    st_echarts(option, height="320px", key=f"chart-series-{m}")


@block("Charts", "Parts of one entity", "theme.shades: one hue, a step of lightness apart")
def parts():
    m = theme.mode()
    kinds = {"Fruit": [310, 280, 330], "Veg": [220, 240, 210], "Bakery": [120, 150, 140], "Dairy": [90, 80, 100]}
    colors = theme.shades(theme.entity_colors(SHOPS, m)["North"], len(kinds), m)
    option = theme.base_option(m) | {
        "legend": {"data": list(kinds), "textStyle": {"color": theme.INK[m]["secondary"]}},
        "xAxis": {"type": "category", "data": ["Jan", "Feb", "Mar"]},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": theme.INK[m]["grid"]}}},
        "series": [{"name": kind, "type": "bar", "stack": "north", "data": values, "color": color,
                    "barWidth": "40%", "itemStyle": {"borderColor": theme.INK[m]["surface"], "borderWidth": 1}}
                   for (kind, values), color in zip(kinds.items(), colors, strict=True)],
        "tooltip": theme.base_option(m)["tooltip"] | {"trigger": "axis"},
    }
    st_echarts(option, height="320px", key=f"chart-parts-{m}")


@block("Charts", "Good and bad changes", "theme.change_color: the same colours as a tile's delta")
def changes():
    m = theme.mode()
    weeks = {"W1": 40, "W2": -25, "W3": 10, "W4": -60, "W5": 30, "W6": 0}
    option = theme.base_option(m) | {
        "xAxis": {"type": "category", "data": list(weeks)},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": theme.INK[m]["grid"]}}},
        # Less spend is good news: good="down".
        "series": [{"type": "bar", "barWidth": "40%", "data": [
            {"value": change, "itemStyle": {"color": theme.change_color(change, "down", m)}}
            for change in weeks.values()]}],
        "tooltip": theme.base_option(m)["tooltip"] | {"trigger": "axis"},
    }
    st_echarts(option, height="280px", key=f"chart-changes-{m}")


@block("Charts", "More than eight entities", "The ninth and later share OTHER: a hue is never made up")
def many():
    m = theme.mode()
    shops = [f"Shop {i + 1}" for i in range(10)]
    colors = theme.entity_colors(shops, m)
    option = theme.base_option(m) | {
        "xAxis": {"type": "category", "data": shops},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": theme.INK[m]["grid"]}}},
        "series": [{"type": "bar", "barWidth": "50%", "data": [
            {"value": 100 - 7 * i, "itemStyle": {"color": colors[shop]}} for i, shop in enumerate(shops)]}],
        "tooltip": theme.base_option(m)["tooltip"],
    }
    st_echarts(option, height="280px", key=f"chart-many-{m}")


# Tables


@block("Tables", "A table and a chart, one selection",
       "common.table: readable headers. A selected row is marked on the chart in SELECTED")
def table_and_chart():
    m = theme.mode()
    totals = daily().assign(day=daily()["day"].dt.date).query("shop == 'North'").tail(14)
    left, right = ui.chart_row([2, 1], key="demo")
    with right, ui.card("demo-days", "Days", "Select a row"):
        picked = common.table(totals[["day", "spend"]], headers={"spend": "Spend (£)"}, float_format="%.2f",
                              on_select="rerun", selection_mode="single-row", key="demo-days").selection.rows
    labels = [f"{d:%d %b}" for d in totals["day"]]
    series = {"type": "line", "data": totals["spend"].tolist(), "color": theme.CATEGORICAL[m][0]}
    if picked:
        mark = {"coord": [labels[picked[0]], totals["spend"].iloc[picked[0]]],
                "itemStyle": {"color": theme.SELECTED[m]}}
        series["markPoint"] = {"symbol": "circle", "symbolSize": 12, "label": {"show": False}, "data": [mark]}
    option = theme.base_option(m) | {
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": theme.INK[m]["grid"]}}},
        "series": [series],
        "tooltip": theme.base_option(m)["tooltip"] | {"trigger": "axis"},
    }
    with left, ui.card("demo-chart", "North, the last 14 days"):
        st_echarts(option, height="360px", key=f"chart-table-{m}-{picked}")


# Ask window


class SampleConversation(ask_window.Conversation):
    """A conversation with no chat behind it: its cost is set here, not added up from calls."""

    cost = Decimal("0.03")


@block("Ask window", "The Ask button", "ask_window.ask_button, at the bottom right of every page "
       "(common.sidebar adds it when spec.ask is on). Here, the drawer says that it can't start")
def button():
    ask_window.ask_button(SPEC, CAPTION)


@block("Ask window", "An answer", "ask_window.show_turn: the answer, the rows of its last query, the SQL and the cost")
def an_answer():
    feb = daily()[daily()["day"] >= "2026-02-01"].groupby("shop")["spend"].sum().sort_values(ascending=False)
    rows = [(shop, Decimal(f"{spend:.2f}")) for shop, spend in feb.items()]
    query = ("select shop, sum(spend) as spend from v_daily\n"
             "where day >= date '2026-02-01' group by shop order by spend desc")
    result = QueryResult(query, ["shop", "spend"], rows, truncated=False)
    turn = ask_window.Turn(
        "Which shop spent most in February?",
        text=f"**{rows[0][0]}** spent most in February: £{rows[0][1]:,}, then {rows[1][0]} (£{rows[1][1]:,}) and "
             f"{rows[2][0]} (£{rows[2][1]:,}). This covers 1 to 28 February, every shop.",
        calls=[ToolCall("run_sql", {"query": query}, ToolResult("3 rows", detail=result))],
        saw_page=True, cost=Decimal("0.03"), input_tokens=3641, output_tokens=594, done=True)
    with ui.card("demo-answer"):
        ask_window.show_turn(SPEC, turn, SampleConversation(DEFAULT_MODEL, turns=[turn]))


# ─── The page ───


def main() -> None:
    st.set_page_config(page_title="duckkit gallery", page_icon=ui.FAVICON, layout="wide")
    common.sidebar(SPEC, CAPTION)
    st.title("duckkit gallery")
    st.caption(f"Every piece of duckkit's look, on one page. {CAPTION}. Open “Code” under a block for the call that "
               "draws it. Switch light and dark in the ⋮ menu.")
    for group, blocks in GROUPS.items():
        with st.container(key=f"gallery-{ui.slug(group)}"):
            ui.section(group, INTRO[group], key=f"gallery-{ui.slug(group)}")
            for item in blocks:
                with st.container(key=f"gallery-block-{ui.slug(group)}-{ui.slug(item.title)}"):
                    ui.subsection(item.title, item.caption, key=f"gallery-{ui.slug(group)}-{ui.slug(item.title)}")
                    item.draw()
                    with st.expander("Code", icon=":material/code:"):
                        st.code(source(item.draw), language="python")
    # What the Ask window tells Claude about this page, as an app's page does (docs/guides/ask.md in an app).
    ask_window.ask_context("Page: the duckkit gallery, every widget on synthetic data.\n"
                           f"Groups: {', '.join(GROUPS)}.\nShops: {', '.join(SHOPS)}, 1 Jan to 28 Feb 2026.")


main()
