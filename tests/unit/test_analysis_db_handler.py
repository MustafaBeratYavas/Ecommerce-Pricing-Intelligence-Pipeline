"""Unit tests for read-only analytics database access and schema tolerance."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from src.analysis.core.db_handler import DBHandler


def _config_for_database(path, busy_timeout="2500"):
    config = MagicMock()

    def get(*keys, default=None):
        if keys == ("paths", "database"):
            return str(path)
        if keys == ("database", "analysis_busy_timeout_ms"):
            return busy_timeout
        return default

    config.get.side_effect = get
    return config


def _create_products_table(path, optional_columns: str = ""):
    connection = sqlite3.connect(path)
    optional_sql = f", {optional_columns}" if optional_columns else ""
    connection.execute(
        f"""
        CREATE TABLE products (
            id INTEGER,
            brand TEXT,
            product_code TEXT,
            product_category TEXT,
            product_name TEXT,
            marketplace TEXT,
            price REAL,
            product_url TEXT,
            scraped_at TEXT
            {optional_sql}
        )
        """
    )
    return connection


def test_db_handler_rejects_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        DBHandler(_config_for_database(tmp_path / "missing.db"))


def test_config_int_falls_back_for_invalid_values(tmp_path):
    db_path = tmp_path / "scraper.db"
    connection = _create_products_table(db_path)
    connection.close()

    handler = DBHandler(_config_for_database(db_path, busy_timeout="not-an-int"))

    assert handler.busy_timeout_ms == 5000


def test_read_only_connection_prevents_writes(tmp_path):
    db_path = tmp_path / "scraper.db"
    connection = _create_products_table(db_path)
    connection.close()
    handler = DBHandler(_config_for_database(db_path))

    with handler.read_only_connection() as read_connection:
        timeout = read_connection.execute("PRAGMA busy_timeout").fetchone()[0]

        assert timeout == 2500
        with pytest.raises(sqlite3.OperationalError):
            read_connection.execute("INSERT INTO products (id) VALUES (1)")


def test_fetch_products_includes_available_optional_columns(tmp_path):
    db_path = tmp_path / "scraper.db"
    connection = _create_products_table(
        db_path,
        "source TEXT, match_verified INTEGER, run_id TEXT",
    )
    connection.execute(
        """
        INSERT INTO products (
            id,
            brand,
            product_code,
            product_category,
            product_name,
            marketplace,
            price,
            product_url,
            scraped_at,
            source,
            match_verified,
            run_id
        )
        VALUES (1, 'Razer', 'RZ01-001', 'Mouse', 'Mouse X', 'Store', 100.0,
                'https://example.test/product', '2026-05-14T00:00:00',
                'direct', 1, 'run-1')
        """
    )
    connection.commit()
    connection.close()
    handler = DBHandler(_config_for_database(db_path))

    products = handler.fetch_products()

    assert products.loc[0, "product_code"] == "RZ01-001"
    assert products.loc[0, "source"] == "direct"
    assert products.loc[0, "match_verified"] == 1
    assert products.loc[0, "run_id"] == "run-1"
