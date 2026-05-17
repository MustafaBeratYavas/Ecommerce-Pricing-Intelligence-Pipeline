"""Unit tests for scraper orchestration and fallback behavior."""

import unittest
from unittest.mock import MagicMock, patch

from selenium.webdriver.common.by import By

from src.core.exceptions import ProductNotFound
from src.models.product import ProductDTO
from src.services.scraper_service import ScraperService


class TestScraperService(unittest.TestCase):
    def setUp(self):
        self.mock_driver = MagicMock()
        self.mock_driver.current_url = "https://www.akakce.com"
        self.mock_driver.page_source = "<html>TEST-001</html>"

        self.mock_search = MagicMock()
        self.mock_detail = MagicMock()
        self.mock_seller = MagicMock()
        self.mock_db = MagicMock()
        self.mock_db.get_product_codes_for_url.return_value = set()

        self.service = ScraperService(
            self.mock_driver,
            self.mock_search,
            self.mock_detail,
            self.mock_seller,
            self.mock_db,
        )

    def _make_result_item(self, title: str, href: str, class_attr: str = ""):
        item = MagicMock()
        title_el = MagicMock()
        title_el.text = title

        link_el = MagicMock()
        link_el.get_attribute.return_value = href

        def find_element(by, value):
            if by == By.CSS_SELECTOR:
                return title_el
            if by == By.TAG_NAME and value == "a":
                return link_el
            raise AssertionError(f"Unexpected selector: {by} {value}")

        item.find_element.side_effect = find_element
        item.get_attribute.return_value = class_attr
        return item

    def test_direct_url_success(self):
        dto = ProductDTO(code="T001", url="https://www.akakce.com/t001.html")
        self.mock_detail.scrape.return_value = True
        self.mock_seller.extract_from_detail_page.side_effect = lambda dto: setattr(
            dto, "sellers", [{"name": "Shop", "identity": "Shop", "price": 100.0}]
        )
        self.mock_driver.page_source = "<html>T001</html>"

        result = self.service.process_product(dto)

        # Direct URL extraction should bypass search when it succeeds.
        self.assertIsNotNone(result.url)
        self.mock_detail.scrape.assert_called_once()

    def test_direct_url_fail_triggers_search(self):
        dto = ProductDTO(code="T002", url="https://www.akakce.com/fail.html")
        self.mock_detail.scrape.return_value = False
        self.mock_search.search_internal.return_value = False
        self.mock_search.search_google.return_value = []

        # Failed direct extraction should fall back to internal search.
        with self.assertRaises(ProductNotFound):
            self.service.process_product(dto)

        self.mock_search.search_internal.assert_called_once()

    def test_no_url_goes_to_search(self):
        dto = ProductDTO(code="T003")
        self.mock_search.search_internal.return_value = False
        self.mock_search.search_google.return_value = []

        # Products without stored URLs should start with internal search.
        with self.assertRaises(ProductNotFound):
            self.service.process_product(dto)

        self.mock_search.search_internal.assert_called_once()

    def test_select_internal_result_prefers_title_with_matching_code(self):
        first = self._make_result_item(
            "Razer Blackshark V2 Pro Kablosuz Kulak Ustu Oyuncu Kulakligi",
            "https://www.akakce.com/first.html",
        )
        second = self._make_result_item(
            "Razer Blackshark V2 Pro RZ04-03220100-R3M1 Siyah Kablosuz",
            "https://www.akakce.com/second.html",
        )

        matched, item = self.service._select_internal_result(
            [first, second], "RZ04-03220100-R3M1"
        )

        self.assertTrue(matched)
        self.assertIs(item, second)

    def test_select_internal_result_rejects_close_variant_title(self):
        first = self._make_result_item(
            "Razer Barracuda X Chroma RZ04-05220300-R3U1",
            "https://www.akakce.com/variant.html",
        )
        second = self._make_result_item(
            "Razer Barracuda X Chroma RZ04-05220300-R3M1",
            "https://www.akakce.com/exact.html",
        )

        matched, item = self.service._select_internal_result(
            [first, second], "RZ04-05220300-R3M1"
        )

        self.assertTrue(matched)
        self.assertIs(item, second)

    def test_select_internal_result_prefers_akakce_detail_over_redirect_card(self):
        redirect_card = self._make_result_item(
            "Razer Kaira Hyperspeed Playstation Lisansli Kablosuz Oyuncu Kulakligi RZ04-03980200-R3G1 Beyaz",
            "https://www.akakce.com/c/?v=10939&p=5003329419",
            class_attr="n-p",
        )
        detail_result = self._make_result_item(
            "Razer Kaira HyperSpeed PlayStation Licensed RZ04-03980200-R3G1 Kablosuz Kulak Ustu Oyuncu Kulakligi",
            "https://www.akakce.com/kulaklik/razer-kaira-hyperspeed-rz04-03980200-r3g1-fiyati.html",
        )

        matched, item = self.service._select_internal_result(
            [redirect_card, detail_result], "RZ04-03980200-R3G1"
        )

        self.assertTrue(matched)
        self.assertIs(item, detail_result)

    def test_analyze_internal_results_card(self):
        item = self._make_result_item(
            "Razer Blackshark V2 Pro RZ04-03220100-R3M1",
            "https://www.akakce.com/second.html",
            class_attr="n-p",
        )
        self.mock_search.get_result_items.return_value = [item]

        with patch.object(self.service, "_handle_card_result") as mock_handler:
            self.service._analyze_internal_results(
                "RZ04-03220100-R3M1", ProductDTO(code="RZ04-03220100-R3M1")
            )
            mock_handler.assert_called_once()

    def test_analyze_internal_results_detail(self):
        item = self._make_result_item(
            "Razer Blackshark V2 Pro RZ04-03220100-R3M1",
            "https://www.akakce.com/second.html",
            class_attr="",
        )
        self.mock_search.get_result_items.return_value = [item]

        with patch.object(self.service, "_handle_detail_result") as mock_handler:
            self.service._analyze_internal_results(
                "RZ04-03220100-R3M1", ProductDTO(code="RZ04-03220100-R3M1")
            )
            mock_handler.assert_called_once()

    def test_analyze_internal_results_conflict_triggers_fallback(self):
        item = self._make_result_item(
            "Razer Blackshark V2 Pro Kablosuz Kulak Ustu Oyuncu Kulakligi",
            "https://www.akakce.com/shared.html",
            class_attr="",
        )
        self.mock_search.get_result_items.return_value = [item]
        self.mock_db.get_product_codes_for_url.return_value = {"OTHER-CODE"}

        with patch.object(self.service, "_handle_detail_result") as mock_handler:
            result = self.service._analyze_internal_results(
                "RZ04-03220100-R3M1", ProductDTO(code="RZ04-03220100-R3M1")
            )

        self.assertFalse(result)
        mock_handler.assert_not_called()

    def test_handle_detail_result_success(self):
        dto = ProductDTO(code="D1")
        mock_el = self._make_result_item(
            "Razer Product", "https://www.akakce.com/d1.html"
        )
        with patch.object(self.service, "_scrape_and_extract", return_value=True):
            result = self.service._handle_detail_result(mock_el, dto, "D1")
            self.assertTrue(result)

    def test_try_google_search_success(self):
        dto = ProductDTO(code="G1")
        self.mock_search.search_google.return_value = ["http://akakce.com/1"]
        # Fallback search should navigate to the first candidate with valid data.
        with patch.object(self.service, "_scrape_and_extract", return_value=True):
            self.service._try_google_search(dto)
            self.assertIsNotNone(dto.url)

    def test_try_google_search_uses_conflicted_url_as_last_resort(self):
        dto = ProductDTO(code="G2")
        self.mock_search.search_google.return_value = [
            "https://www.akakce.com/conflicted.html"
        ]
        self.service._seen_url_codes["https://www.akakce.com/conflicted.html"] = {
            "OTHER-CODE"
        }

        with patch.object(self.service, "_scrape_and_extract", return_value=True):
            self.service._try_google_search(dto)

        self.mock_driver.get.assert_called_with(
            "https://www.akakce.com/conflicted.html"
        )

    @patch("src.services.scraper_service.WebDriverWait")
    def test_google_fallback_rejects_unverified_scraped_page(self, mock_wait_cls):
        mock_wait_cls.return_value.until.return_value = True
        dto = ProductDTO(code="G3")
        self.mock_search.search_internal.return_value = False
        self.mock_search.search_google.return_value = [
            "https://www.akakce.com/wrong.html"
        ]
        self.mock_driver.current_url = "https://www.akakce.com/wrong.html"
        self.mock_driver.page_source = "<html>Different product</html>"
        self.mock_detail.scrape.side_effect = lambda dto: (
            setattr(dto, "title", "Different product") or True
        )
        self.mock_seller.extract_from_detail_page.side_effect = lambda dto: setattr(
            dto, "sellers", [{"name": "Shop", "identity": "Shop", "price": 100.0}]
        )
        self.service.logger.warning = MagicMock()

        with self.assertRaises(ProductNotFound):
            self.service.process_product(dto)

        self.assertFalse(dto.page_match_verified)
        self.service.logger.warning.assert_called()
        self.assertIn(
            "Skipping unverified page",
            self.service.logger.warning.call_args[0][0],
        )

    def test_direct_scrape_rejects_unverified_page(self):
        dto = ProductDTO(code="D2", url="https://www.akakce.com/wrong.html")
        self.mock_driver.page_source = "<html>Different product</html>"
        self.mock_detail.scrape.side_effect = lambda dto: (
            setattr(dto, "title", "Different product") or True
        )
        self.mock_seller.extract_from_detail_page.side_effect = lambda dto: setattr(
            dto, "sellers", [{"name": "Shop", "identity": "Shop", "price": 100.0}]
        )

        result = self.service._scrape_and_extract(dto)

        self.assertFalse(result)
        self.assertFalse(dto.page_match_verified)

    def test_page_source_match_alone_does_not_verify_product(self):
        dto = ProductDTO(
            code="RZ04-05220300-R3M1",
            title="Razer Barracuda X RZ04-05220300-R3U1",
            url="https://www.akakce.com/rz04-05220300-r3u1.html",
        )
        self.mock_driver.current_url = dto.url
        self.mock_driver.page_source = "<html>Related: RZ04-05220300-R3M1</html>"

        self.assertFalse(self.service._page_matches_code(dto))

    def test_scrape_persists_unverified_only_when_explicitly_enabled(self):
        dto = ProductDTO(code="D3", url="https://www.akakce.com/wrong.html")
        self.mock_driver.page_source = "<html>Different product</html>"
        self.mock_detail.scrape.side_effect = lambda dto: (
            setattr(dto, "title", "Different product") or True
        )
        self.mock_seller.extract_from_detail_page.side_effect = lambda dto: setattr(
            dto, "sellers", [{"name": "Shop", "identity": "Shop", "price": 100.0}]
        )
        self.service.config = MagicMock()
        self.service.config.get.side_effect = lambda *args, **kwargs: (
            True
            if args == ("scraping", "persist_unverified_fallback")
            else kwargs.get("default")
        )

        result = self.service._scrape_and_extract(
            dto,
            allow_unverified_code_match=True,
            source_label="google_fallback",
        )

        self.assertTrue(result)
        self.assertFalse(dto.page_match_verified)
        self.assertEqual(dto.source, "google_fallback")

    def test_process_product_returns_dto(self):
        dto = ProductDTO(code="T010")
        self.mock_search.search_internal.return_value = False
        self.mock_search.search_google.return_value = []

        with self.assertRaises(ProductNotFound):
            self.service.process_product(dto)


if __name__ == "__main__":
    unittest.main()
