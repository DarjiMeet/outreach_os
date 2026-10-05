# Company discovery

`POST /api/v1/discovery/companies` accepts industry, location, keywords, employee
range, optional free-form `query`, and `limit` (1–100, default **3**). The
orchestrator's lead-generation endpoint uses the same default.

The limit counts unique companies with identified official websites, not raw
search results or unresolved company names. Discovery:

1. Searches for more candidates than the requested count and extracts companies
   with their source evidence. Directory logo initials must not become name text.
2. Reads company-labelled links from the source page to recover official URLs
   and evidence-supported name corrections. Bare website fields such as
   `Website: www.examplecompany.example` are normalized to HTTPS.
3. Tries official-site queries, queries without location, spelling variants, and
   publicly indexed LinkedIn/directory profiles. Profile website fields can supply
   an official URL; the profile itself never counts as an official website.
   Relevant snippets and unfamiliar company profiles can also supply candidate
   domains. A candidate must match the company domain rules and have readable
   company-name evidence on the destination page before acceptance. Arbitrary
   shared name prefixes do not establish a match.
4. Searches new sources for replacement companies when resolution fails. Existing
   criteria are retained; names and website hosts are deduplicated. The second
   round searches indexed LinkedIn, Wellfound, and Y Combinator company pages.
5. Returns the results found and an explicit discovery summary when the target or
   search budget is reached.

These fallbacks use the existing Tavily API, not a separate search engine or a
signed-in LinkedIn session. Unindexed/inaccessible profiles and provider failures
can still cause a shortfall. Finding an official URL does not guarantee that the
research worker will subsequently be able to crawl it.

Website resolution checks at most five distinct candidate URLs and extracts at
most three additional result pages per company (cached/raw result content is
reused). Removing a trailing `AI` or `HQ` display suffix is allowed for domain
comparison; unrelated domain extensions are not. Destination checks are evidence
heuristics, not proof of ownership or exact location/industry eligibility.

An unresolved company includes `reason` and `diagnostics`. For example:

```json
{
  "company_name": "Example Company",
  "source": "https://directory.example/company/example-company",
  "reason": "website_verification_failed",
  "diagnostics": [
    {"code": "source_unreadable", "url": "https://directory.example/company/example-company"},
    {"code": "candidate_unreadable", "url": "https://examplecompany.example"},
    {"code": "no_verified_website"}
  ]
}
```

Other diagnostic codes include `search_no_results`, `search_failed`,
`source_fetch_failed`, `candidate_identity_mismatch`, `candidate_domain_mismatch`,
`candidate_limit_reached`, and `profile_limit_reached`. Model extraction warnings
include the exception type and HTTP status, when available, without including
response bodies in the API response.

Example partial response (summary fields abbreviated):

```json
{
  "companies": [],
  "discovery_summary": {
    "requested_count": 10,
    "found_count": 0,
    "shortfall": 10,
    "status": "no_results",
    "message": "Found 0 of 10 requested companies with official websites matching your requirements within the search budget.",
    "search_rounds": 3,
    "stop_reason": "search_round_limit",
    "warnings": []
  },
  "unresolved_companies": []
}
```

`status` is `fulfilled`, `partial`, or `no_results`. `stop_reason` is
`target_reached`, `search_round_limit`, or `time_budget_exhausted`. The orchestrator
preserves `discovery_summary` and `unresolved_companies` in graph state and exposes
the summary while waiting for research. Its outer `completed` status means graph
execution finished, not that the requested discovery count was fulfilled.

Budget settings in the discovery service environment:

- `DISCOVERY_MAX_ROUNDS=3`
- `DISCOVERY_TIMEOUT_SECONDS=180`

Tavily calls have individual timeouts and at most four simultaneous requests.
Completed resolutions survive the overall timeout. The orchestrator's discovery
HTTP read timeout is 210 seconds; keep it above the discovery budget if changing
these defaults. Additional search/extraction fallbacks use additional API credits.

Restart discovery and the orchestrator after changing code. Start a **new**
lead-generation request to use the new discovery flow: resuming a checkpoint that
already passed discovery does not rerun that node or repair its saved companies.

### Evidence selection

Discovery sends at most **2,000 characters of selected content per search result**
to its classifier (titles, URLs, instructions, and schema are outside that budget).
The selector scans all available content, removes navigation, and prioritizes
business/products, customers, location, headcount, commercial model, technology,
and business signals, with an extra preference for the user's criteria. It selects
source excerpts, not an LLM-generated summary; no extra model call is added.
Headings and table labels stay attached to facts; `[...]` separates excerpts.
Oversized indivisible rows are skipped rather than truncated into ambiguous facts.
GTM quotations must occur in both selected and original source text. This verifies
quotation presence, not whether the model correctly interpreted the claim.

The research service separately preserves HTML titles, descriptions, organization/
product JSON-LD, headings, table rows, and links before analysis. Each crawled page
is labelled with its source URL. JSON-LD is treated as a website's claims, not
independently verified data. The research analyzer retains its existing 30,000-
character input limit; the discovery 2,000-character cap does not apply to it.
Selection cannot recover facts absent from the fetched page or guarantee that all
relevant facts fit in the window.

Run the offline suites from the discovery, research, and orchestrator directories:

```powershell
..\..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The discovery suite mocks Tavily and classification. The orchestrator suite uses
an in-memory checkpointer to exercise pause/resume reporting without Redis or live
research jobs.
