"""Queue processor that scrapes products and persists valid offer rows."""

from src.core.config import Config
from src.core.exceptions import DatabaseError, DataQualityError
from src.core.logger import Logger
from src.models.product import ProductDTO
from src.services.database import DatabaseService
from src.services.scraper_service import ScraperService


class BatchProcessor:
    def __init__(
        self,
        database: DatabaseService,
        scraper: ScraperService,
    ) -> None:
        self.database = database
        self.scraper = scraper
        self.config = Config()
        self.logger = Logger.get_logger(__name__)

    def run(self, max_retries: int = 3) -> None:
        # Process queued product codes sequentially to keep browser state predictable.
        self.logger.info("Starting ETL pipeline using Database Task Queue.")
        if hasattr(self.database, "reset_stale_in_progress"):
            recovered = self.database.reset_stale_in_progress()
            if recovered:
                self.logger.warning(f"Recovered {recovered} stale in-progress task(s).")

        success_count = 0
        failed_attempt_count = 0
        failed_product_count = 0
        queue_total = self._get_queue_total()

        while True:
            target = self.database.get_pending_product()
            if not target:
                self.logger.info("No pending tasks found. Queue is empty.")
                break

            t_id = target["id"]
            code = target["product_code"]
            err_count = target["error_count"]
            attempt = err_count + 1
            log_prefix = self._format_log_prefix(
                self._get_queue_position(t_id),
                queue_total,
                attempt,
                max_retries,
            )

            self.logger.info(f"{log_prefix} Processing: {code}")

            try:
                dto = ProductDTO(
                    code=code,
                    brand=self.config.get(
                        "scraping", "default_brand", default=ProductDTO.brand
                    ),
                )
                processed = self.scraper.process_product(dto)
                if isinstance(processed, ProductDTO):
                    dto = processed

                rows = dto.to_db_rows()
                self._validate_rows(code, rows)
                self.database.replace_products_snapshot(rows)

                self.logger.info(f"{log_prefix} {code} - {len(rows)} row(s) saved.")
                self.database.update_target_status(t_id, "COMPLETED", err_count)
                success_count += 1

            except DatabaseError as exc:
                # Database failures are treated as retryable because writes can be transient.
                self.logger.error(f"{log_prefix} {code} - DB error: {exc}")
                self.database.update_target_status(t_id, "PENDING", err_count + 1)
                failed_attempt_count += 1
            except Exception as exc:
                # Scraper failures retry until the target reaches its configured budget.
                self.logger.error(f"{log_prefix} {code} - Scraper error: {exc}")
                new_err_count = err_count + 1
                if new_err_count >= max_retries:
                    self.logger.warning(
                        f"{log_prefix} {code} - Max retries reached. Marking FAILED."
                    )
                    self.database.update_target_status(t_id, "FAILED", new_err_count)
                    failed_product_count += 1
                else:
                    self.database.update_target_status(t_id, "PENDING", new_err_count)
                failed_attempt_count += 1

        self.logger.info(
            f"Queue processing completed. "
            f"Completed products: {success_count}, "
            f"Failed products: {failed_product_count}, "
            f"Failed attempts: {failed_attempt_count}"
        )

    @staticmethod
    def _validate_rows(code: str, rows: list[dict]) -> None:
        if not rows:
            raise DataQualityError(f"No rows produced for {code}")

        for index, row in enumerate(rows, start=1):
            if not str(row.get("product_code") or "").strip():
                raise DataQualityError(f"Missing product code for {code} row {index}")

            if not (row.get("product_name") or row.get("product_url")):
                raise DataQualityError(
                    f"Missing product identity for {code} row {index}"
                )

            if int(bool(row.get("match_verified"))) != 1:
                raise DataQualityError(
                    f"Unverified product match for {code} row {index}"
                )

            marketplace = str(row.get("marketplace") or "").strip()
            if not marketplace:
                raise DataQualityError(f"Missing marketplace for {code} row {index}")

            try:
                price = float(row.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0

            if price <= 0:
                raise DataQualityError(
                    f"Missing valid price data for {code} row {index}"
                )

    def _get_queue_total(self) -> int | None:
        try:
            value = self.database.get_target_count()
        except (AttributeError, DatabaseError):
            return None
        return value if isinstance(value, int) and value > 0 else None

    def _get_queue_position(self, target_id: int) -> int:
        try:
            value = self.database.get_target_position(target_id)
        except (AttributeError, DatabaseError):
            value = target_id
        return value if isinstance(value, int) and value > 0 else target_id

    @staticmethod
    def _format_log_prefix(
        position: int,
        total: int | None,
        attempt: int,
        max_retries: int,
    ) -> str:
        product_part = f"{position}/{total}" if total else str(position)
        return f"[{product_part} | attempt {attempt}/{max_retries}]"
