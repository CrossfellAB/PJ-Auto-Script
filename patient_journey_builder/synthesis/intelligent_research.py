"""
Intelligent research client using Claude with web search capability.

This replaces the Brave API + fetch + synthesis approach with a single
Claude session that does intelligent, iterative research.
"""

from anthropic import Anthropic, APIError, RateLimitError as AnthropicRateLimitError
from typing import Dict, Any, List, Optional, Tuple
import json
import time
import logging

from ..utils import CostTracker
from .output_parser import OutputParser, ParseResult

logger = logging.getLogger(__name__)


class IntelligentResearchClient:
    """
    Uses Claude with web search for intelligent domain research.

    Instead of:
    1. Execute predefined searches with Brave API
    2. Fetch pages
    3. Pass content to Claude for synthesis

    This client:
    1. Gives Claude a comprehensive research task
    2. Claude uses web search iteratively as needed
    3. Claude extracts and validates data in real-time
    4. Claude synthesizes findings into structured output

    Benefits:
    - Intelligent query formation (Claude decides what to search)
    - Real-time validation and cross-checking
    - Iterative refinement based on findings
    - Higher quality extraction (Claude reads and understands)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_output_tokens: int = 16000,
        cost_tracker: Optional[CostTracker] = None,
        max_search_iterations: int = 15
    ):
        """
        Initialize the intelligent research client.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            max_output_tokens: Maximum tokens for output
            cost_tracker: Optional cost tracker
            max_search_iterations: Max search tool uses per domain
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.cost_tracker = cost_tracker
        self.max_search_iterations = max_search_iterations
        self.output_parser = OutputParser()

    def research_domain(
        self,
        domain_prompt: str,
        disease: str,
        country: str,
        domain_name: str,
        required_tables: List[str],
        search_queries_hint: Optional[List[str]] = None
    ) -> Tuple[ParseResult, Dict[str, Any]]:
        """
        Execute intelligent research for a single domain.

        Args:
            domain_prompt: The domain synthesis prompt (with table schemas)
            disease: Disease/condition name
            country: Target country
            domain_name: Name of the domain being researched
            required_tables: Tables that must be populated
            search_queries_hint: Optional suggested queries to start with

        Returns:
            Tuple of (ParseResult, metrics dict)
        """
        start_time = time.time()
        total_input_tokens = 0
        total_output_tokens = 0
        search_count = 0

        # Build the research task prompt
        research_prompt = self._build_research_prompt(
            domain_prompt=domain_prompt,
            disease=disease,
            country=country,
            domain_name=domain_name,
            search_queries_hint=search_queries_hint
        )

        # Define web search tool
        tools = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": self.max_search_iterations
            }
        ]

        messages = [
            {
                "role": "user",
                "content": research_prompt
            }
        ]

        logger.info(f"Starting intelligent research for {domain_name}")

        try:
            # Execute research with tool use loop
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_output_tokens,
                tools=tools,
                messages=messages
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Count search tool uses from the response
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    if block.name == 'web_search':
                        search_count += 1

            # Extract the final text response
            final_text = ""
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'text':
                    final_text += block.text

            duration_ms = int((time.time() - start_time) * 1000)

            # Track costs
            if self.cost_tracker:
                self.cost_tracker.record_claude_call(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    model=self.model,
                    duration_ms=duration_ms
                )
                # Track searches (web search has different pricing)
                for _ in range(search_count):
                    self.cost_tracker.record_search(cached=False)

            # Parse the final output
            parse_result = self.output_parser.parse(final_text)

            # Store raw response for debugging
            parse_result.raw_output = final_text

            metrics = {
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'duration_ms': duration_ms,
                'search_count': search_count,
                'parse_success': parse_result.success,
                'parse_method': parse_result.parse_method,
                'estimated_cost': self._estimate_cost(
                    total_input_tokens,
                    total_output_tokens,
                    search_count
                )
            }

            logger.info(
                f"Research completed: {search_count} searches, "
                f"{total_input_tokens} in, {total_output_tokens} out"
            )

            return parse_result, metrics

        except AnthropicRateLimitError as e:
            logger.error(f"Rate limited by Anthropic API: {e}")
            raise
        except APIError as e:
            logger.error(f"API error during research: {e}")
            raise

    def _build_research_prompt(
        self,
        domain_prompt: str,
        disease: str,
        country: str,
        domain_name: str,
        search_queries_hint: Optional[List[str]] = None
    ) -> str:
        """Build the comprehensive research task prompt."""

        hint_section = ""
        if search_queries_hint:
            hint_section = f"""
## SUGGESTED STARTING QUERIES
These are suggested queries to begin your research. You may modify them or create new queries as needed:
{chr(10).join(f'- {q}' for q in search_queries_hint[:5])}
"""

        return f"""# PATIENT JOURNEY RESEARCH TASK

## OBJECTIVE
You are conducting comprehensive pharmaceutical market research on **{disease}** in **{country}**.

You are researching **{domain_name}**.

## RESEARCH INSTRUCTIONS

You have access to web search. Use it strategically to:

1. **Search iteratively** - Start with broad queries, then narrow based on findings
2. **Verify key statistics** - Cross-check important numbers across multiple sources
3. **Find {country}-specific data** - Prioritize local sources over international proxies
4. **Identify named entities** - Find actual names of KOLs, institutions, organizations
5. **Document sources** - Track every source for validation

## RESEARCH METHODOLOGY

For each piece of data you find:
1. Note the source (author, publication, year)
2. Assess confidence (HIGH for {country} registry data, MEDIUM for European proxies, LOW for estimates)
3. Look for corroborating sources when possible

If you cannot find specific data after searching:
- Document the gap explicitly
- Note what searches you tried
- Use "NOT_FOUND" rather than making up data

{hint_section}

## OUTPUT REQUIREMENTS

After completing your research, provide your findings in the following JSON format:

{domain_prompt}

## IMPORTANT REMINDERS

- Use web search to find real, verifiable data - do NOT make up statistics
- Focus on {country}-specific data - use local currency, local institutions
- Name actual people and organizations - not placeholders
- Document every source for validation
- Be explicit about data gaps - this is valuable information

Begin your research now. Use web search to gather the information needed to populate all required tables.
"""

    def _estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        search_count: int
    ) -> float:
        """Estimate cost including web search."""
        # Claude Sonnet pricing (approximate)
        input_cost = input_tokens * 0.003 / 1000
        output_cost = output_tokens * 0.015 / 1000

        # Web search cost (approximate - varies by usage)
        search_cost = search_count * 0.01  # Estimate $0.01 per search

        return input_cost + output_cost + search_cost


class IntelligentResearchOrchestrator:
    """
    Orchestrates intelligent research across all domains.

    This is a simpler alternative to the full orchestrator when
    using intelligent search mode.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        cost_tracker: Optional[CostTracker] = None
    ):
        """Initialize the orchestrator."""
        self.client = IntelligentResearchClient(
            api_key=api_key,
            model=model,
            cost_tracker=cost_tracker
        )
        self.cost_tracker = cost_tracker

    def research_all_domains(
        self,
        disease: str,
        country: str,
        domains: Dict[int, Any],
        start_domain: int = 1,
        end_domain: int = 7,
        progress_callback: Optional[callable] = None
    ) -> Dict[int, Tuple[ParseResult, Dict[str, Any]]]:
        """
        Research all domains using intelligent search.

        Args:
            disease: Disease/condition name
            country: Target country
            domains: Dictionary of domain implementations
            start_domain: First domain to research
            end_domain: Last domain to research
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary mapping domain_id to (ParseResult, metrics)
        """
        results = {}

        for domain_id in range(start_domain, end_domain + 1):
            domain = domains[domain_id]

            if progress_callback:
                progress_callback(domain_id, domain.domain_name, "starting")

            # Get synthesis prompt
            synthesis_prompt = domain.get_synthesis_prompt(disease, country)

            # Get search query hints
            search_hints = domain.generate_search_queries(disease, country)

            try:
                result, metrics = self.client.research_domain(
                    domain_prompt=synthesis_prompt,
                    disease=disease,
                    country=country,
                    domain_name=domain.domain_name,
                    required_tables=domain.required_tables,
                    search_queries_hint=search_hints
                )

                results[domain_id] = (result, metrics)

                if progress_callback:
                    progress_callback(
                        domain_id,
                        domain.domain_name,
                        "completed",
                        metrics
                    )

            except Exception as e:
                logger.error(f"Domain {domain_id} research failed: {e}")

                if progress_callback:
                    progress_callback(
                        domain_id,
                        domain.domain_name,
                        "failed",
                        {"error": str(e)}
                    )

                # Create empty result for failed domain
                empty_result = ParseResult(
                    success=False,
                    tables={},
                    quality_summary={},
                    parse_method="failed",
                    raw_output=""
                )
                results[domain_id] = (empty_result, {"error": str(e)})

        return results
