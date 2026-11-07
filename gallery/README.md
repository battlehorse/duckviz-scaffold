# The gallery

A reference page for duckkit's look: the palette, the type, the widgets of `duckkit.app.ui`, the chart helpers of
`duckkit.app.theme`, tables, and the Ask window, all on synthetic data. Under each block, "Code" shows the function
that drew it.

It lives only in this repo. Apps don't get it: the template doesn't hold it, and nothing in it is a public name of
duckkit. Its theme is the template's own `.streamlit/theme.toml` (`.streamlit/config.toml` points at it), so it shows
what the apps show.

```sh
cd gallery
uv run streamlit run app.py   # http://localhost:8690
uv run pytest -q              # every block draws, and shows its own code
```

The gallery never calls Claude, even with a key in the environment: the Ask window's drawer says that it can't start.

When something is added to duckkit's look (a new widget in `duckkit.app.ui`, a new token in `duckkit.app.theme`), add
a block for it to `blocks.py`, with `@block`. `app.py` draws the page.
