"""Preserve factual HTML structure instead of flattening navigation into prose."""

import json
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


ENTITY_TYPES = {"Organization", "Corporation", "LocalBusiness", "Product", "Service", "SoftwareApplication"}
ENTITY_FIELDS = (
    "name", "legalName", "url", "description", "address", "location",
    "numberOfEmployees", "foundingDate", "industry", "knowsAbout",
    "areaServed", "audience", "category", "offers", "brand", "provider", "sameAs",
)


def _entities(value):
    """Read top-level entities and @graph, not unrelated nested review authors."""
    if isinstance(value, list):
        for item in value:
            yield from _entities(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if isinstance(types, list) and any(isinstance(kind, str) and kind in ENTITY_TYPES for kind in types):
            yield value
        yield from _entities(value.get("@graph", []))


class WebsiteTextExtractor:
    def extract(self, html: str, source_url: str | None = None) -> str:
        soup = BeautifulSoup(html, "html.parser")
        blocks = []
        if soup.title:
            blocks.append("Page title: " + soup.title.get_text(" ", strip=True))
        for meta in soup.find_all("meta"):
            if meta.get("name", "").lower() == "description" or meta.get("property", "").lower() == "og:description":
                if meta.get("content"):
                    blocks.append("Page description: " + " ".join(meta["content"].split()))

        # Read structured company claims BEFORE deleting script elements.
        # Keep each entity together: a page can describe multiple companies.
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
                for entity in _entities(data):
                    facts = {key: entity[key] for key in ENTITY_FIELDS if key in entity}
                    if facts:
                        blocks.append("Structured website claims: " + json.dumps(facts, ensure_ascii=False))
            except (ValueError, TypeError, RecursionError):
                continue

        # Retain footers: they may contain the company address.
        for element in soup.select("script, style, noscript, nav, [role=navigation], form, svg, [hidden], [aria-hidden=true]"):
            if element.parent is not None:
                element.decompose()
        if soup.head:
            soup.head.decompose()
        for anchor in soup.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True)
            url = urljoin(source_url or "", anchor["href"])
            if label and urlparse(url).scheme in {"http", "https"}:
                anchor.replace_with(f"[{label}]({url})")

        for table in soup.find_all("table"):
            rows = []
            headers = []
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"], recursive=False)
                values = [cell.get_text(" ", strip=True) for cell in cells]
                if cells and all(cell.name == "th" for cell in cells):
                    headers = values
                elif values:
                    rows.append(" | ".join(f"{headers[i]}: {value}" if i < len(headers) else value for i, value in enumerate(values)))
            if rows:
                table.replace_with("\n" + "\n".join(rows) + "\n")
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            heading.replace_with("\n" + "#" * int(heading.name[1]) + " " + heading.get_text(" ", strip=True) + "\n")
        for element in soup.find_all(["p", "li", "div", "section", "article", "address", "footer", "br"]):
            element.insert_before("\n")
            element.insert_after("\n")
        body = soup.get_text(" ", strip=False)
        blocks.extend(" ".join(line.split()) for line in body.splitlines() if line.strip())
        return "\n".join(blocks)
