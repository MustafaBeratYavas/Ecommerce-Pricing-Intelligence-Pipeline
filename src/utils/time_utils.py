"""Randomized sleep helpers used to stabilize scraper cadence."""

import random
import time


def random_sleep(min_seconds: float, max_seconds: float) -> None:
    # Use bounded jitter so scripted interactions are less bursty.
    time.sleep(random.uniform(min_seconds, max_seconds))
