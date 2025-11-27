"""
Structured logging configuration for Patient Journey Builder.
"""

import structlog
import logging
import sys
from pathlib import Path
from typing import Optional, List

# Try to import rich, fall back gracefully if not available
try:
    from rich.console import Console
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


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

    # Console handler
    if RICH_AVAILABLE and not json_logs:
        console_handler = RichHandler(
            console=Console(stderr=True),
            show_time=False,  # structlog handles this
            show_path=False,
            rich_tracebacks=True
        )
    else:
        console_handler = logging.StreamHandler(sys.stderr)

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
    logging.getLogger("urllib3").setLevel(logging.WARNING)


class ProgressLogger:
    """
    Progress logging for long-running operations.

    Uses Rich if available, falls back to standard logging.
    """

    def __init__(self):
        """Initialize the progress logger."""
        self.logger = structlog.get_logger()
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

    def _print(self, message: str, style: str = "") -> None:
        """Print message to console."""
        if self.console:
            self.console.print(message, style=style)
        else:
            print(message)

    def _rule(self, title: str) -> None:
        """Print a rule/separator."""
        if self.console:
            self.console.rule(title)
        else:
            print(f"\n{'='*60}")
            print(f"  {title}")
            print(f"{'='*60}")

    def session_start(self, disease: str, country: str, start_domain: int, end_domain: int) -> None:
        """Log start of a research session."""
        self._rule(f"[bold blue]Patient Journey Database Builder")
        self._print(f"  Disease: {disease}")
        self._print(f"  Country: {country}")
        self._print(f"  Domains: {start_domain} to {end_domain}")
        self._print("")

        self.logger.info(
            "session_started",
            disease=disease,
            country=country,
            start_domain=start_domain,
            end_domain=end_domain
        )

    def domain_start(self, domain_id: int, domain_name: str, total_queries: int) -> None:
        """Log start of domain processing."""
        self._rule(f"[bold blue]Domain {domain_id}: {domain_name}")
        self.logger.info(
            "domain_started",
            domain_id=domain_id,
            domain_name=domain_name,
            total_queries=total_queries
        )

    def search_progress(self, current: int, total: int, query: str) -> None:
        """Log search progress."""
        truncated_query = query[:50] + "..." if len(query) > 50 else query
        self._print(f"  [dim]🔍 [{current}/{total}] {truncated_query}[/dim]", style="dim")

    def search_complete(self, total_results: int, cached_count: int) -> None:
        """Log search phase completion."""
        self._print(f"  📊 Found {total_results} results ({cached_count} cached)", style="cyan")
        self.logger.info(
            "search_complete",
            total_results=total_results,
            cached_count=cached_count
        )

    def synthesis_start(self, num_sources: int) -> None:
        """Log start of synthesis."""
        self._print(f"  🧠 Synthesizing {num_sources} sources...", style="cyan")
        self.logger.info("synthesis_started", num_sources=num_sources)

    def synthesis_retry(self, attempt: int, gaps: List[str]) -> None:
        """Log synthesis retry."""
        self._print(f"  ⚠️  Synthesis incomplete, retrying (attempt {attempt})...", style="yellow")
        self.logger.warning(
            "synthesis_retry",
            attempt=attempt,
            gaps=gaps[:3]  # Log first 3 gaps
        )

    def domain_complete(
        self,
        domain_id: int,
        tables_populated: int,
        gaps: List[str],
        duration_seconds: float
    ) -> None:
        """Log domain completion."""
        if gaps:
            self._print(f"  ⚠️  Completed with {len(gaps)} data gaps", style="yellow")
            for gap in gaps[:3]:  # Show first 3 gaps
                self._print(f"     - {gap}", style="dim yellow")
        else:
            self._print(f"  ✅ Complete ({tables_populated} tables)", style="green")

        self.logger.info(
            "domain_completed",
            domain_id=domain_id,
            tables_populated=tables_populated,
            gaps_count=len(gaps),
            duration_seconds=round(duration_seconds, 2)
        )

    def domain_failed(self, domain_id: int, error: str) -> None:
        """Log domain failure."""
        self._print(f"  ❌ Domain {domain_id} failed: {error}", style="red")
        self.logger.error(
            "domain_failed",
            domain_id=domain_id,
            error=error
        )

    def checkpoint_saved(self, session_id: str) -> None:
        """Log checkpoint save."""
        self._print("  💾 Checkpoint saved", style="dim green")
        self.logger.debug("checkpoint_saved", session_id=session_id)

    def final_summary(
        self,
        disease: str,
        country: str,
        completeness: float,
        total_duration: float,
        total_cost: float
    ) -> None:
        """Log final run summary."""
        self._print("")
        self._rule("[bold green]Run Complete")
        self._print(f"  Disease: {disease}")
        self._print(f"  Country: {country}")
        self._print(f"  Completeness: {completeness:.1f}%")
        self._print(f"  Duration: {total_duration/60:.1f} minutes")
        self._print(f"  Estimated Cost: ${total_cost:.2f}")

        self.logger.info(
            "session_completed",
            disease=disease,
            country=country,
            completeness=completeness,
            duration_minutes=round(total_duration/60, 1),
            cost_usd=round(total_cost, 2)
        )

    def cost_estimate(
        self,
        domains: int,
        searches: int,
        estimated_cost: float
    ) -> None:
        """Log cost estimation."""
        self._print("\n🔮 Cost Estimation (Dry Run)\n")
        self._print(f"  Domains to process: {domains}")
        self._print(f"  Estimated searches: {searches}")
        self._print(f"  Estimated cost: ${estimated_cost:.2f}")
