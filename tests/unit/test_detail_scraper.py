"""Unit tests for product detail metadata extraction."""

import unittest
from unittest.mock import MagicMock, patch

from src.models.product import ProductDTO
from src.services.detail_scraper import DetailScraper


class TestDetailScraper(unittest.TestCase):
    def setUp(self):
        self.mock_driver = MagicMock()
        with (
            patch("src.services.detail_scraper.Config"),
            patch("src.services.detail_scraper.Logger"),
        ):
            self.scraper = DetailScraper(self.mock_driver)

    def test_extract_title(self):
        dto = ProductDTO(code="T004")
        mock_el = MagicMock()
        mock_el.text = "Razer DeathAdder V3"
        self.mock_driver.find_elements.return_value = [mock_el]

        self.scraper._extract_title(dto, {"title": "h1"})

        # Preserve title text exactly as exposed by the page element.
        self.assertEqual(dto.title, "Razer DeathAdder V3")

    def test_extract_price(self):
        dto = ProductDTO(code="T005")
        mock_el = MagicMock()
        mock_el.text = "1.500,00 TL"
        self.mock_driver.find_elements.return_value = [mock_el]

        self.scraper._extract_price(dto, {"price": "span.pt"})

        # Normalize localized price text into a float.
        self.assertAlmostEqual(dto.price, 1500.0)

    def test_extract_price_no_element(self):
        dto = ProductDTO(code="T006")
        self.mock_driver.find_elements.return_value = []

        self.scraper._extract_price(dto, {"price": "span.pt"})

        # Missing price elements should leave the DTO price unchanged.
        self.assertAlmostEqual(dto.price, 0.0)

    def test_extract_category_from_brand_leaf(self):
        dto = ProductDTO(code="T007")
        mock_crumbs = [
            MagicMock(text="Elektronik"),
            MagicMock(text="Cevre Birimleri"),
            MagicMock(text="Kulaklik"),
            MagicMock(text="Razer Kulaklik"),
        ]
        self.mock_driver.find_elements.return_value = mock_crumbs

        self.scraper._extract_category(dto, {"category_crumb": "nav ol li a"})

        self.assertEqual(dto.category, "Kulaklik")

    def test_extract_category_uses_leaf_when_no_brand_present(self):
        dto = ProductDTO(code="T008")
        mock_crumbs = [
            MagicMock(text="Elektronik"),
            MagicMock(text="Bilgisayar, Donanim"),
            MagicMock(text="Cevre Birimleri"),
            MagicMock(text="Kulaklik"),
        ]
        self.mock_driver.find_elements.return_value = mock_crumbs

        self.scraper._extract_category(dto, {"category_crumb": "nav ol li a"})

        self.assertEqual(dto.category, "Kulaklik")

    def test_extract_category_single_crumb(self):
        dto = ProductDTO(code="T009")
        self.mock_driver.find_elements.return_value = [MagicMock(text="Kulaklik")]

        self.scraper._extract_category(dto, {"category_crumb": "nav ol li a"})

        self.assertEqual(dto.category, "Kulaklik")

    def test_extract_category_no_crumbs(self):
        dto = ProductDTO(code="T010")
        self.mock_driver.find_elements.return_value = []

        self.scraper._extract_category(dto, {"category_crumb": "nav ol li a"})

        self.assertIsNone(dto.category)

    def test_normalise_category_collapses_whitespace_after_brand_removal(self):
        cleaned = self.scraper._normalise_category("  Razer   Kulaklik  ", "Razer")
        self.assertEqual(cleaned, "Kulaklik")

    def test_full_scrape_success(self):
        dto = ProductDTO(code="T011")
        self.scraper.config = MagicMock()
        self.scraper.config.get.return_value = [0.5, 1.0]

        with (
            patch.object(self.scraper, "_extract_title"),
            patch.object(self.scraper, "_extract_price"),
            patch.object(self.scraper, "_extract_category"),
            patch("src.services.detail_scraper.random.random", return_value=0.5),
            patch("src.services.detail_scraper.time_utils"),
        ):
            # A scrape succeeds when all field extractors complete.
            result = self.scraper.scrape(dto)
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
