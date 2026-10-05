import httpx


class DiscoveryClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            # Allow the discovery service's 180-second budget plus response overhead.
            timeout=httpx.Timeout(210.0, connect=10.0),
        )

    async def discover(
        self,
        criteria: dict,
    ) -> dict:

        response = await self._client.post(
            f"{self.base_url}/api/v1/discovery/companies",
            json=criteria,
        )

        response.raise_for_status()

        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
