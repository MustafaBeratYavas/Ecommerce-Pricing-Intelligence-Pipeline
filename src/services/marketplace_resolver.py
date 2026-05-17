"""Resolve raw seller labels and marketplace IDs into canonical names."""

from __future__ import annotations

import re

from src.core.config import Config
from src.utils import string_utils
from src.utils.normalization_usage import normalization_usage


class MarketplaceResolver:
    # Strip common suffixes while preserving distinctive domains such as .gen.tr.
    _STRIPPABLE_DOMAIN_SUFFIXES = (
        ".com.tr",
        ".com",
        ".net.tr",
        ".net",
        ".org.tr",
        ".org",
        ".co",
        ".io",
    )

    # Noise fragments commonly attached to seller labels.
    _NOISE_PATTERNS = [
        r"\d+[.,]\d+\s+\d+\s+Yorum",
        r"\d+\s+Yorum",
        r"Yorumlar\S*\s+oku",
        r"Yetkili\s+Sat\S+",
        r"\d+[.,]\d+(?=\s*$)",
        r"[★☆]+",
    ]

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        # Compile once because normalization runs for every seller label.
        self._compiled_noise = [
            re.compile(p, flags=re.IGNORECASE) for p in self._NOISE_PATTERNS
        ]

    def normalize_marketplace_name(self, raw_name: str | None) -> str:
        # Apply cleanup before resolving through configured aliases.
        if not raw_name:
            return ""

        alias_map = self._get_marketplace_name_aliases()

        # Check aliases against raw input before destructive cleanup.
        raw_key = self._normalize_key(raw_name.split("/")[0].strip())
        if raw_key in alias_map:
            alias, canonical = alias_map[raw_key]
            normalization_usage.record_hit(
                "scraping.marketplace_name_aliases",
                alias,
                raw_name,
                canonical,
                "MarketplaceResolver.normalize_marketplace_name.raw",
            )
            return canonical

        # Re-check aliases after removing noise and domain suffixes.
        cleaned_name = self._strip_noise(raw_name)
        if not cleaned_name:
            return ""

        normalized_key = self._normalize_key(cleaned_name)
        if normalized_key in alias_map:
            alias, canonical = alias_map[normalized_key]
            normalization_usage.record_hit(
                "scraping.marketplace_name_aliases",
                alias,
                raw_name,
                canonical,
                "MarketplaceResolver.normalize_marketplace_name.cleaned",
            )
            return canonical
        return cleaned_name

    def resolve_marketplace_id(self, marketplace_id: str | None) -> str | None:
        if not marketplace_id:
            return None

        mapping = self.config.get("scraping", "marketplace_id_map", default={}) or {}

        resolved_name = mapping.get(str(marketplace_id).strip())
        if not resolved_name:
            return None
        normalization_usage.record_hit(
            "scraping.marketplace_id_map",
            str(marketplace_id).strip(),
            marketplace_id,
            resolved_name,
            "MarketplaceResolver.resolve_marketplace_id",
        )

        return self.normalize_marketplace_name(resolved_name)

    def resolve_label(self, raw_label: str | None) -> str:
        return self.normalize_marketplace_name(raw_label)

    # Private cleaning helpers.

    def _strip_noise(self, raw_text: str | None) -> str:
        # Remove sub-seller info, ratings, reviews, and domain suffixes.
        if not raw_text:
            return ""

        # Discard everything after the first slash because it represents sub-seller identity.
        text = raw_text.split("/")[0].strip()

        # Run each compiled noise pattern against the text.
        for pattern in self._compiled_noise:
            text = pattern.sub("", text)

        # Strip standard domain suffixes.
        text = self._strip_domain_suffix(text.strip())

        # Collapse any leftover whitespace.
        return re.sub(r"\s+", " ", text).strip()

    def _strip_domain_suffix(self, name: str) -> str:
        # Remove common domain suffixes while preserving distinctive marketplace names.
        lower = name.lower()
        for suffix in self._STRIPPABLE_DOMAIN_SUFFIXES:
            if lower.endswith(suffix):
                stripped = name[: len(name) - len(suffix)].strip()
                if stripped:
                    return stripped
        return name

    def _get_marketplace_name_aliases(self) -> dict[str, tuple[str, str]]:
        aliases = (
            self.config.get("scraping", "marketplace_name_aliases", default={}) or {}
        )
        return {
            self._normalize_key(alias): (alias, canonical)
            for alias, canonical in aliases.items()
            if alias and canonical
        }

    @staticmethod
    def _normalize_key(value: str) -> str:
        return " ".join(string_utils.to_ascii(value).lower().split())
