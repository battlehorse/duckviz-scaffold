"""The gallery: duckkit's look on one page, on synthetic data. A reference for this repo's docs (gallery/README.md).

Each block is a function that draws one thing. The page shows its source under it, read with `inspect`, so the code
shown is the code that ran. Run it from gallery/ (its `.streamlit/config.toml` takes the template's theme file):
`uv run streamlit run app.py`. The blocks are in blocks.py.
"""

import streamlit as st

from blocks import CAPTION, GROUPS, INTRO, SHOPS, SPEC, source
from duckkit.app import ask_window, common, ui


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
