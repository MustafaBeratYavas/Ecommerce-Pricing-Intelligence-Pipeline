"""Shared pytest fixtures for driver mocks, config stubs, and DTO instances."""

from unittest.mock import MagicMock

import pytest

from src.core.config import Config
from src.models.product import ProductDTO


@pytest.fixture
def mock_driver():
    # Provide a minimal driver double with URL and page-source defaults.
    driver = MagicMock()
    driver.current_url = "https://www.akakce.com"
    driver.page_source = "<html></html>"
    return driver


@pytest.fixture
def mock_config():
    # Return empty dictionaries for selector lookups unless a test overrides them.
    config = MagicMock(spec=Config)
    config.get.return_value = {}
    return config


@pytest.fixture
def sample_dto():
    # Pre-populate the fields used by end-to-end scraper service tests.
    return ProductDTO(
        code="TEST-001",
        brand="Razer",
        url="https://www.akakce.com/test-product.html",
    )


@pytest.fixture
def empty_dto():
    # Keep a minimal DTO for validation and fallback-path tests.
    return ProductDTO(code="EMPTY-001")
