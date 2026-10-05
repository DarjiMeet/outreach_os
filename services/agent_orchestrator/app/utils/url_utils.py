import re
from urllib.parse import urlparse

def clean_url(url: str | None) -> str | None:
    if not url:
        return None

    match = re.search(
        r"https?://[^\s]+",
        url,
    )

    if not match:
        return None

    cleaned = match.group(0)

    cleaned = cleaned.rstrip(
        ".,;:)]}"
    )

    parsed = urlparse(cleaned)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    if not parsed.netloc:
        return None

    return cleaned