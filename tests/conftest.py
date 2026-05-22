"""Shared pytest fixtures for browser doubles, config stubs, and DTO state.

Fixtures here keep service tests focused on orchestration boundaries without
starting real browser sessions or touching production configuration.
"""

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
    # Default selector lookups to empty maps so tests opt into required config.
    config = MagicMock(spec=Config)
    config.get.return_value = {}
    return config


@pytest.fixture
def sample_dto():
    # Pre-populate fields shared by scraper orchestration tests.
    return ProductDTO(
        code="TEST-001",
        brand="Razer",
        url="https://www.akakce.com/test-product.html",
    )


@pytest.fixture
def empty_dto():
    # Keep a minimal DTO for validation and fallback-path tests.
    return ProductDTO(code="EMPTY-001")
