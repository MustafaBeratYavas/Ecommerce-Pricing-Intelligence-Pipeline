"""Style contract for analytics charts.

StyleConfig centralizes figure geometry, color tokens, typography, and
configuration-backed overrides so independently implemented plotters render as
one report portfolio. It applies Matplotlib/Seaborn state only when explicitly
requested by the analytics entry point.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from cycler import cycler
from matplotlib import colormaps, font_manager
from matplotlib.colors import to_hex

FigureSize = tuple[float, float]
AxesRect = tuple[float, float, float, float]


class StyleConfig:
    # Centralize geometry so exported charts align inside one report portfolio.
    FIGURE_SIZE: FigureSize = (19.2, 10.8)
    LARGE_FIGURE_SIZE: FigureSize = (19.2, 10.8)
    DPI = 100
    PLOT_RECT: AxesRect = (0.14, 0.17, 0.72, 0.72)
    COLORBAR_RECT: AxesRect = (0.88, 0.17, 0.018, 0.72)

    BACKGROUND = "#0B1020"
    PANEL = "#141A2E"
    GRID = "#2A3250"
    TEXT = "#F1F5F9"
    MUTED_TEXT = "#94A3B8"
    BORDER = "#334155"

    ACCENT = "#38BDF8"
    SUCCESS = "#22C55E"
    WARNING = "#F59E0B"
    DANGER = "#F43F5E"
    PURPLE = "#8B5CF6"
    TEAL = "#14B8A6"
    BLUE = "#3B82F6"
    AMBER = "#FBBF24"

    MARKETPLACE_COLORS = [
        "#38BDF8",
        "#8B5CF6",
        "#22C55E",
        "#F59E0B",
        "#F43F5E",
        "#14B8A6",
        "#A78BFA",
        "#FB7185",
        "#60A5FA",
        "#FACC15",
        "#4ADE80",
        "#E879F9",
    ]

    CATEGORY_COLORS = {
        "Mouse": "#22C55E",
        "Headset": "#8B5CF6",
    }

    TIER_COLORS = {
        "Entry-Level": "#38BDF8",
        "Mid-Range": "#F59E0B",
        "Premium": "#F43F5E",
    }
    PRICE_TIER_ORDER = ["Entry-Level", "Mid-Range", "Premium"]

    FONT_FAMILY: str | list[str] = "Segoe UI"
    FONT_FALLBACKS = ["Liberation Sans", "DejaVu Sans", "Arial", "sans-serif"]
    RESOLVED_FONT_FAMILY = "sans-serif"
    TITLE_SIZE = 20
    SUBTITLE_SIZE = 12
    LABEL_SIZE = 12
    TICK_SIZE = 10
    LEGEND_SIZE = 10
    AXIS_LABEL_PAD = 18
    TICK_LABEL_PAD = 8

    @classmethod
    def refresh_from_config(cls, config=None) -> None:
        # Merge YAML overrides without discarding the code-level report defaults.
        if config is None:
            from src.core.config import Config

            config = Config()

        style = config.get("charts", "style", default={}) or {}
        colors = style.get("colors", {}) or {}
        price_tiers = config.get("analysis", "price_tiers", default={}) or {}

        cls.FIGURE_SIZE = cls._coerce_size(
            style.get("figure_size", cls.FIGURE_SIZE), cls.FIGURE_SIZE
        )
        cls.LARGE_FIGURE_SIZE = cls._coerce_size(
            style.get("large_figure_size", cls.LARGE_FIGURE_SIZE),
            cls.LARGE_FIGURE_SIZE,
        )
        cls.DPI = int(style.get("dpi", cls.DPI))
        cls.PLOT_RECT = cls._coerce_rect(
            style.get("plot_rect", cls.PLOT_RECT), cls.PLOT_RECT
        )
        cls.COLORBAR_RECT = cls._coerce_rect(
            style.get("colorbar_rect", cls.COLORBAR_RECT), cls.COLORBAR_RECT
        )

        cls.BACKGROUND = colors.get("background", cls.BACKGROUND)
        cls.PANEL = colors.get("panel", cls.PANEL)
        cls.GRID = colors.get("grid", cls.GRID)
        cls.TEXT = colors.get("text", cls.TEXT)
        cls.MUTED_TEXT = colors.get("muted_text", cls.MUTED_TEXT)
        cls.BORDER = colors.get("border", cls.BORDER)
        cls.ACCENT = colors.get("accent", cls.ACCENT)
        cls.SUCCESS = colors.get("success", cls.SUCCESS)
        cls.WARNING = colors.get("warning", cls.WARNING)
        cls.DANGER = colors.get("danger", cls.DANGER)
        cls.PURPLE = colors.get("purple", cls.PURPLE)
        cls.TEAL = colors.get("teal", cls.TEAL)
        cls.BLUE = colors.get("blue", cls.BLUE)
        cls.AMBER = colors.get("amber", cls.AMBER)

        cls.MARKETPLACE_COLORS = list(
            style.get("marketplace_colors", cls.MARKETPLACE_COLORS)
        )
        cls.CATEGORY_COLORS = dict(style.get("category_colors", cls.CATEGORY_COLORS))
        cls.TIER_COLORS = dict(style.get("tier_colors", cls.TIER_COLORS))
        cls.PRICE_TIER_ORDER = list(
            price_tiers.get("order")
            or style.get("price_tier_order")
            or cls.PRICE_TIER_ORDER
        )

        cls.FONT_FAMILY = style.get("font_family", cls.FONT_FAMILY)
        cls.TITLE_SIZE = int(style.get("title_size", cls.TITLE_SIZE))
        cls.SUBTITLE_SIZE = int(style.get("subtitle_size", cls.SUBTITLE_SIZE))
        cls.LABEL_SIZE = int(style.get("label_size", cls.LABEL_SIZE))
        cls.TICK_SIZE = int(style.get("tick_size", cls.TICK_SIZE))
        cls.LEGEND_SIZE = int(style.get("legend_size", cls.LEGEND_SIZE))
        cls.AXIS_LABEL_PAD = int(style.get("axis_label_pad", cls.AXIS_LABEL_PAD))
        cls.TICK_LABEL_PAD = int(style.get("tick_label_pad", cls.TICK_LABEL_PAD))

    @classmethod
    def resolve_color(cls, value: str) -> str:
        # Translate semantic color tokens from config into concrete hex values.
        token_map = {
            "accent": cls.ACCENT,
            "success": cls.SUCCESS,
            "warning": cls.WARNING,
            "danger": cls.DANGER,
            "purple": cls.PURPLE,
            "teal": cls.TEAL,
            "blue": cls.BLUE,
            "amber": cls.AMBER,
        }
        return token_map.get(str(value).lower(), value)

    @classmethod
    def get_marketplace_palette(cls, count: int) -> list[str]:
        # Build a deterministic palette for marketplaces beyond the base set.
        palette = []
        for cmap_name in ("tab20", "tab20b", "tab20c", "Set3", "Dark2"):
            cmap = colormaps[cmap_name]
            colors = getattr(cmap, "colors", None)
            if colors is None:
                colors = [cmap(i / max(count - 1, 1)) for i in range(count)]
            palette.extend(colors)

        hex_colors = []
        for color in palette:
            if isinstance(color, str):
                hex_colors.append(color)
            else:
                hex_colors.append(to_hex(color))
        return hex_colors[:count]

    @classmethod
    def _font_candidates(cls) -> list[str]:
        configured = cls.FONT_FAMILY
        if isinstance(configured, str):
            candidates = [configured]
        elif isinstance(configured, (list, tuple)):
            candidates = [str(value) for value in configured]
        else:
            candidates = []

        candidates.extend(cls.FONT_FALLBACKS)
        normalized = []
        seen = set()
        for candidate in candidates:
            family = candidate.strip()
            key = family.lower()
            if family and key not in seen:
                normalized.append(family)
                seen.add(key)
        return normalized

    @classmethod
    def resolve_font_family(cls) -> str:
        available_fonts = {
            font.name.lower(): font.name for font in font_manager.fontManager.ttflist
        }
        generic_families = {"sans-serif", "serif", "monospace", "cursive", "fantasy"}

        for family in cls._font_candidates():
            key = family.lower()
            if key in available_fonts:
                return available_fonts[key]
            if key in generic_families:
                return family

        return "sans-serif"

    @staticmethod
    def _coerce_size(value: object, fallback: FigureSize) -> FigureSize:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return fallback
        try:
            first, second = value
            return (float(first), float(second))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _coerce_rect(value: object, fallback: AxesRect) -> AxesRect:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return fallback
        try:
            left, bottom, width, height = value
            return (float(left), float(bottom), float(width), float(height))
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def apply_theme(cls) -> None:
        # Apply global plotting state at the analytics boundary, not at import time.
        cls.refresh_from_config()
        cls.RESOLVED_FONT_FAMILY = cls.resolve_font_family()
        sns.set_theme(style="darkgrid")
        plt.rcParams.update(
            {
                "figure.facecolor": cls.BACKGROUND,
                "axes.facecolor": cls.PANEL,
                "savefig.facecolor": cls.BACKGROUND,
                "savefig.edgecolor": cls.BACKGROUND,
                "axes.edgecolor": cls.BORDER,
                "axes.labelcolor": cls.TEXT,
                "axes.titlecolor": cls.TEXT,
                "figure.edgecolor": cls.BACKGROUND,
                "grid.color": cls.GRID,
                "grid.alpha": 0.45,
                "axes.grid": True,
                "text.color": cls.TEXT,
                "xtick.color": cls.TEXT,
                "ytick.color": cls.TEXT,
                "font.family": cls.RESOLVED_FONT_FAMILY,
                "font.size": cls.LABEL_SIZE,
                "axes.prop_cycle": cycler(color=cls.MARKETPLACE_COLORS),
                "legend.facecolor": cls.PANEL,
                "legend.edgecolor": cls.BORDER,
                "legend.framealpha": 0.85,
            }
        )
