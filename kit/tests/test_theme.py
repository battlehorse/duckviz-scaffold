"""The look every app shares: the template's theme file follows the tokens, and the tokens keep their rules."""

import base64
import tomllib
from pathlib import Path

import pytest

from duckkit.app import theme

REPO = Path(__file__).parents[2]
MODES = ("light", "dark")


@pytest.fixture(scope="module")
def theme_file() -> dict:
    return tomllib.loads((REPO / "template/.streamlit/theme.toml").read_text())["theme"]


@pytest.mark.parametrize("m", MODES)
def test_the_theme_file_follows_the_tokens(theme_file, m):
    assert theme_file[m] == theme.streamlit_theme(m), "run: uv run --project kit python scripts/theme.py"


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
    distance = min(theme.color_distance(theme.SELECTED[m], c) for c in theme.CATEGORICAL[m])
    assert distance >= 8


@pytest.mark.parametrize("m", MODES)
@pytest.mark.parametrize("surface", [theme.PAGE, theme.SIDEBAR, theme.TABLE_HEADER])
def test_text_reads_on_every_surface(m, surface):
    for ink in ("primary", "secondary", "muted"):
        assert theme.contrast(theme.INK[m][ink], surface[m]) >= 4.5, ink
    for color in (theme.SELECTED, theme.RED, theme.GREEN):
        assert theme.contrast(color[m], surface[m]) >= 4.5


def test_contrast_and_distance_have_their_known_values():
    assert theme.contrast("#000000", "#ffffff") == pytest.approx(21)
    assert theme.color_distance("#123456", "#123456") == 0


def test_a_colour_survives_the_trip_through_oklch():
    for color in theme.CATEGORICAL["light"]:
        assert theme.color_distance(color, theme.from_oklch(*theme.to_oklch(color))) < 1


def test_ink_on_picks_the_text_that_reads():
    assert theme.ink_on("#ffffff") == "#0b0b0b" and theme.ink_on("#0b0b0b") == "#ffffff"


def test_mix_goes_from_one_colour_to_the_other():
    assert theme.mix("#000000", "#ffffff", 0) == "#000000" and theme.mix("#000000", "#ffffff", 1) == "#ffffff"


@pytest.mark.parametrize("m", MODES)
def test_shades_start_at_the_colour_and_stay_visible_on_the_page(m):
    for color in theme.CATEGORICAL[m]:
        steps = theme.shades(color, 4, m)
        assert len(set(steps)) == 4 and theme.color_distance(steps[0], color) < 1


def test_no_shades_asked_means_none():
    assert theme.shades("#2a78d6", 0, "light") == []
