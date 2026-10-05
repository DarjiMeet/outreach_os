from app.providers.tavily_provider import (
    TavilyDiscoveryProvider,
)
from app.services.candidate_classifier import (
    CandidateClassifier,
)
from app.services.discovery_service import (
    DiscoveryService,
)
from app.services.company_deduplicator import (
    CompanyDeduplicator,
)
from app.services.website_resolver import (
    WebsiteResolver,
)
from app.clients.research_client import ResearchClient
from app.config import settings
from app.services.research_submission_service import (
    ResearchSubmissionService,
)



def get_discovery_service() -> DiscoveryService:

    provider = TavilyDiscoveryProvider()
    classifier = CandidateClassifier()
    deduplicator = CompanyDeduplicator()
    website_resolver = WebsiteResolver(
        provider=provider
    )

    return DiscoveryService(
        provider=provider,
        classifier=classifier,
        deduplicator=deduplicator,
        website_resolver=website_resolver
    )


def get_research_submission_service():
    client = ResearchClient(
        base_url=settings.research_service_url
    )

    return ResearchSubmissionService(
        research_client=client
    )