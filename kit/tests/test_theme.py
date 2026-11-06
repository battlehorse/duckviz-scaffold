"""The look every app shares: the template's theme file follows the tokens, and the tokens keep their rules."""

import base64
import math
import tomllib
from pathlib import Path

import pytest

from duckkit.app import theme

REPO = Path(__file__).parents[2]
MODES = ("light", "dark")


def channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear(color: str) -> list[float]:
    return [channel(int(color[i:i + 2], 16)) for i in (1, 3, 5)]


def contrast(a: str, b: str) -> float:
    lum = sorted(sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), linear(x), strict=True)) for x in (a, b))
    return (lum[1] + 0.05) / (lum[0] + 0.05)


def oklab(color: str) -> tuple[float, float, float]:
    r, g, b = linear(color)
    lc = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    mc = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    sc = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
            1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
            0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc)


@pytest.fixture(scope="module")
def theme_file() -> dict:
    return tomllib.loads((REPO / "template/.streamlit/theme.toml").read_text())["theme"]


@pytest.mark.parametrize("m", MODES)
def test_the_theme_file_follows_the_tokens(theme_file, m):
    assert theme_file[m] == theme.streamlit_theme(m), "run scripts/theme.py"


def test_the_font_is_embedded_so_an_update_brings_it(theme_file):
    """A file under static/ would be seeded, and the app would ask another host if the URL were remote."""
    (face,) = theme_file["fontFaces"]
    prefix = "data:font/woff2;base64,"
    assert face["url"].startswith(prefix)
    assert base64.b64decode(face["url"].removeprefix(prefix)) == (REPO / "scripts/fonts/HankenGrotesk-latin.woff2").read_bytes()
    assert face["family"] in theme.FONT and theme_file["font"].startswith(face["family"])


def test_the_config_uses_the_theme_file():
    assert tomllib.loads((REPO / "template/.streamlit/config.toml").read_text())["theme"]["base"] == ".streamlit/theme.toml"


@pytest.mark.parametrize("m", MODES)
def test_a_selection_never_reads_as_a_chart_series(m):
    distance = min(100 * math.dist(oklab(theme.SELECTED[m]), oklab(c)) for c in theme.CATEGORICAL[m])
    assert distance >= 8


@pytest.mark.parametrize("m", MODES)
@pytest.mark.parametrize("surface", [theme.PAGE, theme.SIDEBAR, theme.TABLE_HEADER])
def test_text_reads_on_every_surface(m, surface):
    for ink in ("primary", "secondary", "muted"):
        assert contrast(theme.INK[m][ink], surface[m]) >= 4.5, ink
    for color in (theme.SELECTED, theme.RED, theme.GREEN):
        assert contrast(color[m], surface[m]) >= 4.5
