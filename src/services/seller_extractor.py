"""Parse marketplace and price data from detail pages and result cards."""

import re
import unicodedata
from html import unescape
from math import ceil
from typing import Any
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.core.config import Config
from src.core.logger import Logger
from src.models.product import ProductDTO
from src.services.marketplace_resolver import MarketplaceResolver
from src.utils import string_utils, time_utils
from src.utils.selector_usage import selector_usage

SelectorMap = dict[str, Any]


class SellerExtractor:
    def __init__(self, driver: WebDriver, config: Config | None = None) -> None:
        self.driver = driver
        self.config = config or Config()
        self.logger = Logger.get_logger(__name__)
        self.marketplace_resolver = MarketplaceResolver(self.config)

    def _seller_collection_setting(self, key: str, default):
        settings = self.config.get("scraping", "seller_collection", default={}) or {}
        return settings.get(key, default)

    def _delay_range(self, key: str, default: list[float]) -> list[float]:
        return self.config.get("delays", key, default=default) or default

    def _product_selectors(self, product_sel: SelectorMap | None = None) -> SelectorMap:
        if product_sel is not None:
            return product_sel

        configured = self.config.get("selectors", "product", default={}) or {}
        if isinstance(configured, dict):
            return configured
        return {}

    # Detail page extraction.

    def extract_from_detail_page(self, dto: ProductDTO) -> None:
        product_sel = self._product_selectors()
        try:
            if self._has_no_price_indicator():
                dto.sellers = []
                dto.price = 0.0
                return

            dto.sellers = self._collect_detail_sellers(product_sel)

        except Exception as e:
            self.logger.debug(f"Detail seller extraction error: {e}")
            dto.sellers = []

        if dto.sellers:
            dto.price = float(min(s["price"] for s in dto.sellers))  # type: ignore

    def _collect_detail_sellers(self, product_sel: SelectorMap) -> list[dict]:
        sellers: list[dict] = []
        max_passes = int(self._seller_collection_setting("max_passes", 5))
        stagnant_pass_limit = int(
            self._seller_collection_setting("stagnant_pass_limit", 2)
        )
        stagnant_passes = 0

        self._scroll_to_top()

        # Wait for the seller list to enter the DOM before collection starts.
        try:
            container_sel = product_sel.get("sellers_list", "ul#PL, ul.pl_v9")
            list_wait = float(self._seller_collection_setting("list_wait_seconds", 5))
            WebDriverWait(self.driver, list_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, container_sel))
            )
        except TimeoutException:
            self.logger.debug("Seller list container not found within timeout.")

        # Expand hidden seller rows when the page exposes a load-more control.
        self._expand_all_sellers(product_sel)

        for _pass_num in range(max_passes):
            before_count = len(self._deduplicate(sellers))

            sellers.extend(self._collect_detail_sellers_from_dom(product_sel))
            sellers.extend(self._collect_detail_sellers_from_page_source())
            sellers.extend(self._collect_detail_sellers_from_structured_payload())

            scrolled = self._scroll_down()
            if scrolled:
                sellers.extend(self._collect_detail_sellers_from_dom(product_sel))
                sellers.extend(self._collect_detail_sellers_from_page_source())
                sellers.extend(self._collect_detail_sellers_from_structured_payload())

            final_count = len(self._deduplicate(sellers))

            if final_count <= before_count:
                stagnant_passes += 1
                if stagnant_passes >= stagnant_pass_limit:
                    break
            else:
                stagnant_passes = 0

        result = self._deduplicate(sellers)
        self.logger.debug(f"Seller collection complete: {len(result)} unique seller(s)")
        return result

    def _expand_all_sellers(
        self,
        product_sel: SelectorMap | None = None,
    ) -> None:
        """Click the 'Daha fazla fiyat gör' button if it exists.

        Not every product page has this button.  When present it reveals
        additional seller rows that were hidden behind a fold.  The method
        simply attempts to find and click the button — it does **not** use
        any expected-count heuristic because site-reported totals can
        disagree with visible rows.
        """
        product_sel = self._product_selectors(product_sel)
        max_clicks = int(self._seller_collection_setting("expand_max_clicks", 5))
        clicks = 0
        expand_wait = float(self._seller_collection_setting("expand_wait_seconds", 5))
        wait = WebDriverWait(self.driver, expand_wait)
        previous_count = self._count_seller_items(product_sel)

        # Remove overlays that can intercept clicks on dynamic pages.
        self._dismiss_overlays()

        while clicks < max_clicks:
            try:
                button = self._find_expand_button()
                if not button:
                    # The button may be below the fold, so bring the seller list into view.
                    self._scroll_seller_list_into_view(product_sel)
                    time_utils.random_sleep(
                        *self._delay_range("expand_button_discovery", [0.5, 1.0])
                    )
                    button = self._find_expand_button()
                    if not button:
                        break

                # Center the button before triggering the JavaScript click.
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", button
                )
                time_utils.random_sleep(
                    *self._delay_range("expand_button_click", [0.3, 0.5])
                )

                # Use JavaScript click to avoid intercepted native clicks.
                self.driver.execute_script("arguments[0].click();", button)
                clicks += 1

                current_count = self._wait_for_expanded_seller_count(
                    wait,
                    product_sel,
                    previous_count,
                    button,
                )
                self.logger.debug(
                    f"Expand click {clicks}: sellers {previous_count} -> {current_count}"
                )

                if current_count <= previous_count:
                    # Stop when the click no longer reveals additional rows.
                    if self._find_expand_button() is None:
                        break

                previous_count = current_count
            except Exception as e:
                self.logger.debug(f"Error expanding sellers list: {e}")
                break

    def _dismiss_overlays(self) -> None:
        # Remove consent banners and floating elements that can block controls.
        overlay_selectors = self.config.get(
            "selectors",
            "overlays",
            "dismiss",
            default=[
                "efilli-layout-dynamic",
                "div[class*='cookie']",
                "div[class*='consent']",
                "div[id*='cookie']",
                "#ob-wr",
            ],
        )
        for sel in overlay_selectors:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    self.driver.execute_script("arguments[0].remove();", el)
            except Exception:
                continue

    def _scroll_seller_list_into_view(self, product_sel: SelectorMap) -> None:
        # Move the seller list into view before searching for its expand button.
        container_sel = product_sel.get("sellers_list", "ul#PL, ul.pl_v9")
        try:
            containers = self.driver.find_elements(By.CSS_SELECTOR, container_sel)
            if containers:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'end'});",
                    containers[0],
                )
                time_utils.random_sleep(
                    *self._delay_range("scroll_list_into_view", [0.3, 0.5])
                )
        except Exception:
            pass

    # Card layout extraction.

    def extract_from_card(self, element: WebElement, dto: ProductDTO) -> None:
        sellers = []
        container_sel = self.config.get("selectors", "card", "sellers_container")
        link_sel = self.config.get("selectors", "card", "seller_link")

        try:
            container = element.find_element(By.CSS_SELECTOR, container_sel)
            selector_usage.record_match(
                "selectors.card.sellers_container",
                container_sel,
                1,
                "SellerExtractor.extract_from_card",
            )
            links = container.find_elements(By.CSS_SELECTOR, link_sel)
            selector_usage.record_match(
                "selectors.card.seller_link",
                link_sel,
                len(links),
                "SellerExtractor.extract_from_card",
            )

            for lnk in links:
                seller = self._parse_card_seller(lnk)
                if seller:
                    sellers.append(seller)

        except NoSuchElementException as e:
            selector_usage.record_match(
                "selectors.card.sellers_container",
                container_sel,
                0,
                "SellerExtractor.extract_from_card",
            )
            self.logger.debug(f"Sellers container not found in card: {e}")

        dto.sellers = sellers

        if sellers:
            dto.price = min(s["price"] for s in sellers)
        else:
            try:
                price_sel = self.config.get("selectors", "search_result_price")
                price_text = element.find_element(By.CSS_SELECTOR, price_sel).text
                dto.price = string_utils.clean_price(price_text)
            except NoSuchElementException as e:
                self.logger.debug(f"Price missing in search result: {e}")

    # Private parsing helpers.

    def _parse_detail_seller(
        self, item: WebElement, product_sel: SelectorMap
    ) -> dict | None:
        try:
            # Prefer discounted prices when both original and campaign prices are present.
            price = self._extract_best_price(item, product_sel)

            name = "Unknown"
            try:
                wrapper_sel = product_sel.get(
                    "seller_name_wrapper", "span.v_v8, div.v_v8, b.v_v8"
                )
                name_wrapper = item.find_element(By.CSS_SELECTOR, wrapper_sel)
                selector_usage.record_match(
                    "selectors.product.seller_name_wrapper",
                    wrapper_sel,
                    1,
                    "SellerExtractor._parse_detail_seller",
                )
                wrapper_text = name_wrapper.text.strip()

                # Prefer explicit image alt text, then bold labels, then wrapper text.
                name_imgs = name_wrapper.find_elements(By.TAG_NAME, "img")
                if name_imgs:
                    name = name_imgs[0].get_attribute("alt") or "Unknown"
                else:
                    bold_tags = name_wrapper.find_elements(By.TAG_NAME, "b")
                    if bold_tags:
                        name = bold_tags[0].text.strip()
                    else:
                        name = wrapper_text
            except NoSuchElementException as e:
                selector_usage.record_match(
                    "selectors.product.seller_name_wrapper",
                    product_sel.get(
                        "seller_name_wrapper", "span.v_v8, div.v_v8, b.v_v8"
                    ),
                    0,
                    "SellerExtractor._parse_detail_seller",
                )
                self.logger.debug(f"Seller name element missing: {e}")
                wrapper_text = ""

            # Resolve noisy seller text into a canonical marketplace name.
            name = self.marketplace_resolver.resolve_label(name)
            identity = self._compose_seller_identity(name, wrapper_text)

            if price and name:
                return {"name": name, "price": price, "identity": identity or name}

        except Exception as e:
            self.logger.debug(f"Error parsing detail seller: {e}")

        return None

    def _extract_best_price(self, item: WebElement, product_sel: SelectorMap) -> float:
        # Prefer campaign prices and never persist struck-through original prices.
        campaign_sel = product_sel.get("campaign_price", "span.cmpgn_pt_v8")
        original_price_class = product_sel.get("original_price_class", "orig_pt_v8")

        campaign_els = item.find_elements(By.CSS_SELECTOR, campaign_sel)
        selector_usage.record_match(
            "selectors.product.campaign_price",
            campaign_sel,
            len(campaign_els),
            "SellerExtractor._extract_best_price",
        )
        for el in campaign_els:
            price = string_utils.clean_price(el.text)
            if price > 0:
                return price

        # Fall back to regular prices after excluding struck-through originals.
        price_sel = product_sel.get("seller_price", "span.pt_v8")
        price_elements = item.find_elements(By.CSS_SELECTOR, price_sel)
        selector_usage.record_match(
            "selectors.product.seller_price",
            price_sel,
            len(price_elements),
            "SellerExtractor._extract_best_price",
        )
        for el in price_elements:
            css_class = el.get_attribute("class") or ""
            if original_price_class and original_price_class in css_class:
                continue
            price = string_utils.clean_price(el.text)
            if price > 0:
                return price

        return 0.0

    def _parse_card_seller(self, link_element: WebElement) -> dict | None:
        try:
            price_sel = self.config.get("selectors", "card", "seller_price")
            price_el = link_element.find_element(By.CSS_SELECTOR, price_sel)
            selector_usage.record_match(
                "selectors.card.seller_price",
                price_sel,
                1,
                "SellerExtractor._parse_card_seller",
            )
            price = string_utils.clean_price(price_el.text)

            seller_name = self._resolve_card_seller_name(link_element)
            identity = (
                self._normalise_seller_identity(
                    self._extract_card_seller_label(link_element)
                )
                or self._normalise_seller_identity(link_element.get_attribute("href"))
                or self._normalise_seller_identity(seller_name)
            )

            if price > 0:
                return {"name": seller_name, "price": price, "identity": identity}

        except Exception as e:
            selector_usage.record_match(
                "selectors.card.seller_price",
                self.config.get("selectors", "card", "seller_price"),
                0,
                "SellerExtractor._parse_card_seller",
            )
            self.logger.debug(f"Error parsing card seller: {e}")

        return None

    def _resolve_card_seller_name(self, link_element: WebElement) -> str:
        raw_name = self._extract_card_seller_label(link_element)
        seller_name = self.marketplace_resolver.resolve_label(raw_name)

        if seller_name and not self._looks_like_unknown_label(seller_name):
            if not seller_name.isdigit():
                return seller_name

            resolved_by_label = self.marketplace_resolver.resolve_marketplace_id(
                seller_name
            )
            if resolved_by_label:
                return resolved_by_label

        marketplace_id = self._extract_marketplace_id(link_element)
        if marketplace_id:
            resolved_by_id = self.marketplace_resolver.resolve_marketplace_id(
                marketplace_id
            )
            if resolved_by_id:
                return resolved_by_id
            return f"Bilinmeyen Satici (Akakce ID:{marketplace_id})"

        return "Bilinmeyen Satici"

    def _extract_card_seller_label(self, link_element: WebElement) -> str:
        img_sel = self.config.get("selectors", "card", "seller_name_img")
        text_sel = self.config.get("selectors", "card", "seller_name_text")

        imgs = link_element.find_elements(By.CSS_SELECTOR, img_sel)
        selector_usage.record_match(
            "selectors.card.seller_name_img",
            img_sel,
            len(imgs),
            "SellerExtractor._extract_card_seller_label",
        )
        if imgs:
            return (imgs[0].get_attribute("alt") or "").strip()

        texts = link_element.find_elements(By.CSS_SELECTOR, text_sel)
        selector_usage.record_match(
            "selectors.card.seller_name_text",
            text_sel,
            len(texts),
            "SellerExtractor._extract_card_seller_label",
        )
        if texts:
            return texts[0].text.strip()

        return ""

    def _extract_marketplace_id(self, link_element: WebElement) -> str | None:
        candidates = []

        raw_label = self._extract_card_seller_label(link_element)
        if raw_label:
            candidates.append(raw_label)

        href = link_element.get_attribute("href") or ""
        if href:
            candidates.extend(self._extract_numeric_tokens(href))
            try:
                query = parse_qs(urlparse(href).query)
                candidates.extend(query.get("v", []))
                candidates.extend(query.get("vd", []))
            except Exception:
                pass

        img_sel = self.config.get("selectors", "card", "seller_name_img")
        for img in link_element.find_elements(By.CSS_SELECTOR, img_sel):
            candidates.extend(
                filter(
                    None,
                    [
                        img.get_attribute("alt"),
                        img.get_attribute("src"),
                        img.get_attribute("data-src"),
                    ],
                )
            )

        for candidate in candidates:
            value = (candidate or "").strip()
            if value.isdigit():
                return value

            for token in self._extract_numeric_tokens(value):
                if token.isdigit():
                    return token

        return None

    def _has_no_price_indicator(self) -> bool:
        patterns = self.config.get(
            "scraping",
            "no_price_indicators",
            default=["fiyat bulunamadi"],
        )
        page_text = self._normalized_page_text()
        return any(pattern in page_text for pattern in patterns)

    def _find_expand_button(self) -> WebElement | None:
        # First try configured selectors that are known to target expand controls.
        specific_selectors = (
            self.config.get(
                "selectors",
                "product",
                "sellers_expand_specific",
                default=[],
            )
            or []
        )
        for sel in specific_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                selector_usage.record_match(
                    "selectors.product.sellers_expand_specific",
                    sel,
                    len(elements),
                    "SellerExtractor._find_expand_button",
                )
                for element in elements:
                    if element.is_displayed():
                        self.logger.debug(
                            f"Expand button found via specific selector: {sel}"
                        )
                        return element
            except Exception:
                continue

        # Fall back to visible text matching for layout variants.
        keywords = self.config.get(
            "selectors",
            "product",
            "sellers_expand_keywords",
            default=["daha fazla fiyat gor", "tum fiyatlar", "tum fiyat"],
        )
        selectors = self.config.get(
            "selectors",
            "product",
            "sellers_expand_candidates",
            default="button, a, div, span",
        )

        candidates = self.driver.find_elements(By.CSS_SELECTOR, selectors)
        selector_usage.record_match(
            "selectors.product.sellers_expand_candidates",
            selectors,
            len(candidates),
            "SellerExtractor._find_expand_button",
        )
        for element in candidates:
            try:
                if not element.is_displayed():
                    continue

                raw_text = " ".join(
                    str(value).strip()
                    for value in [
                        element.text,
                        element.get_attribute("title"),
                        element.get_attribute("aria-label"),
                        element.get_attribute("value"),
                    ]
                    if value
                )
                normalized_text = self._normalize_text(raw_text)
                if normalized_text and any(
                    keyword in normalized_text for keyword in keywords
                ):
                    self.logger.debug(
                        f"Expand button found via keyword match: "
                        f"'{normalized_text[:50]}'"
                    )
                    return element
            except Exception:
                continue
        self.logger.debug("No expand button found by any method.")
        return None

    # Site-reported total counters are unreliable; collection relies on visible rows.

    def _count_seller_items(self, product_sel: SelectorMap | None = None) -> int:
        product_sel = self._product_selectors(product_sel)
        container_sel = product_sel.get("sellers_list", "ul#PL, ul.pl_v9")
        item_sel = product_sel.get("sellers_list_item", "li")
        alt_sel = product_sel.get("sellers_alt_item", "li.w_v8")

        return len(self._collect_detail_items(container_sel, item_sel, alt_sel))

    def _normalized_page_text(self) -> str:
        try:
            return self._normalize_text(
                self.driver.find_element(By.TAG_NAME, "body").text
            )
        except Exception:
            return ""

    @staticmethod
    def _extract_numeric_tokens(text: str) -> list[str]:
        return re.findall(r"\b\d{2,}\b", text or "")

    @staticmethod
    def _looks_like_unknown_label(label: str) -> bool:
        lowered = string_utils.to_ascii(label).strip().lower()
        return lowered in {"", "unknown", "bilinmeyen satici", "bilinmeyen satci"}

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        if not text:
            return ""

        normalized = unicodedata.normalize("NFKD", text)
        normalized = normalized.translate(
            str.maketrans(
                {
                    "ç": "c",
                    "Ç": "c",
                    "ğ": "g",
                    "Ğ": "g",
                    "ı": "i",
                    "İ": "i",
                    "ö": "o",
                    "Ö": "o",
                    "ş": "s",
                    "Ş": "s",
                    "ü": "u",
                    "Ü": "u",
                }
            )
        )
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = string_utils.to_ascii(normalized)
        normalized = normalized.lower()
        return re.sub(r"\s+", " ", normalized).strip()

    def _deduplicate(self, sellers: list[dict]) -> list[dict]:
        unique = []
        seen: set = set()
        for s in sellers:
            identity = s.get("identity") or s["name"]
            key = (identity, s["price"])
            if key not in seen:
                unique.append(s)
                seen.add(key)
        return unique

    def _get_detail_seller_items(self, product_sel: SelectorMap) -> list[WebElement]:
        container_sel = product_sel.get("sellers_list", "ul#PL, ul.pl_v9")
        item_sel = product_sel.get("sellers_list_item", "li")
        alt_sel = product_sel.get("sellers_alt_item", "li.w_v8")
        return self._collect_detail_items(container_sel, item_sel, alt_sel)

    def _collect_detail_sellers_from_dom(self, product_sel: SelectorMap) -> list[dict]:
        sellers: list[dict] = []
        for item in self._get_detail_seller_items(product_sel):
            seller = self._parse_detail_seller(item, product_sel)
            if seller:
                sellers.append(seller)
        return sellers

    def _collect_detail_sellers_with_scroll(
        self, product_sel: SelectorMap
    ) -> list[dict]:
        sellers: list[dict] = []
        max_scroll_passes = int(
            self._seller_collection_setting("max_scroll_passes", 12)
        )
        stagnant_pass_limit = int(
            self._seller_collection_setting("stagnant_pass_limit", 2)
        )
        stagnant_passes = 0

        self._scroll_to_top()
        sellers.extend(self._collect_detail_sellers_from_dom(product_sel))

        for _ in range(max_scroll_passes):
            before_count = len(self._deduplicate(sellers))
            if not self._scroll_down():
                break

            self._wait_for_scroll_settle()
            sellers.extend(self._collect_detail_sellers_from_dom(product_sel))
            after_count = len(self._deduplicate(sellers))

            if after_count <= before_count:
                stagnant_passes += 1
                if stagnant_passes >= stagnant_pass_limit and self._is_at_page_bottom():
                    break
            else:
                stagnant_passes = 0

        return sellers

    def _collect_detail_sellers_from_page_source(self) -> list[dict]:
        try:
            page_source = self.driver.page_source or ""
        except Exception:
            return []

        if not isinstance(page_source, str):
            return []

        list_match = re.search(
            r"<ul[^>]+id=[\"']PL[\"'][^>]*>(.*?)</ul>",
            page_source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not list_match:
            return []

        sellers: list[dict] = []
        for item_html in re.findall(
            r"<li\b.*?</li>", list_match.group(1), flags=re.DOTALL
        ):
            seller = self._parse_detail_seller_html(item_html)
            if seller:
                sellers.append(seller)
        return sellers

    def _collect_detail_sellers_from_structured_payload(self) -> list[dict]:
        try:
            page_source = unescape(self.driver.page_source or "")
        except Exception:
            return []

        sellers: list[dict] = []
        if '"pgCode":[0,' not in page_source:
            return sellers

        segments = re.finditer(
            r'"pgCode":\[0,\d+\](?P<body>.*?)(?="pgCode":\[0,\d+\]|\]\]\])',
            page_source,
            flags=re.DOTALL,
        )

        for segment in segments:
            body = segment.group("body")
            price_match = re.search(r'"price":\[0,([0-9]+(?:\.[0-9]+)?)\]', body)
            name_match = re.search(r'"vdName":\[0,"([^"]+)"\]', body)
            nick_match = re.search(r'"pgNick":\[0,"([^"]+)"\]', body)
            if not price_match or not name_match:
                continue

            raw_name = unescape(name_match.group(1)).strip()
            raw_nick = unescape(nick_match.group(1)).strip() if nick_match else ""
            name = self.marketplace_resolver.resolve_label(raw_name)
            if not name:
                continue

            try:
                price = float(price_match.group(1))
            except ValueError:
                continue

            identity = self._compose_seller_identity(
                name,
                f"{raw_name}/{raw_nick}" if raw_nick else raw_name,
            )
            sellers.append({"name": name, "price": price, "identity": identity or name})

        return sellers

    def _parse_detail_seller_html(self, item_html: str) -> dict | None:
        # Use the same campaign-aware price rule for page-source fallback parsing.
        product_sel = self._product_selectors()
        price = self._extract_best_price_html(item_html, product_sel)
        if not price:
            return None

        wrapper_match = re.search(
            r"<span[^>]*class=[\"'][^\"']*\bv_v8\b[^\"']*[\"'][^>]*>(.*?)</span>",
            item_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not wrapper_match:
            return None

        wrapper_html = wrapper_match.group(1)
        img_alt_match = re.search(
            r"<img[^>]+alt=[\"']([^\"']+)[\"']",
            wrapper_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        bold_match = re.search(
            r"<b[^>]*>(.*?)</b>",
            wrapper_html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        raw_name = ""
        wrapper_text = self._strip_html(wrapper_html)
        if img_alt_match:
            raw_name = unescape(img_alt_match.group(1)).strip()
        elif bold_match:
            raw_name = self._strip_html(bold_match.group(1))
        else:
            raw_name = wrapper_text

        name = self.marketplace_resolver.resolve_label(raw_name)
        if not name:
            return None
        identity = self._compose_seller_identity(name, wrapper_text)

        return {
            "name": name,
            "price": price,
            "identity": identity or name,
        }

    def _extract_best_price_html(
        self, item_html: str, product_sel: SelectorMap | None = None
    ) -> float:
        # Prefer campaign price spans in raw HTML.
        product_sel = self._product_selectors(product_sel)
        campaign_class = self._last_css_class_token(
            product_sel.get("campaign_price", "span.cmpgn_pt_v8")
        )
        original_price_class = product_sel.get("original_price_class", "orig_pt_v8")
        campaign_match = re.search(
            rf"<span[^>]*class=[\"'][^\"']*\b{re.escape(campaign_class)}\b[^\"']*[\"'][^>]*>(.*?)</span>",
            item_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if campaign_match:
            price = string_utils.clean_price(self._strip_html(campaign_match.group(1)))
            if price > 0:
                return price

        # Fall back to regular pt_v8 spans while skipping struck-through originals.
        for m in re.finditer(
            r"<span[^>]*class=[\"']([^\"']*\bpt_v8\b[^\"']*)[\"'][^>]*>(.*?)</span>",
            item_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            css_classes = m.group(1)
            if original_price_class and original_price_class in css_classes:
                continue
            price = string_utils.clean_price(self._strip_html(m.group(2)))
            if price > 0:
                return price

        return 0.0

    @staticmethod
    def _last_css_class_token(selector: str) -> str:
        match = re.search(r"\.([A-Za-z0-9_-]+)\s*$", selector or "")
        return match.group(1) if match else str(selector or "").strip()

    def _collect_detail_items(
        self, container_sel: str, item_sel: str, alt_sel: str
    ) -> list[WebElement]:
        items: list[WebElement] = []
        seen_ids: set[str] = set()

        containers = self.driver.find_elements(By.CSS_SELECTOR, container_sel)
        selector_usage.record_match(
            "selectors.product.sellers_list",
            container_sel,
            len(containers),
            "SellerExtractor._collect_detail_items",
        )

        collected_from_containers = 0
        for container in containers:
            try:
                for item in container.find_elements(By.CSS_SELECTOR, item_sel):
                    collected_from_containers += 1
                    element_id = getattr(item, "id", "")
                    if element_id and element_id in seen_ids:
                        continue
                    if element_id:
                        seen_ids.add(element_id)
                    items.append(item)
            except Exception:
                continue
        selector_usage.record_match(
            "selectors.product.sellers_list_item",
            item_sel,
            collected_from_containers,
            "SellerExtractor._collect_detail_items",
        )

        try:
            alt_items = self.driver.find_elements(By.CSS_SELECTOR, alt_sel)
            selector_usage.record_match(
                "selectors.product.sellers_alt_item",
                alt_sel,
                len(alt_items),
                "SellerExtractor._collect_detail_items",
            )
            for item in alt_items:
                element_id = getattr(item, "id", "")
                if element_id and element_id in seen_ids:
                    continue
                if element_id:
                    seen_ids.add(element_id)
                items.append(item)
        except Exception:
            pass

        return items

    def _resolve_click_target(self, element: WebElement) -> WebElement:
        try:
            resolved = self.driver.execute_script(
                """
                return arguments[0].closest(
                    'button, a, [role="button"], .bt_v8, .ca_bt'
                ) || arguments[0];
                """,
                element,
            )
            if resolved:
                return resolved
        except Exception:
            pass
        return element

    def _wait_for_expanded_seller_count(
        self,
        wait: WebDriverWait,
        product_sel: SelectorMap,
        previous_total_count: int,
        button: WebElement,
    ) -> int:
        try:
            wait.until(
                lambda _driver: (
                    self._count_seller_items(product_sel) > previous_total_count
                    or self._is_stale(button)
                    or self._find_expand_button() is None
                )
            )
        except TimeoutException:
            pass

        return self._count_seller_items(product_sel)

    def _scroll_to_top(self) -> None:
        try:
            current_position = self._get_scroll_position()
            if current_position <= 0:
                return

            self._perform_scroll(-current_position, minimum_steps=3)
            self._wait_for_scroll_settle()
        except Exception:
            pass

    def _scroll_down(self) -> bool:
        previous_position = self._get_scroll_position()
        try:
            viewport_height = self._get_viewport_height()
            min_distance = int(
                self._seller_collection_setting("scroll_distance_min_px", 520)
            )
            viewport_ratio = float(
                self._seller_collection_setting("scroll_distance_viewport_ratio", 0.72)
            )
            distance = max(min_distance, int(viewport_height * viewport_ratio))
            self._perform_scroll(distance, minimum_steps=3)
        except Exception:
            return False

        self._wait_for_scroll_settle()
        current_position = self._get_scroll_position()
        return current_position > previous_position

    def _perform_scroll(self, distance: int, minimum_steps: int = 2) -> None:
        absolute_distance = abs(int(distance or 0))
        if absolute_distance == 0:
            return

        direction = 1 if distance > 0 else -1
        max_step_min = int(
            self._seller_collection_setting("scroll_max_step_min_px", 180)
        )
        max_step_ratio = float(
            self._seller_collection_setting("scroll_max_step_viewport_ratio", 0.28)
        )
        max_steps = int(self._seller_collection_setting("scroll_max_steps", 6))
        easing_power = float(
            self._seller_collection_setting("scroll_easing_power", 0.82)
        )
        max_step = max(max_step_min, int(self._get_viewport_height() * max_step_ratio))
        steps = max(minimum_steps, min(max_steps, ceil(absolute_distance / max_step)))
        previous_target = 0

        for step_index in range(1, steps + 1):
            progress = step_index / steps
            eased_progress = progress**easing_power
            current_target = int(round(absolute_distance * eased_progress))
            step_distance = max(1, current_target - previous_target)

            self.driver.execute_script(
                "window.scrollBy(0, arguments[0]);",
                direction * step_distance,
            )
            previous_target = current_target

            if step_index < steps:
                self._wait_for_scroll_motion()

    def _wait_for_scroll_motion(self) -> None:
        time_utils.random_sleep(*self._delay_range("scroll_motion", [0.03, 0.07]))

    def _wait_for_scroll_settle(self) -> None:
        scroll_delay = self.config.get("delays", "scroll", default=[0.2, 0.4]) or [
            0.2,
            0.4,
        ]
        min_delay = scroll_delay[0] if scroll_delay else 0.2
        max_delay = scroll_delay[1] if len(scroll_delay) > 1 else min_delay

        # Keep scroll motion gradual without making the scraper unnecessarily slow.
        factor = float(self._seller_collection_setting("scroll_settle_factor", 0.2))
        lower_bound = float(
            self._seller_collection_setting("scroll_settle_min_seconds", 0.08)
        )
        upper_bound = float(
            self._seller_collection_setting("scroll_settle_max_seconds", 0.24)
        )
        min_delay = min(max(min_delay * factor, lower_bound), upper_bound)
        max_delay = min(max(max_delay * factor, min_delay), upper_bound)
        time_utils.random_sleep(min_delay, max_delay)

    def _get_scroll_position(self) -> int:
        try:
            return int(
                self.driver.execute_script(
                    "return Math.floor(window.pageYOffset || document.documentElement.scrollTop || 0);"
                )
                or 0
            )
        except Exception:
            return 0

    def _get_viewport_height(self) -> int:
        try:
            return int(
                self.driver.execute_script(
                    """
                    return Math.max(
                        window.innerHeight || 0,
                        document.documentElement.clientHeight || 0,
                        1
                    );
                    """
                )
                or 1
            )
        except Exception:
            return int(
                self._seller_collection_setting("default_viewport_height_px", 900)
            )

    def _is_at_page_bottom(self) -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const tolerance = arguments[0];
                    return Math.ceil(window.innerHeight + window.pageYOffset)
                        >= Math.floor(document.body.scrollHeight - tolerance);
                    """,
                    int(self._seller_collection_setting("bottom_tolerance_px", 4)),
                )
            )
        except Exception:
            return False

    @staticmethod
    def _is_stale(element: WebElement) -> bool:
        try:
            element.tag_name
            return False
        except Exception:
            return True

    @staticmethod
    def _normalise_seller_identity(value: str | None) -> str | None:
        normalized = re.sub(r"\s+", " ", (value or "").strip())
        return normalized or None

    def _compose_seller_identity(
        self, marketplace_name: str | None, wrapper_text: str | None = None
    ) -> str | None:
        marketplace = self._normalise_seller_identity(marketplace_name)
        if not marketplace:
            return None

        wrapper = self._normalise_seller_identity(wrapper_text)
        if not wrapper or "/" not in wrapper:
            return marketplace

        sub_seller = wrapper.split("/", 1)[1].strip()
        sub_seller = re.sub(r"\s+", " ", sub_seller)
        sub_seller = re.sub(
            r"\bYorumlar\S*\s+oku\b", "", sub_seller, flags=re.IGNORECASE
        )
        sub_seller = re.sub(
            r"\d+[.,]\d+\s+\d+\s+Yorum", "", sub_seller, flags=re.IGNORECASE
        )
        sub_seller = re.sub(r"\d+\s+Yorum", "", sub_seller, flags=re.IGNORECASE)
        sub_seller = sub_seller.strip(" /-")

        if not sub_seller:
            return marketplace

        return f"{marketplace} / {sub_seller}"

    @staticmethod
    def _strip_html(fragment: str | None) -> str:
        cleaned = re.sub(r"<[^>]+>", " ", fragment or "")
        cleaned = unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()
