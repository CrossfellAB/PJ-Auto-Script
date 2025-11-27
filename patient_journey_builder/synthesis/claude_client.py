"""
Claude API client for data synthesis.
"""

from anthropic import Anthropic, APIError, RateLimitError as AnthropicRateLimitError
from typing import Dict, Any, List, Optional, Tuple
import time
import logging

from ..utils import retry_api, RateLimitError, TransientError, TokenManager, CostTracker
from .output_parser import OutputParser, OutputValidator, ParseResult

logger = logging.getLogger(__name__)


class ClaudeSynthesizer:
    """
    Handles Claude API calls for data synthesis.

    Features:
    - Automatic retry with exponential backoff
    - Token management and context optimization
    - Cost tracking
    - Robust output parsing
    - Synthesis retry for incomplete results
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_output_tokens: int = 8000,
        cost_tracker: Optional[CostTracker] = None
    ):
        """
        Initialize the Claude synthesizer.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            max_output_tokens: Maximum tokens for output
            cost_tracker: Optional cost tracker instance
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.token_manager = TokenManager(model)
        self.output_parser = OutputParser()
        self.cost_tracker = cost_tracker

    def synthesize_domain(
        self,
        domain_prompt: str,
        search_results: List[Dict],
        page_contents: List[Optional[str]],
        required_tables: List[str],
        max_retries: int = 2,
        existing_gaps: Optional[List[str]] = None
    ) -> Tuple[ParseResult, Dict[str, Any]]:
        """
        Synthesize search results into structured domain data.

        Includes retry logic for incomplete results.

        Args:
            domain_prompt: The synthesis prompt for this domain
            search_results: List of search result dicts
            page_contents: List of fetched page contents
            required_tables: List of table names that must be populated
            max_retries: Number of retries if output has gaps
            existing_gaps: Known gaps to focus on (for retries)

        Returns:
            Tuple of (ParseResult, quality_metrics dict)
        """
        # Prioritize content to fit within token budget
        prioritized_results, prioritized_contents = self.token_manager.prioritize_content(
            search_results, page_contents
        )

        # Build context
        context = self._build_context(prioritized_results, prioritized_contents)

        # Prepare prompt
        prompt = domain_prompt

        # Add gap-filling instructions if retrying
        if existing_gaps:
            gap_instruction = f"""

## IMPORTANT: PREVIOUS GAPS TO ADDRESS

The following data gaps were identified in a previous attempt. Please focus on finding this information:
{chr(10).join(f'- {gap}' for gap in existing_gaps)}

If data cannot be found, mark as "NOT_FOUND" with explanation.
"""
            prompt = prompt + gap_instruction

        # Execute synthesis with retry
        result = None
        metrics = {}

        for attempt in range(max_retries + 1):
            try:
                result, metrics = self._execute_synthesis(prompt, context)

                # Validate output
                validator = OutputValidator()
                is_valid, issues = validator.validate(result, required_tables)

                if is_valid or attempt == max_retries:
                    metrics['validation_issues'] = issues
                    metrics['attempts'] = attempt + 1
                    metrics['completeness_score'] = validator.get_completeness_score(result)
                    return result, metrics

                # Retry with gap information
                logger.warning(
                    f"Synthesis incomplete (attempt {attempt + 1}), issues: {issues[:3]}"
                )
                existing_gaps = issues

            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Synthesis failed after {max_retries + 1} attempts: {e}")
                    raise
                logger.warning(f"Synthesis failed (attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)  # Exponential backoff

        # Return last result
        return result, metrics

    @retry_api
    def _execute_synthesis(
        self,
        domain_prompt: str,
        context: str
    ) -> Tuple[ParseResult, Dict[str, Any]]:
        """
        Execute a single synthesis API call.

        Decorated with retry logic for transient failures.

        Args:
            domain_prompt: The synthesis prompt
            context: Search results and content context

        Returns:
            Tuple of (ParseResult, metrics dict)
        """
        # Build messages
        full_content = f"{domain_prompt}\n\n## SEARCH RESULTS AND SOURCES\n\n{context}"

        messages = [
            {
                "role": "user",
                "content": full_content
            }
        ]

        # Count input tokens
        input_tokens = self.token_manager.count_tokens(full_content)

        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_output_tokens,
                messages=messages
            )

            duration_ms = int((time.time() - start_time) * 1000)
            output_text = response.content[0].text
            output_tokens = response.usage.output_tokens
            actual_input_tokens = response.usage.input_tokens

            # Track costs
            if self.cost_tracker:
                self.cost_tracker.record_claude_call(
                    input_tokens=actual_input_tokens,
                    output_tokens=output_tokens,
                    model=self.model,
                    duration_ms=duration_ms
                )

            # Parse output
            parse_result = self.output_parser.parse(output_text)

            metrics = {
                'input_tokens': actual_input_tokens,
                'output_tokens': output_tokens,
                'duration_ms': duration_ms,
                'parse_success': parse_result.success,
                'parse_method': parse_result.parse_method,
                'estimated_cost': self.token_manager.estimate_cost(
                    actual_input_tokens, output_tokens
                )
            }

            logger.info(
                f"Synthesis completed: {actual_input_tokens} in, {output_tokens} out, "
                f"parse={parse_result.success} ({parse_result.parse_method})"
            )

            return parse_result, metrics

        except AnthropicRateLimitError as e:
            # Convert to our retry-compatible exception
            logger.warning(f"Rate limited by Anthropic API")
            raise RateLimitError(retry_after=60.0) from e
        except APIError as e:
            if hasattr(e, 'status_code') and e.status_code >= 500:
                raise TransientError(str(e)) from e
            raise

    def _build_context(
        self,
        search_results: List[Dict],
        page_contents: List[Optional[str]]
    ) -> str:
        """
        Build context string from search results and fetched content.

        Args:
            search_results: List of search result dicts
            page_contents: List of page contents

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, (result, content) in enumerate(zip(search_results, page_contents)):
            source_info = f"""
### Source {i+1}: {result.get('title', 'Unknown')}
URL: {result.get('url', 'N/A')}
Description: {result.get('description', 'No description')}

Content:
{content if content else "[Content not available - page could not be fetched]"}
---
"""
            context_parts.append(source_info)

        return "\n".join(context_parts)

    def get_token_usage_estimate(
        self,
        domain_prompt: str,
        search_results: List[Dict],
        page_contents: List[Optional[str]]
    ) -> Dict[str, Any]:
        """
        Estimate token usage before making API call.

        Useful for cost estimation and budget checking.

        Args:
            domain_prompt: The synthesis prompt
            search_results: Search results to include
            page_contents: Page contents to include

        Returns:
            Dictionary with token usage estimates
        """
        context = self._build_context(search_results, page_contents)
        full_prompt = domain_prompt + context

        input_tokens = self.token_manager.count_tokens(full_prompt)
        estimated_output = min(self.max_output_tokens, input_tokens // 2)

        return {
            'input_tokens': input_tokens,
            'estimated_output_tokens': estimated_output,
            'estimated_cost_usd': self.token_manager.estimate_cost(
                input_tokens, estimated_output
            ),
            'context_utilization': self.token_manager.get_budget_status(input_tokens)
        }

    def simple_query(
        self,
        prompt: str,
        max_tokens: int = 2000
    ) -> str:
        """
        Execute a simple query without synthesis parsing.

        Useful for follow-up questions or clarifications.

        Args:
            prompt: The query prompt
            max_tokens: Maximum output tokens

        Returns:
            Raw response text
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text
