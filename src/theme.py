from __future__ import annotations


THEME_OPTIONS = {
    "charcoal_orange": {
        "label": "炭黑橘",
        "mode": "dark",
        "plotly_template": "plotly_dark",
        "background": "#0F1115",
        "surface": "#171A20",
        "card": "#20242B",
        "sidebar": "#13161B",
        "primary": "#E9EDF3",
        "secondary": "#6FA8DC",
        "accent": "#FDB338",
        "danger": "#FF6B6B",
        "success": "#45C98A",
        "warning": "#FDB338",
        "text": "#F5F7FA",
        "muted_text": "#C4CAD3",
        "border": "#3A414C",
        "table_header": "#292E37",
        "chart_grid": "#353B46",
        "shadow": "0 10px 24px rgba(0, 0, 0, 0.22)",
        "soft_shadow": "0 6px 18px rgba(0, 0, 0, 0.24)",
        "hover_shadow": "0 14px 34px rgba(0, 0, 0, 0.34)",
    },
    "paper_orange": {
        "label": "霧白橘",
        "mode": "light",
        "plotly_template": "plotly_white",
        "background": "#F4F6F8",
        "surface": "#E9EDF2",
        "card": "#FFFFFF",
        "sidebar": "#EDF1F5",
        "primary": "#1F2937",
        "secondary": "#2563EB",
        "accent": "#B45309",
        "danger": "#B91C1C",
        "success": "#047857",
        "warning": "#A16207",
        "text": "#111827",
        "muted_text": "#4B5563",
        "border": "#CBD5E1",
        "table_header": "#E2E8F0",
        "chart_grid": "#D5DCE6",
        "shadow": "0 10px 24px rgba(15, 23, 42, 0.10)",
        "soft_shadow": "0 6px 18px rgba(15, 23, 42, 0.08)",
        "hover_shadow": "0 14px 34px rgba(15, 23, 42, 0.16)",
    },
}

DEFAULT_THEME_NAME = "charcoal_orange"
DARK_THEME_NAME = "charcoal_orange"
LIGHT_THEME_NAME = "paper_orange"
THEME = THEME_OPTIONS[DEFAULT_THEME_NAME]

REQUIRED_THEME_KEYS = {
    "mode",
    "plotly_template",
    "background",
    "surface",
    "card",
    "sidebar",
    "primary",
    "secondary",
    "accent",
    "danger",
    "success",
    "warning",
    "text",
    "muted_text",
    "border",
    "table_header",
    "chart_grid",
    "shadow",
    "soft_shadow",
    "hover_shadow",
}


def get_theme(theme_name: str | None = None) -> dict:
    if not theme_name or theme_name not in THEME_OPTIONS:
        return THEME_OPTIONS[DEFAULT_THEME_NAME]
    return THEME_OPTIONS[theme_name]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    color = hex_color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def relative_luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        normalized = value / 255
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    red, green, blue = hex_to_rgb(hex_color)
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    fg = relative_luminance(foreground)
    bg = relative_luminance(background)
    lighter = max(fg, bg)
    darker = min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


def validate_theme_contrast(theme: dict) -> dict:
    missing = sorted(REQUIRED_THEME_KEYS - set(theme))
    checks = {
        "text_vs_background": contrast_ratio(theme["text"], theme["background"]) >= 4.5,
        "text_vs_card": contrast_ratio(theme["text"], theme["card"]) >= 4.5,
        "muted_text_vs_background": contrast_ratio(theme["muted_text"], theme["background"]) >= 3.0,
        "muted_text_vs_card": contrast_ratio(theme["muted_text"], theme["card"]) >= 3.0,
        "danger_vs_background": contrast_ratio(theme["danger"], theme["background"]) >= 3.0,
        "success_vs_background": contrast_ratio(theme["success"], theme["background"]) >= 3.0,
        "accent_vs_background": contrast_ratio(theme["accent"], theme["background"]) >= 3.0,
    }
    return {
        "passed": not missing and all(checks.values()),
        "missing_keys": missing,
        "checks": checks,
        "ratios": {
            "text_vs_background": contrast_ratio(theme["text"], theme["background"]),
            "text_vs_card": contrast_ratio(theme["text"], theme["card"]),
            "muted_text_vs_background": contrast_ratio(theme["muted_text"], theme["background"]),
            "muted_text_vs_card": contrast_ratio(theme["muted_text"], theme["card"]),
            "danger_vs_background": contrast_ratio(theme["danger"], theme["background"]),
            "success_vs_background": contrast_ratio(theme["success"], theme["background"]),
            "accent_vs_background": contrast_ratio(theme["accent"], theme["background"]),
        },
    }
