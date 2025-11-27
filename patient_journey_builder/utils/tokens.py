"""
Token management utilities for context window optimization.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Try to import tiktoken, fall back to estimation if unavailable
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except Exception:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken unavailable, using character-based token estimation")


@dataclass
class TokenBudget:
    """Defines token allocation for a synthesis request."""

    total_context: int = 180000  # Claude's context window
    system_prompt: int = 2000
    domain_prompt: int = 3000
    output_reserved: int = 8000
    safety_margin: int = 5000

    @property
    def available_for_content(self) -> int:
        """Tokens available for search results and page content."""
        return (
            self.total_context
            - self.system_prompt
            - self.domain_prompt
            - self.output_reserved
            - self.safety_margin
        )


class TokenManager:
    """
    Manages token counting and context window optimization.

    Uses tiktoken for accurate token counting when available,
    falls back to character-based estimation otherwise.
    """

    # Average characters per token (empirically ~4 for English text)
    CHARS_PER_TOKEN = 4

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the token manager.

        Args:
            model: Claude model name (used for cost estimation)
        """
        self.encoding = None
        self.use_tiktoken = False

        if TIKTOKEN_AVAILABLE:
            try:
                # Use cl100k_base encoding (closest to Claude's tokenizer)
                self.encoding = tiktoken.get_encoding("cl100k_base")
                self.use_tiktoken = True
            except Exception as e:
                logger.warning(f"Failed to load tiktoken encoding: {e}")

        self.model = model
        self.budget = TokenBudget()

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        if self.use_tiktoken and self.encoding:
            return len(self.encoding.encode(text))
        else:
            # Fallback: estimate ~4 characters per token
            return len(text) // self.CHARS_PER_TOKEN

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to fit within token limit.

        Args:
            text: Text to truncate
            max_tokens: Maximum tokens allowed

        Returns:
            Truncated text
        """
        if self.use_tiktoken and self.encoding:
            tokens = self.encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text
            truncated_tokens = tokens[:max_tokens]
            return self.encoding.decode(truncated_tokens) + "\n[...truncated]"
        else:
            # Fallback: truncate by characters
            max_chars = max_tokens * self.CHARS_PER_TOKEN
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "\n[...truncated]"

    def prioritize_content(
        self,
        search_results: List[Dict[str, Any]],
        page_contents: List[Optional[str]],
        max_tokens: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], List[Optional[str]]]:
        """
        Prioritize and truncate content to fit within token budget.

        Strategy:
        1. Prioritize by source quality (academic > government > commercial)
        2. Include more results from high-priority sources
        3. Truncate individual pages to fit

        Args:
            search_results: List of search result dicts
            page_contents: List of fetched page contents
            max_tokens: Optional override for token budget

        Returns:
            Tuple of (filtered_results, filtered_contents)
        """
        if max_tokens is None:
            max_tokens = self.budget.available_for_content

        if not search_results:
            return [], []

        # Score and sort results by quality
        scored_results = []
        for i, (result, content) in enumerate(zip(search_results, page_contents)):
            score = self._score_source(result)
            content_tokens = self.count_tokens(content) if content else 0
            scored_results.append({
                'index': i,
                'result': result,
                'content': content,
                'score': score,
                'tokens': content_tokens
            })

        # Sort by score (descending)
        scored_results.sort(key=lambda x: x['score'], reverse=True)

        # Greedily select content within budget
        selected_results = []
        selected_contents = []
        remaining_tokens = max_tokens

        # Reserve tokens per source (diminishing returns)
        tokens_per_source = max_tokens // min(len(scored_results), 15)

        for item in scored_results:
            if remaining_tokens <= 1000:  # Minimum useful content
                break

            # Allocate tokens for this source
            source_budget = min(tokens_per_source, remaining_tokens)

            if item['content']:
                truncated = self.truncate_to_tokens(item['content'], source_budget)
                actual_tokens = self.count_tokens(truncated)
            else:
                truncated = None
                actual_tokens = 0

            # Add result metadata (always include, small token cost)
            result_tokens = self.count_tokens(
                f"{item['result'].get('title', '')} {item['result'].get('description', '')}"
            )

            selected_results.append(item['result'])
            selected_contents.append(truncated)
            remaining_tokens -= (actual_tokens + result_tokens + 50)  # 50 for formatting

        logger.info(
            f"Content prioritized: {len(selected_results)}/{len(search_results)} sources, "
            f"{max_tokens - remaining_tokens}/{max_tokens} tokens used"
        )

        return selected_results, selected_contents

    def _score_source(self, result: Dict[str, Any]) -> int:
        """
        Score a source by quality/relevance.
        Higher score = higher priority.

        Args:
            result: Search result dictionary

        Returns:
            Quality score (higher = better)
        """
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()

        score = 50  # Base score

        # Academic/research sources (highest priority)
        if any(domain in url for domain in [
            'pubmed', 'ncbi.nlm.nih.gov', 'sciencedirect',
            'springer', 'wiley', 'nature.com', 'bmj.com',
            'thelancet', 'nejm.org', '.edu', 'researchgate',
            'doi.org', 'journals.'
        ]):
            score += 40

        # Government/registry sources (high priority)
        elif any(domain in url for domain in [
            '.gov', 'who.int', 'ema.europa.eu', 'fda.gov',
            'nice.org.uk', 'socialstyrelsen.se', 'folkhalsomyndigheten',
            'rki.de', 'nhs.uk', 'cdc.gov'
        ]):
            score += 35

        # Medical organization sources
        elif any(domain in url for domain in [
            'mayoclinic', 'webmd', 'medscape', 'uptodate',
            'medlineplus', 'patient.info', 'healthline'
        ]):
            score += 25

        # Pharma company sources (useful but potentially biased)
        elif any(domain in url for domain in [
            'novartis', 'pfizer', 'roche', 'abbvie',
            'sanofi', 'gsk', 'astrazeneca', 'merck',
            'johnson', 'lilly', 'bayer'
        ]):
            score += 15

        # Boost for recent data indicators in title
        if any(year in title for year in ['2025', '2024', '2023', '2022']):
            score += 10

        # Boost for epidemiology/statistics keywords
        if any(kw in title for kw in [
            'prevalence', 'incidence', 'epidemiology', 'registry',
            'population', 'statistics', 'survey', 'study',
            'trial', 'analysis', 'cohort', 'meta-analysis'
        ]):
            score += 10

        return score

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None
    ) -> float:
        """
        Estimate API cost for a request.

        Pricing (as of 2024):
        - Claude Sonnet: $3/M input, $15/M output
        - Claude Opus: $15/M input, $75/M output

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Optional model override

        Returns:
            Estimated cost in USD
        """
        model = model or self.model

        if 'opus' in model.lower():
            input_rate = 15.0 / 1_000_000
            output_rate = 75.0 / 1_000_000
        else:  # sonnet or default
            input_rate = 3.0 / 1_000_000
            output_rate = 15.0 / 1_000_000

        return (input_tokens * input_rate) + (output_tokens * output_rate)

    def get_budget_status(self, used_tokens: int) -> Dict[str, Any]:
        """
        Get current budget utilization status.

        Args:
            used_tokens: Tokens already used

        Returns:
            Dictionary with budget status information
        """
        available = self.budget.available_for_content
        return {
            'total_budget': available,
            'used': used_tokens,
            'remaining': available - used_tokens,
            'utilization_percent': (used_tokens / available) * 100 if available > 0 else 0
        }
