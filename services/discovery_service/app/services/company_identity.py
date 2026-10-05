"""Conservative identity matching for noisy directory text and website evidence."""

import ipaddress
import re
from urllib.parse import urlparse


DIRECTORY_DOMAINS = (
    "linkedin.com", "wellfound.com", "crunchbase.com", "revenuebase.ai",
    "clutch.co", "goodfirms.co", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "youtube.com", "wikipedia.org", "zoominfo.com",
    "tracxn.com", "glassdoor.com", "ambitionbox.com", "justdial.com",
    "ycombinator.com",
    "cbinsights.com", "internshala.com", "yourstory.com",
)


def public_root(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host or "." not in host:
            return None
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return None
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", host):
            return None
        if host.endswith((".local", ".localhost", ".internal")):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return None
        return f"{parsed.scheme}://{host}"
    except ValueError:
        return None


def is_directory(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in DIRECTORY_DOMAINS)


def short_name(name: str) -> str:
    # Strip legal suffixes, but retain meaningful words such as Technologies.
    return re.sub(
        r"(?:\s+(?:private|limited|pvt\.?|ltd\.?|inc\.?|llc|corp\.?))+$",
        "", name.strip(), flags=re.I,
    ).strip()


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", short_name(name).lower())


def name_variants(name: str) -> list[str]:
    name = " ".join(name.split())
    variants = [name]
    # Only propose a correction. Never persist it without independent text evidence.
    if re.match(r"^([A-Z])\1[a-z]", name):
        variants.append(name[1:])
    return variants


def brand_name(name: str) -> str:
    """A few directory display suffixes may be absent from an official domain."""
    return re.sub(r"\s+(?:AI|HQ)$", "", short_name(name), flags=re.I).strip()


def normalize_website(value: str) -> str | None:
    """Normalize a domain observed in evidence; never guess a domain from a name."""
    value = value.strip().rstrip(".,;:!?")
    if value.startswith("//"):
        value = "https:" + value
    elif "://" not in value:
        value = "https://" + value
    return public_root(value)


def website_candidates(company_name: str, text: str) -> list[str]:
    """Collect matching domains from text, including bare domains, but not email addresses."""
    pattern = (
        r"(?<![\w@./-])(?:https?://|//)?"
        r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}"
        r"(?::\d+)?(?:/[^\s<>\]\)\"']*)?(?![\w@-]|\.[a-z0-9])"
    )
    urls = []
    for match in re.finditer(pattern, text, flags=re.I):
        url = normalize_website(match.group())
        if url and domain_matches_company(company_name, url) and url not in urls:
            urls.append(url)
    return urls


def confirmed_name(name: str, evidence: str) -> str | None:
    for variant in name_variants(name):
        parts = re.findall(r"[a-z0-9]+", short_name(variant).lower())
        if not parts:
            continue
        pattern = r"(?<!\w)" + r"[\W_]*".join(map(re.escape, parts)) + r"(?!\w)"
        if re.search(pattern, evidence, flags=re.I):
            return variant
    return None


def domain_matches_company(company_name: str, url: str) -> bool:
    if not public_root(url) or is_directory(url):
        return False
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    labels = host.split(".")
    # Use the domain rather than a subdomain that happens to contain the brand.
    # Handle common country-code suffixes without runtime suffix-list downloads.
    index = -3 if (
        len(labels) >= 3 and len(labels[-1]) == 2
        and labels[-2] in {"co", "com", "net", "org", "gov", "edu", "ac"}
    ) else -2
    domain = re.sub(r"[^a-z0-9]", "", labels[index])
    company = name_key(company_name)
    if not company or not domain:
        return False
    # A shared prefix does not establish that two names refer to the same business.
    # Permit only an exact name or an explicitly recognized display suffix.
    brand = name_key(brand_name(company_name))
    return company == domain or (len(brand) >= 4 and brand == domain)
