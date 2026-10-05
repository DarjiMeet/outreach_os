import httpx


class ResearchClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=15.0,
        )

    async def create_research(
    self,
    company_name: str,
    company_url: str,
    ) -> dict:

        payload = {
            "company_name": company_name,
            "company_url": company_url,
        }

        response = await self._client.post(
            f"{self.base_url}/api/v1/research/company",
            json=payload,
        )

        print("\n===== RESEARCH REQUEST =====")
        print(payload)

        print("\n===== RESEARCH RESPONSE =====")
        print("STATUS:", response.status_code)
        print("BODY:", response.text)

        response.raise_for_status()

        return response.json()

    async def get_research(
        self,
        research_id: str,
    )->dict:

        response = await self._client.get(
            f"{self.base_url}/api/v1/research/company/{research_id}",
        )

        print("\n===== RESEARCH GET REQUEST =====")
        print("RESEARCH ID:", research_id)

        print("\n===== RESEARCH GET RESPONSE =====")
        print("STATUS:", response.status_code)
        print("BODY:", response.text)

        response.raise_for_status()

        return response.json()

    async def get_research_result(
        self,
        research_id:str
    )->dict:

        response = await self._client.get(
            f"{self.base_url}/api/v1/research/company/"
            f"{research_id}/result"
        )

        response.raise_for_status()

        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
