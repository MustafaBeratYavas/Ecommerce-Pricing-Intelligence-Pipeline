"""Application-specific exception hierarchy for runtime layers."""


class ScraperError(Exception):
    """Base type for pipeline-specific failures."""

    pass


class NetworkError(ScraperError):
    """Raised when navigation or element lookup fails due to network issues."""

    pass


class CaptchaError(ScraperError):
    """Raised when anti-bot challenges block progress."""

    pass


class ProductNotFound(ScraperError):
    """Raised when no product page can be resolved for a target code."""

    pass


class DataQualityError(ScraperError):
    """Raised when a resolved page does not meet the minimum data contract."""

    pass


class ConfigurationError(ScraperError):
    """Raised when required configuration is missing or invalid."""

    pass


class BrowserInitError(ScraperError):
    """Raised when the browser runtime cannot be started."""

    pass


class DatabaseError(ScraperError):
    """Raised when SQLite operations fail or the database is unavailable."""

    pass
