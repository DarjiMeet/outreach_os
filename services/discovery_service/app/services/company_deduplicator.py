from app.services.company_identity import name_key


class CompanyDeduplicator:

    def normalize_name(
        self,
        name: str,
    ) -> str:

        return name_key(name)

    def deduplicate(
        self,
        companies,
    ):
        unique = {}

        for company in companies:
            key = self.normalize_name(
                company.company_name
            )

            existing = unique.get(key)

            if existing is None:
                unique[key] = company
                continue

            if company.confidence > existing.confidence:
                unique[key] = company

        return list(unique.values())
