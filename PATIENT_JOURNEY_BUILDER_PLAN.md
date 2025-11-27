# Patient Journey Database Builder - Implementation Plan

## Project Overview

Build a Python application that automates the creation of pharmaceutical patient journey databases by orchestrating web searches and Claude API calls to populate structured data across 7 research domains.

**Proven methodology:** This automation replicates a manual research process that has been validated with a Chronic Spontaneous Urticaria (CSU) database for Sweden. The skill definition and prompts are available in the project files.

---

## Architecture Overview

```
patient_journey_builder/
├── main.py                      # CLI entry point and orchestrator
├── config.py                    # Configuration and environment variables
├── requirements.txt             # Dependencies
├── .env.example                 # Template for API keys
│
├── core/
│   ├── __init__.py
│   ├── orchestrator.py          # Main workflow controller
│   ├── session_manager.py       # Handles session state and resumption
│   └── checkpoint.py            # Validation and checkpoint logic
│
├── search/
│   ├── __init__.py
│   ├── brave_search.py          # Brave Search API integration
│   ├── web_fetch.py             # Full page content retrieval
│   └── search_cache.py          # Cache management for search results
│
├── synthesis/
│   ├── __init__.py
│   ├── claude_client.py         # Anthropic API wrapper
│   └── table_builder.py         # Converts Claude output to structured data
│
├── domains/
│   ├── __init__.py
│   ├── base_domain.py           # Abstract base class for domains
│   ├── domain_1_epidemiology.py
│   ├── domain_2_healthcare_finances.py
│   ├── domain_3_competitive_landscape.py
│   ├── domain_4_clinical_pathways.py
│   ├── domain_5_patient_experience.py
│   ├── domain_6_segmentation.py
│   └── domain_7_stakeholders.py
│
├── prompts/
│   ├── __init__.py
│   ├── system_prompts.py        # Base system prompts
│   └── domain_prompts.py        # Domain-specific prompts (from existing skill)
│
├── models/
│   ├── __init__.py
│   ├── database.py              # Pydantic models for database structure
│   ├── search_result.py         # Search result models
│   └── session_state.py         # Session state models
│
├── output/
│   ├── __init__.py
│   ├── json_exporter.py         # Export to JSON
│   ├── markdown_exporter.py     # Export to Markdown
│   └── templates/               # Jinja2 templates for markdown output
│
├── data/
│   ├── cache/                   # Search result cache (gitignored)
│   ├── sessions/                # Session state files (gitignored)
│   └── outputs/                 # Generated databases
│
└── tests/
    ├── __init__.py
    ├── test_search.py
    ├── test_synthesis.py
    └── test_domains.py
```

---

## Core Components Specification

### 1. Configuration (`config.py`)

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str
    brave_api_key: str
    
    # Model settings
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8000
    
    # Search settings
    searches_per_domain: int = 17
    max_search_results: int = 10
    
    # Rate limiting
    search_delay_seconds: float = 1.0
    api_delay_seconds: float = 2.0
    
    # Paths
    cache_dir: str = "data/cache"
    session_dir: str = "data/sessions"
    output_dir: str = "data/outputs"
    
    class Config:
        env_file = ".env"
```

### 2. Data Models (`models/database.py`)

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

class DomainStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class SearchLogEntry(BaseModel):
    query: str
    source_found: str
    key_data_points: str
    timestamp: datetime
    cached: bool = False

class DataTable(BaseModel):
    table_name: str
    headers: List[str]
    rows: List[Dict[str, Any]]
    sources: List[str]
    confidence_level: str  # HIGH, MEDIUM, LOW
    data_gaps: List[str]

class DomainData(BaseModel):
    domain_id: int
    domain_name: str
    status: DomainStatus
    search_log: List[SearchLogEntry]
    tables: List[DataTable]
    quality_summary: Dict[str, Any]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class PatientJourneyDatabase(BaseModel):
    # Metadata
    disease_area: str
    country: str
    created_at: datetime
    updated_at: datetime
    version: str = "1.0"
    
    # Session tracking
    current_domain: int = 1
    total_domains: int = 7
    overall_status: str = "in_progress"
    
    # Domain data
    domains: Dict[int, DomainData] = {}
    
    # Validation
    completeness_score: float = 0.0
    data_gaps_summary: List[str] = []
```

### 3. Session Manager (`core/session_manager.py`)

```python
class SessionManager:
    """Handles session persistence and resumption."""
    
    def __init__(self, disease: str, country: str, session_dir: str):
        self.session_id = f"{country.lower()}_{disease.lower().replace(' ', '_')}"
        self.session_file = Path(session_dir) / f"{self.session_id}_session.json"
    
    def load_or_create(self) -> PatientJourneyDatabase:
        """Load existing session or create new one."""
        if self.session_file.exists():
            return PatientJourneyDatabase.parse_file(self.session_file)
        return PatientJourneyDatabase(
            disease_area=self.disease,
            country=self.country,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    def save(self, database: PatientJourneyDatabase):
        """Persist session state to disk."""
        database.updated_at = datetime.now()
        self.session_file.write_text(database.json(indent=2))
    
    def get_resume_point(self, database: PatientJourneyDatabase) -> int:
        """Determine which domain to resume from."""
        for domain_id in range(1, 8):
            if domain_id not in database.domains:
                return domain_id
            if database.domains[domain_id].status != DomainStatus.COMPLETED:
                return domain_id
        return 8  # All complete
```

### 4. Search Integration (`search/brave_search.py`)

```python
import httpx
from typing import List
from models.search_result import SearchResult

class BraveSearchClient:
    """Brave Search API client with caching support."""
    
    BASE_URL = "https://api.search.brave.com/res/v1/web/search"
    
    def __init__(self, api_key: str, cache: SearchCache):
        self.api_key = api_key
        self.cache = cache
        self.client = httpx.Client(timeout=30.0)
    
    def search(self, query: str, country: str = None) -> List[SearchResult]:
        """Execute search with caching."""
        cache_key = f"{query}_{country}"
        
        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Execute search
        headers = {"X-Subscription-Token": self.api_key}
        params = {
            "q": query,
            "count": 10,
            "country": country or "us",
            "search_lang": "en"
        }
        
        response = self.client.get(self.BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        
        results = self._parse_results(response.json())
        self.cache.set(cache_key, results)
        
        return results
    
    def _parse_results(self, data: dict) -> List[SearchResult]:
        """Parse Brave API response into SearchResult objects."""
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                description=item.get("description", ""),
                source=item.get("meta_url", {}).get("hostname", "")
            ))
        return results
```

### 5. Web Content Fetcher (`search/web_fetch.py`)

```python
import httpx
from bs4 import BeautifulSoup
from typing import Optional

class WebFetcher:
    """Fetches and extracts content from web pages."""
    
    def __init__(self, cache: SearchCache):
        self.cache = cache
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        )
    
    def fetch(self, url: str, max_tokens: int = 4000) -> Optional[str]:
        """Fetch and extract main content from URL."""
        cache_key = f"page_{url}"
        
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            response = self.client.get(url)
            response.raise_for_status()
            
            content = self._extract_content(response.text)
            truncated = self._truncate_to_tokens(content, max_tokens)
            
            self.cache.set(cache_key, truncated)
            return truncated
            
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
            return None
    
    def _extract_content(self, html: str) -> str:
        """Extract main text content from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script, style, nav elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Get text
        text = soup.get_text(separator='\n', strip=True)
        return text
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Rough truncation to approximate token limit."""
        # Approximate: 1 token ≈ 4 characters
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text
```

### 6. Claude Synthesis Client (`synthesis/claude_client.py`)

```python
from anthropic import Anthropic
from typing import Dict, Any

class ClaudeSynthesizer:
    """Handles Claude API calls for data synthesis."""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = Anthropic(api_key=api_key)
        self.model = model
    
    def synthesize_domain(
        self,
        domain_prompt: str,
        search_results: List[Dict],
        page_contents: List[str],
        existing_data: Optional[DomainData] = None
    ) -> Dict[str, Any]:
        """
        Synthesize search results into structured domain data.
        
        Returns dict with:
        - tables: List of populated data tables
        - search_log: Annotated search log
        - data_gaps: Identified gaps
        - quality_summary: Quality metrics
        """
        
        # Build context with search results and page contents
        context = self._build_context(search_results, page_contents)
        
        # Build prompt
        messages = [
            {
                "role": "user",
                "content": f"{domain_prompt}\n\n## SEARCH RESULTS AND SOURCES\n\n{context}"
            }
        ]
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            messages=messages
        )
        
        # Parse structured output
        return self._parse_domain_output(response.content[0].text)
    
    def _build_context(self, search_results: List, page_contents: List) -> str:
        """Build context string from search results and fetched content."""
        context_parts = []
        
        for i, (result, content) in enumerate(zip(search_results, page_contents)):
            context_parts.append(f"""
### Source {i+1}: {result.title}
URL: {result.url}
Description: {result.description}

Content:
{content if content else "[Content not available]"}
---
""")
        
        return "\n".join(context_parts)
    
    def _parse_domain_output(self, output: str) -> Dict[str, Any]:
        """Parse Claude's output into structured data."""
        # Implementation depends on output format
        # Could use structured output prompting or regex parsing
        pass
```

### 7. Domain Base Class (`domains/base_domain.py`)

```python
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseDomain(ABC):
    """Abstract base class for domain research sessions."""
    
    domain_id: int
    domain_name: str
    
    @property
    @abstractmethod
    def search_queries(self) -> List[str]:
        """Return list of search queries for this domain."""
        pass
    
    @property
    @abstractmethod
    def table_schemas(self) -> Dict[str, List[str]]:
        """Return table name -> column headers mapping."""
        pass
    
    @property
    @abstractmethod
    def synthesis_prompt(self) -> str:
        """Return the synthesis prompt for Claude."""
        pass
    
    @abstractmethod
    def validate_completeness(self, data: DomainData) -> tuple[bool, List[str]]:
        """
        Validate domain data completeness.
        Returns (is_complete, list_of_gaps).
        """
        pass
    
    def generate_search_queries(self, disease: str, country: str) -> List[str]:
        """Generate country/disease-specific search queries."""
        return [
            query.format(disease=disease, country=country)
            for query in self.search_queries
        ]
```

### 8. Example Domain Implementation (`domains/domain_1_epidemiology.py`)

```python
class EpidemiologyDomain(BaseDomain):
    """Domain 1: Epidemiology research session."""
    
    domain_id = 1
    domain_name = "Epidemiology"
    
    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} prevalence {country} epidemiology",
            "{disease} incidence rate {country} registry",
            "{disease} age distribution gender {country} demographics",
            "{disease} quality of life DLQI {country} Nordic",
            "{disease} depression anxiety psychiatric comorbidity",
            "{disease} disease duration remission natural history",
            "{disease} autoimmune comorbidity thyroid disease",
            "{disease} work productivity absenteeism economic burden",
            "{country} population statistics adults",
            "{disease} angioedema prevalence",
            "{disease} sleep disturbance insomnia",
            "{country} population {major_city} county",
            # ... more queries from existing skill
        ]
    
    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "prevalence_incidence": [
                "Metric", "Value", "95% CI", "Source", "Year", "Confidence"
            ],
            "estimated_patient_population": [
                "Category", "Estimate", "Calculation", "Source"
            ],
            "demographics": [
                "Category", "Value", "Source", "Year"
            ],
            "age_distribution": [
                "Age Group", "Prevalence/%", "Notes", "Source"
            ],
            # ... more tables from existing skill
        }
    
    @property
    def synthesis_prompt(self) -> str:
        return """
You are a pharmaceutical market research analyst conducting epidemiological research.

## TASK
Analyze the provided search results and populate the following data tables for {disease} in {country}.

## OUTPUT FORMAT
Return your analysis as a JSON object with the following structure:

```json
{
  "search_log": [
    {"query": "...", "source_found": "...", "key_data_points": "..."}
  ],
  "tables": {
    "prevalence_incidence": {
      "headers": ["Metric", "Value", "95% CI", "Source", "Year", "Confidence"],
      "rows": [...]
    },
    ...
  },
  "data_gaps": ["Gap 1", "Gap 2"],
  "quality_summary": {
    "searches_completed": 12,
    "tables_populated": 10,
    "confidence_level": "HIGH",
    "primary_source_quality": "HIGH",
    "data_recency": "2020-2024"
  }
}
```

## TABLES TO POPULATE
{table_schemas}

## IMPORTANT
- Use "NOT_FOUND" for data that cannot be located
- Cross-validate key statistics across multiple sources
- Note confidence level (HIGH/MEDIUM/LOW) for each data point
- Document data gaps explicitly
"""
    
    def validate_completeness(self, data: DomainData) -> tuple[bool, List[str]]:
        """Check if domain data meets minimum completeness criteria."""
        gaps = []
        
        # Check required tables exist
        required_tables = ["prevalence_incidence", "demographics", "estimated_patient_population"]
        for table_name in required_tables:
            if not any(t.table_name == table_name for t in data.tables):
                gaps.append(f"Missing table: {table_name}")
        
        # Check minimum row counts
        for table in data.tables:
            if len(table.rows) < 3:
                gaps.append(f"Insufficient data in {table.table_name}: only {len(table.rows)} rows")
        
        # Check for critical data points
        prevalence_table = next((t for t in data.tables if t.table_name == "prevalence_incidence"), None)
        if prevalence_table:
            has_prevalence = any("prevalence" in str(row).lower() for row in prevalence_table.rows)
            if not has_prevalence:
                gaps.append("Missing: prevalence data")
        
        return len(gaps) == 0, gaps
```

### 9. Main Orchestrator (`core/orchestrator.py`)

```python
class PatientJourneyOrchestrator:
    """Main orchestrator for patient journey database creation."""
    
    def __init__(self, config: Settings):
        self.config = config
        self.search_client = BraveSearchClient(config.brave_api_key, SearchCache(config.cache_dir))
        self.web_fetcher = WebFetcher(SearchCache(config.cache_dir))
        self.synthesizer = ClaudeSynthesizer(config.anthropic_api_key, config.claude_model)
        
        self.domains = {
            1: EpidemiologyDomain(),
            2: HealthcareFinancesDomain(),
            3: CompetitiveLandscapeDomain(),
            4: ClinicalPathwaysDomain(),
            5: PatientExperienceDomain(),
            6: SegmentationDomain(),
            7: StakeholdersDomain(),
        }
    
    def run(
        self,
        disease: str,
        country: str,
        start_domain: int = 1,
        end_domain: int = 7
    ) -> PatientJourneyDatabase:
        """
        Run the patient journey database creation.
        
        Args:
            disease: Disease area (e.g., "Chronic Spontaneous Urticaria")
            country: Target country (e.g., "Sweden")
            start_domain: Domain to start from (for resumption)
            end_domain: Domain to end at
        
        Returns:
            Completed PatientJourneyDatabase
        """
        # Initialize or load session
        session_manager = SessionManager(disease, country, self.config.session_dir)
        database = session_manager.load_or_create()
        
        print(f"\n{'='*60}")
        print(f"Patient Journey Database Builder")
        print(f"Disease: {disease}")
        print(f"Country: {country}")
        print(f"Starting from Domain {start_domain}")
        print(f"{'='*60}\n")
        
        for domain_id in range(start_domain, end_domain + 1):
            domain = self.domains[domain_id]
            
            print(f"\n--- Domain {domain_id}: {domain.domain_name} ---")
            
            try:
                # Execute domain research
                domain_data = self._execute_domain(domain, disease, country)
                
                # Validate completeness
                is_complete, gaps = domain.validate_completeness(domain_data)
                
                if not is_complete:
                    print(f"⚠️  Domain {domain_id} has gaps: {gaps}")
                    domain_data.status = DomainStatus.COMPLETED  # Continue anyway but note gaps
                    domain_data.quality_summary["validation_gaps"] = gaps
                else:
                    print(f"✅ Domain {domain_id} complete")
                    domain_data.status = DomainStatus.COMPLETED
                
                # Save to database
                database.domains[domain_id] = domain_data
                database.current_domain = domain_id + 1
                
                # Checkpoint save
                session_manager.save(database)
                print(f"💾 Checkpoint saved")
                
            except Exception as e:
                print(f"❌ Domain {domain_id} failed: {e}")
                database.domains[domain_id] = DomainData(
                    domain_id=domain_id,
                    domain_name=domain.domain_name,
                    status=DomainStatus.FAILED,
                    search_log=[],
                    tables=[],
                    quality_summary={"error": str(e)}
                )
                session_manager.save(database)
                raise
        
        # Final export
        database.overall_status = "completed"
        database.completeness_score = self._calculate_completeness(database)
        session_manager.save(database)
        
        return database
    
    def _execute_domain(self, domain: BaseDomain, disease: str, country: str) -> DomainData:
        """Execute research for a single domain."""
        
        domain_data = DomainData(
            domain_id=domain.domain_id,
            domain_name=domain.domain_name,
            status=DomainStatus.IN_PROGRESS,
            search_log=[],
            tables=[],
            quality_summary={},
            started_at=datetime.now()
        )
        
        # Generate search queries
        queries = domain.generate_search_queries(disease, country)
        
        # Execute searches
        all_results = []
        all_contents = []
        
        for i, query in enumerate(queries):
            print(f"  🔍 Search {i+1}/{len(queries)}: {query[:50]}...")
            
            results = self.search_client.search(query, country=country)
            all_results.extend(results[:3])  # Top 3 per query
            
            # Fetch top result content
            if results:
                content = self.web_fetcher.fetch(results[0].url)
                all_contents.append(content)
            
            # Rate limiting
            time.sleep(self.config.search_delay_seconds)
        
        print(f"  📊 Synthesizing {len(all_results)} search results...")
        
        # Synthesize with Claude
        synthesis_result = self.synthesizer.synthesize_domain(
            domain_prompt=domain.synthesis_prompt.format(
                disease=disease,
                country=country,
                table_schemas=json.dumps(domain.table_schemas, indent=2)
            ),
            search_results=all_results,
            page_contents=all_contents
        )
        
        # Populate domain data from synthesis
        domain_data.search_log = [
            SearchLogEntry(**entry) for entry in synthesis_result.get("search_log", [])
        ]
        domain_data.tables = [
            DataTable(table_name=name, **data)
            for name, data in synthesis_result.get("tables", {}).items()
        ]
        domain_data.quality_summary = synthesis_result.get("quality_summary", {})
        domain_data.completed_at = datetime.now()
        
        return domain_data
    
    def _calculate_completeness(self, database: PatientJourneyDatabase) -> float:
        """Calculate overall database completeness score."""
        completed = sum(
            1 for d in database.domains.values()
            if d.status == DomainStatus.COMPLETED
        )
        return completed / 7 * 100
```

### 10. CLI Entry Point (`main.py`)

```python
import click
from core.orchestrator import PatientJourneyOrchestrator
from output.json_exporter import export_to_json
from output.markdown_exporter import export_to_markdown
from config import Settings

@click.command()
@click.option('--disease', '-d', required=True, help='Disease area (e.g., "Chronic Spontaneous Urticaria")')
@click.option('--country', '-c', required=True, help='Target country (e.g., "Sweden")')
@click.option('--start-domain', '-s', default=1, help='Domain to start from (1-7)')
@click.option('--end-domain', '-e', default=7, help='Domain to end at (1-7)')
@click.option('--output-format', '-o', type=click.Choice(['json', 'markdown', 'both']), default='both')
def main(disease: str, country: str, start_domain: int, end_domain: int, output_format: str):
    """
    Patient Journey Database Builder
    
    Automates pharmaceutical patient journey research across 7 domains:
    1. Epidemiology
    2. Healthcare Finances
    3. Competitive Landscape
    4. Clinical Pathways
    5. Patient Experience
    6. Patient Segmentation
    7. Stakeholder Mapping
    """
    
    # Load configuration
    config = Settings()
    
    # Initialize orchestrator
    orchestrator = PatientJourneyOrchestrator(config)
    
    # Run research
    database = orchestrator.run(
        disease=disease,
        country=country,
        start_domain=start_domain,
        end_domain=end_domain
    )
    
    # Export results
    output_base = f"{config.output_dir}/{country.lower()}_{disease.lower().replace(' ', '_')}"
    
    if output_format in ['json', 'both']:
        json_path = export_to_json(database, f"{output_base}_database.json")
        click.echo(f"📄 JSON exported: {json_path}")
    
    if output_format in ['markdown', 'both']:
        md_path = export_to_markdown(database, f"{output_base}_database.md")
        click.echo(f"📝 Markdown exported: {md_path}")
    
    click.echo(f"\n✅ Database complete! Completeness: {database.completeness_score:.1f}%")

if __name__ == "__main__":
    main()
```

---

## Implementation Phases

### Phase 1: Foundation (Day 1-2)
1. Set up project structure
2. Implement configuration and settings
3. Create Pydantic data models
4. Implement search cache
5. Build Brave Search client
6. Build web content fetcher
7. Write unit tests for search components

### Phase 2: Claude Integration (Day 2-3)
1. Implement Claude synthesis client
2. Build prompt templates
3. Create structured output parser
4. Test synthesis with sample data
5. Handle rate limiting and retries

### Phase 3: Domain Implementation (Day 3-5)
1. Implement base domain class
2. Port Domain 1 (Epidemiology) prompts from existing skill
3. Port remaining 6 domains
4. Implement validation logic per domain
5. Test each domain independently

### Phase 4: Orchestration (Day 5-6)
1. Implement session manager
2. Build main orchestrator
3. Add checkpoint/resume logic
4. Implement CLI
5. End-to-end testing

### Phase 5: Export & Polish (Day 6-7)
1. JSON exporter
2. Markdown exporter with templates
3. Error handling improvements
4. Documentation
5. Final testing with real disease/country

---

## Key Files to Reference

The existing skill files contain the proven prompts and schemas. These should be read and ported:

1. **`/mnt/skills/user/pharmaceutical-patient-journey/SKILL.md`** - Main skill definition with domain schemas
2. **`/mnt/project/SWEDEN_CSU_DATABASE.md`** - Example output showing all 7 domains with exact table structures
3. **`/mnt/project/CSU_SWEDEN_PIVOT_POINTS_ANALYSIS.md`** - Example analytical output (optional future feature)

---

## Dependencies (`requirements.txt`)

```
anthropic>=0.25.0
httpx>=0.27.0
beautifulsoup4>=4.12.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
click>=8.1.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

---

## Environment Variables (`.env.example`)

```
ANTHROPIC_API_KEY=sk-ant-...
BRAVE_API_KEY=BSA...
CLAUDE_MODEL=claude-sonnet-4-20250514
CACHE_DIR=data/cache
SESSION_DIR=data/sessions
OUTPUT_DIR=data/outputs
```

---

## Usage Examples

```bash
# Full run for new disease/country
python main.py --disease "Atopic Dermatitis" --country "Germany"

# Resume from Domain 4
python main.py --disease "Atopic Dermatitis" --country "Germany" --start-domain 4

# Run only specific domains
python main.py --disease "Psoriasis" --country "UK" --start-domain 1 --end-domain 3

# JSON output only
python main.py --disease "CSU" --country "Sweden" --output-format json
```

---

## Success Criteria

1. **Functional**: Can produce a complete 7-domain database comparable to the manual CSU Sweden example
2. **Resumable**: Can restart from any domain after failure
3. **Cached**: Search results are cached to avoid redundant API calls
4. **Validated**: Each domain is validated before proceeding
5. **Exportable**: Outputs both JSON and Markdown formats
6. **Cost-effective**: Optimizes API usage through caching and batching

---

## Notes for Implementation

1. **Read the existing skill first** - The prompts in `/mnt/skills/user/pharmaceutical-patient-journey/SKILL.md` are battle-tested and should be ported carefully

2. **Match the output structure** - The tables in `SWEDEN_CSU_DATABASE.md` define exactly what the synthesis should produce

3. **Language handling** - Some queries may need local language variants (e.g., Swedish terms for Swedish market)

4. **Source quality** - Prioritize academic sources (PubMed, registries) over general web content

5. **Error resilience** - Handle rate limits, timeouts, and empty results gracefully
