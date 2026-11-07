"""The look every app shares: its colours, its font and the chart styling, in light and dark.

These tokens are the one source. `scripts/theme.py` writes them into the template's `.streamlit/theme.toml`, and a test
holds the file to them. Streamlit does not pass its theme to CSS on the page, so code that draws on the page must take
its colours from here.

The palettes come from the dataviz reference palette and were checked with its validator (light and dark): the
categorical order passes CVD and normal-vision separation for adjacent series. Three light-mode categorical colours
sit below 3:1 contrast on the surface, so every chart should have a table view beside it.
"""

import streamlit as st

# Fixed categorical order: assign in this order, never cycle; past 8 entities fold into OTHER grey.
CATEGORICAL = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
}
OTHER = {"light": "#b5b3ab", "dark": "#5c5b56"}  # de-emphasis grey for "Other" / context

INK = {
    "light": {"primary": "#22211e", "secondary": "#52514e", "muted": "#6a6862", "grid": "#e1e0d9",
              "axis": "#c3c2b7", "surface": "#ffffff"},
    "dark": {"primary": "#f2f1ec", "secondary": "#c3c2b7", "muted": "#a5a39b", "grid": "#2c2c2a",
             "axis": "#383835", "surface": "#1a1a19"},
}

# The page's background, for elements that must cover the page.
PAGE = {"light": "#fbfaf7", "dark": "#141412"}
SIDEBAR = {"light": "#f1efe9", "dark": "#1c1c1a"}  # the sidebar and the background of widgets
BORDER = {"light": "#e1e0d9", "dark": "#2f2f2b"}
TABLE_HEADER = {"light": "#f4f3ee", "dark": "#20201e"}
# The one colour of a selected control, table row or chart mark. It is Streamlit's primary colour, so widgets and tables
# follow it with no CSS. Red is not a selection: it is bad news. Kept at OKLab distance 8 or more from every CATEGORICAL
# colour, so a selection never reads as a series.
SELECTED = {"light": "#0f6e7c", "dark": "#5fc9d6"}
RED = {"light": "#b42318", "dark": "#ffa198"}
GREEN = {"light": "#0b6b2f", "dark": "#7fdc9b"}

# Its figures are tabular by default. A table needs that: Streamlit draws tables on a canvas that CSS can't reach.
FONT = "'Hanken Grotesk', system-ui, -apple-system, 'Segoe UI', sans-serif"  # single quotes: safe in SVG attributes

WATCH_KEY = "theme-watch"  # session state of the theme watcher (see common.watch_theme)


def streamlit_theme(m: str) -> dict:
    """The options of `[theme.light]` or `[theme.dark]` in `.streamlit/theme.toml`."""
    return {
        "primaryColor": SELECTED[m],
        "backgroundColor": PAGE[m],
        "secondaryBackgroundColor": SIDEBAR[m],
        "textColor": INK[m]["primary"],
        "borderColor": BORDER[m],
        "dataframeBorderColor": BORDER[m],
        "dataframeHeaderBackgroundColor": TABLE_HEADER[m],
        "redColor": RED[m],
        "greenColor": GREEN[m],
        "chartCategoricalColors": CATEGORICAL[m],
    }


def mode() -> str:
    """"light" or "dark", following the viewer's Streamlit theme.

    Prefers what the theme watcher saw on the page: st.context.theme can lag a theme change (Streamlit issue
    #11920), and a change doesn't rerun the page, so charts would keep the old theme's colours.
    """
    try:
        watched = (st.session_state.get(WATCH_KEY) or {}).get("mode")
        if watched in ("light", "dark"):
            return watched
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # noqa: BLE001 — outside a running app (tests), default to light
        return "light"


def base_option(m: str) -> dict:
    """Options shared by every chart: font, tooltip look, no gratuitous animation delay."""
    ink = INK[m]
    return {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": FONT, "color": ink["secondary"]},
        "animationDuration": 400,
        "tooltip": {
            "backgroundColor": ink["surface"], "borderColor": ink["axis"], "borderWidth": 1,
            "textStyle": {"color": ink["primary"], "fontFamily": FONT, "fontSize": 12},
            "extraCssText": "box-shadow: 0 2px 8px rgba(0,0,0,.12); border-radius: 6px;",
        },
    }


def entity_colors(names: list[str], m: str) -> dict[str, str]:
    """Each entity's colour: categorical slots in the order given (pass the full list, so a filter never repaints
    one); entities past the eighth share the OTHER grey."""
    palette = CATEGORICAL[m]
    return {n: palette[i] if i < len(palette) else OTHER[m] for i, n in enumerate(names)}
