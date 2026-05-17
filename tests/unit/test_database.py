"""Unit tests for database lifecycle, queue state, and persistence behavior."""

import sqlite3
import unittest
from unittest.mock import patch

from src.services.database import DatabaseService


class TestDatabaseService(unittest.TestCase):
    def setUp(self):
        DatabaseService.reset_instance()

        self.config_patcher = patch("src.services.database.Config")
        self.logger_patcher = patch("src.services.database.Logger")
        self.mock_config = self.config_patcher.start()
        self.mock_logger = self.logger_patcher.start()

        self.mock_config.return_value.get.return_value = ":memory:"

        with patch.object(DatabaseService, "_connect"):
            self.db = DatabaseService()

        self.db._connection = sqlite3.connect(":memory:")
        self.db._connection.execute("PRAGMA journal_mode=WAL;")
        self.db._connection.execute(DatabaseService._CREATE_TABLE_SQL)
        self.db._connection.execute(DatabaseService._CREATE_TARGETS_TABLE_SQL)
        self.db._connection.commit()

    def tearDown(self):
        if self.db._connection:
            self.db._connection.close()
        DatabaseService.reset_instance()
        self.config_patcher.stop()
        self.logger_patcher.stop()

    def _sample_row(self, **overrides):
        row = {
            "brand": "Razer",
            "product_code": "RZ01-001",
            "product_category": "Kulaklık",
            "product_name": "Razer Barracuda X",
            "marketplace": "Trendyol",
            "price": 4990.0,
            "product_url": "https://www.akakce.com/test.html",
            "scraped_at": "2026-04-18",
        }
        row.update(overrides)
        return row

    def test_insert_single_product(self):
        row = self._sample_row()
        self.db.insert_product(row)

        cursor = self.db.conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)

    def test_insert_product_persists_data(self):
        row = self._sample_row(brand="MSI", product_code="MSI-123")
        self.db.insert_product(row)

        cursor = self.db.conn.execute(
            """
            SELECT brand, product_code, source, match_verified, run_id
            FROM products
            WHERE product_code = ?
            """,
            ("MSI-123",),
        )
        result = cursor.fetchone()
        self.assertEqual(result[0], "MSI")
        self.assertEqual(result[1], "MSI-123")
        self.assertEqual(result[2], "unknown")
        self.assertEqual(result[3], 1)
        self.assertIsNotNone(result[4])

    def test_insert_products_batch(self):
        rows = [
            self._sample_row(marketplace="Amazon"),
            self._sample_row(marketplace="Trendyol"),
            self._sample_row(marketplace="Hepsiburada"),
        ]
        self.db.insert_products(rows)

        cursor = self.db.conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        # Persist every row from the provided batch.
        self.assertEqual(count, 3)

    def test_insert_products_empty_list(self):
        self.db.insert_products([])

        cursor = self.db.conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0)

    def test_replace_products_snapshot_replaces_same_day_rows(self):
        old_rows = [
            self._sample_row(product_code="CODE-1", marketplace="Amazon", price=100.0),
            self._sample_row(
                product_code="CODE-1", marketplace="Trendyol", price=110.0
            ),
        ]
        new_rows = [
            self._sample_row(
                product_code="CODE-1", marketplace="Hepsiburada", price=120.0
            ),
        ]

        self.db.insert_products(old_rows)
        self.db.replace_products_snapshot(new_rows)

        cursor = self.db.conn.execute(
            "SELECT marketplace, price FROM products WHERE product_code = 'CODE-1'"
        )
        result = cursor.fetchall()
        self.assertEqual(result, [("Hepsiburada", 120.0)])

    def test_replace_products_snapshot_rejects_obvious_partial_replacement(self):
        old_rows = [
            self._sample_row(
                product_code="CODE-1",
                marketplace=f"Market-{index}",
                price=100.0 + index,
            )
            for index in range(10)
        ]
        new_rows = [
            self._sample_row(
                product_code="CODE-1",
                marketplace="Only-One-Market",
                price=120.0,
            )
        ]

        self.db.insert_products(old_rows)

        with self.assertRaises(Exception):
            self.db.replace_products_snapshot(new_rows)

        cursor = self.db.conn.execute(
            "SELECT COUNT(*) FROM products WHERE product_code = 'CODE-1'"
        )
        self.assertEqual(cursor.fetchone()[0], 10)

    def test_insert_product_with_none_values_is_rejected(self):
        row = self._sample_row(brand=None, marketplace=None, price=None)

        with self.assertRaises(Exception):
            self.db.insert_product(row)

        cursor = self.db.conn.execute("SELECT COUNT(*) FROM products")
        self.assertEqual(cursor.fetchone()[0], 0)

    def test_insert_product_rejects_unverified_rows(self):
        row = self._sample_row(match_verified=0)

        with self.assertRaises(Exception):
            self.db.insert_product(row)

        cursor = self.db.conn.execute("SELECT COUNT(*) FROM products")
        self.assertEqual(cursor.fetchone()[0], 0)

    def test_scraped_at_format(self):
        row = self._sample_row(scraped_at="2026-04-18")
        self.db.insert_product(row)

        cursor = self.db.conn.execute("SELECT scraped_at FROM products")
        result = cursor.fetchone()[0]
        self.assertEqual(result, "2026-04-18")

    def test_get_product_codes_for_url_returns_matching_codes(self):
        self.db.insert_product(self._sample_row(product_code="CODE-1"))
        self.db.insert_product(
            self._sample_row(
                product_code="CODE-2",
                marketplace="Amazon",
                product_url="https://www.akakce.com/test.html/",
            )
        )
        self.db.insert_product(
            self._sample_row(
                product_code="CODE-3",
                marketplace="Hepsiburada",
                product_url="https://www.akakce.com/other.html",
            )
        )

        codes = self.db.get_product_codes_for_url("https://www.akakce.com/test.html")

        self.assertEqual(codes, {"CODE-1", "CODE-2"})

    def test_context_manager(self):
        with self.db as db:
            db.insert_product(self._sample_row())

            cursor = db.conn.execute("SELECT COUNT(*) FROM products")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

    def test_task_queue_operations(self):

        self.db.add_target_product("T-001")
        self.db.add_target_product("T-002")
        self.db.add_target_product("T-001")

        # Claim pending queue items sequentially.
        target1 = self.db.get_pending_product()
        self.assertIsNotNone(target1)
        assert target1 is not None
        self.assertEqual(target1["product_code"], "T-001")
        self.assertEqual(target1["error_count"], 0)

        self.db.update_target_status(target1["id"], "COMPLETED", 0)

        target2 = self.db.get_pending_product()
        self.assertIsNotNone(target2)
        assert target2 is not None
        self.assertEqual(target2["product_code"], "T-002")

        self.db.update_target_status(
            target2["id"], "PENDING", target2["error_count"] + 1
        )

        target3 = self.db.get_pending_product()
        self.assertIsNotNone(target3)
        assert target3 is not None
        self.assertEqual(target3["product_code"], "T-002")
        self.assertEqual(target3["error_count"], 1)

        self.db.update_target_status(target3["id"], "FAILED", 1)

        empty = self.db.get_pending_product()
        # Return None once the pending queue is exhausted.
        self.assertIsNone(empty)

    def test_queue_count_and_position_are_stable_across_retries(self):
        self.db.add_target_product("T-001")
        self.db.add_target_product("T-002")

        target1 = self.db.get_pending_product()
        assert target1 is not None
        self.db.update_target_status(target1["id"], "PENDING", 1)
        target1_retry = self.db.get_pending_product()
        assert target1_retry is not None

        self.assertEqual(self.db.get_target_count(), 2)
        self.assertEqual(self.db.get_target_position(target1_retry["id"]), 1)
        self.assertEqual(target1_retry["product_code"], "T-001")

    def test_sync_target_product_requeues_existing_completed_target(self):
        self.db.add_target_product("T-001")
        target = self.db.get_pending_product()
        assert target is not None
        self.db.update_target_status(target["id"], "COMPLETED", 0)

        self.db.sync_target_product("T-001")

        requeued = self.db.get_pending_product()
        self.assertIsNotNone(requeued)
        assert requeued is not None
        self.assertEqual(requeued["product_code"], "T-001")
        self.assertEqual(requeued["error_count"], 0)

    def test_update_target_status_rejects_invalid_status(self):
        self.db.add_target_product("T-001")
        target = self.db.get_pending_product()
        assert target is not None

        with self.assertRaises(Exception):
            self.db.update_target_status(target["id"], "DONE", 0)

    def test_target_status_check_constraint_rejects_invalid_status(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                """
                INSERT INTO target_products (product_code, status)
                VALUES (?, ?)
                """,
                ("T-INVALID", "DONE"),
            )

    def test_ensure_schema_creates_expected_indexes(self):
        self.db._ensure_schema()

        indexes = {
            row[1]
            for row in self.db.conn.execute("PRAGMA index_list(products)").fetchall()
        }
        target_indexes = {
            row[1]
            for row in self.db.conn.execute(
                "PRAGMA index_list(target_products)"
            ).fetchall()
        }

        self.assertIn("idx_products_code_scraped_at", indexes)
        self.assertIn("idx_products_product_url", indexes)
        self.assertIn("idx_products_run_id", indexes)
        self.assertIn("idx_target_products_status_id", target_indexes)

    def test_singleton_pattern(self):
        db2 = DatabaseService()
        self.assertIs(self.db, db2)

    def test_ensure_connection_reconnects_after_close(self):

        self.db.close()
        self.assertIsNone(self.db._connection)

        original_connect = self.db._connect

        def mock_reconnect():
            self.db._connection = sqlite3.connect(":memory:")
            self.db._connection.execute(DatabaseService._CREATE_TABLE_SQL)
            self.db._connection.execute(DatabaseService._CREATE_TARGETS_TABLE_SQL)
            self.db._connection.commit()

        self.db._connect = mock_reconnect

        self.db._ensure_connection()
        # Reopen the singleton connection after an explicit close.
        self.assertIsNotNone(self.db._connection)
        assert self.db._connection is not None

        self.db.insert_product(self._sample_row())
        cursor = self.db._connection.execute("SELECT COUNT(*) FROM products")
        self.assertEqual(cursor.fetchone()[0], 1)

        self.db._connect = original_connect

    def test_reconnect_refreshes_run_id(self):
        self.db.close()
        self.db._run_id = "stale-run-id"

        original_connect = self.db._connect

        def mock_reconnect():
            self.db._connection = sqlite3.connect(":memory:")
            self.db._connection.execute(DatabaseService._CREATE_TABLE_SQL)
            self.db._connection.execute(DatabaseService._CREATE_TARGETS_TABLE_SQL)
            self.db._connection.commit()

        self.db._connect = mock_reconnect

        self.db._ensure_connection()

        self.assertNotEqual(self.db._run_id, "stale-run-id")

        self.db._connect = original_connect

    def test_ensure_connection_noop_when_connected(self):

        conn_before = self.db._connection
        self.db._ensure_connection()
        self.assertIs(self.db._connection, conn_before)


if __name__ == "__main__":
    unittest.main()
