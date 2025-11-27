"""
API cost tracking for Patient Journey Builder.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class APICall:
    """Record of a single API call."""

    timestamp: datetime
    api_type: str  # 'search', 'fetch', 'claude'
    endpoint: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False
    cost_usd: float = 0.0
    duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class DomainCosts:
    """Cost breakdown for a single domain."""

    domain_id: int
    domain_name: str = ""
    search_calls: int = 0
    fetch_calls: int = 0
    claude_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hits: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class RunCosts:
    """Total costs for a complete run."""

    session_id: str
    disease: str = ""
    country: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    domains: Dict[int, DomainCosts] = field(default_factory=dict)
    api_calls: List[APICall] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        """Get total cost across all domains."""
        return sum(d.total_cost_usd for d in self.domains.values())

    @property
    def total_search_calls(self) -> int:
        """Get total search API calls."""
        return sum(d.search_calls for d in self.domains.values())

    @property
    def total_fetch_calls(self) -> int:
        """Get total fetch calls."""
        return sum(d.fetch_calls for d in self.domains.values())

    @property
    def total_claude_calls(self) -> int:
        """Get total Claude API calls."""
        return sum(d.claude_calls for d in self.domains.values())

    @property
    def total_tokens(self) -> tuple:
        """Get total input and output tokens."""
        input_t = sum(d.total_input_tokens for d in self.domains.values())
        output_t = sum(d.total_output_tokens for d in self.domains.values())
        return input_t, output_t

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_calls = sum(d.search_calls + d.fetch_calls for d in self.domains.values())
        cache_hits = sum(d.cache_hits for d in self.domains.values())
        return cache_hits / total_calls if total_calls > 0 else 0.0

    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()


class CostTracker:
    """
    Tracks API costs across the entire run.

    Provides detailed cost breakdown per domain and session,
    with export capabilities for analysis.
    """

    # Pricing constants (update as needed)
    PRICING = {
        'brave_search': 0.005,  # per search
        'claude_sonnet_input': 3.0 / 1_000_000,
        'claude_sonnet_output': 15.0 / 1_000_000,
        'claude_opus_input': 15.0 / 1_000_000,
        'claude_opus_output': 75.0 / 1_000_000,
    }

    def __init__(
        self,
        session_id: str,
        output_dir: str = "data/costs",
        disease: str = "",
        country: str = ""
    ):
        """
        Initialize the cost tracker.

        Args:
            session_id: Unique identifier for this session
            output_dir: Directory to save cost reports
            disease: Disease being researched
            country: Target country
        """
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.run_costs = RunCosts(
            session_id=session_id,
            disease=disease,
            country=country,
            started_at=datetime.now()
        )
        self._current_domain: Optional[int] = None

    def start_domain(self, domain_id: int, domain_name: str = "") -> None:
        """
        Start tracking costs for a domain.

        Args:
            domain_id: Domain number (1-7)
            domain_name: Human-readable domain name
        """
        self._current_domain = domain_id
        if domain_id not in self.run_costs.domains:
            self.run_costs.domains[domain_id] = DomainCosts(
                domain_id=domain_id,
                domain_name=domain_name
            )

    def end_domain(self, duration_seconds: float) -> None:
        """
        End tracking for current domain.

        Args:
            duration_seconds: Time spent on domain
        """
        if self._current_domain and self._current_domain in self.run_costs.domains:
            self.run_costs.domains[self._current_domain].duration_seconds = duration_seconds

    def record_search(self, cached: bool = False, duration_ms: int = 0) -> None:
        """
        Record a search API call.

        Args:
            cached: Whether result was from cache
            duration_ms: Call duration in milliseconds
        """
        if self._current_domain is None:
            return

        domain = self.run_costs.domains.get(self._current_domain)
        if not domain:
            return

        domain.search_calls += 1

        if cached:
            domain.cache_hits += 1
            cost = 0.0
        else:
            cost = self.PRICING['brave_search']

        domain.total_cost_usd += cost

        self.run_costs.api_calls.append(APICall(
            timestamp=datetime.now(),
            api_type='search',
            endpoint='brave_search',
            cached=cached,
            cost_usd=cost,
            duration_ms=duration_ms
        ))

    def record_fetch(self, cached: bool = False, duration_ms: int = 0, success: bool = True) -> None:
        """
        Record a web fetch (no direct cost, but track for metrics).

        Args:
            cached: Whether content was from cache
            duration_ms: Fetch duration in milliseconds
            success: Whether fetch was successful
        """
        if self._current_domain is None:
            return

        domain = self.run_costs.domains.get(self._current_domain)
        if not domain:
            return

        domain.fetch_calls += 1

        if cached:
            domain.cache_hits += 1

        self.run_costs.api_calls.append(APICall(
            timestamp=datetime.now(),
            api_type='fetch',
            endpoint='web_fetch',
            cached=cached,
            duration_ms=duration_ms,
            success=success
        ))

    def record_claude_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "sonnet",
        duration_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """
        Record a Claude API call.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name (sonnet or opus)
            duration_ms: Call duration in milliseconds
            success: Whether call was successful
            error: Error message if failed
        """
        if self._current_domain is None:
            return

        domain = self.run_costs.domains.get(self._current_domain)
        if not domain:
            return

        domain.claude_calls += 1
        domain.total_input_tokens += input_tokens
        domain.total_output_tokens += output_tokens

        # Calculate cost
        if 'opus' in model.lower():
            cost = (
                input_tokens * self.PRICING['claude_opus_input'] +
                output_tokens * self.PRICING['claude_opus_output']
            )
        else:
            cost = (
                input_tokens * self.PRICING['claude_sonnet_input'] +
                output_tokens * self.PRICING['claude_sonnet_output']
            )

        domain.total_cost_usd += cost

        self.run_costs.api_calls.append(APICall(
            timestamp=datetime.now(),
            api_type='claude',
            endpoint=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            success=success,
            error=error
        ))

        logger.debug(
            f"Claude call recorded: {input_tokens} in, {output_tokens} out, ${cost:.4f}"
        )

    def get_summary(self) -> Dict[str, Any]:
        """
        Get cost summary.

        Returns:
            Dictionary with summary statistics
        """
        input_t, output_t = self.run_costs.total_tokens
        return {
            'session_id': self.session_id,
            'disease': self.run_costs.disease,
            'country': self.run_costs.country,
            'total_cost_usd': round(self.run_costs.total_cost, 4),
            'search_calls': self.run_costs.total_search_calls,
            'fetch_calls': self.run_costs.total_fetch_calls,
            'claude_calls': self.run_costs.total_claude_calls,
            'claude_input_tokens': input_t,
            'claude_output_tokens': output_t,
            'cache_hit_rate': round(self.run_costs.cache_hit_rate * 100, 1),
            'domains_processed': len(self.run_costs.domains),
            'duration_seconds': round(self.run_costs.duration_seconds, 1)
        }

    def get_domain_summary(self, domain_id: int) -> Optional[Dict[str, Any]]:
        """
        Get summary for a specific domain.

        Args:
            domain_id: Domain number

        Returns:
            Dictionary with domain statistics or None
        """
        domain = self.run_costs.domains.get(domain_id)
        if not domain:
            return None

        return {
            'domain_id': domain.domain_id,
            'domain_name': domain.domain_name,
            'search_calls': domain.search_calls,
            'fetch_calls': domain.fetch_calls,
            'claude_calls': domain.claude_calls,
            'input_tokens': domain.total_input_tokens,
            'output_tokens': domain.total_output_tokens,
            'cache_hits': domain.cache_hits,
            'cost_usd': round(domain.total_cost_usd, 4),
            'duration_seconds': round(domain.duration_seconds, 1)
        }

    def save(self) -> Path:
        """
        Save cost data to file.

        Returns:
            Path to saved file
        """
        self.run_costs.completed_at = datetime.now()

        output_file = self.output_dir / f"{self.session_id}_costs.json"

        # Convert to serializable format
        data = {
            'session_id': self.session_id,
            'disease': self.run_costs.disease,
            'country': self.run_costs.country,
            'started_at': self.run_costs.started_at.isoformat(),
            'completed_at': self.run_costs.completed_at.isoformat(),
            'summary': self.get_summary(),
            'domains': {
                str(k): {
                    'domain_id': v.domain_id,
                    'domain_name': v.domain_name,
                    'search_calls': v.search_calls,
                    'fetch_calls': v.fetch_calls,
                    'claude_calls': v.claude_calls,
                    'total_input_tokens': v.total_input_tokens,
                    'total_output_tokens': v.total_output_tokens,
                    'cache_hits': v.cache_hits,
                    'total_cost_usd': round(v.total_cost_usd, 4),
                    'duration_seconds': round(v.duration_seconds, 1)
                }
                for k, v in self.run_costs.domains.items()
            }
        }

        output_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Cost report saved: {output_file}")

        return output_file


def estimate_run_cost(
    domains: int = 7,
    searches_per_domain: int = 17,
    avg_input_tokens: int = 150000,
    avg_output_tokens: int = 6000,
    model: str = "sonnet"
) -> Dict[str, float]:
    """
    Estimate cost for a full run.

    Args:
        domains: Number of domains to process
        searches_per_domain: Searches per domain
        avg_input_tokens: Average input tokens per domain
        avg_output_tokens: Average output tokens per domain
        model: Claude model (sonnet or opus)

    Returns:
        Dictionary with cost breakdown
    """
    total_searches = domains * searches_per_domain
    search_cost = total_searches * CostTracker.PRICING['brave_search']

    total_input = domains * avg_input_tokens
    total_output = domains * avg_output_tokens

    if 'opus' in model.lower():
        claude_cost = (
            total_input * CostTracker.PRICING['claude_opus_input'] +
            total_output * CostTracker.PRICING['claude_opus_output']
        )
    else:
        claude_cost = (
            total_input * CostTracker.PRICING['claude_sonnet_input'] +
            total_output * CostTracker.PRICING['claude_sonnet_output']
        )

    return {
        'search_cost': round(search_cost, 2),
        'claude_cost': round(claude_cost, 2),
        'total_cost': round(search_cost + claude_cost, 2),
        'total_searches': total_searches,
        'total_input_tokens': total_input,
        'total_output_tokens': total_output
    }
