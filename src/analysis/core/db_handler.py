"""Read-only access layer for the SQLite products warehouse."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

import pandas as pd

from src.core.config import Config
from src.definitions import ROOT_DIR


class DBHandler:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        # Resolve the warehouse path from config while keeping analysis read-only.
        db_relative_path = self.config.get(
            "paths", "database", default="database/scraper.db"
        )
        self.busy_timeout_ms = self._config_int(
            ("database", "analysis_busy_timeout_ms"), 5000
        )
        self.db_path = os.path.join(ROOT_DIR, db_relative_path)

        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"SQLite database not found: {self.db_path}")

        self._uri = f"file:{self.db_path}?mode=ro"

    @contextmanager
    def read_only_connection(self) -> Generator[sqlite3.Connection, None, None]:
        # Open SQLite in URI read-only mode to protect the scraper warehouse.
        connection = sqlite3.connect(self._uri, uri=True)
        try:
            connection.execute("PRAGMA query_only = ON;")
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms};")
            yield connection
        finally:
            connection.close()

    def _config_int(self, keys: tuple[str, ...], default: int) -> int:
        try:
            return int(self.config.get(*keys, default=default))
        except (TypeError, ValueError):
            return default

    def fetch_products(self) -> pd.DataFrame:
        # Select optional migration columns only when the local warehouse has them.
        with self.read_only_connection() as connection:
            columns = self._resolve_product_columns(connection)
            query = f"SELECT {', '.join(columns)} FROM products"
            return pd.read_sql_query(query, connection)

    @staticmethod
    def _resolve_product_columns(connection: sqlite3.Connection) -> list[str]:
        # Keep compatibility with older databases created before optional fields.
        required_columns = [
            "id",
            "brand",
            "product_code",
            "product_category",
            "product_name",
            "marketplace",
            "price",
            "product_url",
            "scraped_at",
        ]
        optional_columns = ["source", "match_verified", "run_id"]
        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(products)")
        }
        return required_columns + [
            column for column in optional_columns if column in existing_columns
        ]
