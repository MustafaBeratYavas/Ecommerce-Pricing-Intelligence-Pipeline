"""Coordinate product resolution across direct URLs, internal search, and fallback search.

ScraperService owns the high-level decision flow for resolving a ProductDTO,
delegating page parsing, seller offer extraction, search, and database lookups
to specialized collaborators. It validates product-code evidence before
allowing downstream persistence or reporting.
"""

from urllib.parse import urlparse

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.core.config import Config
from src.core.exceptions import DataQualityError, ProductNotFound, ScraperError
from src.core.logger import Logger
from src.models.product import ProductDTO
from src.services.database import DatabaseService
from src.services.detail_scraper import DetailScraper
from src.services.search_service import SearchService
from src.services.seller_extractor import SellerExtractor
from src.utils import string_utils
from src.utils.selector_usage import selector_usage


class ScraperService:
    def __init__(
        self,
        driver: WebDriver,
        search_service: SearchService,
        detail_scraper: DetailScraper,
        seller_extractor: SellerExtractor,
        database: DatabaseService | None = None,
    ) -> None:
        self.driver = driver
        self.config = Config()
        self.logger = Logger.get_logger(__name__)
        self.database = database
        self._seen_url_codes: dict[str, set[str]] = {}

        # Keep collaborators injected so resolution paths remain unit-testable.
        self.search = search_service
        self.detail = detail_scraper
        self.seller = seller_extractor

    def process_product(self, dto: ProductDTO) -> ProductDTO:
        # Attempt resolution strategies in order of confidence.
        self.logger.info(f"[{dto.code}] Processing...")

        # Stored URLs are highest confidence but still must pass identity checks.
        if dto.url and "akakce.com" in dto.url:
            if self._try_direct_url(dto):
                self._validate_resolved_product(dto)
                return dto

        # Native marketplace search keeps resolution inside the target domain.
        try:
            if self.search.search_internal(dto.code):
                if self._analyze_internal_results(dto.code, dto):
                    self._validate_resolved_product(dto)
                    return dto
        except ScraperError as exc:
            self.logger.error(f"[{dto.code}] Internal search error: {exc}")

        # Fallback search is last because it has the broadest matching surface.
        self.logger.info(f"[{dto.code}] Switching to fallback search.")
        self._try_google_search(dto)

        self._validate_resolved_product(dto)
        return dto

    def _try_direct_url(self, dto: ProductDTO) -> bool:
        # Revalidate stored URLs because marketplace pages can drift between runs.
        self.logger.info(f"[{dto.code}] Source URL found. Attempting direct access.")
        try:
            assert dto.url is not None, "Direct URL called with no URL set"
            self.driver.get(dto.url)
            if self._scrape_and_extract(dto, source_label="direct_url"):
                self._remember_url(dto.code, dto.url)
                return True
            # Drop stale URLs so future retries do not repeat known-bad navigation.
            dto.url = None
        except Exception as exc:
            self.logger.warning(f"[{dto.code}] Direct URL failed: {exc}")
            dto.url = None
        return False

    def _analyze_internal_results(self, code: str, dto: ProductDTO) -> bool:
        # Route result layouts without assuming the marketplace renders one shape.
        try:
            items = self.search.get_result_items()
            if not items:
                return False

            matched_by_code, selected_item = self._select_internal_result(items, code)

            # Require a title signal before trusting a selected result element.
            title_sel = self.config.get("selectors", "search_result_title")
            selected_item.find_element(By.CSS_SELECTOR, title_sel)
            selector_usage.record_match(
                "selectors.search_result_title",
                title_sel,
                1,
                "ScraperService._analyze_internal_results",
            )

            # Preserve result-page category context when detail pages omit it.
            if not dto.category:
                try:
                    cat_links = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        self.config.get(
                            "selectors",
                            "product",
                            "search_category_links",
                            default="p.wbb_v8 a",
                        ),
                    )
                    if cat_links:
                        dto.category = string_utils.clean_text(cat_links[0].text)
                    else:
                        cat_links = self.driver.find_elements(
                            By.XPATH, "//p[contains(text(), 'kategoriye git')]/a"
                        )
                        if cat_links:
                            dto.category = string_utils.clean_text(cat_links[0].text)
                except Exception as e:
                    self.logger.debug(f"[{code}] Category extraction failed: {e}")

            candidate_url = self._get_result_url(selected_item)
            if (
                not matched_by_code
                and candidate_url
                and self._url_conflicts_with_other_code(candidate_url, code)
            ):
                self.logger.info(
                    f"[{code}] Internal result URL is already associated with "
                    "another product code. Switching to fallback search."
                )
                return False
            if not matched_by_code and not self._allows_unverified_persistence():
                self.logger.info(
                    f"[{code}] Internal result did not expose the requested code. "
                    "Switching to fallback search."
                )
                return False

            # Separate compact cards from navigable detail pages before extraction.
            class_attr = selected_item.get_attribute("class") or ""
            selected_href = self._get_result_href(selected_item)
            is_redirect = "n-p" in class_attr or not self._is_akakce_detail_url(
                selected_href
            )

            if is_redirect:
                return self._handle_card_result(selected_item, dto, code)

            return self._handle_detail_result(selected_item, dto, code)

        except NoSuchElementException as exc:
            self.logger.error(f"[{code}] Result element not found: {exc}")
            return False
        except ScraperError as exc:
            self.logger.error(f"[{code}] Result analysis error: {exc}")
            return False

    def _handle_card_result(
        self,
        element: WebElement,
        dto: ProductDTO,
        code: str,
    ) -> bool:
        # Compact result cards expose enough offer data to avoid extra navigation.
        self._extract_card_data(element, dto, code)
        dto.source = "internal_card"
        dto.page_match_verified = self._page_matches_code(dto)
        if not dto.page_match_verified and not self._allows_unverified_persistence():
            self.logger.warning(
                self._format_unverified_page_message(dto, "internal_card")
            )
            return False
        self._remember_url(code, dto.url)
        return True

    def _handle_detail_result(
        self,
        element: WebElement,
        dto: ProductDTO,
        code: str,
    ) -> bool:
        # Detail results require navigation before the full extractor can run.
        link = element.find_element(By.TAG_NAME, "a")
        self.driver.execute_script("arguments[0].click();", link)

        # Wait for identity content rather than relying on navigation completion.
        try:
            page_switch_delays = self.config.get(
                "delays", "page_switch", default=[5.0, 6.0]
            )
            wait_time = page_switch_delays[0] if page_switch_delays else 5.0
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        self.config.get("selectors", "product", "title", default="h1"),
                    )
                )
            )
        except TimeoutException:
            self.logger.debug(f"[{code}] Detail page load wait timeout.")

        # Cache the resolved URL only after the selected result has loaded.
        dto.url = self.driver.current_url

        if not self._scrape_and_extract(dto, source_label="internal_detail"):
            dto.url = None
            return False

        self._remember_url(code, dto.url)
        return True

    def _try_google_search(self, dto: ProductDTO) -> None:
        # Iterate fallback candidates until one yields validated offer data.
        try:
            urls = self.search.search_google(dto.code, dto.brand)
            preferred_urls = [
                url
                for url in urls
                if not self._url_conflicts_with_other_code(url, dto.code)
            ]
            conflicted_urls = [
                url
                for url in urls
                if self._url_conflicts_with_other_code(url, dto.code)
            ]

            for url in preferred_urls + conflicted_urls:
                try:
                    if url in conflicted_urls:
                        self.logger.warning(
                            f"[{dto.code}] Google fallback reused a URL already linked "
                            "to another product code. Proceeding as last resort."
                        )
                    self.driver.get(url)

                    # Wait for the target identity field before extraction starts.
                    try:
                        google_switch_delays = self.config.get(
                            "delays", "google_switch", default=[5.0, 6.0]
                        )
                        wait_time = (
                            google_switch_delays[0] if google_switch_delays else 5.0
                        )
                        WebDriverWait(self.driver, wait_time).until(
                            EC.presence_of_element_located(
                                (
                                    By.CSS_SELECTOR,
                                    self.config.get(
                                        "selectors", "product", "title", default="h1"
                                    ),
                                )
                            )
                        )
                    except TimeoutException:
                        self.logger.debug(
                            f"[{dto.code}] Fallback page load wait timeout."
                        )

                    dto.url = self.driver.current_url

                    if not self._scrape_and_extract(
                        dto,
                        allow_unverified_code_match=True,
                        source_label="google_fallback",
                    ):
                        dto.url = None
                        continue

                    self._remember_url(dto.code, dto.url)
                    # Stop at the first fallback candidate that produces valid data.
                    return

                except StaleElementReferenceException:
                    continue

        except ScraperError as exc:
            self.logger.error(f"[{dto.code}] Google search error: {exc}")

    def _scrape_and_extract(
        self,
        dto: ProductDTO,
        allow_unverified_code_match: bool = False,
        source_label: str = "resolved page",
    ) -> bool:
        # Extract metadata before seller offers so DTO identity is available.
        try:
            if not self.detail.scrape(dto):
                return False
            self.seller.extract_from_detail_page(dto)
            page_matches = self._page_matches_code(dto)

            if not page_matches:
                dto.page_match_verified = False
                message = self._format_unverified_page_message(dto, source_label)
                if (
                    allow_unverified_code_match
                    and self._allows_unverified_persistence()
                ):
                    dto.source = source_label
                    self.logger.warning(
                        message
                        + " Persisting because persist_unverified_fallback=true."
                    )
                    return True
                self.logger.warning(message + " Skipping unverified page.")
                return False

            dto.page_match_verified = True
            dto.source = source_label
            return True
        except ScraperError as exc:
            self.logger.error(f"[{dto.code}] Detail page parsing error: {exc}")
            return False

    def _extract_card_data(
        self,
        element: WebElement,
        dto: ProductDTO,
        code: str,
    ) -> None:
        # Card extraction stays local to avoid replacing the current result page.
        try:
            title_sel = self.config.get("selectors", "search_result_title")
            dto.title = element.find_element(By.CSS_SELECTOR, title_sel).text.strip()
            dto.url = self._get_result_url(element) or self.driver.current_url

            # Delegate seller parsing to the card-specific extractor.
            self.seller.extract_from_card(element, dto)

        except NoSuchElementException as exc:
            self.logger.error(f"[{code}] Card element not found: {exc}")
        except Exception as exc:
            self.logger.error(f"[{code}] Extraction failed: {exc}")

    def _select_internal_result(
        self,
        items: list[WebElement],
        code: str,
    ) -> tuple[bool, WebElement]:
        # Prefer exact-code result pages that keep extraction inside Akakce.
        matched_items = []
        for item in items:
            title = self._get_result_title(item)
            if string_utils.contains_exact_lookup_token(title, code):
                matched_items.append(item)

        for item in matched_items:
            href = self._get_result_href(item)
            if self._is_akakce_detail_url(href):
                return True, item

        if matched_items:
            return True, matched_items[0]
        return False, items[0]

    def _get_result_title(self, item: WebElement) -> str:
        title_sel = self.config.get("selectors", "search_result_title")
        try:
            title = item.find_element(By.CSS_SELECTOR, title_sel).text.strip()
            selector_usage.record_match(
                "selectors.search_result_title",
                title_sel,
                1,
                "ScraperService._get_result_title",
            )
            return title
        except NoSuchElementException:
            selector_usage.record_match(
                "selectors.search_result_title",
                title_sel,
                0,
                "ScraperService._get_result_title",
            )
            return ""

    def _get_result_url(self, item: WebElement) -> str | None:
        href = self._get_result_href(item)
        if href and self._is_akakce_url(href):
            return href
        return None

    def _get_result_href(self, item: WebElement) -> str | None:
        try:
            link = item.find_element(By.TAG_NAME, "a")
            return link.get_attribute("href")
        except NoSuchElementException:
            return None

    @classmethod
    def _is_akakce_detail_url(cls, url: str | None) -> bool:
        if not cls._is_akakce_url(url):
            return False
        parsed = urlparse(url or "")
        path = parsed.path.rstrip("/")
        if not path:
            return False
        return path != "/c" and not path.startswith("/c/")

    @staticmethod
    def _is_akakce_url(url: str | None) -> bool:
        if not url:
            return False
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return host == "akakce.com" or host.endswith(".akakce.com")

    def _remember_url(self, code: str, url: str | None) -> None:
        canonical = self._canonicalize_url(url)
        if not canonical:
            return
        self._seen_url_codes.setdefault(canonical, set()).add(code)

    def _url_conflicts_with_other_code(self, url: str, code: str) -> bool:
        canonical = self._canonicalize_url(url)
        if not canonical:
            return False

        seen_codes = self._seen_url_codes.get(canonical, set()) - {code}
        if seen_codes:
            return True

        if self.database is None:
            return False

        known_codes = self.database.get_product_codes_for_url(canonical) - {code}
        return bool(known_codes)

    @staticmethod
    def _canonicalize_url(url: str | None) -> str:
        return string_utils.canonicalize_url(url)

    @staticmethod
    def _normalize_lookup_token(text: str | None) -> str:
        return string_utils.normalize_lookup_token(text)

    def _page_matches_code(self, dto: ProductDTO) -> bool:
        # Keep verification tied to product identity fields. Full page-source scans
        # can match related products or embedded recommendations for nearby SKUs.
        candidates = [dto.title, dto.url, getattr(self.driver, "current_url", "")]
        return any(
            string_utils.contains_exact_lookup_token(candidate, dto.code)
            for candidate in candidates
            if candidate
        )

    def _validate_resolved_product(self, dto: ProductDTO) -> None:
        if not dto.title and not dto.url:
            raise ProductNotFound(f"No product page resolved for {dto.code}")

        if not self._page_matches_code(dto):
            if not self._allows_unverified_persistence():
                raise ProductNotFound(
                    f"Resolved page does not match requested product code: {dto.code}"
                )
            dto.page_match_verified = False

        if not dto.page_match_verified and not self._allows_unverified_persistence():
            raise ProductNotFound(
                f"Resolved page does not match requested product code: {dto.code}"
            )

        if not dto.has_price_signal():
            raise DataQualityError(f"No valid price data extracted for {dto.code}")

    def _format_unverified_page_message(
        self,
        dto: ProductDTO,
        source_label: str,
    ) -> str:
        title = string_utils.clean_text(dto.title) if dto.title else ""
        url = dto.url or getattr(self.driver, "current_url", "")
        return (
            f"[{dto.code}] {source_label} page did not expose requested product code. "
            f"Page is unverified. url='{url}' title='{title}'"
        )

    def _allows_unverified_persistence(self) -> bool:
        return bool(
            self.config.get(
                "scraping",
                "persist_unverified_fallback",
                default=False,
            )
        )
