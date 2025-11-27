"""
Base domain class for research domains.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from ..models import DomainData, DataTable


class BaseDomain(ABC):
    """
    Abstract base class for domain research sessions.

    Each domain (1-7) should inherit from this class and implement
    the required abstract methods to define:
    - Search queries for the domain
    - Table schemas for data collection
    - Synthesis prompt for Claude
    - Validation criteria
    """

    domain_id: int
    domain_name: str

    @property
    @abstractmethod
    def search_queries(self) -> List[str]:
        """
        Return list of search query templates for this domain.

        Templates can include placeholders:
        - {disease}: Disease/condition name
        - {country}: Target country
        - {major_city}: Major city in the country

        Returns:
            List of query template strings
        """
        pass

    @property
    @abstractmethod
    def table_schemas(self) -> Dict[str, List[str]]:
        """
        Return table schemas for this domain.

        Returns:
            Dictionary mapping table name -> list of column headers
        """
        pass

    @property
    @abstractmethod
    def required_tables(self) -> List[str]:
        """
        Return list of required table names that must be populated.

        Returns:
            List of table names
        """
        pass

    @property
    def critical_fields(self) -> Dict[str, List[str]]:
        """
        Return critical fields that should be present in tables.

        Override in subclasses for domain-specific validation.

        Returns:
            Dictionary mapping table name -> list of critical field values
        """
        return {}

    @property
    @abstractmethod
    def synthesis_prompt(self) -> str:
        """
        Return the synthesis prompt template for Claude.

        The prompt should instruct Claude on:
        - What data to extract
        - Output format (JSON structure)
        - How to handle missing data

        Returns:
            Prompt template string
        """
        pass

    def generate_search_queries(
        self,
        disease: str,
        country: str,
        major_city: str = ""
    ) -> List[str]:
        """
        Generate country/disease-specific search queries.

        Args:
            disease: Disease/condition name
            country: Target country
            major_city: Optional major city name

        Returns:
            List of formatted search queries
        """
        queries = []
        for query_template in self.search_queries:
            try:
                query = query_template.format(
                    disease=disease,
                    country=country,
                    major_city=major_city
                )
                queries.append(query)
            except KeyError:
                # Template has unrecognized placeholder, use as-is
                queries.append(query_template)
        return queries

    def get_synthesis_prompt(
        self,
        disease: str,
        country: str
    ) -> str:
        """
        Get the formatted synthesis prompt.

        Args:
            disease: Disease/condition name
            country: Target country

        Returns:
            Formatted prompt string
        """
        import json
        return self.synthesis_prompt.format(
            disease=disease,
            country=country,
            table_schemas=json.dumps(self.table_schemas, indent=2)
        )

    def validate_completeness(
        self,
        data: DomainData
    ) -> tuple[bool, List[str]]:
        """
        Validate domain data completeness.

        Args:
            data: DomainData to validate

        Returns:
            Tuple of (is_complete, list_of_gaps)
        """
        gaps = []

        # Check required tables exist
        for table_name in self.required_tables:
            table = data.get_table(table_name)
            if not table:
                gaps.append(f"Missing table: {table_name}")
            elif len(table.rows) < 2:
                gaps.append(f"Insufficient data in {table_name}: only {len(table.rows)} rows")

        # Check critical fields
        for table_name, fields in self.critical_fields.items():
            table = data.get_table(table_name)
            if not table:
                continue

            for field in fields:
                has_field = any(
                    field.lower() in str(row).lower()
                    for row in table.rows
                )
                if not has_field:
                    gaps.append(f"Missing critical data '{field}' in {table_name}")

        return len(gaps) == 0, gaps

    def create_domain_data(self) -> DomainData:
        """
        Create an initialized DomainData object for this domain.

        Returns:
            New DomainData instance
        """
        from ..models import DomainStatus
        from datetime import datetime

        return DomainData(
            domain_id=self.domain_id,
            domain_name=self.domain_name,
            status=DomainStatus.NOT_STARTED,
            started_at=datetime.now()
        )


# Base synthesis prompt template used by all domains
BASE_SYNTHESIS_PROMPT = """
You are a pharmaceutical market research analyst conducting research on {disease} in {country}.

## TASK
Analyze the provided search results and populate the following data tables.

## OUTPUT FORMAT
Return your analysis as a JSON object with the following structure:

```json
{{
  "search_log": [
    {{"query": "...", "source_found": "...", "key_data_points": "..."}}
  ],
  "tables": {{
    "table_name": {{
      "headers": ["Column1", "Column2", ...],
      "rows": [
        {{"Column1": "value1", "Column2": "value2", ...}},
        ...
      ],
      "sources": ["source1", "source2"],
      "confidence_level": "HIGH|MEDIUM|LOW"
    }}
  }},
  "data_gaps": ["Gap 1", "Gap 2"],
  "quality_summary": {{
    "searches_completed": 12,
    "tables_populated": 10,
    "confidence_level": "HIGH|MEDIUM|LOW",
    "primary_source_quality": "HIGH|MEDIUM|LOW",
    "data_recency": "2020-2024"
  }}
}}
```

## TABLES TO POPULATE
{table_schemas}

## IMPORTANT GUIDELINES
- Use "NOT_FOUND" for data that cannot be located
- Cross-validate key statistics across multiple sources when possible
- Note confidence level (HIGH/MEDIUM/LOW) based on source quality
- Document data gaps explicitly
- Prioritize recent data (last 5 years)
- Cite sources for each data point where possible
"""
