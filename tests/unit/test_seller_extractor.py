"""Unit tests for seller identification, price parsing, expansion, and deduplication."""

import unittest
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from src.models.product import ProductDTO
from src.services.seller_extractor import SellerExtractor


class TestSellerExtractor(unittest.TestCase):
    def setUp(self):
        self.mock_driver = MagicMock()
        with (
            patch("src.services.seller_extractor.Config"),
            patch("src.services.seller_extractor.Logger"),
        ):
            self.extractor = SellerExtractor(self.mock_driver)
            self.extractor.config = MagicMock()
            self.extractor.marketplace_resolver.config = self.extractor.config
            self.extractor.logger = MagicMock()

    def _mock_config_get(self, *keys, **kwargs):
        mapping = {
            ("scraping", "marketplace_id_map"): {
                "10939": "Koçtaş",
                "11116": "Trendyol",
                "11168": "Amazon",
                "11222": "Pasaj",
            },
            ("scraping", "marketplace_name_aliases"): {
                "Amazon.com.tr": "Amazon",
                "Amazon Türkiye": "Amazon",
                "Hepsiburada Premium": "Hepsiburada",
                "Koctas": "Koçtaş",
                "MediaMarkt Pazaryeri": "MediaMarkt",
                "N11": "n11",
                "Turkcell": "Pasaj",
                "Turkcell Pasaj": "Pasaj",
                "Trendyol Plus": "Trendyol",
            },
            ("selectors", "product"): {
                "sellers_list": "ul#PL",
                "sellers_list_item": "li",
                "sellers_alt_item": "li.w_v8",
                "seller_price": "span.pt_v8",
                "seller_name_wrapper": "span.v_v8",
                "sellers_expand_candidates": "button, a, div, span",
                "sellers_expand_keywords": [
                    "daha fazla fiyat gor",
                    "tum fiyatlar",
                    "tum fiyat",
                ],
            },
            ("selectors", "card", "sellers_container"): "div.p_w_v9",
            ("selectors", "card", "seller_link"): "a",
            ("selectors", "card", "seller_price"): "span.pt_v8",
            ("selectors", "card", "seller_name_img"): "span.l img",
            ("selectors", "card", "seller_name_text"): "span.l b",
            ("selectors", "search_result_price"): "span.pt_v8",
        }
        return mapping.get(keys, kwargs.get("default"))

    def test_extract_from_detail_page_with_sellers(self):
        self.extractor.config.get = self._mock_config_get

        mock_ul = MagicMock()
        mock_item = MagicMock()

        mock_price_el = MagicMock()
        mock_price_el.text = "1.500,00 TL"

        mock_name_wrapper = MagicMock()
        mock_name_wrapper.text = "Trendyol"
        mock_name_wrapper.find_elements.side_effect = [
            [],
            [MagicMock(text="Trendyol")],
        ]

        def item_find_element(by, sel):
            if "pt_v8" in sel:
                return mock_price_el
            if "v_v8" in sel:
                return mock_name_wrapper
            raise NoSuchElementException()

        mock_item.find_element.side_effect = item_find_element

        def item_find_elements(by, sel):
            if "cmpgn_pt_v8" in sel:
                return []
            if "pt_v8" in sel:
                return [mock_price_el]
            return []

        mock_item.find_elements.side_effect = item_find_elements
        mock_ul.find_elements.return_value = [mock_item]

        def driver_find_elements(by, sel):
            if by == By.CSS_SELECTOR and ("ul#PL" in sel or "ul.pl_v9" in sel):
                return [mock_ul]
            if by == By.CSS_SELECTOR and sel == "li.w_v8":
                return []
            if by == By.CSS_SELECTOR and sel == "button, a, div, span":
                return []
            if by == By.CSS_SELECTOR and sel == "h1, h2, h3, h4, div, span, a, button":
                return []
            return []

        self.mock_driver.find_elements.side_effect = driver_find_elements
        self.mock_driver.find_element.side_effect = NoSuchElementException()

        dto = ProductDTO(code="T001")
        self.extractor.extract_from_detail_page(dto)

        self.assertEqual(len(dto.sellers), 1)
        self.assertEqual(dto.sellers[0]["name"], "Trendyol")
        self.assertEqual(dto.price, 1500.0)

    def test_extract_from_detail_page_no_sellers(self):
        self.extractor.config.get = self._mock_config_get
        self.mock_driver.find_elements.return_value = []
        self.mock_driver.find_element.side_effect = NoSuchElementException()

        dto = ProductDTO(code="T002")
        self.extractor.extract_from_detail_page(dto)

        self.assertEqual(dto.sellers, [])

    def test_extract_from_detail_page_collects_all_seller_containers(self):
        self.extractor.config.get = self._mock_config_get

        first_ul = MagicMock()
        second_ul = MagicMock()
        first_item = MagicMock()
        second_item = MagicMock()

        first_ul.find_elements.return_value = [first_item]
        second_ul.find_elements.return_value = [second_item]

        price_1 = MagicMock()
        price_1.text = "1.000,00 TL"
        wrapper_1 = MagicMock()
        wrapper_1.text = "Trendyol / Seller-1"
        wrapper_1.find_elements.side_effect = [[], [MagicMock(text="Trendyol")]]

        price_2 = MagicMock()
        price_2.text = "1.250,00 TL"
        wrapper_2 = MagicMock()
        wrapper_2.text = "Amazon / Seller-2"
        wrapper_2.find_elements.side_effect = [[], [MagicMock(text="Amazon")]]

        def first_item_find_element(by, sel):
            if "pt_v8" in sel:
                return price_1
            if "v_v8" in sel:
                return wrapper_1
            raise NoSuchElementException()

        def second_item_find_element(by, sel):
            if "pt_v8" in sel:
                return price_2
            if "v_v8" in sel:
                return wrapper_2
            raise NoSuchElementException()

        first_item.find_element.side_effect = first_item_find_element
        second_item.find_element.side_effect = second_item_find_element

        def first_item_find_elements(by, sel):
            if "cmpgn_pt_v8" in sel:
                return []
            if "pt_v8" in sel:
                return [price_1]
            return []

        first_item.find_elements.side_effect = first_item_find_elements

        def second_item_find_elements(by, sel):
            if "cmpgn_pt_v8" in sel:
                return []
            if "pt_v8" in sel:
                return [price_2]
            return []

        second_item.find_elements.side_effect = second_item_find_elements

        def driver_find_elements(by, sel):
            if by == By.CSS_SELECTOR and sel == "ul#PL":
                return [first_ul, second_ul]
            if by == By.CSS_SELECTOR and sel == "li.w_v8":
                return []
            if by == By.CSS_SELECTOR and sel == "button, a, div, span":
                return []
            if by == By.CSS_SELECTOR and sel == "h1, h2, h3, h4, div, span, a, button":
                return []
            return []

        self.mock_driver.find_elements.side_effect = driver_find_elements
        self.mock_driver.find_element.side_effect = NoSuchElementException()

        dto = ProductDTO(code="T006")
        self.extractor.extract_from_detail_page(dto)

        self.assertEqual(len(dto.sellers), 2)
        self.assertEqual(dto.price, 1000.0)

    def test_extract_from_detail_page_uses_page_source_fallback_for_missing_dom_items(
        self,
    ):
        self.extractor.config.get = self._mock_config_get
        self.mock_driver.page_source = """
        <html><body>
            <h2>Fiyat Listesi</h2>
            <ul id="PL" class="pl_v9 pg_v9">
                <li>
                    <span class="pb_v8"><span class="pt_v8 ">3.990<i>,00 TL</i></span></span>
                    <span class="w_v8"><span class="v_v8"><img alt="Amazon.com.tr" src="//cdn.akakce.com/im/m6/11168.svg">/Nethouse</span></span>
                </li>
                <li>
                    <span class="pb_v8"><span class="pt_v8 ">3.990<i>,00 TL</i></span></span>
                    <span class="w_v8"><span class="v_v8"><img alt="Trendyol" src="//cdn.akakce.com/im/m6/11116.svg">/Nethouse</span></span>
                </li>
            </ul>
        </body></html>
        """

        def driver_find_elements(by, sel):
            if by == By.CSS_SELECTOR and sel == "ul#PL":
                return []
            if by == By.CSS_SELECTOR and sel == "li.w_v8":
                return []
            if by == By.CSS_SELECTOR and sel == "button, a, div, span":
                return []
            if by == By.CSS_SELECTOR and sel == "h1, h2, h3, h4, div, span, a, button":
                header = MagicMock()
                header.text = "Fiyat Listesi"
                return [header]
            return []

        self.mock_driver.find_elements.side_effect = driver_find_elements
        self.mock_driver.find_element.side_effect = NoSuchElementException()
        self.mock_driver.execute_script.return_value = 0

        dto = ProductDTO(code="T007")
        self.extractor.extract_from_detail_page(dto)

        self.assertEqual(len(dto.sellers), 2)
        self.assertEqual(
            [seller["name"] for seller in dto.sellers], ["Amazon", "Trendyol"]
        )

    def test_extract_from_card_no_container(self):
        self.extractor.config.get = self._mock_config_get
        mock_element = MagicMock()
        mock_element.find_element.side_effect = NoSuchElementException()

        dto = ProductDTO(code="T003")
        self.extractor.extract_from_card(mock_element, dto)

        self.assertEqual(dto.sellers, [])

    def test_extract_from_card_with_price_fallback(self):
        self.extractor.config.get = self._mock_config_get
        mock_element = MagicMock()
        mock_element.find_element.side_effect = [
            NoSuchElementException(),
            MagicMock(text="999,99 TL"),
        ]

        dto = ProductDTO(code="T004")
        self.extractor.extract_from_card(mock_element, dto)

        self.assertEqual(dto.sellers, [])

    def test_deduplicate(self):
        sellers = [
            {"name": "Amazon", "price": 100.0},
            {"name": "Amazon", "price": 100.0},
            {"name": "Trendyol", "price": 120.0},
        ]
        result = self.extractor._deduplicate(sellers)
        self.assertEqual(len(result), 2)

    def test_deduplicate_empty(self):
        result = self.extractor._deduplicate([])
        self.assertEqual(result, [])

    def test_deduplicate_keeps_same_marketplace_when_identity_differs(self):
        sellers = [
            {"name": "Pttavm", "price": 4999.0, "identity": "Pttavm / NetHouse"},
            {"name": "Pttavm", "price": 4999.0, "identity": "Pttavm / HFTEKNOLOJI"},
        ]

        result = self.extractor._deduplicate(sellers)

        self.assertEqual(len(result), 2)

    def test_deduplicate_keeps_same_price_when_marketplace_differs_but_merchant_matches(
        self,
    ):
        sellers = [
            {"name": "Amazon", "price": 3990.0, "identity": "Amazon / Nethouse"},
            {"name": "Trendyol", "price": 3990.0, "identity": "Trendyol / Nethouse"},
        ]

        result = self.extractor._deduplicate(sellers)

        self.assertEqual(len(result), 2)

    def test_parse_detail_seller_no_price(self):
        product_sel = {"seller_price": "span.pt_v8", "seller_name_wrapper": "span.v_v8"}
        mock_item = MagicMock()
        mock_item.find_element.side_effect = NoSuchElementException()

        result = self.extractor._parse_detail_seller(mock_item, product_sel)
        self.assertIsNone(result)

    def test_parse_card_seller_with_img(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "500,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.return_value = "Hepsiburada"
        mock_link.get_attribute.return_value = None

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Hepsiburada")

    def test_parse_card_seller_normalizes_marketplace_alias(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "500,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.return_value = "Hepsiburada Premium"
        mock_link.get_attribute.return_value = None

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Hepsiburada")

    def test_parse_card_seller_with_text(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "750,00 TL"
        mock_text = MagicMock()
        mock_text.text = "N11"
        mock_link.get_attribute.return_value = None

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return []
            if sel == "span.l b":
                return [mock_text]
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "n11")

    def test_parse_card_seller_with_text_normalizes_alias(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "750,00 TL"
        mock_text = MagicMock()
        mock_text.text = "Trendyol Plus"
        mock_link.get_attribute.return_value = None

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return []
            if sel == "span.l b":
                return [mock_text]
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Trendyol")

    def test_parse_detail_seller_normalizes_marketplace_alias(self):
        self.extractor.config.get = self._mock_config_get
        product_sel = {"seller_price": "span.pt_v8", "seller_name_wrapper": "span.v_v8"}
        mock_item = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "2.999,00 TL"
        mock_name_wrapper = MagicMock()
        mock_name_wrapper.text = "MediaMarkt Pazaryeri"
        mock_name_wrapper.find_elements.side_effect = [
            [],
            [MagicMock(text="MediaMarkt Pazaryeri")],
        ]

        def item_find_element(by, sel):
            if "pt_v8" in sel:
                return mock_price_el
            if "v_v8" in sel:
                return mock_name_wrapper
            raise NoSuchElementException()

        mock_item.find_element.side_effect = item_find_element

        def item_find_elements(by, sel):
            if "cmpgn_pt_v8" in sel:
                return []
            if "pt_v8" in sel:
                return [mock_price_el]
            return []

        mock_item.find_elements.side_effect = item_find_elements

        result = self.extractor._parse_detail_seller(mock_item, product_sel)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "MediaMarkt")
        self.assertEqual(result["price"], 2999.0)

    def test_parse_detail_seller_html_preserves_decimal_part(self):
        self.extractor.config.get = self._mock_config_get
        item_html = """
        <li>
            <span class="pb_v8"><span class="pt_v8 ">4.596<i>,94 TL</i></span></span>
            <span class="w_v8"><span class="v_v8"><img alt="Amazon Türkiye" src="https://cdn.akakce.com/im/m6/10001.svg">/Nethouse</span></span>
        </li>
        """

        result = self.extractor._parse_detail_seller_html(item_html)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Amazon")
        self.assertEqual(result["price"], 4596.94)

    def test_parse_card_seller_maps_numeric_alt_to_marketplace_name(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "15.499,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.side_effect = lambda attr: {
            "alt": "11222",
            "src": "//cdn.akakce.com/im/m6/11222.svg?16042026",
            "data-src": None,
        }.get(attr)
        mock_link.get_attribute.return_value = (
            "https://www.akakce.com/c/?z=134&s=0&v=11222&p=1475589084"
            "&c=20753&k=5555&g=1475578484&f=%2Fr%2F%3Fpr%3D1475589084%26vd%3D11222"
        )

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Pasaj")
        self.assertEqual(result["price"], 15499.0)

    def test_parse_card_seller_maps_koctas_marketplace_id(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "11.149,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.side_effect = lambda attr: {
            "alt": "10939",
            "src": "//cdn.akakce.com/im/m6/10939.svg",
            "data-src": None,
        }.get(attr)
        mock_link.get_attribute.return_value = "https://www.akakce.com/c/?v=10939"

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Koçtaş")
        self.assertEqual(result["price"], 11149.0)

    def test_parse_card_seller_unknown_numeric_id_is_not_used_as_marketplace_name(self):
        self.extractor.config.get = self._mock_config_get
        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "899,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.side_effect = lambda attr: {
            "alt": "99999",
            "src": "//cdn.akakce.com/im/m6/99999.svg?16042026",
            "data-src": None,
        }.get(attr)
        mock_link.get_attribute.return_value = "https://www.akakce.com/c/?v=99999"

        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect

        result = self.extractor._parse_card_seller(mock_link)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Bilinmeyen Satici (Akakce ID:99999)")

    def test_extract_from_card_with_sellers(self):
        self.extractor.config.get = self._mock_config_get
        mock_element = MagicMock()
        mock_container = MagicMock()
        mock_element.find_element.return_value = mock_container

        mock_link = MagicMock()
        mock_price_el = MagicMock()
        mock_price_el.text = "300,00 TL"
        mock_img = MagicMock()
        mock_img.get_attribute.return_value = "Amazon"
        mock_link.get_attribute.return_value = None
        mock_link.find_element.return_value = mock_price_el

        def find_elements_side_effect(by, sel):
            if sel == "span.l img":
                return [mock_img]
            if sel == "span.l b":
                return []
            return []

        mock_link.find_elements.side_effect = find_elements_side_effect
        mock_container.find_elements.return_value = [mock_link]

        dto = ProductDTO(code="T005")
        self.extractor.extract_from_card(mock_element, dto)

        self.assertEqual(len(dto.sellers), 1)
        self.assertEqual(dto.price, 300.0)

    @patch("src.services.seller_extractor.WebDriverWait")
    def test_expand_all_sellers_no_buttons(self, mock_wait_cls):
        self.extractor.config.get = self._mock_config_get
        self.mock_driver.find_elements.return_value = []

        self.extractor._expand_all_sellers()

        mock_wait_cls.assert_called_once()

    @patch("src.services.seller_extractor.WebDriverWait")
    def test_expand_all_sellers_clicks_button(self, mock_wait_cls):
        self.extractor.config.get = self._mock_config_get
        mock_button = MagicMock()
        mock_button.is_displayed.return_value = True
        mock_button.text = "Daha fazla fiyat gör"
        mock_button.get_attribute.return_value = None

        mock_header = MagicMock()
        mock_header.text = "Fiyat Listesi"

        mock_container = MagicMock()
        visible_before = MagicMock()
        visible_after_1 = MagicMock()
        visible_after_2 = MagicMock()

        call_count = {"n": 0}

        def find_elements_side_effect(by, sel):
            if by == By.CSS_SELECTOR and sel == "h1, h2, h3, h4, div, span, a, button":
                return [mock_header]
            if by == By.CSS_SELECTOR and sel == "button, a, div, span":
                return [mock_button]
            if by == By.CSS_SELECTOR and sel == "ul#PL":
                return [mock_container]
            if by == By.CSS_SELECTOR and sel == "li.w_v8":
                return []
            return []

        self.mock_driver.find_elements.side_effect = find_elements_side_effect
        self.mock_driver.find_element.side_effect = NoSuchElementException()

        def container_find_elements_side_effect(by, sel):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [visible_before]
            return [visible_before, visible_after_1, visible_after_2]

        mock_container.find_elements.side_effect = container_find_elements_side_effect

        mock_wait_instance = MagicMock()
        mock_wait_cls.return_value = mock_wait_instance
        mock_wait_instance.until.return_value = mock_button

        self.extractor._expand_all_sellers()

        self.mock_driver.execute_script.assert_called()

    @patch("src.services.seller_extractor.WebDriverWait")
    def test_expand_all_sellers_scrolls_to_find_follow_up_button(self, mock_wait_cls):
        self.extractor.config.get = self._mock_config_get
        mock_button = MagicMock()
        mock_button.click = MagicMock()

        self.extractor._count_seller_items = MagicMock(side_effect=[2, 2, 4])
        self.extractor._find_expand_button = MagicMock(
            side_effect=[None, mock_button, None]
        )
        self.extractor._scroll_down = MagicMock(side_effect=[True, False])
        self.extractor._wait_for_expanded_seller_count = MagicMock(return_value=4)
        self.extractor._is_at_page_bottom = MagicMock(return_value=False)
        self.extractor._scroll_seller_list_into_view = MagicMock()

        mock_wait_instance = MagicMock()
        mock_wait_cls.return_value = mock_wait_instance
        mock_wait_instance.until.return_value = mock_button

        self.extractor._expand_all_sellers()

        self.extractor._scroll_seller_list_into_view.assert_called()
        self.mock_driver.execute_script.assert_any_call(
            "arguments[0].click();", mock_button
        )

    def test_find_expand_button_handles_turkish_text(self):
        self.extractor.config.get = self._mock_config_get
        button = MagicMock()
        button.is_displayed.return_value = True
        button.text = "Daha fazla fiyat gör"
        button.get_attribute.return_value = None
        self.mock_driver.find_elements.return_value = [button]

        result = self.extractor._find_expand_button()

        self.assertIs(result, button)

    def test_scroll_down_uses_incremental_steps(self):
        self.extractor._get_scroll_position = MagicMock(side_effect=[120, 840])
        self.extractor._get_viewport_height = MagicMock(return_value=1000)
        self.extractor._wait_for_scroll_motion = MagicMock()
        self.extractor._wait_for_scroll_settle = MagicMock()

        result = self.extractor._scroll_down()

        self.assertTrue(result)
        scroll_calls = [
            call
            for call in self.mock_driver.execute_script.call_args_list
            if call.args and call.args[0] == "window.scrollBy(0, arguments[0]);"
        ]
        self.assertGreaterEqual(len(scroll_calls), 3)
        self.assertTrue(all(call.args[1] > 0 for call in scroll_calls))

    def test_scroll_to_top_uses_incremental_steps(self):
        self.extractor._get_scroll_position = MagicMock(return_value=900)
        self.extractor._get_viewport_height = MagicMock(return_value=1000)
        self.extractor._wait_for_scroll_motion = MagicMock()
        self.extractor._wait_for_scroll_settle = MagicMock()

        self.extractor._scroll_to_top()

        scroll_calls = [
            call
            for call in self.mock_driver.execute_script.call_args_list
            if call.args and call.args[0] == "window.scrollBy(0, arguments[0]);"
        ]
        self.assertGreaterEqual(len(scroll_calls), 3)
        self.assertTrue(all(call.args[1] < 0 for call in scroll_calls))


if __name__ == "__main__":
    unittest.main()
