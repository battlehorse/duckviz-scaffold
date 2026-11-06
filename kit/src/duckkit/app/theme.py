"""The look every app shares: its colours, its font and the chart styling, in light and dark.

These tokens are the one source. `scripts/theme.py` writes them into the template's `.streamlit/theme.toml`, and a test
holds the file to them. Streamlit does not pass its theme to CSS on the page, so code that draws on the page must take
its colours from here.

The palettes come from the dataviz reference palette and were checked with its validator (light and dark): the
categorical order passes CVD and normal-vision separation for adjacent series. Three light-mode categorical colours
sit below 3:1 contrast on the surface, so every chart should have a table view beside it.
"""

import math

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

SHADE_STEP = 0.075  # OKLCH lightness between shades: above the 0.06 an ordinal ramp needs to tell steps apart

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


def hex_rgb(color: str) -> list[int]:
    """The red, green and blue (0-255) of a "#rrggbb" colour."""
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def _linear(channel: float) -> float:
    """An sRGB channel (0-1) in linear light."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _gamma(channel: float) -> float:
    """A linear-light channel (0-1) back in sRGB."""
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _rgb(color: str) -> list[float]:
    """The linear-light red, green and blue (0-1) of a "#rrggbb" colour."""
    return [_linear(channel / 255) for channel in hex_rgb(color)]


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two colours."""
    lum = [0.2126 * r + 0.7152 * g + 0.0722 * b_ for r, g, b_ in (_rgb(a), _rgb(b))]
    return (max(lum) + 0.05) / (min(lum) + 0.05)


def ink_on(color: str) -> str:
    """Black or white text, whichever reads better on `color`."""
    return "#0b0b0b" if contrast("#0b0b0b", color) > contrast("#ffffff", color) else "#ffffff"


def mix(color: str, other: str, t: float) -> str:
    """Blend `color` towards `other` by t (0 = color, 1 = other)."""
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(hex_rgb(color), hex_rgb(other), strict=True))


def oklab(color: str) -> tuple[float, float, float]:
    """OKLab lightness, a and b of a colour (Björn Ottosson's OKLab)."""
    r, g, b = _rgb(color)
    lms = [(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3),
           (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3),
           (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)]
    return (0.2104542553 * lms[0] + 0.7936177850 * lms[1] - 0.0040720468 * lms[2],
            1.9779984951 * lms[0] - 2.4285922050 * lms[1] + 0.4505937099 * lms[2],
            0.0259040371 * lms[0] + 0.7827717662 * lms[1] - 0.8086757660 * lms[2])


def color_distance(a: str, b: str) -> float:
    """How far apart two colours look: the OKLab distance times 100, the dataviz palette's delta E."""
    return 100 * math.dist(oklab(a), oklab(b))


def to_oklch(color: str) -> tuple[float, float, float]:
    """OKLCH lightness, chroma and hue (degrees) of a colour."""
    lightness, a, b = oklab(color)
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_oklch(lightness: float, chroma: float, hue: float) -> str:
    """The colour at OKLCH (lightness, chroma, hue), its chroma reduced until it fits in sRGB."""
    while True:
        a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
        lms = [(lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3,
               (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3,
               (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3]
        rgb = [4.0767416621 * lms[0] - 3.3077115913 * lms[1] + 0.2309699292 * lms[2],
               -1.2684380046 * lms[0] + 2.6097574011 * lms[1] - 0.3413193965 * lms[2],
               -0.0041960863 * lms[0] - 0.7034186147 * lms[1] + 1.7076147010 * lms[2]]
        if all(-1e-4 <= x <= 1 + 1e-4 for x in rgb) or chroma <= 0:
            return "#" + "".join(f"{round(_gamma(min(max(x, 0.0), 1.0)) * 255):02x}" for x in rgb)
        chroma = max(chroma - 0.002, 0.0)


def shades(color: str, n: int, m: str) -> list[str]:
    """`n` shades of `color`, biggest first, for the parts of one entity: the colour itself, then the same hue a
    SHADE_STEP of OKLCH lightness at a time, keeping most of its chroma. Steps go lighter, except in light mode when the
    lightest would fall below 2:1 on the page (already light hues), where they go darker."""
    lightness, chroma, hue = to_oklch(color)
    lighter = [from_oklch(lightness + SHADE_STEP * i, chroma * (1 - 0.25 * i / max(n - 1, 1)), hue) for i in range(n)]
    if m == "dark" or contrast(lighter[-1], PAGE[m]) >= 2.05:
        return lighter
    return [from_oklch(lightness - SHADE_STEP * i, chroma, hue) for i in range(n)]
