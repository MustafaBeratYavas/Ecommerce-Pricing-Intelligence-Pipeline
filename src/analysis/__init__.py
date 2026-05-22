"""Analytics pipeline for transforming scraper output into strategic reports.

The package reads validated warehouse snapshots, derives comparison metrics,
renders chart artifacts, and writes markdown reporting outputs. It should not
mutate scraper queue state or product persistence tables.
"""
