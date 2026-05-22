"""Own SQLite persistence, queue state, and snapshot replacement.

DatabaseService is the database boundary for the scraping pipeline. It manages
schema compatibility, run-scoped identifiers, queue state transitions, and
validated product-offer writes while hiding SQLite transaction details from
scraper orchestration.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional

from src.core.config import Config
from src.core.exceptions import DatabaseError
from src.core.logger import Logger
from src.definitions import ROOT_DIR
from src.utils import string_utils


class DatabaseService:
    _instance: Optional["DatabaseService"] = None

    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            brand           TEXT,
            product_code    TEXT    NOT NULL,
            product_category TEXT,
            product_name    TEXT,
            marketplace     TEXT,
            price           REAL,
            product_url     TEXT,
            scraped_at      TEXT    NOT NULL,
            source          TEXT    NOT NULL DEFAULT 'unknown',
            match_verified  INTEGER NOT NULL DEFAULT 1,
            run_id          TEXT
        );
    """

    _CREATE_TARGETS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS target_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
            error_count INTEGER DEFAULT 0 CHECK (error_count >= 0),
            last_scraped_at TEXT
        );
    """

    _CREATE_INDEX_SQL = [
        """
        CREATE INDEX IF NOT EXISTS idx_products_code_scraped_at
        ON products (product_code, scraped_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_products_product_url
        ON products (product_url)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_products_run_id
        ON products (run_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_target_products_status_id
        ON target_products (status, id)
        """,
    ]

    _INSERT_SQL = """
        INSERT INTO products
            (brand, product_code, product_category, product_name,
             marketplace, price, product_url, scraped_at,
             source, match_verified, run_id)
        VALUES
            (:brand, :product_code, :product_category, :product_name,
             :marketplace, :price, :product_url, :scraped_at,
             :source, :match_verified, :run_id);
    """

    _PRODUCT_COLUMNS = {
        "brand",
        "product_code",
        "product_category",
        "product_name",
        "marketplace",
        "price",
        "product_url",
        "scraped_at",
        "source",
        "match_verified",
        "run_id",
    }
    _VALID_TARGET_STATUSES = {"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"}

    def __new__(cls) -> "DatabaseService":
        # Reuse one service per process so queue and run metadata stay consistent.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return

        self.logger = Logger.get_logger(__name__)
        self.config = Config()
        self._run_id = self._new_run_id()
        self._snapshot_replacement_min_ratio = self._config_float(
            (
                "database",
                "snapshot_replacement_min_ratio",
            ),
            0.5,
        )

        db_rel_path = self.config.get("paths", "database", default="data/scraper.db")
        self._db_path = os.path.join(ROOT_DIR, db_rel_path)

        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

        self._connection: sqlite3.Connection | None = None
        self._connect()
        self._initialised = True

    def _connect(self) -> None:
        # Open the connection and migrate local warehouses before runtime writes.
        try:
            connect_timeout = self._config_float(
                ("database", "connect_timeout_seconds"), 30
            )
            busy_timeout_ms = self._config_int(("database", "busy_timeout_ms"), 30000)
            self._connection = sqlite3.connect(self._db_path, timeout=connect_timeout)
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA foreign_keys=ON;")
            self._connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
            self._connection.execute(self._CREATE_TABLE_SQL)
            self._connection.execute(self._CREATE_TARGETS_TABLE_SQL)
            self._ensure_schema()
            self._connection.commit()
            self.logger.info(f"Database connected: {self._db_path}")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to initialise database: {exc}") from exc

    def _config_float(self, keys: tuple[str, ...], default: float) -> float:
        try:
            return float(self.config.get(*keys, default=default))
        except (TypeError, ValueError):
            return default

    def _config_int(self, keys: tuple[str, ...], default: int) -> int:
        try:
            return int(self.config.get(*keys, default=default))
        except (TypeError, ValueError):
            return default

    def _ensure_schema(self) -> None:
        # Keep existing local warehouses compatible with the current row contract.
        assert self._connection is not None, "Database connection is not initialised"
        existing_columns = self._get_table_columns("products")
        migrations = {
            "source": "ALTER TABLE products ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'",
            "match_verified": (
                "ALTER TABLE products "
                "ADD COLUMN match_verified INTEGER NOT NULL DEFAULT 1"
            ),
            "run_id": "ALTER TABLE products ADD COLUMN run_id TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing_columns:
                self._connection.execute(statement)

        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        assert self._connection is not None, "Database connection is not initialised"
        for statement in self._CREATE_INDEX_SQL:
            self._connection.execute(statement)

    def _get_table_columns(self, table_name: str) -> set[str]:
        assert self._connection is not None, "Database connection is not initialised"
        cursor = self._connection.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def _ensure_connection(self) -> None:
        # Reconnect closed singletons so tests and sequential runs stay isolated.
        if self._connection is None:
            self.logger.info("Reconnecting to database (Singleton recovery)...")
            self._run_id = self._new_run_id()
            self._connect()

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the active connection, raising if unexpectedly None."""
        assert self._connection is not None, "Database connection is not initialised"
        return self._connection

    def __enter__(self) -> "DatabaseService":
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        # Clear the cached handle so the singleton can reconnect cleanly later.
        if self._connection:
            try:
                self._connection.close()
                self.logger.info("Database connection closed.")
            except sqlite3.Error as exc:
                self.logger.warning(f"Error closing database: {exc}")
            finally:
                self._connection = None

    def insert_product(self, row: dict) -> None:
        # Insert one normalized row through the same validation path as batches.
        self._ensure_connection()
        normalized_row = self._normalize_product_row(row)
        self._validate_normalized_product_rows([normalized_row])
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(self._INSERT_SQL, normalized_row)
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to insert product: {exc}") from exc

    def insert_products(self, rows: list[dict]) -> None:
        # Insert a batch in one transaction so a product snapshot is all-or-nothing.
        if not rows:
            return

        self._ensure_connection()
        normalized_rows = [self._normalize_product_row(row) for row in rows]
        self._validate_normalized_product_rows(normalized_rows)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.executemany(self._INSERT_SQL, normalized_rows)
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to insert product batch: {exc}") from exc

    def replace_products_snapshot(self, rows: list[dict]) -> None:
        # Replace same-day snapshots only after the incoming batch passes safeguards.
        if not rows:
            return

        self._ensure_connection()
        normalized_rows = [self._normalize_product_row(row) for row in rows]
        self._validate_normalized_product_rows(normalized_rows)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            snapshot_keys: set[tuple[str, str]] = set()
            for row in normalized_rows:
                product_code = str(row.get("product_code") or "").strip()
                scraped_at = str(row.get("scraped_at") or "").strip()
                if product_code and scraped_at:
                    snapshot_keys.add((product_code, scraped_at))

            self._validate_snapshot_replacement(normalized_rows, snapshot_keys)

            for product_code, scraped_at in snapshot_keys:
                self.conn.execute(
                    """
                    DELETE FROM products
                    WHERE product_code = ?
                      AND scraped_at = ?
                    """,
                    (product_code, scraped_at),
                )

            self.conn.executemany(self._INSERT_SQL, normalized_rows)
            self.conn.commit()
        except DatabaseError:
            self.conn.rollback()
            raise
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(
                f"Failed to replace product snapshot batch: {exc}"
            ) from exc

    def _validate_normalized_product_rows(self, rows: list[dict]) -> None:
        for index, row in enumerate(rows, start=1):
            product_code = str(row.get("product_code") or "").strip()
            if not product_code:
                raise DatabaseError(f"Missing product_code in product row {index}")

            scraped_at = str(row.get("scraped_at") or "").strip()
            if not scraped_at:
                raise DatabaseError(f"Missing scraped_at in product row {index}")

            if not (row.get("product_name") or row.get("product_url")):
                raise DatabaseError(f"Missing product identity in product row {index}")

            if int(row.get("match_verified") or 0) != 1:
                raise DatabaseError(f"Unverified product row rejected: {product_code}")

            marketplace = str(row.get("marketplace") or "").strip()
            if not marketplace:
                raise DatabaseError(f"Missing marketplace in product row {index}")

            try:
                price = float(row.get("price") or 0)
            except (TypeError, ValueError) as exc:
                raise DatabaseError(f"Invalid price in product row {index}") from exc

            if price <= 0:
                raise DatabaseError(f"Non-positive price in product row {index}")

    def _validate_snapshot_replacement(
        self,
        rows: list[dict],
        snapshot_keys: set[tuple[str, str]],
    ) -> None:
        for product_code, scraped_at in snapshot_keys:
            existing_count = self._count_active_snapshot_rows(product_code, scraped_at)
            if existing_count < 4:
                continue

            new_count = sum(
                1
                for row in rows
                if row.get("product_code") == product_code
                and row.get("scraped_at") == scraped_at
            )
            minimum_expected = max(
                1,
                int(existing_count * self._snapshot_replacement_min_ratio),
            )
            if new_count < minimum_expected:
                raise DatabaseError(
                    "Refusing to replace a richer same-day snapshot for "
                    f"{product_code} on {scraped_at}: existing={existing_count}, "
                    f"new={new_count}, minimum_expected={minimum_expected}"
                )

    def _count_active_snapshot_rows(
        self, product_code: object, scraped_at: object
    ) -> int:
        cursor = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM products
            WHERE product_code = ?
              AND scraped_at = ?
              AND match_verified = 1
              AND price IS NOT NULL
              AND price > 0
              AND marketplace IS NOT NULL
              AND TRIM(marketplace) <> ''
            """,
            (product_code, scraped_at),
        )
        return int(cursor.fetchone()[0])

    def _normalize_product_row(self, row: dict) -> dict:
        normalized = {column: row.get(column) for column in self._PRODUCT_COLUMNS}
        normalized["source"] = normalized.get("source") or "unknown"
        normalized["match_verified"] = self._coerce_match_verified(
            normalized.get("match_verified")
        )
        normalized["run_id"] = normalized.get("run_id") or self._run_id
        return normalized

    @staticmethod
    def _coerce_match_verified(value: object) -> int:
        if value is None:
            return 1
        if isinstance(value, str):
            return 0 if value.strip().lower() in {"0", "false", "no"} else 1
        return int(bool(value))

    def add_target_product(self, code: str) -> None:
        # Enqueue once; repeated seeds should not duplicate queue work.
        self._ensure_connection()
        try:
            sql = "INSERT OR IGNORE INTO target_products (product_code) VALUES (?)"
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(sql, (code,))
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to seed target code: {exc}") from exc

    def sync_target_product(self, code: str) -> None:
        # Requeue existing seed targets so each seeded run can refresh them.
        self._ensure_connection()
        try:
            sql = """
                INSERT INTO target_products
                    (product_code, status, error_count, last_scraped_at)
                VALUES
                    (?, 'PENDING', 0, NULL)
                ON CONFLICT(product_code) DO UPDATE SET
                    status = 'PENDING',
                    error_count = 0,
                    last_scraped_at = NULL
            """
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(sql, (code,))
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to synchronize target code: {exc}") from exc

    def get_pending_product(self) -> dict | None:
        # Claim one pending target atomically from the local queue.
        self._ensure_connection()
        try:
            cursor = self.conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                SELECT id, product_code, error_count
                FROM target_products
                WHERE status = 'PENDING'
                ORDER BY id ASC LIMIT 1
                """
            )
            row = cursor.fetchone()

            if not row:
                self.conn.commit()
                return None

            t_id, code, err_count = row

            cursor.execute(
                """
                UPDATE target_products
                SET status = 'IN_PROGRESS'
                WHERE id = ? AND status = 'PENDING'
                """,
                (t_id,),
            )
            if cursor.rowcount != 1:
                self.conn.rollback()
                return None

            self.conn.commit()
            return {"id": t_id, "product_code": code, "error_count": err_count}

        except sqlite3.Error as exc:
            self.conn.rollback()
            self.logger.error(f"Error fetching pending product: {exc}")
            raise DatabaseError(f"Queue lock error: {exc}") from exc

    def get_target_count(self) -> int:
        # Keep queue sizing stable for progress logging.
        self._ensure_connection()
        try:
            cursor = self.conn.execute("SELECT COUNT(*) FROM target_products")
            return int(cursor.fetchone()[0])
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to count target products: {exc}") from exc

    def get_target_position(self, target_id: int) -> int:
        # Use the persisted row order as the stable human-facing position.
        self._ensure_connection()
        try:
            cursor = self.conn.execute(
                """
                SELECT COUNT(*)
                FROM target_products
                WHERE id <= ?
                """,
                (target_id,),
            )
            return int(cursor.fetchone()[0])
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to calculate target position: {exc}") from exc

    def reset_stale_in_progress(self) -> int:
        # Recover in-progress items from interrupted runs before new work starts.
        self._ensure_connection()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            cursor = self.conn.execute(
                """
                UPDATE target_products
                SET status = 'PENDING'
                WHERE status = 'IN_PROGRESS'
                """
            )
            self.conn.commit()
            return cursor.rowcount
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to reset stale queue items: {exc}") from exc

    def update_target_status(
        self, target_id: int, status: str, error_count: int = 0
    ) -> None:
        # Keep retry accounting and last-processed metadata in one update.
        if status not in self._VALID_TARGET_STATUSES:
            raise DatabaseError(f"Invalid target status: {status}")

        self._ensure_connection()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            sql = """
                UPDATE target_products
                SET status = ?, error_count = ?, last_scraped_at = ?
                WHERE id = ?
            """
            self.conn.execute(sql, (status, error_count, now, target_id))
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise DatabaseError(f"Failed to update target status: {exc}") from exc

    def get_product_codes_for_url(self, url: str) -> set[str]:
        # Use persisted URL-code links to avoid reusing one page for another SKU.
        self._ensure_connection()
        canonical = self._canonicalize_url(url)
        if not canonical:
            return set()

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT product_code, product_url
                FROM products
                WHERE product_url IS NOT NULL
                """
            )
            return {
                product_code
                for product_code, product_url in cursor.fetchall()
                if self._canonicalize_url(product_url) == canonical
            }
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to query product codes by URL: {exc}") from exc

    @staticmethod
    def _canonicalize_url(url: str | None) -> str:
        return string_utils.canonicalize_url(url)

    @staticmethod
    def _new_run_id() -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S%f")

    @classmethod
    def reset_instance(cls) -> None:
        # Reset singleton state for isolated tests.
        cls._instance = None
