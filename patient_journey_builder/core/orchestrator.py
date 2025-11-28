"""
Main orchestrator for patient journey database creation.

Supports two modes:
1. Standard mode: Brave Search API + web fetch + Claude synthesis
2. Intelligent mode: Claude with web search for integrated research
"""

import time
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from ..config import Settings
from ..models import (
    PatientJourneyDatabase,
    DomainData,
    DomainStatus,
    DataTable,
    SearchLogEntry,
    QualitySummary,
)
from ..search import SearchCache, BraveSearchClient, WebFetcher
from ..synthesis import ClaudeSynthesizer, IntelligentResearchClient
from ..domains import get_domain, get_all_domains
from ..utils import (
    CostTracker,
    ProgressLogger,
    AdaptiveRateLimiter,
)
from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class PatientJourneyOrchestrator:
    """
    Main orchestrator for patient journey database creation.

    Coordinates all components to:
    1. Execute search queries for each domain
    2. Fetch and extract web content
    3. Synthesize data with Claude
    4. Validate and store results
    5. Track costs and progress
    """

    def __init__(
        self,
        config: Settings,
        cost_tracker: Optional[CostTracker] = None,
        use_cache: bool = True,
        intelligent_mode: bool = False
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Application settings
            cost_tracker: Optional cost tracker
            use_cache: Whether to use caching
            intelligent_mode: Use Claude intelligent search instead of Brave API
        """
        self.config = config
        self.intelligent_mode = intelligent_mode

        # Initialize cache (used in standard mode)
        self.cache = SearchCache(
            cache_dir=config.cache_dir,
            enabled=use_cache
        )

        # Initialize rate limiters
        self.search_rate_limiter = AdaptiveRateLimiter(
            base_delay=config.search_delay_seconds
        )
        self.fetch_rate_limiter = AdaptiveRateLimiter(
            base_delay=0.5
        )

        # Initialize clients based on mode
        if intelligent_mode:
            # Intelligent mode: Claude does search + synthesis
            self.intelligent_client = IntelligentResearchClient(
                api_key=config.anthropic_api_key,
                model=config.claude_model,
                max_output_tokens=config.max_output_tokens,
                cost_tracker=cost_tracker,
                max_search_iterations=15
            )
            self.search_client = None
            self.web_fetcher = None
        else:
            # Standard mode: Brave Search + fetch + Claude synthesis
            self.intelligent_client = None
            self.search_client = BraveSearchClient(
                api_key=config.brave_api_key,
                cache=self.cache,
                rate_limiter=self.search_rate_limiter
            )
            self.web_fetcher = WebFetcher(
                cache=self.cache,
                rate_limiter=self.fetch_rate_limiter,
                enable_pdf=config.enable_pdf_extraction
            )

        # Cost tracker
        self.cost_tracker = cost_tracker

        # Initialize synthesizer (created per-run to use cost tracker)
        self.synthesizer: Optional[ClaudeSynthesizer] = None

        # Progress logger
        self.progress = ProgressLogger()

        # Get all domains
        self.domains = get_all_domains()

    def run(
        self,
        disease: str,
        country: str,
        start_domain: int = 1,
        end_domain: int = 7,
        major_city: str = ""
    ) -> PatientJourneyDatabase:
        """
        Run the patient journey database creation.

        Args:
            disease: Disease area (e.g., "Chronic Spontaneous Urticaria")
            country: Target country (e.g., "Sweden")
            start_domain: Domain to start from (for resumption)
            end_domain: Domain to end at
            major_city: Optional major city for localization

        Returns:
            Completed PatientJourneyDatabase
        """
        run_start = time.time()

        # Initialize session
        session_manager = SessionManager(
            disease=disease,
            country=country,
            session_dir=self.config.session_dir
        )
        database = session_manager.load_or_create()

        # Update cost tracker with session info
        if self.cost_tracker:
            self.cost_tracker.run_costs.disease = disease
            self.cost_tracker.run_costs.country = country

        # Initialize synthesizer with cost tracker
        self.synthesizer = ClaudeSynthesizer(
            api_key=self.config.anthropic_api_key,
            model=self.config.claude_model,
            max_output_tokens=self.config.max_output_tokens,
            cost_tracker=self.cost_tracker
        )

        # Log session start
        self.progress.session_start(disease, country, start_domain, end_domain)

        # Process each domain
        for domain_id in range(start_domain, end_domain + 1):
            domain = self.domains[domain_id]
            domain_start = time.time()

            # Start domain tracking
            if self.cost_tracker:
                self.cost_tracker.start_domain(domain_id, domain.domain_name)

            self.progress.domain_start(
                domain_id,
                domain.domain_name,
                len(domain.search_queries)
            )

            try:
                # Execute domain research (mode depends on initialization)
                if self.intelligent_mode:
                    domain_data = self._execute_domain_intelligent(
                        domain=domain,
                        disease=disease,
                        country=country
                    )
                else:
                    domain_data = self._execute_domain(
                        domain=domain,
                        disease=disease,
                        country=country,
                        major_city=major_city
                    )

                # Validate completeness
                is_complete, gaps = domain.validate_completeness(domain_data)

                domain_duration = time.time() - domain_start

                if not is_complete:
                    if self.config.strict_mode:
                        raise ValueError(f"Domain {domain_id} validation failed: {gaps}")

                    domain_data.status = DomainStatus.COMPLETED
                    domain_data.quality_summary.validation_gaps = gaps
                else:
                    domain_data.status = DomainStatus.COMPLETED

                domain_data.completed_at = datetime.now()

                # Log domain completion
                self.progress.domain_complete(
                    domain_id=domain_id,
                    tables_populated=len(domain_data.tables),
                    gaps=gaps,
                    duration_seconds=domain_duration
                )

                # End domain cost tracking
                if self.cost_tracker:
                    self.cost_tracker.end_domain(domain_duration)

                # Save to database
                database.set_domain(domain_data)
                database.current_domain = domain_id + 1

                # Checkpoint save
                session_manager.save(database)
                self.progress.checkpoint_saved(session_manager.session_id)

            except Exception as e:
                logger.error(f"Domain {domain_id} failed: {e}")
                self.progress.domain_failed(domain_id, str(e))

                # Save failed state
                if domain_id not in database.domains:
                    database.domains[domain_id] = DomainData(
                        domain_id=domain_id,
                        domain_name=domain.domain_name,
                        status=DomainStatus.FAILED,
                        quality_summary=QualitySummary(
                            validation_gaps=[f"Error: {str(e)}"]
                        )
                    )
                else:
                    database.domains[domain_id].status = DomainStatus.FAILED

                session_manager.save(database)

                if self.config.strict_mode:
                    raise

        # Finalize
        database.overall_status = "completed"
        database.completeness_score = database.calculate_completeness()

        # Calculate total cost
        if self.cost_tracker:
            database.total_cost_usd = self.cost_tracker.run_costs.total_cost

        session_manager.save(database)

        # Log final summary
        run_duration = time.time() - run_start
        self.progress.final_summary(
            disease=disease,
            country=country,
            completeness=database.completeness_score,
            total_duration=run_duration,
            total_cost=database.total_cost_usd
        )

        return database

    def _execute_domain(
        self,
        domain,
        disease: str,
        country: str,
        major_city: str
    ) -> DomainData:
        """
        Execute research for a single domain.

        Args:
            domain: Domain instance
            disease: Disease name
            country: Target country
            major_city: Major city for localization

        Returns:
            DomainData with research results
        """
        domain_data = domain.create_domain_data()
        domain_data.status = DomainStatus.IN_PROGRESS

        # Generate search queries
        queries = domain.generate_search_queries(disease, country, major_city)

        # Execute searches
        all_results = []
        all_contents = []
        search_log = []
        cached_count = 0

        for i, query in enumerate(queries):
            self.progress.search_progress(i + 1, len(queries), query)

            # Execute search
            results, was_cached = self.search_client.search(
                query=query,
                country=self._get_country_code(country),
                count=self.config.max_search_results
            )

            if was_cached:
                cached_count += 1

            # Track in cost tracker
            if self.cost_tracker:
                self.cost_tracker.record_search(cached=was_cached)

            # Add top results
            for result in results[:self.config.top_results_to_fetch]:
                all_results.append(result.model_dump())

                # Fetch content
                fetched = self.web_fetcher.fetch(result.url)

                if self.cost_tracker:
                    self.cost_tracker.record_fetch(
                        cached=fetched.fetch_time_ms == 0,
                        success=fetched.success
                    )

                all_contents.append(fetched.content if fetched.success else None)

            # Log search
            search_log.append(SearchLogEntry(
                query=query,
                source_found=results[0].source if results else "",
                key_data_points=f"Found {len(results)} results",
                cached=was_cached,
                results_count=len(results)
            ))

            # Rate limiting between queries
            if not was_cached and i < len(queries) - 1:
                time.sleep(self.config.search_delay_seconds)

        self.progress.search_complete(len(all_results), cached_count)

        # Synthesize results
        self.progress.synthesis_start(len(all_results))

        synthesis_prompt = domain.get_synthesis_prompt(disease, country)

        parse_result, metrics = self.synthesizer.synthesize_domain(
            domain_prompt=synthesis_prompt,
            search_results=all_results,
            page_contents=all_contents,
            required_tables=domain.required_tables,
            max_retries=self.config.max_synthesis_retries
        )

        # Build domain data from results
        domain_data.search_log = search_log
        domain_data.raw_synthesis_output = parse_result.raw_output

        # Convert parsed tables to DataTable objects
        for table_name, table_data in parse_result.tables.items():
            domain_data.tables.append(DataTable(
                table_name=table_name,
                headers=table_data.get('headers', []),
                rows=table_data.get('rows', []),
                sources=table_data.get('sources', []),
                confidence_level=table_data.get('confidence_level', 'MEDIUM'),
                data_gaps=table_data.get('data_gaps', [])
            ))

        # Quality summary
        domain_data.quality_summary = QualitySummary(
            searches_completed=len(queries),
            tables_populated=len(domain_data.tables),
            confidence_level=parse_result.quality_summary.get('confidence_level', 'MEDIUM'),
            primary_source_quality=parse_result.quality_summary.get('primary_source_quality', 'MEDIUM'),
            data_recency=parse_result.quality_summary.get('data_recency', 'Unknown'),
            parse_method=parse_result.parse_method
        )

        # Token usage
        domain_data.input_tokens = metrics.get('input_tokens', 0)
        domain_data.output_tokens = metrics.get('output_tokens', 0)
        domain_data.estimated_cost_usd = metrics.get('estimated_cost', 0.0)

        return domain_data

    def _execute_domain_intelligent(
        self,
        domain,
        disease: str,
        country: str
    ) -> DomainData:
        """
        Execute intelligent research for a single domain using Claude web search.

        This method uses Claude's built-in web search capability for more
        intelligent, iterative research that produces higher quality output.

        Args:
            domain: Domain instance
            disease: Disease name
            country: Target country

        Returns:
            DomainData with research results
        """
        domain_data = domain.create_domain_data()
        domain_data.status = DomainStatus.IN_PROGRESS

        # Get synthesis prompt with table schemas
        synthesis_prompt = domain.get_synthesis_prompt(disease, country)

        # Get search query hints (these guide Claude's initial searches)
        search_hints = domain.generate_search_queries(disease, country, "")

        self.progress.synthesis_start(len(search_hints))

        # Execute intelligent research
        parse_result, metrics = self.intelligent_client.research_domain(
            domain_prompt=synthesis_prompt,
            disease=disease,
            country=country,
            domain_name=domain.domain_name,
            required_tables=domain.required_tables,
            search_queries_hint=search_hints
        )

        # Build domain data from results
        domain_data.raw_synthesis_output = parse_result.raw_output

        # Store raw response for enhanced markdown export
        domain_data.raw_response = {
            'search_log': parse_result.search_log if hasattr(parse_result, 'search_log') else [],
            'named_entities': parse_result.named_entities if hasattr(parse_result, 'named_entities') else None,
            'data_gaps': parse_result.data_gaps if hasattr(parse_result, 'data_gaps') else [],
            'sources_for_validation': parse_result.sources if hasattr(parse_result, 'sources') else []
        }

        # Also check quality_summary for these fields
        if parse_result.quality_summary:
            qs = parse_result.quality_summary
            if 'search_log' in qs:
                domain_data.raw_response['search_log'] = qs['search_log']
            if 'named_entities' in qs:
                domain_data.raw_response['named_entities'] = qs['named_entities']
            if 'data_gaps' in qs:
                domain_data.raw_response['data_gaps'] = qs['data_gaps']
            if 'sources_for_validation' in qs:
                domain_data.raw_response['sources_for_validation'] = qs['sources_for_validation']

        # Convert parsed tables to DataTable objects
        for table_name, table_data in parse_result.tables.items():
            domain_data.tables.append(DataTable(
                table_name=table_name,
                headers=table_data.get('headers', []),
                rows=table_data.get('rows', []),
                sources=table_data.get('sources', []),
                confidence_level=table_data.get('confidence_level', 'MEDIUM'),
                data_gaps=table_data.get('data_gaps', [])
            ))

        # Quality summary
        domain_data.quality_summary = QualitySummary(
            searches_completed=metrics.get('search_count', 0),
            tables_populated=len(domain_data.tables),
            confidence_level=parse_result.quality_summary.get('confidence_level', 'MEDIUM') if parse_result.quality_summary else 'MEDIUM',
            primary_source_quality=parse_result.quality_summary.get('primary_source_quality', 'MEDIUM') if parse_result.quality_summary else 'MEDIUM',
            data_recency=parse_result.quality_summary.get('data_recency', 'Unknown') if parse_result.quality_summary else 'Unknown',
            parse_method=f"intelligent_search ({metrics.get('search_count', 0)} searches)"
        )

        # Token usage
        domain_data.input_tokens = metrics.get('input_tokens', 0)
        domain_data.output_tokens = metrics.get('output_tokens', 0)
        domain_data.estimated_cost_usd = metrics.get('estimated_cost', 0.0)

        self.progress.synthesis_complete(
            len(domain_data.tables),
            parse_result.success
        )

        return domain_data

    def _get_country_code(self, country: str) -> str:
        """
        Get two-letter country code.

        Args:
            country: Country name

        Returns:
            Two-letter country code
        """
        country_codes = {
            'sweden': 'SE',
            'germany': 'DE',
            'united kingdom': 'GB',
            'uk': 'GB',
            'france': 'FR',
            'spain': 'ES',
            'italy': 'IT',
            'netherlands': 'NL',
            'belgium': 'BE',
            'denmark': 'DK',
            'norway': 'NO',
            'finland': 'FI',
            'usa': 'US',
            'united states': 'US',
            'canada': 'CA',
            'australia': 'AU',
            'japan': 'JP',
        }
        return country_codes.get(country.lower(), 'US')

    def estimate_run(
        self,
        disease: str,
        country: str,
        start_domain: int = 1,
        end_domain: int = 7
    ) -> Dict[str, Any]:
        """
        Estimate cost and time for a run without executing.

        Args:
            disease: Disease name
            country: Target country
            start_domain: Starting domain
            end_domain: Ending domain

        Returns:
            Dictionary with estimates
        """
        from ..utils import estimate_run_cost

        domains_to_run = end_domain - start_domain + 1
        total_queries = sum(
            len(self.domains[d].search_queries)
            for d in range(start_domain, end_domain + 1)
        )

        cost_estimate = estimate_run_cost(
            domains=domains_to_run,
            searches_per_domain=self.config.searches_per_domain,
            model=self.config.claude_model
        )

        return {
            'disease': disease,
            'country': country,
            'domains': domains_to_run,
            'total_queries': total_queries,
            'estimated_time_minutes': domains_to_run * 5,  # ~5 min per domain
            **cost_estimate
        }

    def close(self) -> None:
        """Clean up resources."""
        if self.search_client:
            self.search_client.close()
        if self.web_fetcher:
            self.web_fetcher.close()
