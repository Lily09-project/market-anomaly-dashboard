from __future__ import annotations

from pathlib import Path

from src.theme import get_theme, validate_theme_contrast


class _FakeStreamlit:
    def __init__(self) -> None:
        self.rendered = ""

    def markdown(self, value: str, unsafe_allow_html: bool = False) -> None:
        assert unsafe_allow_html is True
        self.rendered = value


def test_ui_pro_max_tokens_cover_both_theme_modes() -> None:
    source = Path("app.py").read_text(encoding="utf-8")
    for theme_name in ("charcoal_orange", "paper_orange"):
        assert validate_theme_contrast(get_theme(theme_name))["passed"]
    for token in (
        "--ui-font:",
        "--ui-data-font:",
        "box-sizing: border-box",
        "font-size: clamp(",
        "min-width: 0",
        "min-height: 44px",
        "overflow-x: auto",
        "outline: 3px solid",
        "prefers-reduced-motion: reduce",
    ):
        assert token in source
