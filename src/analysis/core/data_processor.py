"""Prepare warehouse snapshots for the analytics pipeline.

DataProcessor coerces raw SQLite rows into validated, latest-run datasets and
product-level metrics consumed by strategic plotters. It filters unverified
product matches out of analytics views but does not read from or write to the
database directly.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol, cast

import numpy as np
import pandas as pd

from src.core.config import Config
from src.utils import string_utils
from src.utils.normalization_usage import normalization_usage


class ConfigProvider(Protocol):
    def get(self, *keys: str, default: Any = None) -> Any: ...


@dataclass(frozen=True)
class AnalyticsDataset:
    raw: pd.DataFrame
    latest_snapshot: pd.DataFrame
    latest_active_offers: pd.DataFrame
    product_metrics: pd.DataFrame
    category_offer_totals: pd.DataFrame
    latest_date: str
    rejected_latest_rows: int = 0


class DataProcessor:
    DEFAULT_CATEGORY_ALIASES = {
        "Kulaklık": "Headset",
    }

    def __init__(self, config: ConfigProvider | None = None) -> None:
        self.config = config or Config()

    def prepare_dataset(self, df: pd.DataFrame) -> AnalyticsDataset:
        data = df.copy()

        # Coerce storage-oriented rows before any analytics filtering occurs.
        data["scraped_at"] = pd.to_datetime(data["scraped_at"], errors="coerce")
        data["price"] = pd.to_numeric(data["price"], errors="coerce")
        data["product_code"] = (
            data["product_code"].fillna("Unknown SKU").astype(str).str.strip()
        )
        data["product_name"] = (
            data["product_name"].fillna("Unknown Product").astype(str).str.strip()
        )
        data["product_category"] = (
            data["product_category"].fillna("Unclassified").astype(str).str.strip()
        )
        data["brand"] = data["brand"].fillna("Unknown Brand").astype(str).str.strip()
        data["marketplace"] = data["marketplace"].fillna("").astype(str).str.strip()
        data["source"] = data.get("source", "unknown")
        data["match_verified"] = self._build_match_verified_mask(data)

        # Normalize labels only after row-level validity has been established.
        data["product_category"] = data["product_category"].apply(
            self.translate_category
        )
        data["marketplace"] = data["marketplace"].apply(self.normalize_marketplace_name)

        valid_dates = data["scraped_at"].dropna()
        if valid_dates.empty:
            raise ValueError(
                "No valid scrape dates were found in the products dataset."
            )

        latest_date = valid_dates.max()
        latest_snapshot = data.loc[data["scraped_at"] == latest_date].copy()
        # Keep strategic charts focused on verified rows from the latest run.
        verified_latest_snapshot = latest_snapshot.loc[
            latest_snapshot["match_verified"]
        ].copy()

        latest_active_offers = verified_latest_snapshot.loc[
            verified_latest_snapshot["price"].notna()
            & (verified_latest_snapshot["price"] > 0)
            & verified_latest_snapshot["marketplace"].ne("")
        ].copy()

        product_metrics = self._build_product_metrics(
            verified_latest_snapshot,
            latest_active_offers,
        )
        category_offer_totals = (
            latest_active_offers.groupby("product_category")["product_code"]
            .nunique()
            .reset_index(name="category_product_count")
        )

        return AnalyticsDataset(
            raw=data,
            latest_snapshot=latest_snapshot,
            latest_active_offers=latest_active_offers,
            product_metrics=product_metrics,
            category_offer_totals=category_offer_totals,
            latest_date=latest_date.strftime("%Y-%m-%d"),
            rejected_latest_rows=int((~latest_snapshot["match_verified"]).sum()),
        )

    def translate_category(self, raw_category: str | None) -> str:
        category = (raw_category or "").strip()
        if not category:
            return "Unclassified"

        # Prefer exact configured labels, then tolerate localized ASCII variants.
        ascii_category = self._ascii_text(category)
        aliases = self._get_category_aliases()
        if category in aliases:
            canonical = aliases[category]
            normalization_usage.record_hit(
                "analysis.category_aliases",
                category,
                category,
                canonical,
                "DataProcessor.translate_category",
            )
            return canonical
        if ascii_category in aliases:
            canonical = aliases[ascii_category]
            normalization_usage.record_hit(
                "analysis.category_aliases",
                ascii_category,
                category,
                canonical,
                "DataProcessor.translate_category.ascii",
            )
            return canonical
        return category

    def normalize_marketplace_name(self, raw_name: str | None) -> str:
        name = (raw_name or "").strip()
        if not name:
            return ""

        # Apply canonical aliases before presentation-only display aliases.
        ascii_key = self._normalize_key(name)
        config_aliases = (
            self.config.get("scraping", "marketplace_name_aliases", default={}) or {}
        )
        normalized_aliases = {
            self._normalize_key(alias): (alias, canonical)
            for alias, canonical in config_aliases.items()
            if alias and canonical
        }

        if ascii_key in normalized_aliases:
            alias, canonical = normalized_aliases[ascii_key]
            normalization_usage.record_hit(
                "scraping.marketplace_name_aliases",
                alias,
                name,
                canonical,
                "DataProcessor.normalize_marketplace_name.canonical",
            )
        else:
            canonical = name
        canonical_key = self._normalize_key(canonical)
        display_aliases = self._get_marketplace_display_aliases()
        if canonical_key in display_aliases:
            alias, display_name = display_aliases[canonical_key]
            normalization_usage.record_hit(
                "analysis.marketplace_display_aliases",
                alias,
                canonical,
                display_name,
                "DataProcessor.normalize_marketplace_name.display",
            )
        else:
            display_name = canonical
        return display_name

    def assign_price_tier(self, price: float | int | None) -> str | None:
        if price is None or pd.isna(price):
            return None
        entry_upper, mid_upper = self._price_tier_limits()
        labels = self._price_tier_labels()
        if float(price) < entry_upper:
            return labels["entry"]
        if float(price) <= mid_upper:
            return labels["mid"]
        return labels["premium"]

    def _build_product_metrics(
        self,
        latest_snapshot: pd.DataFrame,
        latest_active_offers: pd.DataFrame,
    ) -> pd.DataFrame:
        # Preserve zero-offer products so portfolio charts can show coverage gaps.
        product_dimension = cast(
            pd.DataFrame,
            (
                latest_snapshot.sort_values(["product_code", "product_name"])
                .groupby("product_code", as_index=False)
                .agg(
                    brand=("brand", "first"),
                    product_category=("product_category", "first"),
                    product_name=("product_name", "first"),
                    product_url=("product_url", "first"),
                )
            ),
        )

        if latest_active_offers.empty:
            product_dimension["offer_count"] = 0
            product_dimension["seller_count"] = 0
            product_dimension["min_price"] = np.nan
            product_dimension["max_price"] = np.nan
            product_dimension["avg_price"] = np.nan
            product_dimension["median_price"] = np.nan
            product_dimension["price_spread_pct"] = np.nan
            product_dimension["price_tier"] = None
            return product_dimension

        # Derive offer-depth and price-spread signals once for all plotters.
        metrics = cast(
            pd.DataFrame,
            latest_active_offers.groupby("product_code", as_index=False).agg(
                offer_count=("price", "size"),
                seller_count=("marketplace", "nunique"),
                min_price=("price", "min"),
                max_price=("price", "max"),
                avg_price=("price", "mean"),
                median_price=("price", "median"),
            ),
        )
        metrics["price_spread_pct"] = np.where(
            metrics["min_price"] > 0,
            (metrics["max_price"] - metrics["min_price"]) / metrics["min_price"] * 100,
            np.nan,
        )
        metrics["price_tier"] = cast(pd.Series, metrics["min_price"]).apply(
            self.assign_price_tier
        )

        merged = cast(
            pd.DataFrame,
            product_dimension.merge(metrics, on="product_code", how="left"),
        )
        merged["offer_count"] = merged["offer_count"].fillna(0).astype(int)
        merged["seller_count"] = merged["seller_count"].fillna(0).astype(int)
        return merged

    @staticmethod
    def _ascii_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return normalized.encode("ascii", "ignore").decode("ascii").strip()

    def _normalize_key(self, value: str) -> str:
        return " ".join(self._ascii_text(value).lower().split())

    def _get_marketplace_display_aliases(self) -> dict[str, tuple[str, str]]:
        aliases = (
            self.config.get("analysis", "marketplace_display_aliases", default={}) or {}
        )
        return {
            self._normalize_key(alias): (alias, display_name)
            for alias, display_name in aliases.items()
            if alias and display_name
        }

    def _get_category_aliases(self) -> dict[str, str]:
        aliases = (
            self.config.get("analysis", "category_aliases", default={})
            or self.DEFAULT_CATEGORY_ALIASES
        )
        return {
            **self.DEFAULT_CATEGORY_ALIASES,
            **{alias: canonical for alias, canonical in aliases.items() if canonical},
        }

    def _price_tier_limits(self) -> tuple[float, float]:
        tiers = self.config.get("analysis", "price_tiers", default={}) or {}
        entry_upper = float(tiers.get("entry_upper", 3000))
        mid_upper = float(tiers.get("mid_upper", 8000))
        if mid_upper < entry_upper:
            mid_upper = entry_upper
        return entry_upper, mid_upper

    def _price_tier_labels(self) -> dict[str, str]:
        tiers = self.config.get("analysis", "price_tiers", default={}) or {}
        labels = tiers.get("labels", {}) or {}
        return {
            "entry": labels.get("entry", "Entry-Level"),
            "mid": labels.get("mid", "Mid-Range"),
            "premium": labels.get("premium", "Premium"),
        }

    def _build_match_verified_mask(self, data: pd.DataFrame) -> pd.Series:
        # Require both stored verification and visible product-code evidence.
        stored_flag = (
            data["match_verified"]
            if "match_verified" in data.columns
            else pd.Series(True, index=data.index)
        )
        stored_flag = stored_flag.fillna(True).map(self._coerce_match_flag)
        computed_flag = data.apply(self._row_exposes_product_code, axis=1)
        return stored_flag & computed_flag

    def _row_exposes_product_code(self, row: pd.Series) -> bool:
        product_code = row.get("product_code")
        if not self._lookup_token(product_code):
            return False

        candidates = [
            row.get("product_name"),
            row.get("product_url"),
        ]
        return any(
            string_utils.contains_exact_lookup_token(candidate, product_code)
            for candidate in candidates
            if candidate
        )

    @staticmethod
    def _lookup_token(value: object) -> str:
        if value is None or value is pd.NA or value is pd.NaT:
            return ""
        if isinstance(value, float) and math.isnan(value):
            return ""
        if isinstance(value, np.floating) and bool(np.isnan(value)):
            return ""
        return string_utils.normalize_lookup_token(value)

    @staticmethod
    def _coerce_match_flag(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no"}
        return bool(value)
