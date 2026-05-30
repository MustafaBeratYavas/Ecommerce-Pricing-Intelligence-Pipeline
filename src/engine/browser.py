"""Manage the SeleniumBase browser lifecycle for scraper runs.

BrowserEngine translates configuration-backed browser settings into one driver
session and guarantees shutdown through a context-manager boundary. It does not
perform scraping or product resolution itself.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from seleniumbase import Driver

from src.core.config import Config
from src.core.logger import Logger
from src.definitions import ROOT_DIR


class BrowserEngine:
    def __init__(self) -> None:
        self.config = Config()
        self.logger = Logger.get_logger(__name__)
        self.driver: Any = None

    def __enter__(self) -> Any:
        # Start the driver at the context boundary so callers get a ready handle.
        self.start()
        assert self.driver is not None, (
            "BrowserEngine.start() failed to initialise the driver"
        )
        return self.driver

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.stop()

    def start(self) -> None:
        # Launch one configured browser session per engine instance.
        if self.driver:
            return

        headless = self.config.get("browser", "headless", default=False)
        page_load_timeout = self.config.get("browser", "page_load_timeout", default=30)
        user_agent = self.config.get("browser", "user_agent")

        user_data_rel = self.config.get(
            "browser", "user_data_dir", default="data/chrome_profile"
        )
        user_data_abs = os.path.join(ROOT_DIR, user_data_rel)
        profile_name = self.config.get("browser", "profile_name", default="Profile 1")

        try:
            self.logger.info("Initializing browser engine (UC Mode)...")
            self.logger.info(f"Profile path: {user_data_abs}")
            self._prepare_user_data_dir(user_data_abs, profile_name)

            chromium_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-popup-blocking",
            ]
            if headless:
                chromium_args.extend(["--disable-gpu", "--window-size=1920,1080"])
            else:
                chromium_args.append("--start-maximized")
            if profile_name:
                chromium_args.append(f"--profile-directory={profile_name}")

            driver_kwargs: dict[str, Any] = {
                "uc": True,
                "chromium_arg": chromium_args,
                "user_data_dir": user_data_abs,
                "no_sandbox": True,
                "disable_gpu": bool(headless),
            }
            if headless:
                driver_kwargs["headless2"] = True
            else:
                driver_kwargs["headed"] = True

            self.driver = Driver(
                **driver_kwargs,
            )

            if user_agent:
                self.driver.execute_cdp_cmd("Network.enable", {})
                self.driver.execute_cdp_cmd(
                    "Network.setUserAgentOverride", {"userAgent": user_agent}
                )

            self.driver.set_page_load_timeout(page_load_timeout)

            base_url = self.config.get("urls", "base", default="https://www.akakce.com")
            reconnect_time = self.config.get("browser", "reconnect_time", default=6)
            try:
                self.driver.uc_open_with_reconnect(
                    base_url, reconnect_time=reconnect_time
                )  # type: ignore[attr-defined]
                self.logger.info("Initial page loaded with reconnect strategy.")
            except Exception as e:
                self.logger.warning(
                    f"Reconnect navigation failed, using direct get: {e}"
                )
                self.driver.get(base_url)

            captcha_enabled = self.config.get(
                "browser", "captcha_auto_click", default=True
            )
            if captcha_enabled:
                try:
                    self.driver.uc_gui_click_captcha()  # type: ignore[attr-defined]
                    self.logger.info("CAPTCHA auto-click attempted.")
                except Exception as e:
                    self.logger.debug(
                        f"CAPTCHA click skipped (none detected or failed): {e}"
                    )

            if not headless:
                self.driver.maximize_window()

            self.logger.info("Browser engine started successfully.")

        except Exception as e:
            self.logger.critical(f"Failed to start browser engine: {e}")
            self.stop()
            raise

    def _prepare_user_data_dir(self, user_data_abs: str, profile_name: str) -> None:
        user_data_path = Path(user_data_abs)
        user_data_path.mkdir(parents=True, exist_ok=True)
        if profile_name:
            (user_data_path / profile_name).mkdir(parents=True, exist_ok=True)

        for lock_name in ("SingletonCookie", "SingletonLock", "SingletonSocket"):
            lock_path = user_data_path / lock_name
            try:
                lock_path.unlink(missing_ok=True)
            except OSError as exc:
                self.logger.debug(
                    f"Could not remove Chrome profile lock {lock_path}: {exc}"
                )

    def stop(self) -> None:
        # Always clear the cached handle so failed shutdowns cannot be reused.
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Browser engine stopped.")
            except Exception as e:
                self.logger.warning(f"Error while stopping browser: {e}")
            finally:
                self.driver = None
