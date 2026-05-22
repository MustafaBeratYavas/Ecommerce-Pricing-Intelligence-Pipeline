"""Timing helpers for paced browser interactions.

The scraping pipeline uses bounded jitter to reduce brittle back-to-back UI
actions while keeping tests able to patch timing behavior cleanly.
"""

import random
import time


def random_sleep(min_seconds: float, max_seconds: float) -> None:
    # Use bounded jitter so scripted interactions are less bursty.
    time.sleep(random.uniform(min_seconds, max_seconds))
