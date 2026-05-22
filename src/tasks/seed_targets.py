"""Seed product targets into the scraper queue from a text file.

The task normalizes and deduplicates manual product-code lists, then delegates
queue insertion and requeue semantics to DatabaseService. It does not scrape or
validate product pages.
"""

import argparse
import os
import sys

# Support direct source-tree execution while preserving absolute package imports.
if __name__ == "__main__" and __package__ is None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, root_dir)

from src.services.database import DatabaseService


def seed_from_file(file_path: str) -> None:
    # Normalize the manual list before touching persistent queue state.
    if not os.path.exists(file_path):
        print(f"Error: Input file not found at '{file_path}'")
        sys.exit(1)

    try:
        with open(file_path, encoding="utf-8") as f:
            # Ignore optional slash suffixes sometimes used in manual lists.
            codes = [line.split("/")[0].strip() for line in f if line.strip()]

        # Preserve source order while removing duplicate codes.
        seen = set()
        unique_codes = []
        for c in codes:
            if c and c not in seen:
                seen.add(c)
                unique_codes.append(c)

        if not unique_codes:
            print("Warning: No valid product codes found in the provided file.")
            return

        print(f"Read {len(unique_codes)} unique product codes from {file_path}")

        # Persist the cleaned list and requeue existing targets for a fresh run.
        with DatabaseService() as db:
            synchronized = 0
            for code in unique_codes:
                try:
                    db.sync_target_product(code)
                    synchronized += 1
                except Exception as e:
                    print(f"  [ERROR] Failed to synchronize '{code}': {e}")

            print(
                "Successfully synchronized "
                f"{synchronized} product(s) to the database task queue."
            )

    except Exception as e:
        print(f"Fatal error during seeding: {e}")
        sys.exit(1)


def main():
    # Keep CLI parsing separate from queue mutation for testability.
    parser = argparse.ArgumentParser(
        description="E-Commerce Pricing Intelligence Pipeline - Database Seeding Utility",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--file",
        "-f",
        required=True,
        help="Path to the .txt file containing product codes (one per line)",
    )

    args = parser.parse_args()
    seed_from_file(args.file)


if __name__ == "__main__":
    main()
