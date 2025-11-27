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

## New Components: Resilience & Observability

### Architecture Update

Add these new modules to the project structure:

```
patient_journey_builder/
├── ...existing structure...
│
├── utils/
│   ├── __init__.py
│   ├── retry.py                 # Exponential backoff and retry logic
│   ├── tokens.py                # Token counting and context management
│   ├── logging_config.py        # Structured logging setup
│   └── cost_tracker.py          # API cost tracking
│
├── localization/
│   ├── __init__.py
│   ├── config.py                # Country/language configuration
│   └── translations/
│       ├── sweden.yaml
│       ├── germany.yaml
│       └── uk.yaml
│
└── ...rest of structure...
```

---

### 11. Resilience Layer (`utils/retry.py`)

```python
import asyncio
import functools
import random
from typing import TypeVar, Callable, Any, Optional, Type, Tuple
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)
import httpx
import structlog

logger = structlog.get_logger()

T = TypeVar('T')

# Custom exceptions for retry categorization
class RetryableError(Exception):
    """Base class for errors that should trigger a retry."""
    pass

class RateLimitError(RetryableError):
    """API rate limit hit."""
    def __init__(self, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after: {retry_after}s")

class TransientError(RetryableError):
    """Temporary network or server error."""
    pass

class PermanentError(Exception):
    """Error that should not be retried."""
    pass


def create_retry_decorator(
    max_attempts: int = 4,
    min_wait: float = 2.0,
    max_wait: float = 60.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        RetryableError,
        httpx.TimeoutException,
        httpx.NetworkError,
    )
):
    """
    Create a retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        retryable_exceptions: Tuple of exception types to retry on
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retryable_exceptions),
        before_sleep=before_sleep_log(logger, structlog.stdlib.INFO),
        reraise=True
    )


# Pre-configured decorators for common use cases
retry_search = create_retry_decorator(
    max_attempts=4,
    min_wait=2.0,
    max_wait=16.0
)

retry_api = create_retry_decorator(
    max_attempts=3,
    min_wait=4.0,
    max_wait=60.0
)

retry_fetch = create_retry_decorator(
    max_attempts=3,
    min_wait=1.0,
    max_wait=8.0
)


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts based on API responses.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self._consecutive_successes = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        """Wait according to current rate limit."""
        await asyncio.sleep(self.current_delay)

    def on_success(self):
        """Call after successful request to potentially decrease delay."""
        self._consecutive_successes += 1
        if self._consecutive_successes >= 5:
            self.current_delay = max(
                self.base_delay,
                self.current_delay / self.backoff_factor
            )
            self._consecutive_successes = 0

    def on_rate_limit(self, retry_after: Optional[float] = None):
        """Call when rate limited to increase delay."""
        self._consecutive_successes = 0
        if retry_after:
            self.current_delay = min(retry_after, self.max_delay)
        else:
            self.current_delay = min(
                self.current_delay * self.backoff_factor,
                self.max_delay
            )


def handle_http_error(response: httpx.Response) -> None:
    """
    Convert HTTP errors to appropriate exception types.

    Raises:
        RateLimitError: For 429 responses
        TransientError: For 5xx responses
        PermanentError: For 4xx responses (except 429)
    """
    if response.status_code == 429:
        retry_after = response.headers.get('retry-after')
        raise RateLimitError(
            retry_after=float(retry_after) if retry_after else None
        )
    elif response.status_code >= 500:
        raise TransientError(
            f"Server error: {response.status_code} - {response.text[:200]}"
        )
    elif response.status_code >= 400:
        raise PermanentError(
            f"Client error: {response.status_code} - {response.text[:200]}"
        )
```

---

### 12. Token Management (`utils/tokens.py`)

```python
import tiktoken
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

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
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        # Use cl100k_base encoding (closest to Claude's tokenizer)
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.model = model
        self.budget = TokenBudget()

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit."""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens) + "\n[...truncated]"

    def prioritize_content(
        self,
        search_results: List[Dict[str, Any]],
        page_contents: List[Optional[str]],
        max_tokens: int = None
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Prioritize and truncate content to fit within token budget.

        Strategy:
        1. Prioritize by source quality (academic > government > commercial)
        2. Include more results from high-priority sources
        3. Truncate individual pages to fit

        Returns:
            Tuple of (filtered_results, filtered_contents)
        """
        if max_tokens is None:
            max_tokens = self.budget.available_for_content

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
            "content_prioritized",
            total_sources=len(search_results),
            selected_sources=len(selected_results),
            tokens_used=max_tokens - remaining_tokens,
            token_budget=max_tokens
        )

        return selected_results, selected_contents

    def _score_source(self, result: Dict[str, Any]) -> int:
        """
        Score a source by quality/relevance.
        Higher score = higher priority.
        """
        url = result.get('url', '').lower()
        source = result.get('source', '').lower()
        title = result.get('title', '').lower()

        score = 50  # Base score

        # Academic/research sources (highest priority)
        if any(domain in url for domain in [
            'pubmed', 'ncbi.nlm.nih.gov', 'sciencedirect',
            'springer', 'wiley', 'nature.com', 'bmj.com',
            'thelancet', 'nejm.org', '.edu', 'researchgate'
        ]):
            score += 40

        # Government/registry sources (high priority)
        elif any(domain in url for domain in [
            '.gov', 'who.int', 'ema.europa.eu', 'fda.gov',
            'nice.org.uk', 'socialstyrelsen.se', 'folkhalsomyndigheten'
        ]):
            score += 35

        # Medical organization sources
        elif any(domain in url for domain in [
            'mayoclinic', 'webmd', 'medscape', 'uptodate',
            'medlineplus', 'patient.info'
        ]):
            score += 25

        # Pharma company sources (useful but potentially biased)
        elif any(domain in url for domain in [
            'novartis', 'pfizer', 'roche', 'abbvie',
            'sanofi', 'gsk', 'astrazeneca'
        ]):
            score += 15

        # Boost for recent data indicators in title
        if any(year in title for year in ['2024', '2023', '2022']):
            score += 10

        # Boost for epidemiology/statistics keywords
        if any(kw in title for kw in [
            'prevalence', 'incidence', 'epidemiology', 'registry',
            'population', 'statistics', 'survey', 'study'
        ]):
            score += 10

        return score

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = None
    ) -> float:
        """
        Estimate API cost for a request.

        Pricing (as of 2024, may need updating):
        - Claude Sonnet: $3/M input, $15/M output
        - Claude Opus: $15/M input, $75/M output
        """
        model = model or self.model

        if 'opus' in model.lower():
            input_rate = 15.0 / 1_000_000
            output_rate = 75.0 / 1_000_000
        else:  # sonnet
            input_rate = 3.0 / 1_000_000
            output_rate = 15.0 / 1_000_000

        return (input_tokens * input_rate) + (output_tokens * output_rate)
```

---

### 13. Structured Logging (`utils/logging_config.py`)

```python
import structlog
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler

def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    json_logs: bool = False
) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
        json_logs: If True, output JSON formatted logs (for production)
    """

    # Shared processors for all outputs
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        # JSON output for production/aggregation
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handlers = []

    # Console handler with Rich
    console_handler = RichHandler(
        console=Console(stderr=True),
        show_time=False,  # structlog handles this
        show_path=False,
        rich_tracebacks=True
    )
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class ProgressLogger:
    """
    Rich-based progress logging for long-running operations.
    """

    def __init__(self):
        self.console = Console()
        self.logger = structlog.get_logger()

    def domain_start(self, domain_id: int, domain_name: str, total_queries: int):
        """Log start of domain processing."""
        self.console.rule(f"[bold blue]Domain {domain_id}: {domain_name}")
        self.logger.info(
            "domain_started",
            domain_id=domain_id,
            domain_name=domain_name,
            total_queries=total_queries
        )

    def search_progress(self, current: int, total: int, query: str):
        """Log search progress."""
        truncated_query = query[:50] + "..." if len(query) > 50 else query
        self.console.print(
            f"  🔍 [{current}/{total}] {truncated_query}",
            style="dim"
        )

    def synthesis_start(self, num_sources: int):
        """Log start of synthesis."""
        self.console.print(
            f"  📊 Synthesizing {num_sources} sources...",
            style="cyan"
        )

    def domain_complete(
        self,
        domain_id: int,
        tables_populated: int,
        gaps: List[str],
        duration_seconds: float
    ):
        """Log domain completion."""
        if gaps:
            self.console.print(
                f"  ⚠️  Completed with {len(gaps)} data gaps",
                style="yellow"
            )
            for gap in gaps[:3]:  # Show first 3 gaps
                self.console.print(f"     - {gap}", style="dim yellow")
        else:
            self.console.print(
                f"  ✅ Complete ({tables_populated} tables)",
                style="green"
            )

        self.logger.info(
            "domain_completed",
            domain_id=domain_id,
            tables_populated=tables_populated,
            gaps_count=len(gaps),
            duration_seconds=round(duration_seconds, 2)
        )

    def checkpoint_saved(self, session_id: str):
        """Log checkpoint save."""
        self.console.print("  💾 Checkpoint saved", style="dim green")

    def final_summary(
        self,
        disease: str,
        country: str,
        completeness: float,
        total_duration: float,
        total_cost: float
    ):
        """Log final run summary."""
        self.console.print()
        self.console.rule("[bold green]Run Complete")
        self.console.print(f"  Disease: {disease}")
        self.console.print(f"  Country: {country}")
        self.console.print(f"  Completeness: {completeness:.1f}%")
        self.console.print(f"  Duration: {total_duration/60:.1f} minutes")
        self.console.print(f"  Estimated Cost: ${total_cost:.2f}")
```

---

### 14. Cost Tracker (`utils/cost_tracker.py`)

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import json
from pathlib import Path
import structlog

logger = structlog.get_logger()

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
    search_calls: int = 0
    fetch_calls: int = 0
    claude_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hits: int = 0
    total_cost_usd: float = 0.0


@dataclass
class RunCosts:
    """Total costs for a complete run."""
    session_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    domains: Dict[int, DomainCosts] = field(default_factory=dict)
    api_calls: List[APICall] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(d.total_cost_usd for d in self.domains.values())

    @property
    def total_search_calls(self) -> int:
        return sum(d.search_calls for d in self.domains.values())

    @property
    def total_claude_tokens(self) -> tuple:
        input_t = sum(d.total_input_tokens for d in self.domains.values())
        output_t = sum(d.total_output_tokens for d in self.domains.values())
        return input_t, output_t

    @property
    def cache_hit_rate(self) -> float:
        total_calls = sum(d.search_calls + d.fetch_calls for d in self.domains.values())
        cache_hits = sum(d.cache_hits for d in self.domains.values())
        return cache_hits / total_calls if total_calls > 0 else 0.0


class CostTracker:
    """
    Tracks API costs across the entire run.
    """

    # Pricing constants (update as needed)
    PRICING = {
        'brave_search': 0.005,  # per search
        'claude_sonnet_input': 3.0 / 1_000_000,
        'claude_sonnet_output': 15.0 / 1_000_000,
        'claude_opus_input': 15.0 / 1_000_000,
        'claude_opus_output': 75.0 / 1_000_000,
    }

    def __init__(self, session_id: str, output_dir: str = "data/costs"):
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.run_costs = RunCosts(
            session_id=session_id,
            started_at=datetime.now()
        )
        self._current_domain: Optional[int] = None

    def start_domain(self, domain_id: int):
        """Start tracking costs for a domain."""
        self._current_domain = domain_id
        if domain_id not in self.run_costs.domains:
            self.run_costs.domains[domain_id] = DomainCosts(domain_id=domain_id)

    def record_search(self, cached: bool = False, duration_ms: int = 0):
        """Record a search API call."""
        if self._current_domain is None:
            return

        domain = self.run_costs.domains[self._current_domain]
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

    def record_fetch(self, cached: bool = False, duration_ms: int = 0):
        """Record a web fetch (no direct cost, but track for metrics)."""
        if self._current_domain is None:
            return

        domain = self.run_costs.domains[self._current_domain]
        domain.fetch_calls += 1

        if cached:
            domain.cache_hits += 1

        self.run_costs.api_calls.append(APICall(
            timestamp=datetime.now(),
            api_type='fetch',
            endpoint='web_fetch',
            cached=cached,
            duration_ms=duration_ms
        ))

    def record_claude_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "sonnet",
        duration_ms: int = 0
    ):
        """Record a Claude API call."""
        if self._current_domain is None:
            return

        domain = self.run_costs.domains[self._current_domain]
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
            duration_ms=duration_ms
        ))

        logger.debug(
            "claude_call_recorded",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 4)
        )

    def get_summary(self) -> Dict:
        """Get cost summary."""
        input_t, output_t = self.run_costs.total_claude_tokens
        return {
            'session_id': self.session_id,
            'total_cost_usd': round(self.run_costs.total_cost, 4),
            'search_calls': self.run_costs.total_search_calls,
            'claude_input_tokens': input_t,
            'claude_output_tokens': output_t,
            'cache_hit_rate': round(self.run_costs.cache_hit_rate * 100, 1),
            'domains_processed': len(self.run_costs.domains)
        }

    def save(self):
        """Save cost data to file."""
        self.run_costs.completed_at = datetime.now()

        output_file = self.output_dir / f"{self.session_id}_costs.json"

        # Convert to serializable format
        data = {
            'session_id': self.session_id,
            'started_at': self.run_costs.started_at.isoformat(),
            'completed_at': self.run_costs.completed_at.isoformat(),
            'summary': self.get_summary(),
            'domains': {
                str(k): {
                    'domain_id': v.domain_id,
                    'search_calls': v.search_calls,
                    'fetch_calls': v.fetch_calls,
                    'claude_calls': v.claude_calls,
                    'total_input_tokens': v.total_input_tokens,
                    'total_output_tokens': v.total_output_tokens,
                    'cache_hits': v.cache_hits,
                    'total_cost_usd': round(v.total_cost_usd, 4)
                }
                for k, v in self.run_costs.domains.items()
            }
        }

        output_file.write_text(json.dumps(data, indent=2))
        logger.info("cost_report_saved", path=str(output_file))
```

---

### 15. Localization Configuration (`localization/config.py`)

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import yaml

@dataclass
class CountryConfig:
    """Configuration for a specific country."""
    country_code: str
    country_name: str
    language_code: str
    search_language: str

    # Local terminology for medical concepts
    medical_terms: Dict[str, str] = field(default_factory=dict)

    # Preferred data sources for this country
    priority_sources: List[str] = field(default_factory=list)

    # Government health authority domains
    health_authority_domains: List[str] = field(default_factory=list)

    # Population data
    population: Optional[int] = None
    major_cities: List[str] = field(default_factory=list)

    # Healthcare system specifics
    healthcare_system_type: str = ""  # e.g., "single-payer", "insurance-based"
    currency: str = "USD"

    def localize_query(self, query_template: str, disease: str) -> str:
        """
        Localize a search query for this country.

        Replaces placeholders and optionally adds local language terms.
        """
        query = query_template.format(
            disease=disease,
            country=self.country_name,
            major_city=self.major_cities[0] if self.major_cities else ""
        )

        # Add local language variant if available
        local_disease = self.medical_terms.get(disease.lower())
        if local_disease and local_disease != disease:
            query = f"{query} OR {local_disease}"

        return query


class LocalizationManager:
    """
    Manages country-specific configurations.
    """

    # Built-in configurations for common markets
    BUILTIN_CONFIGS = {
        'sweden': CountryConfig(
            country_code='SE',
            country_name='Sweden',
            language_code='sv',
            search_language='en',  # Search in English, most medical lit is English
            medical_terms={
                'chronic spontaneous urticaria': 'kronisk spontan urtikaria',
                'atopic dermatitis': 'atopisk dermatit',
                'psoriasis': 'psoriasis',
            },
            priority_sources=[
                'socialstyrelsen.se',
                'folkhalsomyndigheten.se',
                'lakemedelsverket.se',
                'sbu.se',
                'tlv.se',
            ],
            health_authority_domains=[
                'socialstyrelsen.se',
                'folkhalsomyndigheten.se'
            ],
            population=10_500_000,
            major_cities=['Stockholm', 'Gothenburg', 'Malmö'],
            healthcare_system_type='single-payer',
            currency='SEK'
        ),
        'germany': CountryConfig(
            country_code='DE',
            country_name='Germany',
            language_code='de',
            search_language='en',
            medical_terms={
                'chronic spontaneous urticaria': 'chronische spontane Urtikaria',
                'atopic dermatitis': 'atopische Dermatitis',
            },
            priority_sources=[
                'rki.de',
                'g-ba.de',
                'iqwig.de',
                'awmf.org',
            ],
            health_authority_domains=[
                'rki.de',
                'bundesgesundheitsministerium.de'
            ],
            population=84_000_000,
            major_cities=['Berlin', 'Munich', 'Hamburg', 'Frankfurt'],
            healthcare_system_type='insurance-based',
            currency='EUR'
        ),
        'uk': CountryConfig(
            country_code='GB',
            country_name='United Kingdom',
            language_code='en',
            search_language='en',
            medical_terms={},  # English-speaking
            priority_sources=[
                'nice.org.uk',
                'nhs.uk',
                'gov.uk',
                'bnf.nice.org.uk',
            ],
            health_authority_domains=[
                'nhs.uk',
                'gov.uk/dhsc'
            ],
            population=67_000_000,
            major_cities=['London', 'Manchester', 'Birmingham', 'Edinburgh'],
            healthcare_system_type='single-payer',
            currency='GBP'
        ),
    }

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir) if config_dir else None
        self._configs: Dict[str, CountryConfig] = dict(self.BUILTIN_CONFIGS)

        # Load custom configs from YAML files
        if self.config_dir and self.config_dir.exists():
            self._load_custom_configs()

    def _load_custom_configs(self):
        """Load custom country configs from YAML files."""
        for yaml_file in self.config_dir.glob('*.yaml'):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                    config = CountryConfig(**data)
                    self._configs[config.country_name.lower()] = config
            except Exception as e:
                print(f"Warning: Failed to load {yaml_file}: {e}")

    def get_config(self, country: str) -> CountryConfig:
        """
        Get configuration for a country.

        Falls back to a generic config if country not found.
        """
        country_lower = country.lower()

        if country_lower in self._configs:
            return self._configs[country_lower]

        # Return generic config
        return CountryConfig(
            country_code='XX',
            country_name=country,
            language_code='en',
            search_language='en'
        )

    def generate_localized_queries(
        self,
        base_queries: List[str],
        disease: str,
        country: str
    ) -> List[str]:
        """Generate localized search queries for a country."""
        config = self.get_config(country)

        localized = []
        for query in base_queries:
            localized.append(config.localize_query(query, disease))

        # Add country-specific source queries
        for source in config.priority_sources[:3]:
            localized.append(f"site:{source} {disease}")

        return localized
```

---

### 16. Robust Output Parsing (`synthesis/output_parser.py`)

```python
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

@dataclass
class ParseResult:
    """Result of parsing Claude's output."""
    success: bool
    data: Optional[Dict[str, Any]]
    errors: List[str]
    raw_output: str

    @property
    def tables(self) -> Dict:
        return self.data.get('tables', {}) if self.data else {}

    @property
    def search_log(self) -> List:
        return self.data.get('search_log', []) if self.data else []

    @property
    def data_gaps(self) -> List:
        return self.data.get('data_gaps', []) if self.data else []


class OutputParser:
    """
    Robust parser for Claude's domain synthesis output.

    Handles multiple output formats and provides graceful degradation.
    """

    def parse(self, output: str) -> ParseResult:
        """
        Parse Claude's output into structured data.

        Attempts multiple parsing strategies in order:
        1. JSON code block extraction
        2. Raw JSON parsing
        3. Markdown table extraction (fallback)
        """
        errors = []

        # Strategy 1: Extract JSON from code block
        json_data = self._extract_json_block(output)
        if json_data:
            validation_errors = self._validate_structure(json_data)
            if not validation_errors:
                return ParseResult(
                    success=True,
                    data=json_data,
                    errors=[],
                    raw_output=output
                )
            errors.extend(validation_errors)

        # Strategy 2: Try parsing entire output as JSON
        try:
            json_data = json.loads(output)
            validation_errors = self._validate_structure(json_data)
            if not validation_errors:
                return ParseResult(
                    success=True,
                    data=json_data,
                    errors=[],
                    raw_output=output
                )
            errors.extend(validation_errors)
        except json.JSONDecodeError:
            pass

        # Strategy 3: Extract markdown tables as fallback
        tables = self._extract_markdown_tables(output)
        if tables:
            logger.warning(
                "json_parse_failed_using_markdown_fallback",
                tables_found=len(tables)
            )
            return ParseResult(
                success=True,
                data={
                    'tables': tables,
                    'search_log': [],
                    'data_gaps': ['Structured output parsing failed - extracted from markdown'],
                    'quality_summary': {'parse_method': 'markdown_fallback'}
                },
                errors=errors,
                raw_output=output
            )

        # All strategies failed
        logger.error("output_parse_failed", errors=errors)
        return ParseResult(
            success=False,
            data=None,
            errors=errors + ['All parsing strategies failed'],
            raw_output=output
        )

    def _extract_json_block(self, text: str) -> Optional[Dict]:
        """Extract JSON from markdown code block."""
        # Match ```json ... ``` or ``` ... ```
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_structure(self, data: Dict) -> List[str]:
        """Validate the parsed data has expected structure."""
        errors = []

        if not isinstance(data, dict):
            errors.append("Root must be a dictionary")
            return errors

        # Check for required top-level keys
        if 'tables' not in data:
            errors.append("Missing 'tables' key")
        elif not isinstance(data['tables'], dict):
            errors.append("'tables' must be a dictionary")

        # Validate table structure
        if 'tables' in data and isinstance(data['tables'], dict):
            for table_name, table_data in data['tables'].items():
                if not isinstance(table_data, dict):
                    errors.append(f"Table '{table_name}' must be a dictionary")
                    continue

                if 'headers' not in table_data:
                    errors.append(f"Table '{table_name}' missing 'headers'")

                if 'rows' not in table_data:
                    errors.append(f"Table '{table_name}' missing 'rows'")
                elif not isinstance(table_data['rows'], list):
                    errors.append(f"Table '{table_name}' rows must be a list")

        return errors

    def _extract_markdown_tables(self, text: str) -> Dict[str, Dict]:
        """
        Extract tables from markdown format as fallback.

        Parses tables like:
        | Header1 | Header2 |
        |---------|---------|
        | Value1  | Value2  |
        """
        tables = {}

        # Find all markdown tables
        table_pattern = r'(?:^|\n)(\|[^\n]+\|)\n(\|[-:| ]+\|)\n((?:\|[^\n]+\|\n?)+)'
        matches = re.findall(table_pattern, text)

        for i, (header_row, separator, body) in enumerate(matches):
            # Parse headers
            headers = [h.strip() for h in header_row.strip('|').split('|')]

            # Parse rows
            rows = []
            for row_text in body.strip().split('\n'):
                if row_text.strip():
                    values = [v.strip() for v in row_text.strip('|').split('|')]
                    if len(values) == len(headers):
                        row_dict = dict(zip(headers, values))
                        rows.append(row_dict)

            # Generate table name from first header or use index
            table_name = f"table_{i+1}"
            if headers:
                # Try to find table name from preceding text
                table_name = self._infer_table_name(text, header_row) or table_name

            tables[table_name] = {
                'headers': headers,
                'rows': rows,
                'sources': [],
                'confidence_level': 'LOW'  # Markdown fallback = lower confidence
            }

        return tables

    def _infer_table_name(self, text: str, header_row: str) -> Optional[str]:
        """Try to infer table name from text preceding the table."""
        # Find position of header row
        pos = text.find(header_row)
        if pos <= 0:
            return None

        # Look for a heading in the 200 chars before
        preceding = text[max(0, pos-200):pos]

        # Match markdown heading
        heading_match = re.search(r'#+\s*([^\n]+)\n*$', preceding)
        if heading_match:
            name = heading_match.group(1).strip()
            # Convert to snake_case
            name = re.sub(r'[^\w\s]', '', name.lower())
            name = re.sub(r'\s+', '_', name)
            return name

        return None


class OutputValidator:
    """
    Validates synthesized domain data for completeness and quality.
    """

    def __init__(self, min_rows_per_table: int = 2):
        self.min_rows = min_rows_per_table

    def validate(
        self,
        parse_result: ParseResult,
        required_tables: List[str],
        critical_fields: Dict[str, List[str]] = None
    ) -> tuple[bool, List[str]]:
        """
        Validate parsed output against requirements.

        Args:
            parse_result: The parsed output
            required_tables: List of table names that must be present
            critical_fields: Dict mapping table names to required field names

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        if not parse_result.success:
            issues.append("Output parsing failed")
            return False, issues

        tables = parse_result.tables

        # Check required tables exist
        for table_name in required_tables:
            if table_name not in tables:
                issues.append(f"Missing required table: {table_name}")
            elif len(tables[table_name].get('rows', [])) < self.min_rows:
                issues.append(
                    f"Table '{table_name}' has insufficient data "
                    f"({len(tables[table_name].get('rows', []))} rows, "
                    f"minimum {self.min_rows})"
                )

        # Check critical fields
        if critical_fields:
            for table_name, fields in critical_fields.items():
                if table_name not in tables:
                    continue

                table_rows = tables[table_name].get('rows', [])
                for field in fields:
                    has_field = any(
                        field.lower() in str(row).lower()
                        for row in table_rows
                    )
                    if not has_field:
                        issues.append(
                            f"Missing critical data '{field}' in table '{table_name}'"
                        )

        # Check for NOT_FOUND markers (data gaps)
        not_found_count = 0
        for table in tables.values():
            for row in table.get('rows', []):
                if 'NOT_FOUND' in str(row):
                    not_found_count += 1

        if not_found_count > 10:
            issues.append(f"High number of missing data points: {not_found_count}")

        return len(issues) == 0, issues
```

---

## Core Components Specification

### 1. Configuration (`config.py`)

```python
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, Literal
from pathlib import Path

class Settings(BaseSettings):
    """
    Application configuration with environment variable support.

    All settings can be overridden via environment variables or .env file.
    """

    # API Keys (required)
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    brave_api_key: str = Field(..., description="Brave Search API key")

    # Model settings
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for synthesis"
    )
    max_output_tokens: int = Field(
        default=8000,
        description="Maximum tokens for Claude output"
    )

    # Search settings
    searches_per_domain: int = Field(
        default=17,
        description="Number of search queries per domain"
    )
    max_search_results: int = Field(
        default=10,
        description="Maximum results per search query"
    )
    top_results_to_fetch: int = Field(
        default=3,
        description="Number of top results to fetch full content for"
    )

    # Rate limiting (base values - adaptive limiter adjusts these)
    search_delay_seconds: float = Field(
        default=1.0,
        ge=0.5,
        description="Base delay between search requests"
    )
    api_delay_seconds: float = Field(
        default=2.0,
        ge=1.0,
        description="Base delay between Claude API calls"
    )

    # Retry settings
    max_retries: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed requests"
    )
    retry_min_wait: float = Field(
        default=2.0,
        description="Minimum wait between retries (seconds)"
    )
    retry_max_wait: float = Field(
        default=60.0,
        description="Maximum wait between retries (seconds)"
    )

    # Validation settings
    strict_mode: bool = Field(
        default=False,
        description="If True, fail on validation errors instead of continuing"
    )
    min_rows_per_table: int = Field(
        default=2,
        description="Minimum rows required per table for validation"
    )
    max_synthesis_retries: int = Field(
        default=2,
        description="Retries for Claude synthesis if output has gaps"
    )

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level"
    )
    log_file: Optional[str] = Field(
        default=None,
        description="Optional log file path"
    )
    json_logs: bool = Field(
        default=False,
        description="Output logs as JSON (for production)"
    )

    # Paths
    cache_dir: str = Field(default="data/cache")
    session_dir: str = Field(default="data/sessions")
    output_dir: str = Field(default="data/outputs")
    cost_dir: str = Field(default="data/costs")
    localization_dir: Optional[str] = Field(
        default=None,
        description="Directory for custom country configs"
    )

    # Feature flags
    enable_cost_tracking: bool = Field(
        default=True,
        description="Track and report API costs"
    )
    enable_pdf_extraction: bool = Field(
        default=True,
        description="Attempt to extract content from PDF links"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("cache_dir", "session_dir", "output_dir", "cost_dir", pre=True)
    def ensure_directories_exist(cls, v):
        """Create directories if they don't exist."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @validator("anthropic_api_key", "brave_api_key")
    def validate_api_keys(cls, v, field):
        """Validate API keys are not empty or placeholder values."""
        if not v or v.startswith("your-") or v == "xxx":
            raise ValueError(f"{field.name} must be set to a valid API key")
        return v
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
from anthropic import Anthropic, APIError, RateLimitError as AnthropicRateLimitError
from typing import Dict, Any, List, Optional, Tuple
import time
import structlog

from utils.retry import retry_api, RateLimitError, TransientError
from utils.tokens import TokenManager
from utils.cost_tracker import CostTracker
from synthesis.output_parser import OutputParser, OutputValidator, ParseResult

logger = structlog.get_logger()


class ClaudeSynthesizer:
    """
    Handles Claude API calls for data synthesis with:
    - Automatic retry with exponential backoff
    - Token management and context optimization
    - Cost tracking
    - Robust output parsing
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_output_tokens: int = 8000,
        cost_tracker: Optional[CostTracker] = None
    ):
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

        # Add gap-filling instructions if retrying
        if existing_gaps:
            gap_instruction = f"""

## IMPORTANT: PREVIOUS GAPS TO ADDRESS

The following data gaps were identified in a previous attempt. Please focus on finding this information:
{chr(10).join(f'- {gap}' for gap in existing_gaps)}

If data cannot be found, mark as "NOT_FOUND" with explanation.
"""
            domain_prompt = domain_prompt + gap_instruction

        # Execute synthesis with retry
        for attempt in range(max_retries + 1):
            try:
                result, metrics = self._execute_synthesis(domain_prompt, context)

                # Validate output
                validator = OutputValidator()
                is_valid, issues = validator.validate(result, required_tables)

                if is_valid or attempt == max_retries:
                    metrics['validation_issues'] = issues
                    metrics['attempts'] = attempt + 1
                    return result, metrics

                # Retry with gap information
                logger.warning(
                    "synthesis_incomplete_retrying",
                    attempt=attempt + 1,
                    issues=issues
                )
                existing_gaps = issues

            except Exception as e:
                if attempt == max_retries:
                    raise
                logger.warning(
                    "synthesis_failed_retrying",
                    attempt=attempt + 1,
                    error=str(e)
                )
                time.sleep(2 ** attempt)  # Exponential backoff

        # Should not reach here, but return last result
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
        """
        # Build messages
        messages = [
            {
                "role": "user",
                "content": f"{domain_prompt}\n\n## SEARCH RESULTS AND SOURCES\n\n{context}"
            }
        ]

        # Count input tokens
        full_prompt = domain_prompt + context
        input_tokens = self.token_manager.count_tokens(full_prompt)

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

            # Track costs
            if self.cost_tracker:
                self.cost_tracker.record_claude_call(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=output_tokens,
                    model=self.model,
                    duration_ms=duration_ms
                )

            # Parse output
            parse_result = self.output_parser.parse(output_text)

            metrics = {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': output_tokens,
                'duration_ms': duration_ms,
                'parse_success': parse_result.success,
                'estimated_cost': self.token_manager.estimate_cost(
                    response.usage.input_tokens, output_tokens
                )
            }

            logger.info(
                "synthesis_completed",
                input_tokens=metrics['input_tokens'],
                output_tokens=metrics['output_tokens'],
                parse_success=parse_result.success
            )

            return parse_result, metrics

        except AnthropicRateLimitError as e:
            # Convert to our retry-compatible exception
            raise RateLimitError(retry_after=60.0) from e
        except APIError as e:
            if e.status_code >= 500:
                raise TransientError(str(e)) from e
            raise

    def _build_context(
        self,
        search_results: List[Dict],
        page_contents: List[Optional[str]]
    ) -> str:
        """Build context string from search results and fetched content."""
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
    ) -> Dict[str, int]:
        """
        Estimate token usage before making API call.

        Useful for cost estimation and budget checking.
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
            )
        }
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
import sys
from pathlib import Path

from core.orchestrator import PatientJourneyOrchestrator
from output.json_exporter import export_to_json
from output.markdown_exporter import export_to_markdown
from config import Settings
from utils.logging_config import configure_logging, ProgressLogger
from utils.cost_tracker import CostTracker


@click.command()
@click.option('--disease', '-d', required=True, help='Disease area (e.g., "Chronic Spontaneous Urticaria")')
@click.option('--country', '-c', required=True, help='Target country (e.g., "Sweden")')
@click.option('--start-domain', '-s', default=1, type=click.IntRange(1, 7), help='Domain to start from (1-7)')
@click.option('--end-domain', '-e', default=7, type=click.IntRange(1, 7), help='Domain to end at (1-7)')
@click.option('--output-format', '-o', type=click.Choice(['json', 'markdown', 'both']), default='both')
@click.option('--strict', is_flag=True, help='Fail on validation errors instead of continuing')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), default='INFO')
@click.option('--log-file', type=click.Path(), help='Optional log file path')
@click.option('--json-logs', is_flag=True, help='Output logs as JSON (for production)')
@click.option('--dry-run', is_flag=True, help='Estimate costs without making API calls')
@click.option('--no-cache', is_flag=True, help='Disable caching (always fetch fresh data)')
@click.version_option(version='1.0.0')
def main(
    disease: str,
    country: str,
    start_domain: int,
    end_domain: int,
    output_format: str,
    strict: bool,
    log_level: str,
    log_file: str,
    json_logs: bool,
    dry_run: bool,
    no_cache: bool
):
    """
    Patient Journey Database Builder

    Automates pharmaceutical patient journey research across 7 domains:

    \b
    1. Epidemiology
    2. Healthcare Finances
    3. Competitive Landscape
    4. Clinical Pathways
    5. Patient Experience
    6. Patient Segmentation
    7. Stakeholder Mapping

    \b
    Examples:
        # Full run for new disease/country
        python main.py --disease "Atopic Dermatitis" --country "Germany"

        # Resume from Domain 4
        python main.py -d "Atopic Dermatitis" -c "Germany" -s 4

        # Strict mode with debug logging
        python main.py -d "CSU" -c "Sweden" --strict --log-level DEBUG

        # Estimate costs without running
        python main.py -d "Psoriasis" -c "UK" --dry-run
    """
    # Configure logging
    configure_logging(
        log_level=log_level,
        log_file=log_file,
        json_logs=json_logs
    )

    progress = ProgressLogger()

    try:
        # Load configuration
        config = Settings()

        # Override config with CLI flags
        if strict:
            config.strict_mode = True
        config.log_level = log_level

        # Initialize cost tracker
        session_id = f"{country.lower()}_{disease.lower().replace(' ', '_')}"
        cost_tracker = CostTracker(session_id, config.cost_dir) if config.enable_cost_tracking else None

        # Dry run mode - estimate costs only
        if dry_run:
            _estimate_costs(disease, country, start_domain, end_domain, config, progress)
            return

        # Initialize orchestrator
        orchestrator = PatientJourneyOrchestrator(
            config=config,
            cost_tracker=cost_tracker,
            use_cache=not no_cache
        )

        # Run research
        database = orchestrator.run(
            disease=disease,
            country=country,
            start_domain=start_domain,
            end_domain=end_domain
        )

        # Export results
        output_base = Path(config.output_dir) / f"{session_id}"

        if output_format in ['json', 'both']:
            json_path = export_to_json(database, f"{output_base}_database.json")
            click.echo(f"📄 JSON exported: {json_path}")

        if output_format in ['markdown', 'both']:
            md_path = export_to_markdown(database, f"{output_base}_database.md")
            click.echo(f"📝 Markdown exported: {md_path}")

        # Save cost report
        if cost_tracker:
            cost_tracker.save()
            summary = cost_tracker.get_summary()
            progress.final_summary(
                disease=disease,
                country=country,
                completeness=database.completeness_score,
                total_duration=(database.updated_at - database.created_at).total_seconds(),
                total_cost=summary['total_cost_usd']
            )
        else:
            click.echo(f"\n✅ Database complete! Completeness: {database.completeness_score:.1f}%")

    except ValueError as e:
        # Configuration errors
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n⚠️  Interrupted by user. Progress has been saved.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        if log_level == 'DEBUG':
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _estimate_costs(
    disease: str,
    country: str,
    start_domain: int,
    end_domain: int,
    config: Settings,
    progress: ProgressLogger
):
    """Estimate costs without making API calls."""
    from utils.tokens import TokenManager

    click.echo("\n🔮 Cost Estimation (Dry Run)\n")
    click.echo(f"Disease: {disease}")
    click.echo(f"Country: {country}")
    click.echo(f"Domains: {start_domain} to {end_domain}")
    click.echo()

    token_manager = TokenManager(config.claude_model)

    # Estimates based on typical usage
    domains_to_run = end_domain - start_domain + 1
    searches_per_domain = config.searches_per_domain
    total_searches = domains_to_run * searches_per_domain

    # Brave Search costs
    search_cost = total_searches * 0.005  # $0.005 per search

    # Claude API costs (estimates)
    avg_input_tokens_per_domain = 150000  # ~150k tokens of search context
    avg_output_tokens_per_domain = 6000   # ~6k tokens of structured output

    total_input_tokens = domains_to_run * avg_input_tokens_per_domain
    total_output_tokens = domains_to_run * avg_output_tokens_per_domain

    claude_cost = token_manager.estimate_cost(total_input_tokens, total_output_tokens)

    total_cost = search_cost + claude_cost

    click.echo("📊 Estimated API Usage:")
    click.echo(f"  • Search queries: {total_searches}")
    click.echo(f"  • Claude input tokens: ~{total_input_tokens:,}")
    click.echo(f"  • Claude output tokens: ~{total_output_tokens:,}")
    click.echo()
    click.echo("💰 Estimated Costs:")
    click.echo(f"  • Brave Search: ${search_cost:.2f}")
    click.echo(f"  • Claude API:   ${claude_cost:.2f}")
    click.echo(f"  • Total:        ${total_cost:.2f}")
    click.echo()
    click.echo("⏱️  Estimated Time: ~{:.0f} minutes".format(domains_to_run * 5))
    click.echo()
    click.echo("Note: Actual costs may vary based on search result quality and content length.")


@click.command()
@click.option('--session-id', '-s', required=True, help='Session ID to inspect')
@click.option('--config-dir', default='data/sessions', help='Session directory')
def status(session_id: str, config_dir: str):
    """Check status of an existing session."""
    from core.session_manager import SessionManager

    session_file = Path(config_dir) / f"{session_id}_session.json"

    if not session_file.exists():
        click.echo(f"❌ Session not found: {session_id}")
        return

    # Load and display status
    import json
    data = json.loads(session_file.read_text())

    click.echo(f"\n📋 Session: {session_id}")
    click.echo(f"Disease: {data.get('disease_area')}")
    click.echo(f"Country: {data.get('country')}")
    click.echo(f"Status: {data.get('overall_status')}")
    click.echo(f"Current Domain: {data.get('current_domain')}/7")
    click.echo(f"Completeness: {data.get('completeness_score', 0):.1f}%")
    click.echo()

    click.echo("Domain Status:")
    for domain_id, domain_data in data.get('domains', {}).items():
        status_icon = {
            'completed': '✅',
            'in_progress': '🔄',
            'failed': '❌',
            'not_started': '⬜'
        }.get(domain_data.get('status'), '❓')
        click.echo(f"  {status_icon} Domain {domain_id}: {domain_data.get('domain_name')} - {domain_data.get('status')}")


# Create CLI group
@click.group()
def cli():
    """Patient Journey Database Builder CLI"""
    pass

cli.add_command(main, name='run')
cli.add_command(status)


if __name__ == "__main__":
    cli()
```

---

## Implementation Phases

### Phase 1: Foundation
1. Set up project structure and virtual environment
2. Implement configuration with Pydantic Settings
3. Create all Pydantic data models
4. Implement search cache with TTL support
5. Build Brave Search client with retry logic
6. Build web content fetcher with PDF support
7. Write unit tests for search components

### Phase 1.5: Resilience Layer (NEW)
1. Implement retry utilities with tenacity
2. Create custom exception hierarchy
3. Build adaptive rate limiter
4. Implement token manager with tiktoken
5. Create source quality scorer
6. Write tests for resilience components

### Phase 2: Claude Integration
1. Implement Claude synthesis client with retry logic
2. Build prompt templates with Jinja2
3. Create robust output parser (JSON + markdown fallback)
4. Implement output validator
5. Add synthesis retry for incomplete results
6. Test synthesis with mock data
7. Handle rate limiting with exponential backoff

### Phase 3: Domain Implementation
1. Implement base domain class with validation
2. Port Domain 1 (Epidemiology) prompts from existing skill
3. Port remaining 6 domains with table schemas
4. Implement per-domain validation criteria
5. Add critical field checking per domain
6. Test each domain independently with fixtures

### Phase 4: Orchestration
1. Implement session manager with file locking
2. Build main orchestrator with all integrations
3. Add checkpoint/resume logic
4. Integrate cost tracking
5. Add progress logging with Rich
6. Implement CLI with all options
7. End-to-end testing

### Phase 5: Localization & Observability (NEW)
1. Implement localization manager
2. Create country configs for Sweden, Germany, UK
3. Add YAML config loading for custom countries
4. Configure structured logging with structlog
5. Implement cost tracker with reporting
6. Add dry-run cost estimation

### Phase 6: Export & Polish
1. JSON exporter with schema validation
2. Markdown exporter with Jinja2 templates
3. Add session status command
4. Comprehensive error handling
5. Write user documentation
6. Final E2E testing with real disease/country

---

## Test Coverage Specification

### Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── fixtures/
│   ├── search_results.json        # Sample Brave API responses
│   ├── page_contents.json         # Sample fetched content
│   ├── claude_outputs.json        # Sample Claude responses
│   └── expected_tables.json       # Expected parsed output
│
├── unit/
│   ├── __init__.py
│   ├── test_config.py             # Configuration tests
│   ├── test_retry.py              # Retry/backoff tests
│   ├── test_tokens.py             # Token management tests
│   ├── test_cost_tracker.py       # Cost tracking tests
│   ├── test_output_parser.py      # Output parsing tests
│   ├── test_localization.py       # Localization tests
│   ├── test_search_cache.py       # Cache tests
│   └── test_session_manager.py    # Session tests
│
├── integration/
│   ├── __init__.py
│   ├── test_brave_search.py       # Search integration (mocked)
│   ├── test_web_fetch.py          # Web fetcher (mocked)
│   ├── test_claude_client.py      # Claude integration (mocked)
│   └── test_orchestrator.py       # Full orchestration (mocked)
│
└── e2e/
    ├── __init__.py
    └── test_full_run.py           # End-to-end with real APIs (optional)
```

### Key Test Files

#### `tests/conftest.py` - Shared Fixtures

```python
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import Settings
from models.database import PatientJourneyDatabase, DomainData, DataTable
from models.search_result import SearchResult


@pytest.fixture
def test_config():
    """Test configuration with mock API keys."""
    return Settings(
        anthropic_api_key="test-key",
        brave_api_key="test-key",
        cache_dir="tests/data/cache",
        session_dir="tests/data/sessions",
        output_dir="tests/data/outputs",
        strict_mode=False
    )


@pytest.fixture
def sample_search_results():
    """Sample search results for testing."""
    return [
        SearchResult(
            title="CSU Prevalence in Sweden - PubMed",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            description="Study on chronic spontaneous urticaria prevalence...",
            source="pubmed.ncbi.nlm.nih.gov"
        ),
        SearchResult(
            title="Swedish National Patient Registry",
            url="https://socialstyrelsen.se/statistics/",
            description="National health statistics from Sweden...",
            source="socialstyrelsen.se"
        ),
    ]


@pytest.fixture
def sample_page_content():
    """Sample fetched page content."""
    return """
    Chronic Spontaneous Urticaria (CSU) Epidemiology in Sweden

    Prevalence: 0.5-1% of adult population
    Incidence: 1.4 per 1000 person-years

    The Swedish National Patient Registry shows:
    - Total diagnosed patients: ~50,000
    - Female:Male ratio: 2:1
    - Peak age: 30-50 years
    """


@pytest.fixture
def sample_claude_output():
    """Sample Claude synthesis output."""
    return '''```json
{
    "tables": {
        "prevalence_incidence": {
            "headers": ["Metric", "Value", "95% CI", "Source", "Year", "Confidence"],
            "rows": [
                {"Metric": "Prevalence", "Value": "0.5-1%", "95% CI": "N/A", "Source": "PubMed", "Year": "2023", "Confidence": "HIGH"},
                {"Metric": "Incidence", "Value": "1.4/1000", "95% CI": "1.2-1.6", "Source": "Registry", "Year": "2022", "Confidence": "HIGH"}
            ]
        }
    },
    "search_log": [
        {"query": "CSU prevalence Sweden", "source_found": "PubMed", "key_data_points": "0.5-1% prevalence"}
    ],
    "data_gaps": [],
    "quality_summary": {"confidence_level": "HIGH", "tables_populated": 1}
}
```'''


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing."""
    with patch('anthropic.Anthropic') as mock:
        client = MagicMock()
        mock.return_value = client

        # Mock response
        response = MagicMock()
        response.content = [MagicMock(text='{"tables": {}}')]
        response.usage.input_tokens = 1000
        response.usage.output_tokens = 500
        client.messages.create.return_value = response

        yield client


@pytest.fixture
def temp_session_dir(tmp_path):
    """Temporary directory for session files."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    return session_dir
```

#### `tests/unit/test_output_parser.py`

```python
import pytest
from synthesis.output_parser import OutputParser, OutputValidator, ParseResult


class TestOutputParser:
    """Tests for OutputParser class."""

    @pytest.fixture
    def parser(self):
        return OutputParser()

    def test_parse_valid_json_block(self, parser, sample_claude_output):
        """Test parsing valid JSON from code block."""
        result = parser.parse(sample_claude_output)

        assert result.success is True
        assert 'tables' in result.data
        assert 'prevalence_incidence' in result.tables
        assert len(result.errors) == 0

    def test_parse_raw_json(self, parser):
        """Test parsing raw JSON without code block."""
        raw_json = '{"tables": {"test": {"headers": ["A"], "rows": []}}}'
        result = parser.parse(raw_json)

        assert result.success is True
        assert 'test' in result.tables

    def test_parse_markdown_fallback(self, parser):
        """Test markdown table extraction as fallback."""
        markdown = """
        ## Results

        | Metric | Value |
        |--------|-------|
        | Prevalence | 0.5% |
        | Incidence | 1.4/1000 |
        """
        result = parser.parse(markdown)

        assert result.success is True
        assert len(result.tables) >= 1

    def test_parse_invalid_output(self, parser):
        """Test handling of completely invalid output."""
        result = parser.parse("This is not valid data at all.")

        assert result.success is False
        assert len(result.errors) > 0

    def test_parse_incomplete_json(self, parser):
        """Test handling of incomplete JSON structure."""
        incomplete = '{"tables": "not a dict"}'
        result = parser.parse(incomplete)

        # Should fail validation even if JSON parses
        assert len(result.errors) > 0


class TestOutputValidator:
    """Tests for OutputValidator class."""

    @pytest.fixture
    def validator(self):
        return OutputValidator(min_rows_per_table=2)

    def test_validate_complete_output(self, validator, sample_claude_output):
        """Test validation of complete output."""
        parser = OutputParser()
        parse_result = parser.parse(sample_claude_output)

        is_valid, issues = validator.validate(
            parse_result,
            required_tables=['prevalence_incidence']
        )

        assert is_valid is True
        assert len(issues) == 0

    def test_validate_missing_table(self, validator):
        """Test validation catches missing required tables."""
        parse_result = ParseResult(
            success=True,
            data={'tables': {}},
            errors=[],
            raw_output=""
        )

        is_valid, issues = validator.validate(
            parse_result,
            required_tables=['prevalence_incidence']
        )

        assert is_valid is False
        assert any('Missing required table' in issue for issue in issues)

    def test_validate_insufficient_rows(self, validator):
        """Test validation catches tables with too few rows."""
        parse_result = ParseResult(
            success=True,
            data={
                'tables': {
                    'test_table': {
                        'headers': ['A'],
                        'rows': [{'A': '1'}]  # Only 1 row, need 2
                    }
                }
            },
            errors=[],
            raw_output=""
        )

        is_valid, issues = validator.validate(
            parse_result,
            required_tables=['test_table']
        )

        assert is_valid is False
        assert any('insufficient data' in issue.lower() for issue in issues)
```

#### `tests/unit/test_retry.py`

```python
import pytest
import asyncio
from unittest.mock import MagicMock, patch
import httpx

from utils.retry import (
    create_retry_decorator,
    AdaptiveRateLimiter,
    handle_http_error,
    RateLimitError,
    TransientError,
    PermanentError
)


class TestRetryDecorator:
    """Tests for retry decorator functionality."""

    def test_successful_call_no_retry(self):
        """Test that successful calls don't retry."""
        call_count = 0

        @create_retry_decorator(max_attempts=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_transient_error(self):
        """Test retry on transient errors."""
        call_count = 0

        @create_retry_decorator(max_attempts=3, min_wait=0.1, max_wait=0.2)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransientError("Temporary failure")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_no_retry_on_permanent_error(self):
        """Test that permanent errors are not retried."""
        call_count = 0

        @create_retry_decorator(max_attempts=3)
        def permanent_failure():
            nonlocal call_count
            call_count += 1
            raise PermanentError("Bad request")

        with pytest.raises(PermanentError):
            permanent_failure()

        assert call_count == 1  # No retries


class TestAdaptiveRateLimiter:
    """Tests for adaptive rate limiter."""

    @pytest.fixture
    def limiter(self):
        return AdaptiveRateLimiter(base_delay=1.0, max_delay=10.0)

    def test_initial_delay(self, limiter):
        """Test initial delay is base delay."""
        assert limiter.current_delay == 1.0

    def test_backoff_on_rate_limit(self, limiter):
        """Test delay increases on rate limit."""
        limiter.on_rate_limit()
        assert limiter.current_delay == 2.0  # 1.0 * 2.0

        limiter.on_rate_limit()
        assert limiter.current_delay == 4.0  # 2.0 * 2.0

    def test_respect_retry_after(self, limiter):
        """Test respects retry-after header."""
        limiter.on_rate_limit(retry_after=5.0)
        assert limiter.current_delay == 5.0

    def test_max_delay_cap(self, limiter):
        """Test delay doesn't exceed max."""
        for _ in range(10):
            limiter.on_rate_limit()
        assert limiter.current_delay <= 10.0

    def test_decrease_on_success(self, limiter):
        """Test delay decreases after consecutive successes."""
        limiter.on_rate_limit()  # Increase to 2.0
        limiter.on_rate_limit()  # Increase to 4.0

        for _ in range(5):
            limiter.on_success()

        assert limiter.current_delay < 4.0


class TestHttpErrorHandler:
    """Tests for HTTP error handling."""

    def test_rate_limit_error(self):
        """Test 429 raises RateLimitError."""
        response = MagicMock()
        response.status_code = 429
        response.headers = {'retry-after': '60'}

        with pytest.raises(RateLimitError) as exc_info:
            handle_http_error(response)

        assert exc_info.value.retry_after == 60.0

    def test_server_error(self):
        """Test 5xx raises TransientError."""
        response = MagicMock()
        response.status_code = 503
        response.text = "Service Unavailable"

        with pytest.raises(TransientError):
            handle_http_error(response)

    def test_client_error(self):
        """Test 4xx raises PermanentError."""
        response = MagicMock()
        response.status_code = 400
        response.text = "Bad Request"

        with pytest.raises(PermanentError):
            handle_http_error(response)
```

#### `tests/integration/test_orchestrator.py`

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from core.orchestrator import PatientJourneyOrchestrator
from models.database import PatientJourneyDatabase, DomainStatus


class TestOrchestratorIntegration:
    """Integration tests for the orchestrator."""

    @pytest.fixture
    def mock_orchestrator(self, test_config, temp_session_dir):
        """Create orchestrator with mocked dependencies."""
        test_config.session_dir = str(temp_session_dir)

        with patch('core.orchestrator.BraveSearchClient') as mock_search, \
             patch('core.orchestrator.WebFetcher') as mock_fetch, \
             patch('core.orchestrator.ClaudeSynthesizer') as mock_synth:

            # Configure mock search
            mock_search_instance = MagicMock()
            mock_search_instance.search.return_value = [
                MagicMock(title="Test", url="http://test.com", description="Test")
            ]
            mock_search.return_value = mock_search_instance

            # Configure mock fetcher
            mock_fetch_instance = MagicMock()
            mock_fetch_instance.fetch.return_value = "Sample content"
            mock_fetch.return_value = mock_fetch_instance

            # Configure mock synthesizer
            mock_synth_instance = MagicMock()
            mock_synth_instance.synthesize_domain.return_value = (
                MagicMock(
                    success=True,
                    tables={'test_table': {'headers': ['A'], 'rows': [{'A': '1'}, {'A': '2'}]}},
                    data_gaps=[]
                ),
                {'input_tokens': 1000, 'output_tokens': 500}
            )
            mock_synth.return_value = mock_synth_instance

            orchestrator = PatientJourneyOrchestrator(config=test_config)
            yield orchestrator

    def test_run_single_domain(self, mock_orchestrator):
        """Test running a single domain."""
        database = mock_orchestrator.run(
            disease="Test Disease",
            country="Sweden",
            start_domain=1,
            end_domain=1
        )

        assert database is not None
        assert 1 in database.domains
        assert database.domains[1].status == DomainStatus.COMPLETED

    def test_session_persistence(self, mock_orchestrator, temp_session_dir):
        """Test session is persisted after each domain."""
        mock_orchestrator.run(
            disease="Test Disease",
            country="Sweden",
            start_domain=1,
            end_domain=2
        )

        session_file = temp_session_dir / "sweden_test_disease_session.json"
        assert session_file.exists()

    def test_resume_from_checkpoint(self, mock_orchestrator, temp_session_dir):
        """Test resuming from a checkpoint."""
        # First run - complete domain 1
        mock_orchestrator.run(
            disease="Test Disease",
            country="Sweden",
            start_domain=1,
            end_domain=1
        )

        # Second run - resume from domain 2
        database = mock_orchestrator.run(
            disease="Test Disease",
            country="Sweden",
            start_domain=2,
            end_domain=2
        )

        assert 1 in database.domains
        assert 2 in database.domains

    def test_strict_mode_fails_on_gaps(self, test_config, temp_session_dir):
        """Test strict mode fails on validation errors."""
        test_config.strict_mode = True
        test_config.session_dir = str(temp_session_dir)

        with patch('core.orchestrator.BraveSearchClient'), \
             patch('core.orchestrator.WebFetcher'), \
             patch('core.orchestrator.ClaudeSynthesizer') as mock_synth:

            # Return output with gaps
            mock_synth_instance = MagicMock()
            mock_synth_instance.synthesize_domain.return_value = (
                MagicMock(
                    success=True,
                    tables={},  # Empty tables = validation failure
                    data_gaps=['Missing critical data']
                ),
                {}
            )
            mock_synth.return_value = mock_synth_instance

            orchestrator = PatientJourneyOrchestrator(config=test_config)

            with pytest.raises(Exception):  # Should raise validation error
                orchestrator.run(
                    disease="Test",
                    country="Sweden",
                    start_domain=1,
                    end_domain=1
                )
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=patient_journey_builder --cov-report=html

# Run only unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_output_parser.py -v

# Run with parallel execution
pytest tests/ -n auto

# Run E2E tests (requires real API keys)
pytest tests/e2e/ -v --run-e2e
```

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
pytest-asyncio>=0.23.0
structlog>=24.1.0
rich>=13.7.0
tenacity>=8.2.0
tiktoken>=0.6.0
PyPDF2>=3.0.0
```

---

## Environment Variables (`.env.example`)

```bash
# Required API Keys
ANTHROPIC_API_KEY=sk-ant-your-key-here
BRAVE_API_KEY=BSA-your-key-here

# Model Configuration
CLAUDE_MODEL=claude-sonnet-4-20250514
MAX_OUTPUT_TOKENS=8000

# Search Settings
SEARCHES_PER_DOMAIN=17
MAX_SEARCH_RESULTS=10
TOP_RESULTS_TO_FETCH=3

# Rate Limiting
SEARCH_DELAY_SECONDS=1.0
API_DELAY_SECONDS=2.0

# Retry Settings
MAX_RETRIES=4
RETRY_MIN_WAIT=2.0
RETRY_MAX_WAIT=60.0

# Validation
STRICT_MODE=false
MIN_ROWS_PER_TABLE=2
MAX_SYNTHESIS_RETRIES=2

# Logging
LOG_LEVEL=INFO
LOG_FILE=
JSON_LOGS=false

# Paths
CACHE_DIR=data/cache
SESSION_DIR=data/sessions
OUTPUT_DIR=data/outputs
COST_DIR=data/costs
LOCALIZATION_DIR=

# Features
ENABLE_COST_TRACKING=true
ENABLE_PDF_EXTRACTION=true
```

---

## Usage Examples

```bash
# Full run for new disease/country
python main.py run --disease "Atopic Dermatitis" --country "Germany"

# Resume from Domain 4
python main.py run -d "Atopic Dermatitis" -c "Germany" -s 4

# Run only specific domains
python main.py run -d "Psoriasis" -c "UK" -s 1 -e 3

# JSON output only
python main.py run -d "CSU" -c "Sweden" -o json

# Strict mode - fail on validation errors
python main.py run -d "CSU" -c "Sweden" --strict

# Debug logging to file
python main.py run -d "CSU" -c "Sweden" --log-level DEBUG --log-file run.log

# Estimate costs without running (dry run)
python main.py run -d "Psoriasis" -c "Germany" --dry-run

# Disable caching (force fresh data)
python main.py run -d "CSU" -c "Sweden" --no-cache

# Check status of existing session
python main.py status -s "sweden_chronic_spontaneous_urticaria"

# Production mode with JSON logs
python main.py run -d "CSU" -c "Sweden" --json-logs --log-file /var/log/pj-builder.log
```

---

## Success Criteria

### Core Functionality
1. **Functional**: Can produce a complete 7-domain database comparable to the manual CSU Sweden example
2. **Resumable**: Can restart from any domain after failure with session persistence
3. **Cached**: Search results and web content are cached to avoid redundant API calls
4. **Validated**: Each domain is validated before proceeding with configurable strictness
5. **Exportable**: Outputs both JSON and Markdown formats with proper schema

### Resilience (NEW)
6. **Retry Logic**: All API calls use exponential backoff with configurable retries
7. **Rate Limit Handling**: Adaptive rate limiting based on API responses
8. **Error Recovery**: Transient errors are retried, permanent errors fail fast

### Observability (NEW)
9. **Structured Logging**: All operations logged with structlog for debugging
10. **Cost Tracking**: Complete cost breakdown per domain and session
11. **Progress Reporting**: Rich console output showing real-time progress
12. **Dry Run Mode**: Estimate costs before committing to full run

### Quality (NEW)
13. **Token Management**: Context window optimized with source prioritization
14. **Output Parsing**: Robust parser with JSON and markdown fallback
15. **Synthesis Retry**: Incomplete results trigger retry with gap-filling prompts
16. **Source Scoring**: Academic/government sources prioritized over commercial

### Internationalization (NEW)
17. **Localization Support**: Country-specific configurations for search queries
18. **Multi-Country Ready**: Built-in support for Sweden, Germany, UK with extensible YAML configs

### Testing (NEW)
19. **Test Coverage**: Unit tests for all utility modules
20. **Integration Tests**: Mocked end-to-end tests for orchestrator
21. **Fixtures**: Comprehensive test fixtures for reproducible testing

---

## Notes for Implementation

1. **Read the existing skill first** - The prompts in `/mnt/skills/user/pharmaceutical-patient-journey/SKILL.md` are battle-tested and should be ported carefully

2. **Match the output structure** - The tables in `SWEDEN_CSU_DATABASE.md` define exactly what the synthesis should produce

3. **Language handling** - The LocalizationManager handles local language variants automatically for configured countries

4. **Source quality** - TokenManager's `_score_source()` method prioritizes academic sources (PubMed, registries) over general web content

5. **Error resilience** - The retry utilities and adaptive rate limiter handle rate limits, timeouts, and transient errors automatically

6. **Cost awareness** - Use `--dry-run` to estimate costs before running, and review cost reports after each run

7. **Strict vs. permissive mode** - Use `--strict` for production to ensure data quality, permissive mode for exploration

---

## Summary of Improvements

This enhanced plan adds the following new components:

| Component | File | Purpose |
|-----------|------|---------|
| Retry utilities | `utils/retry.py` | Exponential backoff, error classification |
| Token manager | `utils/tokens.py` | Context optimization, source prioritization |
| Logging config | `utils/logging_config.py` | Structured logging, progress display |
| Cost tracker | `utils/cost_tracker.py` | API cost tracking and reporting |
| Localization | `localization/config.py` | Country-specific search configurations |
| Output parser | `synthesis/output_parser.py` | Robust JSON/markdown parsing |
| Enhanced config | `config.py` | Full Pydantic settings with validation |
| Enhanced CLI | `main.py` | Dry-run, strict mode, status commands |

**Key additions to original plan:**
- 6 new utility modules for production readiness
- Comprehensive test suite with fixtures
- 2 new implementation phases (1.5 and 5)
- Extended CLI with 6 new command-line options
- 21 success criteria (up from 6)
