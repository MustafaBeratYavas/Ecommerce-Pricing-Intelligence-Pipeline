"""Product data transfer object and database row conversion logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.utils import string_utils


@dataclass
class ProductDTO:
    code: str
    url: str | None = None
    brand: str = "Razer"
    title: str | None = None
    category: str | None = None
    price: float = 0.0
    sellers: list[dict[str, str | float]] = field(default_factory=list)
    page_match_verified: bool = True
    source: str = "unknown"
    run_id: str | None = None

    def has_identity_match(self) -> bool:
        # Direct/internal pages must expose the requested SKU unless explicitly marked unverified.
        return any(
            string_utils.contains_exact_lookup_token(value, self.code)
            for value in (self.title, self.url)
        )

    def has_price_signal(self) -> bool:
        # Persistence requires at least one visible price signal.
        if any(float(seller.get("price") or 0) > 0 for seller in self.sellers):
            return True
        return float(self.price or 0) > 0

    def to_db_rows(self) -> list[dict[str, Any]]:
        # Convert the current product snapshot into database-ready rows.
        today = date.today().strftime("%Y-%m-%d")

        # Share immutable product metadata across seller-level offer rows.
        base: dict[str, Any] = {
            "brand": self.brand,
            "product_code": self.code,
            "product_category": self.category,
            "product_name": self.title,
            "product_url": self.url,
            "scraped_at": today,
            "source": self.source,
            "match_verified": int(bool(self.page_match_verified)),
            "run_id": self.run_id,
        }

        # Store a product-level row when no seller-level offers were extracted.
        if not self.sellers:
            row = base.copy()
            row["marketplace"] = None
            row["price"] = self.price if self.price else None
            return [row]

        # Expand seller offers while keeping sub-seller identity out of storage.
        rows: list[dict[str, Any]] = []
        seen_storage_keys: set[tuple[str | None, float | None]] = set()
        for seller in self.sellers:
            marketplace = seller.get("name")
            price = seller.get("price")
            price_value = float(price) if isinstance(price, (float, int)) else None
            storage_key = (
                marketplace if isinstance(marketplace, str) else None,
                price_value,
            )
            if storage_key in seen_storage_keys:
                continue
            seen_storage_keys.add(storage_key)

            row = base.copy()
            row["marketplace"] = marketplace
            row["price"] = price_value
            rows.append(row)

        return rows
