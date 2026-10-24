"""Colours and shared chart styling for ECharts charts, in light and dark.

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
    "light": {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
              "axis": "#c3c2b7", "surface": "#fcfcfb"},
    "dark": {"primary": "#ffffff", "secondary": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a",
             "axis": "#383835", "surface": "#1a1a19"},
}

# Streamlit's own page background (its default light and dark themes), for elements that must cover the page.
PAGE = {"light": "#ffffff", "dark": "#0e1117"}

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"  # single quotes: safe inside SVG attributes

WATCH_KEY = "theme-watch"  # session state of the theme watcher (see common.watch_theme)


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
