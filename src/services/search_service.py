"""Internal marketplace search and fallback discovery workflows."""

from urllib.parse import urlparse

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.core.config import Config
from src.core.exceptions import NetworkError
from src.core.logger import Logger
from src.utils import string_utils, time_utils
from src.utils.selector_usage import selector_usage


class SearchService:
    def __init__(
        self, driver: WebDriver, wait: WebDriverWait, config: Config | None = None
    ):
        self.driver = driver
        self.wait = wait
        self.config = config or Config()
        self.logger = Logger.get_logger(__name__)

    def _type_human_like(self, element, text: str) -> None:
        # Type with per-character jitter to keep input verification reliable.
        element.clear()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.BACKSPACE)
        for char in text:
            element.send_keys(char)
            time_utils.random_sleep(*self.config.get("delays", "typing"))

    def _type_and_confirm_internal_query(self, element, code: str) -> bool:
        # Re-type until the search box contains the exact target code.
        verify_timeout = self.config.get(
            "scraping", "input_verification_timeout", default=2.0
        )
        max_retries = self.config.get(
            "scraping", "input_verification_retries", default=2
        )

        for attempt in range(1, max_retries + 1):
            self._type_human_like(element, code)
            try:
                WebDriverWait(self.driver, verify_timeout).until(
                    lambda _driver: (
                        (element.get_attribute("value") or "").strip() == code
                    )
                )
                return True
            except TimeoutException:
                current_value = (element.get_attribute("value") or "").strip()
                self.logger.warning(
                    f"[{code}] Search input verification failed on attempt "
                    f"{attempt}/{max_retries}: '{current_value}'"
                )

        return False

    def _find_search_box(
        self, selector: str, selector_path: str = "runtime.search_box"
    ):
        # Wait until the search input is clickable and ready for typing.
        try:
            element = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            selector_usage.record_match(
                selector_path, selector, 1, "SearchService._find_search_box"
            )
            return element
        except TimeoutException:
            selector_usage.record_match(
                selector_path, selector, 0, "SearchService._find_search_box"
            )
            raise NetworkError(f"Search box not clickable: {selector}")

    def check_no_result(self) -> bool:
        # Treat no-result and suggestion pages as failed internal matches.
        try:
            no_res_sel = self.config.get("selectors", "search_no_result")
            elements = self.driver.find_elements(By.CSS_SELECTOR, no_res_sel)
            selector_usage.record_match(
                "selectors.search_no_result",
                no_res_sel,
                len(elements),
                "SearchService.check_no_result",
            )
            if elements:
                text = string_utils.to_ascii(elements[0].text).lower()
                phrases = self.config.get(
                    "scraping",
                    "no_result_phrases",
                    default=["bulunamadi", "ilginizi cekebilir"],
                )
                return any(phrase in text for phrase in phrases)
            return False
        except Exception:
            return False

    def search_internal(self, code: str) -> bool:
        # Run the site's native search flow for a product code.
        base_url = self.config.get("urls", "base", default="https://www.akakce.com")
        current = self.driver.current_url.lower()

        if "akakce.com" not in current or "google" in current:
            self.driver.get(base_url)
            time_utils.random_sleep(
                *self.config.get("delays", "internal_navigation", default=[1.0, 1.5])
            )

        input_sel = self.config.get("selectors", "search_input")
        try:
            search_box = self._find_search_box(input_sel, "selectors.search_input")
        except NetworkError:
            self.logger.warning(f"[{code}] Search box not found or not clickable.")
            return False

        if not self._type_and_confirm_internal_query(search_box, code):
            self.logger.warning(
                f"[{code}] Search input could not be verified. Skipping internal search."
            )
            return False

        time_utils.random_sleep(*self.config.get("delays", "pre_enter"))
        search_box.send_keys(Keys.RETURN)
        time_utils.random_sleep(*self.config.get("delays", "post_search"))

        if self.check_no_result():
            return False

        return True

    def search_google(self, code: str, brand: str | None = None) -> list[str]:
        # Run the fallback query and collect candidate product URLs.
        brand = brand or self.config.get("scraping", "default_brand", default="Razer")
        search_url = self.config.get("urls", "search", default="https://www.google.com")
        self.driver.get(search_url)

        input_sel = self.config.get(
            "selectors",
            "google",
            "search_input",
            default="textarea[name='q'], input[name='q']",
        )
        try:
            search_box = self._find_search_box(input_sel, "runtime.google.search_input")
        except NetworkError:
            self.logger.warning(f"[{code}] Google search box not found.")
            return []

        query_template = self.config.get("scraping", "google_query_format")
        query = query_template.replace("{code}", code).replace("{brand}", brand).strip()
        query = " ".join(query.split())
        self._type_human_like(search_box, query)

        search_box.send_keys(Keys.RETURN)
        time_utils.random_sleep(*self.config.get("delays", "post_search"))

        link_sel = self.config.get("selectors", "google", "result_link")
        links = self.driver.find_elements(By.CSS_SELECTOR, link_sel)
        selector_usage.record_match(
            "selectors.google.result_link",
            link_sel,
            len(links),
            "SearchService.search_google",
        )

        akakce_urls = []
        seen_urls = set()
        for link in links:
            try:
                href = link.get_attribute("href")
                if self._is_akakce_url(href):
                    canonical_url = self._canonicalize_url(href)
                    if not canonical_url or canonical_url in seen_urls:
                        continue
                    seen_urls.add(canonical_url)
                    akakce_urls.append(href)
            except Exception:
                continue

        return akakce_urls

    def get_result_items(self):
        # Return raw search result cards from the current results page.
        list_sel = self.config.get("selectors", "search_result_item")
        items = self.driver.find_elements(By.CSS_SELECTOR, list_sel)
        selector_usage.record_match(
            "selectors.search_result_item",
            list_sel,
            len(items),
            "SearchService.get_result_items",
        )
        return items

    @staticmethod
    def _is_akakce_url(url: str | None) -> bool:
        if not url:
            return False
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return host == "akakce.com" or host.endswith(".akakce.com")

    @staticmethod
    def _canonicalize_url(url: str | None) -> str:
        return string_utils.canonicalize_url(url)
