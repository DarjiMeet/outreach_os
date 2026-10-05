from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.clients.website_client import WebsiteClient
from app.extractors.website_text_extractor import WebsiteTextExtractor
from app.schemas.crawl import CrawlResult


class CompanyCrawler:
    def __init__(
        self,
        website_client: WebsiteClient,
        text_extractor: WebsiteTextExtractor,
    ):
        self.website_client = website_client
        self.text_extractor = text_extractor

    async def crawl(self, start_url: str) -> CrawlResult:
        homepage_html = await self.website_client.fetch(start_url)

        homepage_text = self.text_extractor.extract(
            homepage_html
        )

        useful_links = self._find_useful_links(
            start_url,
            homepage_html,
        )

        pages = [homepage_text]
        source_urls = [start_url]


        for url in useful_links[:4]:
            try:
                html = await self.website_client.fetch(url)

                text = self.text_extractor.extract(html)

                pages.append(text)
                source_urls.append(url)

            except Exception:
                continue

        return CrawlResult(
        text="\n\n".join(pages),
        source_urls=source_urls,
        )

    def _find_useful_links(
        self,
        base_url: str,
        html: str,
    ) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")

        base_domain = urlparse(base_url).netloc

        keywords = {
            "about",
            "company",
            "products",
            "product",
            "services",
            "solutions",
            "careers",
        }

        discovered = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]

            absolute_url = urljoin(
                base_url,
                href,
            )

            parsed = urlparse(absolute_url)

            if parsed.netloc != base_domain:
                continue

            path = parsed.path.lower()

            if any(
                keyword in path
                for keyword in keywords
            ):
                if absolute_url not in discovered:
                    discovered.append(absolute_url)

        return discovered
