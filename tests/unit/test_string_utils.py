"""Unit tests for price parsing, SKU matching, and text normalization helpers."""

import unittest

from src.utils.string_utils import (
    canonicalize_url,
    clean_price,
    clean_text,
    contains_exact_lookup_token,
    contains_lookup_token,
    normalize_lookup_token,
    to_ascii,
)


class TestCleanPrice(unittest.TestCase):
    def test_standard_turkish_format(self):
        self.assertAlmostEqual(clean_price("38.500,00 TL"), 38500.00)

    def test_with_whitespace(self):
        self.assertAlmostEqual(clean_price(" 1.200 tl "), 1200.0)

    def test_with_lira_symbol(self):
        self.assertAlmostEqual(clean_price("₺ 999,99"), 999.99)

    def test_empty_string(self):
        # Empty price inputs should safely normalize to the zero-price contract.
        self.assertAlmostEqual(clean_price(""), 0.0)

    def test_none_input(self):
        self.assertAlmostEqual(clean_price(None), 0.0)

    def test_invalid_text(self):
        self.assertAlmostEqual(clean_price("geçersiz"), 0.0)

    def test_integer_price(self):
        self.assertAlmostEqual(clean_price("500 TL"), 500.0)

    def test_decimal_only(self):
        self.assertAlmostEqual(clean_price("0,99 TL"), 0.99)

    def test_large_number(self):
        self.assertAlmostEqual(clean_price("1.234.567,89 TL"), 1234567.89)


class TestCleanText(unittest.TestCase):
    def test_slash_split(self):
        self.assertEqual(clean_text("Trendyol / Satıcı"), "Trendyol")

    def test_no_slash(self):
        self.assertEqual(clean_text("Hepsiburada"), "Hepsiburada")

    def test_with_whitespace(self):
        self.assertEqual(clean_text("  Amazon  "), "Amazon")

    def test_empty_string(self):
        self.assertEqual(clean_text(""), "")

    def test_none_input(self):
        self.assertEqual(clean_text(None), "")


class TestToAscii(unittest.TestCase):
    def test_turkish_chars(self):
        # Localized characters should transliterate without losing case intent.
        self.assertEqual(to_ascii("çğışöüÇĞİŞÖÜ"), "cgisouCGISOU")

    def test_plain_ascii(self):
        self.assertEqual(to_ascii("Hello"), "Hello")

    def test_empty(self):
        self.assertEqual(to_ascii(""), "")

    def test_none(self):
        self.assertEqual(to_ascii(None), "")


class TestLookupHelpers(unittest.TestCase):
    def test_normalize_lookup_token_collapses_sku_noise(self):
        self.assertEqual(
            normalize_lookup_token("RZ04-05220300-R3M1"), "rz0405220300r3m1"
        )

    def test_contains_lookup_token_matches_normalized_candidate(self):
        self.assertTrue(
            contains_lookup_token(
                "Razer BlackShark RZ04 03220100 R3M1",
                "RZ04-03220100-R3M1",
            )
        )

    def test_contains_lookup_token_rejects_missing_token(self):
        self.assertFalse(contains_lookup_token("Razer BlackShark V2", "RZ04-999"))

    def test_contains_exact_lookup_token_matches_hyphenated_sku(self):
        self.assertTrue(
            contains_exact_lookup_token(
                "Razer Barracuda X RZ04-05220300-R3M1 Siyah",
                "RZ04-05220300-R3M1",
            )
        )

    def test_contains_exact_lookup_token_matches_url_slug(self):
        self.assertTrue(
            contains_exact_lookup_token(
                "https://www.akakce.com/kulaklik/rz04-05220300-r3m1-fiyati.html",
                "RZ04-05220300-R3M1",
            )
        )

    def test_contains_exact_lookup_token_rejects_close_variant(self):
        self.assertFalse(
            contains_exact_lookup_token(
                "Razer Barracuda X RZ04-05220300-R3U1",
                "RZ04-05220300-R3M1",
            )
        )

    def test_contains_exact_lookup_token_rejects_longer_suffix(self):
        self.assertFalse(
            contains_exact_lookup_token(
                "Razer Barracuda X RZ04-05220300-R3M10",
                "RZ04-05220300-R3M1",
            )
        )

    def test_canonicalize_url_removes_query_fragment_and_trailing_slash(self):
        self.assertEqual(
            canonicalize_url("https://Akakce.com/Product/?a=1#reviews"),
            "https://akakce.com/product",
        )


if __name__ == "__main__":
    unittest.main()
