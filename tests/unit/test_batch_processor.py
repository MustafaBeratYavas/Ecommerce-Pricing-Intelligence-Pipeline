"""Unit tests for queue progression, retry handling, and persistence delegation."""

import unittest
from unittest.mock import MagicMock, patch

from src.core.exceptions import DatabaseError
from src.engine.batch_processor import BatchProcessor
from src.models.product import ProductDTO


class TestBatchProcessor(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_scraper = MagicMock()

        # Isolate queue orchestration from real database and scraper implementations.
        with patch("src.engine.batch_processor.Logger"):
            self.processor = BatchProcessor(self.mock_db, self.mock_scraper)
            self.mock_logger = MagicMock()
            self.processor.logger = self.mock_logger

    def test_run_success(self):
        self.mock_db.get_pending_product.side_effect = [
            {"id": 1, "product_code": "T001", "error_count": 0},
            None,
        ]

        result_dto = ProductDTO(
            code="T001",
            brand="Razer",
            title="Test Product T001",
            url="https://www.akakce.com/test-product-t001.html",
            sellers=[{"name": "Amazon", "identity": "Amazon", "price": 100.0}],
        )
        self.mock_scraper.process_product.return_value = result_dto

        self.processor.run()

        # Successful processing should persist rows and mark the target completed.
        self.mock_scraper.process_product.assert_called_once()
        self.mock_db.replace_products_snapshot.assert_called_once()
        self.mock_db.update_target_status.assert_called_once_with(1, "COMPLETED", 0)

    def test_run_multiple_codes(self):
        self.mock_db.get_pending_product.side_effect = [
            {"id": 1, "product_code": "T001", "error_count": 0},
            {"id": 2, "product_code": "T002", "error_count": 0},
            None,
        ]
        self.mock_scraper.process_product.side_effect = [
            ProductDTO(
                code="T001",
                title="Test Product T001",
                url="https://www.akakce.com/test-product-t001.html",
                sellers=[{"name": "Amazon", "identity": "Amazon", "price": 100.0}],
            ),
            ProductDTO(
                code="T002",
                title="Test Product T002",
                url="https://www.akakce.com/test-product-t002.html",
                sellers=[{"name": "Trendyol", "identity": "Trendyol", "price": 200.0}],
            ),
        ]

        self.processor.run()

        self.assertEqual(self.mock_scraper.process_product.call_count, 2)
        self.assertEqual(self.mock_db.replace_products_snapshot.call_count, 2)
        self.assertEqual(self.mock_db.update_target_status.call_count, 2)

    def test_run_scraper_exception_pending_retry(self):
        self.mock_db.get_pending_product.side_effect = [
            {"id": 1, "product_code": "T001", "error_count": 0},
            None,
        ]
        self.mock_scraper.process_product.side_effect = Exception("Crash")

        self.processor.run(max_retries=3)

        # Retryable scraper errors should return the target to pending.
        self.mock_db.update_target_status.assert_called_once_with(1, "PENDING", 1)

    def test_run_scraper_exception_max_retries_fail(self):
        self.mock_db.get_pending_product.side_effect = [
            {"id": 1, "product_code": "T001", "error_count": 2},
            None,
        ]
        self.mock_scraper.process_product.side_effect = Exception("Crash")

        self.processor.run(max_retries=3)

        # Exhausted retries should mark the target as failed.
        self.mock_db.update_target_status.assert_called_once_with(1, "FAILED", 3)

    def test_run_database_error_continues(self):
        self.mock_db.get_pending_product.side_effect = [
            {"id": 1, "product_code": "T001", "error_count": 0},
            None,
        ]
        self.mock_scraper.process_product.return_value = ProductDTO(
            code="T001",
            title="Test Product T001",
            url="https://www.akakce.com/test-product-t001.html",
            sellers=[{"name": "Amazon", "identity": "Amazon", "price": 100.0}],
        )
        self.mock_db.replace_products_snapshot.side_effect = DatabaseError("DB crash")

        self.processor.run()

        self.mock_db.update_target_status.assert_called_once_with(1, "PENDING", 1)

    def test_validate_rows_rejects_marketplace_less_offer(self):
        rows = [
            {
                "product_code": "T001",
                "product_name": "Test Product T001",
                "product_url": "https://www.akakce.com/test-product-t001.html",
                "marketplace": None,
                "price": 100.0,
                "match_verified": 1,
            }
        ]

        with self.assertRaises(Exception):
            self.processor._validate_rows("T001", rows)

    def test_validate_rows_rejects_unverified_offer(self):
        rows = [
            {
                "product_code": "T001",
                "product_name": "Test Product T001",
                "product_url": "https://www.akakce.com/test-product-t001.html",
                "marketplace": "Amazon",
                "price": 100.0,
                "match_verified": 0,
            }
        ]

        with self.assertRaises(Exception):
            self.processor._validate_rows("T001", rows)

    def test_log_prefix_uses_stable_product_position_across_retries(self):
        self.mock_db.get_target_count.return_value = 100
        self.mock_db.get_target_position.return_value = 44
        self.mock_db.get_pending_product.side_effect = [
            {"id": 44, "product_code": "T044", "error_count": 0},
            {"id": 44, "product_code": "T044", "error_count": 1},
            {"id": 44, "product_code": "T044", "error_count": 2},
            None,
        ]
        self.mock_scraper.process_product.side_effect = Exception("Crash")

        self.processor.run(max_retries=3)

        info_messages = [
            call.args[0] for call in self.mock_logger.info.call_args_list if call.args
        ]

        self.assertIn("[44/100 | attempt 1/3] Processing: T044", info_messages)
        self.assertIn("[44/100 | attempt 2/3] Processing: T044", info_messages)
        self.assertIn("[44/100 | attempt 3/3] Processing: T044", info_messages)

    def test_run_empty_queue(self):
        self.mock_db.get_pending_product.return_value = None

        self.processor.run()

        self.mock_scraper.process_product.assert_not_called()
        self.mock_db.replace_products_snapshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
