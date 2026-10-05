import httpx


class ResearchClient:
    def __init__(self, base_url:str):
        self.base_url = base_url.rstrip("/")

    async def create_research_job(
        self,
        company_name:str,
        company_url:str
    )->dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/research/company",
                json={
                    "company_name": company_name,
                    "company_url": company_url
                }
            )

            response.raise_for_status()
            return response.json()

    