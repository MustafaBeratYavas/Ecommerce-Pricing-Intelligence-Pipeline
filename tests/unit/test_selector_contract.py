"""Selector contract tests against small local HTML fixtures."""

import re
from pathlib import Path
from unittest.mock import MagicMock

from src.core.config import Config
from src.definitions import ROOT_DIR
from src.models.product import ProductDTO
from src.services.seller_extractor import SellerExtractor
from src.utils import string_utils

FIXTURE_DIR = Path(ROOT_DIR) / "tests" / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _selector_has_fixture_match(selector: str, html: str) -> bool:
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue

        if " " in part:
            if all(
                _selector_has_fixture_match(segment, html) for segment in part.split()
            ):
                return True
            continue

        id_match = re.fullmatch(r"([a-z0-9]+)#([A-Za-z0-9_-]+)", part)
        if id_match and re.search(
            rf"<{id_match.group(1)}[^>]+id=[\"']{id_match.group(2)}[\"']",
            html,
            flags=re.IGNORECASE,
        ):
            return True

        class_match = re.fullmatch(r"([a-z0-9]+)\.([A-Za-z0-9_-]+)", part)
        if class_match and re.search(
            rf"<{class_match.group(1)}[^>]+class=[\"'][^\"']*"
            rf"\b{class_match.group(2)}\b",
            html,
            flags=re.IGNORECASE,
        ):
            return True

        attr_match = re.fullmatch(r"([a-z0-9]+)\[([A-Za-z0-9_-]+)='([^']+)'\]", part)
        if attr_match and re.search(
            rf"<{attr_match.group(1)}[^>]+{attr_match.group(2)}=[\"']"
            rf"{re.escape(attr_match.group(3))}[\"']",
            html,
            flags=re.IGNORECASE,
        ):
            return True

        if re.search(rf"<{re.escape(part)}[\s>]", html, flags=re.IGNORECASE):
            return True

    return False


def test_detail_fixture_matches_configured_product_selectors():
    html = _fixture("detail_page_valid.html")
    config = Config()
    product_selectors = config.get("selectors", "product")

    assert _selector_has_fixture_match(product_selectors["title"], html)
    assert _selector_has_fixture_match(product_selectors["category_crumb"], html)
    assert _selector_has_fixture_match(product_selectors["price"], html)
    assert _selector_has_fixture_match(product_selectors["sellers_list"], html)
    assert _selector_has_fixture_match(product_selectors["seller_price"], html)
    assert _selector_has_fixture_match(product_selectors["seller_name_wrapper"], html)


def test_card_fixture_matches_configured_card_selectors():
    html = _fixture("card_result_valid.html")
    config = Config()

    assert _selector_has_fixture_match(
        config.get("selectors", "search_result_item"), html
    )
    assert _selector_has_fixture_match(
        config.get("selectors", "search_result_title"), html
    )
    assert _selector_has_fixture_match(
        config.get("selectors", "search_result_price"), html
    )
    assert _selector_has_fixture_match(
        config.get("selectors", "card", "sellers_container"), html
    )
    assert _selector_has_fixture_match(
        config.get("selectors", "card", "seller_price"), html
    )
    assert _selector_has_fixture_match(
        config.get("selectors", "card", "seller_name_img"), html
    )


def test_detail_fixture_page_source_parser_extracts_marketplaces():
    extractor = SellerExtractor(MagicMock())
    html = _fixture("detail_page_valid.html")
    sellers = []

    for item_html in re.findall(r"<li\b.*?</li>", html, flags=re.DOTALL):
        seller = extractor._parse_detail_seller_html(item_html)
        if seller:
            sellers.append(seller)

    assert [seller["name"] for seller in sellers] == ["Amazon", "Trendyol"]
    assert [seller["price"] for seller in sellers] == [4596.94, 4799.0]


def test_wrong_variant_fixture_fails_exact_identity_match():
    html = _fixture("fallback_wrong_variant.html")
    title_match = re.search(r"<h1>(.*?)</h1>", html, flags=re.DOTALL)
    assert title_match is not None
    title = title_match.group(1)
    dto = ProductDTO(
        code="RZ04-05220300-R3M1",
        title=title,
        url="https://www.akakce.com/rz04-05220300-r3u1.html",
    )

    assert not dto.has_identity_match()
    assert not string_utils.contains_exact_lookup_token(title, dto.code)
