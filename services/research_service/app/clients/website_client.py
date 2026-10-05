import httpx

from app.exceptions.website import (
    WebsiteBlockedError,
    WebsiteNotFoundError,
    WebsiteTemporaryError,
)


class WebsiteClient:
    def __init__(self):
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=20.0,
            write=10.0,
            pool=10.0,
        )

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self.headers,
            ) as client:

                response = await client.get(url)

                if response.status_code in (401, 403):
                    raise WebsiteBlockedError(
                        f"Website blocked request: {response.status_code}"
                    )

                if response.status_code == 404:
                    raise WebsiteNotFoundError(
                        f"Website page not found: {url}"
                    )

                if response.status_code >= 500:
                    raise WebsiteTemporaryError(
                        f"Website server error: {response.status_code}"
                    )

                response.raise_for_status()

                return response.text

        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
        ) as exc:
            raise WebsiteTemporaryError(str(exc)) from exc