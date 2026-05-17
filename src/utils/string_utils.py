"""Convert raw scraper text into stable comparison and storage values."""

import re


def clean_price(price_text: str | None) -> float:
    # Normalize Turkish-formatted prices before numeric conversion.
    if not price_text:
        return 0.0

    # Remove currency tokens and whitespace noise.
    cleaned = (
        price_text.replace("TL", "")
        .replace("tl", "")
        .replace("â‚º", "")
        .replace("₺", "")
        .strip()
    )
    cleaned = re.sub(r"\s+", "", cleaned)

    # Translate local separators into a Python-friendly decimal representation.
    cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def clean_text(text: str | None) -> str:
    # Keep the marketplace label before any slash-delimited sub-seller suffix.
    if not text:
        return ""
    return text.split("/")[0].strip()


# Turkish-to-ASCII map used for tolerant text matching.
_TR_MAP = str.maketrans(
    {
        "ç": "c",
        "Ç": "C",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "Ö": "O",
        "ş": "s",
        "Ş": "S",
        "ü": "u",
        "Ü": "U",
    }
)


def to_ascii(text: str | None) -> str:
    # Transliterate Turkish characters without changing the original casing.
    if not text:
        return ""
    return text.translate(_TR_MAP)


def normalize_lookup_token(text: object) -> str:
    # Collapse product codes and titles into comparable alphanumeric tokens.
    if text is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", to_ascii(str(text)).lower())


def contains_lookup_token(candidate: object, token: object) -> bool:
    # Return True only when the normalized token appears in the candidate field.
    normalized_token = normalize_lookup_token(token)
    if not normalized_token:
        return False
    return normalized_token in normalize_lookup_token(candidate)


def contains_exact_lookup_token(candidate: object, token: object) -> bool:
    # Match SKU-like tokens exactly while tolerating separators such as hyphens.
    if candidate is None or token is None:
        return False

    groups = re.findall(r"[a-z0-9]+", to_ascii(str(token)).lower())
    if not groups:
        return False

    normalized_token = "".join(groups)
    candidate_text = to_ascii(str(candidate)).lower()
    separated_pattern = r"[^a-z0-9]+".join(re.escape(group) for group in groups)
    contiguous_pattern = re.escape(normalized_token)
    pattern = rf"(?<![a-z0-9])(?:{separated_pattern}|{contiguous_pattern})(?![a-z0-9])"
    return re.search(pattern, candidate_text) is not None


def canonicalize_url(url: str | None) -> str:
    # Normalize URLs so equivalent product links compare cleanly.
    if not url:
        return ""
    trimmed = url.split("#", 1)[0].split("?", 1)[0]
    return trimmed.rstrip("/").lower()
