"""Integration coverage for launching the live browser engine."""

import os
import unittest

from src.engine.browser import BrowserEngine


@unittest.skipUnless(
    os.getenv("RUN_LIVE_BROWSER_TESTS") == "1",
    "Set RUN_LIVE_BROWSER_TESTS=1 to run live browser integration tests.",
)
class TestBrowser(unittest.TestCase):
    def test_browser_launch(self):
        try:
            with BrowserEngine() as driver:
                driver.get("https://www.google.com")
                # Confirm the browser can render a live external page.
                self.assertIn("Google", driver.title)
        except Exception as e:
            self.fail(f"Browser launch failed: {e}")


if __name__ == "__main__":
    unittest.main()
