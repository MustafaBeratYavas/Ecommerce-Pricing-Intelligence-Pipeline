"""Regression checks for the curated default seed product universe."""

from pathlib import Path

from src.definitions import ROOT_DIR


def test_product_codes_inventory_is_mouse_and_headset_only():
    codes = [
        line.strip()
        for line in (Path(ROOT_DIR) / "product_codes.txt").read_text().splitlines()
        if line.strip()
    ]

    assert len(codes) == 50
    assert len(set(codes)) == 50
    assert sum(code.startswith("RZ01-") for code in codes) == 25
    assert sum(code.startswith("RZ04-") for code in codes) == 25
    assert not any(code.startswith("RZ03-") for code in codes)
    assert not any(code.startswith("RZ07-") for code in codes)
