"""The shared widgets: sections, cards, status chips, tiles and layout, thin wrappers on Streamlit's own.

Each one is a Streamlit widget in a keyed container, styled by one stylesheet (`style()`, which `common.sidebar` adds to
every page). Without the stylesheet they still work, and look like plain Streamlit. The CSS targets `.st-key-ui-*`, our
own keys, so a Streamlit release can't rename them. A `data-testid` selector is allowed only with a comment that says
why. Streamlit does not pass its theme to CSS on the page, so colours come from `duckkit.app.theme`, through
`light-dark()`, which follows the color-scheme Streamlit sets. A theme switch then needs no rerun.
"""

import re
from pathlib import Path

import streamlit as st

from duckkit.app import theme

# The tab's icon, for st.set_page_config. A file, because Streamlit fetches a Material or emoji icon from another host.
FAVICON = Path(__file__).parent / "favicon.svg"

# What each kind means: an icon and a colour, always with a word (`status`). Colour alone never carries the meaning.
STATUS = {
    "good": (":material/check_circle:", "green"),
    "info": (":material/info:", "blue"),
    "warning": (":material/warning:", "orange"),
    "error": (":material/error:", "red"),
}


def both(tokens: dict[str, str]) -> str:
    """A token's two colours as a CSS value that follows the theme."""
    return f"light-dark({tokens['light']}, {tokens['dark']})"


def stylesheet() -> str:
    """The CSS of the shared widgets."""
    surface = {m: theme.INK[m]["surface"] for m in ("light", "dark")}
    muted = {m: theme.INK[m]["muted"] for m in ("light", "dark")}
    on_selected = {m: theme.PAGE[m] for m in ("light", "dark")}
    return f"""<style>
[class*="st-key-ui-section-"] {{ border-bottom: 1px solid {both(theme.BORDER)}; padding-bottom: 0.4rem; gap: 0.1rem; }}
/* Streamlit's heading has a margin of -1rem under it, which its bottom padding makes up for: keep that padding. */
[class*="st-key-ui-section-"] h3 {{ padding: 0 0 1rem; }}
[class*="st-key-ui-subsection-"] {{ gap: 0; }}
[class*="st-key-ui-subsection-"] h3 {{ font-size: 0.95rem; padding: 0 0 1rem; color: {both(muted)}; }}
[class*="st-key-ui-card-"] {{ background: {both(surface)}; }}
/* The one selected segment reads at a glance. Pills stay as Streamlit draws them: a multi-select is often all on, and a
   row of solid pills shouts. A key can't reach inside a button group, so the test id finds it, and ARIA, which is a
   standard, says which is selected. !important: Streamlit's own rule for a selected one wins without. */
[data-testid="stButtonGroup"] button[aria-checked="true"] {{
  background-color: {both(theme.SELECTED)} !important; border-color: {both(theme.SELECTED)};
  color: {both(on_selected)} !important;
}}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: inherit !important; }}
/* The filter bar stays under Streamlit's header (3.75rem, opaque) as the page scrolls. The sticky element is the layout
   wrapper, which has no key, so its test id finds it: the container alone is as tall as its wrapper, so it has no room
   to stick. Off on narrow windows, where the bar would fill the screen. */
@media (min-width: 900px) {{
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-ui-filters-"]) {{
    position: sticky; top: 3.75rem; z-index: 100; background-color: {both(theme.PAGE)};
    border-bottom: 1px solid {both(theme.BORDER)};
    box-shadow: 0 8px 10px -8px light-dark(rgba(0, 0, 0, 0.12), rgba(0, 0, 0, 0.35));
    padding-bottom: 0.5rem; margin-bottom: 0.5rem;
  }}
}}
/* The Ask button (duckkit.app.ask_window) floats at the bottom right of every page, over the content: the sidebar is
   folded away on a phone, so the button can't live there. */
.st-key-ui-ask-button {{ position: fixed; right: 1.5rem; bottom: 1.5rem; z-index: 990; width: auto; }}
.st-key-ui-ask-button button {{ box-shadow: 0 4px 14px light-dark(rgba(0, 0, 0, 0.18), rgba(0, 0, 0, 0.5)); }}
/* Columns have no key of their own, so their test ids reach them inside our keyed containers. Short of room, filters
   wrap and keep each button in sight, tiles wrap and keep their numbers whole, and charts stack. */
[class*="st-key-ui-filters-"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; row-gap: 0.5rem; }}
[class*="st-key-ui-filters-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ min-width: min(100%, 12rem); }}
[class*="st-key-ui-filters-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([data-testid="stButtonGroup"]) {{
  flex: 0 1 max-content !important; width: auto !important; max-width: 100%;
}}
[class*="st-key-ui-tiles-"] [data-testid="stHorizontalBlock"] {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(11.5rem, 1fr));
}}
[class*="st-key-ui-tiles-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ width: auto; min-width: 0; }}
/* A metric's label has no key either, so its test id reaches it: a long label wraps rather than end in "…". */
[class*="st-key-ui-tiles-"] [data-testid="stMetricLabel"] p {{ white-space: normal; overflow: visible; }}
/* A delta has no key either, so its test id reaches it, in any metric: its last word says what it means (`delta`), so
   it wraps rather than end in "…". */
[data-testid="stMetricDelta"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricDelta"] [data-testid="stMarkdownContainer"] p {{ white-space: normal; overflow: visible; }}
/* Columns again, by their test ids: below 900px, charts side by side would be too narrow to read. */
@media (max-width: 900px) {{
  [class*="st-key-ui-charts-"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; row-gap: 1.5rem; }}
  [class*="st-key-ui-charts-"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ min-width: 100%; }}
}}
</style>"""


def style() -> None:
    """Add the stylesheet to the page."""
    st.html(stylesheet())


def slug(text: str) -> str:
    """`text` as part of a key: "Spend over time" → "spend-over-time"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def section(title: str, caption: str | None = None, key: str | None = None) -> None:
    """A section's heading, with a rule under it. `key` tells apart two sections with the same title."""
    with st.container(key=f"ui-section-{key or slug(title)}"):
        st.subheader(title, anchor=False)
        if caption:
            st.caption(caption)


def subsection(title: str, caption: str | None = None, key: str | None = None) -> None:
    """A smaller heading inside a section."""
    with st.container(key=f"ui-subsection-{key or slug(title)}"):
        st.subheader(title, anchor=False)
        if caption:
            st.caption(caption)


def card(key: str, title: str | None = None, caption: str | None = None):
    """A container that stands apart from the page: `with card("spend"): ...`. It holds `title` and `caption` first."""
    box = st.container(border=True, key=f"ui-card-{key}")
    if title:
        with box:
            subsection(title, caption, key=f"card-{key}")  # its own key: a page may also have a subsection `key`
    return box


def filter_bar(key: str = "page"):
    """A container for a page's filters, pinned under the header as the page scrolls."""
    return st.container(key=f"ui-filters-{key}")


def tile_row(n: int, key: str = "page") -> list:
    """`n` columns for headline tiles. Short of room they wrap onto more rows, rather than cut a number short."""
    with st.container(key=f"ui-tiles-{key}"):
        return st.columns(n)


def tile(where, label: str, value: str, note: str | None = None, **kwargs) -> None:
    """A headline tile in `where` (a column): a bordered metric as tall as its row. `note` is a grey line under the
    number, a delta with no arrow or colour. Any other st.metric argument passes through and wins."""
    if note is not None:
        kwargs = {"delta": note, "delta_color": "off", "delta_arrow": "off", **kwargs}
    where.metric(label, value, **{"border": True, "height": "stretch", **kwargs})


def delta(change: float | None, text: str, good: str | None = None) -> dict:
    """The arguments of a metric that shows a change: `ui.tile(where, "Spend", "£1,200", **ui.delta(-120, "£120 less",
    good="down"))`. `text` says the change and the arrow shows its direction. `good` is the direction that is good news
    (see `theme.verdict`): the colour and a word then say what it means, so colour never carries that alone. With no
    `good` the change stays grey, because a direction alone is neither good nor bad."""
    word = theme.verdict(change, good)
    rise = theme.verdict(change, "up")  # asked with up as the good direction, "better" means that it went up
    return {
        "delta": f"{text}, {word}" if word else text,
        "delta_color": {"better": "green", "worse": "red", None: "gray"}[word],
        "delta_arrow": {"better": "up", "worse": "down", None: "off"}[rise],
    }


def chart_row(spec, key: str = "page") -> list:
    """Columns for charts side by side (`spec` as in st.columns), one under the other below 900px, where they would be
    too narrow to read."""
    with st.container(key=f"ui-charts-{key}"):
        return st.columns(spec, gap="large")


def status(kind: str, text: str) -> None:
    """A chip that says how something stands: `kind` is good, info, warning or error."""
    if kind not in STATUS:
        raise ValueError(f"no status {kind!r}: use one of {', '.join(STATUS)}")
    icon, color = STATUS[kind]
    st.badge(text, icon=icon, color=color)
