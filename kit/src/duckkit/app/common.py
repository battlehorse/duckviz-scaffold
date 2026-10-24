"""What every page needs: one snapshot of the contract's views, the theme watcher, the idle pause of a hosted app,
the "Reload data" button, and readable tables.

The snapshot is made once per process (`st.cache_resource`) and shared by every session; each query gets its own
cursor, which is safe across Streamlit's threads. "Reload data" clears the caches, so the next run takes a new one.
"""

import time

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitAPIException

from duckkit.app import theme
from duckkit.snapshot import ContractError, contract_snapshot
from duckkit.spec import AppSpec

DATA_ERRORS = (FileNotFoundError, ContractError)  # no database yet, or one whose views the app can't read


@st.cache_resource(show_spinner=False)
def load_contract_snapshot(_spec: AppSpec):
    """The in-memory copy of the contract views (duckkit.snapshot), made once and shared by every session."""
    return contract_snapshot(_spec)


def con(spec: AppSpec):
    """A new cursor on the snapshot: one per query."""
    return load_contract_snapshot(spec).cursor()


def reload_button(help: str = "Pick up a newer ingest (`/ingest`)") -> None:
    """A "Reload data" button that takes a new snapshot."""
    if st.button("Reload data", icon=":material/refresh:", help=help):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()


# Reports the page's actual colour scheme when it differs from the one the charts were drawn with, which reruns the
# page: Streamlit doesn't rerun on a theme change, so charts coloured in Python would keep the old theme.
_THEME_JS = """
export default function ({ data, setStateValue }) {
  let drawn = data;
  const check = () => {
    const app = document.querySelector(".stApp");
    if (!app) return;
    const now = getComputedStyle(app).colorScheme === "dark" ? "dark" : "light";
    if (now !== drawn) { drawn = now; setStateValue("mode", now); }
  };
  check();
  const timer = setInterval(check, 500);
  return () => clearInterval(timer);
}
"""
_theme_watcher = None


def watch_theme() -> None:
    """Rerun the page when the browser switches light/dark, so the charts' colours follow (theme.mode())."""
    global _theme_watcher
    args = {"key": theme.WATCH_KEY, "data": theme.mode(), "on_mode_change": lambda: None}
    try:
        _theme_watcher(**args)
    except (TypeError, StreamlitAPIException):  # not registered yet, or with an earlier runtime (tests)
        _theme_watcher = st.components.v2.component("theme_watcher", js=_THEME_JS)
        _theme_watcher(**args)


# Sends an idle tab to a plain page with no live connection, so Cloud Run can scale to zero. The page is the app's
# static/paused.html (served by --server.enableStaticServing, as the template's Dockerfile does).
_IDLE_JS = """
export default function ({ data }) {
  window.__idleMs = data.minutes * 60000;
  window.__idleLast = Date.now();
  if (window.__idleWatch) return;
  window.__idleWatch = true;
  const touch = () => { window.__idleLast = Date.now(); };
  for (const e of ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"]) {
    document.addEventListener(e, touch, { capture: true, passive: true });
  }
  setInterval(() => {
    if (Date.now() - window.__idleLast < window.__idleMs) return;
    const back = encodeURIComponent(location.pathname + location.search);
    location.replace("/app/static/paused.html?back=" + back);
  }, 15000);
}
"""
_idle_watcher = None


def watch_idle(spec: AppSpec) -> None:
    """In a hosted app (spec.app_db set), pause the tab after spec.idle_minutes without activity."""
    global _idle_watcher
    if not (spec.app_db and spec.idle_minutes > 0):
        return
    args = {"key": "idle-watch", "data": {"minutes": spec.idle_minutes, "run": time.time()}}
    try:
        _idle_watcher(**args)
    except (TypeError, StreamlitAPIException):  # not registered yet, or with an earlier runtime (tests)
        _idle_watcher = st.components.v2.component("idle_watcher", js=_IDLE_JS)
        _idle_watcher(**args)


def sidebar(spec: AppSpec, caption: str | None = None) -> None:
    """The top of every page's sidebar: how fresh the data is (`caption`), the version a hosted app runs, the
    "Reload data" button; and the theme and idle watchers."""
    with st.sidebar:
        parts = [p for p in (caption, spec.version and f"version {spec.version}") if p]
        if parts:
            st.caption(" · ".join(parts))
        reload_button()
        watch_theme()
        watch_idle(spec)


def header(column: str, known: dict[str, str] | None = None) -> str:
    """A readable column header: `known` names first, else "first_seen" → "First seen"."""
    if known and column in known:
        return known[column]
    text = str(column).replace("_", " ")
    return text[:1].upper() + text[1:]


def table(df: pd.DataFrame, headers: dict[str, str] | None = None, timezone: str | None = None,
          float_format: str = "%.1f", **kwargs):
    """st.dataframe with readable headers, times in `timezone` (shown without the offset), and `float_format`."""
    out = df.copy()
    for column in out.columns:
        if timezone and isinstance(out[column].dtype, pd.DatetimeTZDtype):
            out[column] = out[column].dt.tz_convert(timezone).dt.tz_localize(None)
    config = {c: header(c, headers) for c in out.columns}
    for c in out.select_dtypes("float").columns:
        config[c] = st.column_config.NumberColumn(header(c, headers), format=float_format)
    return st.dataframe(out, column_config=config, hide_index=True, **kwargs)
