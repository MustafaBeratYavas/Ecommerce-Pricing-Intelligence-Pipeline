"""Unit tests for browser lifecycle and configuration-backed startup."""

import unittest
from unittest.mock import MagicMock, patch

from src.engine.browser import BrowserEngine


class TestBrowserEngine(unittest.TestCase):
    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_init(self, mock_logger, mock_config):
        engine = BrowserEngine()
        self.assertIsNone(engine.driver)

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_context_manager_enter_calls_start(self, mock_logger, mock_config):
        engine = BrowserEngine()
        engine.start = MagicMock()
        engine.driver = MagicMock()
        # The context boundary should hand callers an initialized driver.
        result = engine.__enter__()
        engine.start.assert_called_once()
        self.assertEqual(result, engine.driver)

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_context_manager_exit_calls_stop(self, mock_logger, mock_config):
        engine = BrowserEngine()
        engine.stop = MagicMock()
        # Exiting the context should always release the cached driver.
        engine.__exit__(None, None, None)
        engine.stop.assert_called_once()

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_start_skips_if_driver_exists(self, mock_logger, mock_config):
        engine = BrowserEngine()
        engine.driver = MagicMock()
        engine.start()
        self.assertIsNotNone(engine.driver)

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_stop_quits_driver(self, mock_logger, mock_config):
        engine = BrowserEngine()
        mock_driver = MagicMock()
        engine.driver = mock_driver
        engine.logger = MagicMock()

        engine.stop()

        mock_driver.quit.assert_called_once()
        self.assertIsNone(engine.driver)

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_stop_handles_quit_error(self, mock_logger, mock_config):
        engine = BrowserEngine()
        mock_driver = MagicMock()
        mock_driver.quit.side_effect = Exception("quit failed")
        engine.driver = mock_driver
        engine.logger = MagicMock()

        engine.stop()

        self.assertIsNone(engine.driver)

    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_stop_no_driver(self, mock_logger, mock_config):
        engine = BrowserEngine()
        engine.driver = None
        engine.logger = MagicMock()
        engine.stop()
        self.assertIsNone(engine.driver)

    @patch("src.engine.browser.Driver")
    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_start_initializes_driver(self, mock_logger, mock_config, mock_driver_cls):
        engine = BrowserEngine()
        engine.logger = MagicMock()

        mock_config_instance = MagicMock()
        engine.config = mock_config_instance
        engine._prepare_user_data_dir = MagicMock()
        mock_config_instance.get.side_effect = lambda *a, **kw: {
            ("browser", "headless"): True,
            ("browser", "window_size"): "1920,1080",
            ("browser", "page_load_timeout"): 30,
            ("browser", "user_agent"): None,
            ("browser", "user_data_dir"): "data/chrome_profile",
            ("urls", "base"): "https://www.akakce.com",
            ("browser", "reconnect_time"): 6,
            ("browser", "captcha_auto_click"): False,
        }.get(a, kw.get("default"))

        mock_driver_instance = MagicMock()
        mock_driver_cls.return_value = mock_driver_instance

        # Startup should translate config values into SeleniumBase arguments.
        engine.start()

        mock_driver_cls.assert_called_once()
        driver_kwargs = mock_driver_cls.call_args.kwargs
        self.assertTrue(driver_kwargs["headless2"])
        self.assertTrue(driver_kwargs["no_sandbox"])
        self.assertTrue(driver_kwargs["disable_gpu"])
        engine._prepare_user_data_dir.assert_called_once()
        self.assertEqual(engine.driver, mock_driver_instance)

    @patch("src.engine.browser.Driver")
    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_start_sets_user_agent_before_initial_navigation(
        self, mock_logger, mock_config, mock_driver_cls
    ):
        engine = BrowserEngine()
        engine.logger = MagicMock()

        mock_config_instance = MagicMock()
        engine.config = mock_config_instance
        engine._prepare_user_data_dir = MagicMock()
        mock_config_instance.get.side_effect = lambda *a, **kw: {
            ("browser", "headless"): True,
            ("browser", "page_load_timeout"): 30,
            ("browser", "user_agent"): "Custom UA",
            ("browser", "user_data_dir"): "data/chrome_profile",
            ("browser", "profile_name"): "Profile 1",
            ("urls", "base"): "https://www.akakce.com",
            ("browser", "reconnect_time"): 6,
            ("browser", "captcha_auto_click"): False,
        }.get(a, kw.get("default"))

        mock_driver_instance = MagicMock()
        mock_driver_cls.return_value = mock_driver_instance

        engine.start()

        call_names = [call[0] for call in mock_driver_instance.method_calls]
        self.assertLess(
            call_names.index("execute_cdp_cmd"),
            call_names.index("uc_open_with_reconnect"),
        )
        mock_driver_instance.execute_cdp_cmd.assert_any_call(
            "Network.setUserAgentOverride", {"userAgent": "Custom UA"}
        )

    @patch("src.engine.browser.Driver")
    @patch("src.engine.browser.Config")
    @patch("src.engine.browser.Logger")
    def test_start_failure_calls_stop(self, mock_logger, mock_config, mock_driver_cls):
        engine = BrowserEngine()
        engine.logger = MagicMock()
        engine.config = MagicMock()
        engine.config.get.side_effect = Exception("config fail")

        # Failed startup should not leave a stale driver handle behind.
        with self.assertRaises(Exception):
            engine.start()

        self.assertIsNone(engine.driver)


if __name__ == "__main__":
    unittest.main()
