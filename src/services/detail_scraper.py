"""Extract title, category, and price fields from a product detail page."""

import random
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from src.core.config import Config
from src.core.logger import Logger
from src.models.product import ProductDTO
from src.utils import string_utils, time_utils
from src.utils.selector_usage import selector_usage


class DetailScraper:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self.config = Config()
        self.logger = Logger.get_logger(__name__)

    def scrape(self, dto: ProductDTO) -> bool:
        # Extract primary metadata from the current detail page.
        product_sel = self.config.get("selectors", "product")
        if not product_sel:
            self.logger.warning(
                "Product selectors not configured — skipping detail scrape"
            )
            return False

        # Read fields independently so partial metadata can still be retained.
        self._extract_title(dto, product_sel)
        self._extract_price(dto, product_sel)
        self._extract_category(dto, product_sel)

        # Add a light delay to reduce back-to-back page interactions.
        delay_range = self.config.get("delays", "post_detail", default=[0.5, 1.5])
        if random.random() > 0.3:
            time_utils.random_sleep(*delay_range)

        return True

    def _extract_title(self, dto: ProductDTO, selectors: dict) -> None:
        # Read the first matching title element.
        title_sel = selectors.get("title", "h1")
        elements = self.driver.find_elements(By.CSS_SELECTOR, title_sel)
        selector_usage.record_match(
            "selectors.product.title",
            title_sel,
            len(elements),
            "DetailScraper._extract_title",
        )
        if elements:
            dto.title = elements[0].text.strip()

    def _extract_price(self, dto: ProductDTO, selectors: dict) -> None:
        # Read and normalize the primary price element.
        price_sel = selectors.get("price", "span.pt_v8")
        elements = self.driver.find_elements(By.CSS_SELECTOR, price_sel)
        selector_usage.record_match(
            "selectors.product.price",
            price_sel,
            len(elements),
            "DetailScraper._extract_price",
        )
        if elements:
            dto.price = string_utils.clean_price(elements[0].text)

    def _normalise_category(self, raw_category: str, brand: str | None) -> str:
        # Remove embedded brand text from the leaf category when present.
        category = raw_category.strip()
        if not category:
            return ""

        if brand:
            category = re.sub(
                rf"\b{re.escape(brand.strip())}\b", "", category, flags=re.IGNORECASE
            )

        return re.sub(r"\s+", " ", category).strip()

    def _extract_category(self, dto: ProductDTO, selectors: dict) -> None:
        # Use the most specific breadcrumb leaf as the product category.
        crumb_sel = selectors.get("category_crumb", "nav ol li a")
        crumbs = self.driver.find_elements(By.CSS_SELECTOR, crumb_sel)
        selector_usage.record_match(
            "selectors.product.category_crumb",
            crumb_sel,
            len(crumbs),
            "DetailScraper._extract_category",
        )
        crumb_texts = [
            crumb.text.strip() for crumb in crumbs if crumb.text and crumb.text.strip()
        ]

        if not crumb_texts:
            return

        leaf_category = self._normalise_category(crumb_texts[-1], dto.brand)
        dto.category = leaf_category or crumb_texts[-1]
