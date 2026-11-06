"""The shared widgets: sections, cards and status chips, thin wrappers on Streamlit's own.

Each one is a Streamlit widget in a keyed container, styled by one stylesheet (`style()`, which `common.sidebar` adds to
every page). Without the stylesheet they still work, and look like plain Streamlit. The CSS targets `.st-key-ui-*`, our
own keys, so a Streamlit release can't rename them. A `data-testid` selector is allowed only with a comment that says
why. Streamlit does not pass its theme to CSS on the page, so colours come from `duckkit.app.theme`, through
`light-dark()`, which follows the color-scheme Streamlit sets. A theme switch then needs no rerun.
"""

import re

import streamlit as st

from duckkit.app import theme

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
/* A selected pill or segment reads at a glance. A key can't reach inside these widgets, so the test id finds them, and
   ARIA, which is a standard, says which is selected. !important: Streamlit's own rule for a selected one wins without. */
[data-testid="stButtonGroup"] button:is([aria-checked="true"], [aria-pressed="true"]) {{
  background-color: {both(theme.SELECTED)} !important; border-color: {both(theme.SELECTED)};
  color: {both(on_selected)} !important;
}}
[data-testid="stButtonGroup"] button:is([aria-checked="true"], [aria-pressed="true"]) p {{ color: inherit !important; }}
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


def status(kind: str, text: str) -> None:
    """A chip that says how something stands: `kind` is good, info, warning or error."""
    if kind not in STATUS:
        raise ValueError(f"no status {kind!r}: use one of {', '.join(STATUS)}")
    icon, color = STATUS[kind]
    st.badge(text, icon=icon, color=color)
