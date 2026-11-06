"""Write the template's .streamlit/theme.toml from duckkit.app.theme, with the font embedded.

The font is a data URI, not a file under static/: everything in src/ is seeded, so a font there would never reach an app
that updates. Run it after a change to the tokens or the font: `uv run --project kit python scripts/theme.py`. A test in
kit/tests/test_theme.py fails when the file and the tokens differ.
"""

import base64
import json
from pathlib import Path

from duckkit.app import theme

ROOT = Path(__file__).parent.parent
FONT_FILE = ROOT / "scripts/fonts/HankenGrotesk-latin.woff2"  # Google Fonts' Latin file, every weight
OUT = ROOT / "template/.streamlit/theme.toml"

BASE = {
    "font": "Hanken Grotesk, sans-serif",
    "headingFont": "Hanken Grotesk, sans-serif",
    "baseRadius": "6px",
    # Hanken Grotesk runs about 5% wider than Streamlit's font. At the default sizes, real apps cut headline numbers
    # short ("£158…") and clip their controls. These two sizes win that width back.
    "baseFontSize": 15,
    "metricValueFontSize": "1.9rem",
    "headingFontWeights": [700, 600, 600, 600, 600, 600],
    "metricValueFontWeight": 500,
    "showWidgetBorder": True,
    "showSidebarBorder": True,
}


def table(options: dict) -> str:
    """TOML lines for `options`. JSON writes strings, numbers, booleans and lists as TOML does."""
    return "".join(f"{key} = {json.dumps(value)}\n" for key, value in options.items())


def main() -> None:
    font = base64.b64encode(FONT_FILE.read_bytes()).decode()
    OUT.write_text(
        "# Written by the scaffold's scripts/theme.py from duckkit.app.theme.\n"
        "# Don't edit: it comes from the scaffold, and an edit clashes with the next `copier update`.\n"
        "# Hanken Grotesk is under the SIL Open Font License (OFL-HankenGrotesk.txt, in this folder).\n\n"
        f"[theme]\n{table(BASE)}\n"
        f'[[theme.fontFaces]]\nfamily = "Hanken Grotesk"\nweight = "100 900"\nurl = "data:font/woff2;base64,{font}"\n\n'
        f"[theme.light]\n{table(theme.streamlit_theme('light'))}\n"
        f"[theme.dark]\n{table(theme.streamlit_theme('dark'))}")


if __name__ == "__main__":
    main()
