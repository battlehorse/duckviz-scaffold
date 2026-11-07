# The design system

Every app made from the scaffold looks the same: one theme, a few shared widgets, and rules for colour. This page shows
them, in light and dark mode. The screenshots come from [the gallery](../gallery/README.md), a page in this repo that
draws each piece on synthetic data. Under each block, the gallery shows the code that draws it.

| Piece | Module | Source |
|---|---|---|
| The tokens: colours, font, chart options, the colour of a change | [`duckkit.app.theme`](kit.md#duckkitapptheme) | [theme.py](../kit/src/duckkit/app/theme.py) |
| The widgets: sections, cards, the filter bar, tiles, status chips | [`duckkit.app.ui`](kit.md#duckkitappui) | [ui.py](../kit/src/duckkit/app/ui.py) |
| Tables, the sidebar, the theme watcher | [`duckkit.app.common`](kit.md#duckkitappcommon) | [common.py](../kit/src/duckkit/app/common.py) |
| The Ask window | [`duckkit.app.ask_window`](kit.md#duckkitappask_window) | [ask_window.py](../kit/src/duckkit/app/ask_window.py) |
| Streamlit's own theme options and the font | the template's [`.streamlit/theme.toml`](../template/.streamlit/theme.toml), written by [`scripts/theme.py`](../scripts/theme.py) | |

## See it, and remake the screenshots

```sh
cd gallery
uv run streamlit run app.py              # http://localhost:8690; switch light and dark in the ⋮ menu
uv run playwright install chromium       # once
uv run python screenshots.py             # rewrites docs/design-system/*.png
```

Remake the screenshots after a change to duckkit's look, and before a release (docs/upgrading.md).

## A page

The sidebar, the page, and the Ask button at the bottom right. With the `ask` option, `common.sidebar` adds the button
to every page.

| Light | Dark |
|---|---|
| ![The top of the gallery, light](design-system/overview-light.png) | ![The top of the gallery, dark](design-system/overview-dark.png) |

## Palette

From `duckkit.app.theme`. These rules hold in every app:
- **Categorical colours** follow the entity, in a fixed order, and are never cycled. `entity_colors` gives them out,
  from the full list of entities, so a filter never repaints a series. Past eight entities, the rest share the
  `OTHER` grey.
- **`SELECTED`** marks the one selected control, row or chart mark. It is Streamlit's primary colour.
- **`GOOD` and `BAD`** say what a change means, never which way it went. They never colour a series.
- **Ink** colours text, axes and grid lines. Text never wears a series colour.
- **`shades`** gives the parts of one entity: the same hue, a step of lightness apart.

The palettes passed the dataviz validator in both modes. Three light-mode categorical colours sit below 3:1 contrast
on the page, so a chart should have a table beside it.

| Light | Dark |
|---|---|
| ![Palette, light](design-system/palette-light.png) | ![Palette, dark](design-system/palette-dark.png) |

## Type

Hanken Grotesk, embedded in `.streamlit/theme.toml`, so no font comes from another host. Its figures are tabular, so
columns of numbers line up.

| Light | Dark |
|---|---|
| ![Type, light](design-system/type-light.png) | ![Type, dark](design-system/type-dark.png) |

## Layout

The widgets of `duckkit.app.ui`, each one a Streamlit widget in a keyed container, styled by one stylesheet:
- `section` and `subsection`: a heading, a caption and a rule.
- `filter_bar`: it stays under the header as the page scrolls.
- `tile_row`, `tile` and `delta`: headline numbers. `delta` gives a change its arrow from its direction, and its colour
  and a word ("better", "worse") from `good`, the direction that is good news.
- `card`: a container that stands apart from the page.
- `status`: an icon and a word, never colour alone.

| Light | Dark |
|---|---|
| ![Layout, light](design-system/layout-light.png) | ![Layout, dark](design-system/layout-dark.png) |

## Controls

Streamlit's own widgets, as the theme draws them. The one selected segment is `SELECTED`. Pills stay light, because a
multi-select is often all on.

| Light | Dark |
|---|---|
| ![Controls, light](design-system/controls-light.png) | ![Controls, dark](design-system/controls-dark.png) |

## Charts

ECharts options built from `theme.base_option(mode)`, which sets the font, the tooltip and the animation. Each chart
takes `theme.mode()`, and its key holds the mode, so it redraws when the viewer switches theme.

| Light | Dark |
|---|---|
| ![Charts, light](design-system/charts-light.png) | ![Charts, dark](design-system/charts-dark.png) |

## Tables

`common.table`: readable headers, times in the app's time zone, and one number format. A selected row is marked on the
chart beside it in `SELECTED`.

| Light | Dark |
|---|---|
| ![Tables, light](design-system/tables-light.png) | ![Tables, dark](design-system/tables-dark.png) |

## The Ask window

An answer as the drawer shows it: the text, the rows of its last query, the SQL under "Queries", and the cost. The
gallery never calls Claude, so its own drawer says that it can't start.

| Light | Dark |
|---|---|
| ![Ask window, light](design-system/ask-window-light.png) | ![Ask window, dark](design-system/ask-window-dark.png) |
| ![The drawer, light](design-system/ask-drawer-light.png) | ![The drawer, dark](design-system/ask-drawer-dark.png) |
