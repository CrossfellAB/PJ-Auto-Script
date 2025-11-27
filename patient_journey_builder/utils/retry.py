"""
Retry utilities with exponential backoff for API resilience.
"""

import asyncio
import time
from typing import TypeVar, Callable, Optional, Type, Tuple
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
import httpx
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


# Custom exceptions for retry categorization
class RetryableError(Exception):
    """Base class for errors that should trigger a retry."""
    pass


class RateLimitError(RetryableError):
    """API rate limit hit."""

    def __init__(self, retry_after: Optional[float] = None, message: str = "Rate limited"):
        self.retry_after = retry_after
        super().__init__(f"{message}. Retry after: {retry_after}s")


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

    Returns:
        A retry decorator configured with the specified parameters
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retryable_exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
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

    Increases delay on rate limits, decreases on consecutive successes.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        """
        Initialize the rate limiter.

        Args:
            base_delay: Initial delay between requests
            max_delay: Maximum delay cap
            backoff_factor: Multiplier for increasing delay
        """
        self.base_delay = base_delay
        self.current_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self._consecutive_successes = 0
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    def wait_sync(self) -> None:
        """Synchronous wait according to current rate limit."""
        time.sleep(self.current_delay)

    async def wait(self) -> None:
        """Async wait according to current rate limit."""
        await asyncio.sleep(self.current_delay)

    def on_success(self) -> None:
        """Call after successful request to potentially decrease delay."""
        self._consecutive_successes += 1
        if self._consecutive_successes >= 5:
            self.current_delay = max(
                self.base_delay,
                self.current_delay / self.backoff_factor
            )
            self._consecutive_successes = 0
            logger.debug(f"Rate limiter: decreased delay to {self.current_delay:.2f}s")

    def on_rate_limit(self, retry_after: Optional[float] = None) -> None:
        """Call when rate limited to increase delay."""
        self._consecutive_successes = 0
        if retry_after:
            self.current_delay = min(retry_after, self.max_delay)
        else:
            self.current_delay = min(
                self.current_delay * self.backoff_factor,
                self.max_delay
            )
        logger.warning(f"Rate limiter: increased delay to {self.current_delay:.2f}s")

    def reset(self) -> None:
        """Reset to base delay."""
        self.current_delay = self.base_delay
        self._consecutive_successes = 0


def handle_http_error(response: httpx.Response) -> None:
    """
    Convert HTTP errors to appropriate exception types.

    Args:
        response: The HTTP response to check

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


def with_retry(
    func: Callable[..., T],
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
) -> Callable[..., T]:
    """
    Wrap a function with retry logic.

    This is an alternative to using decorators directly.

    Args:
        func: Function to wrap
        max_attempts: Maximum retry attempts
        min_wait: Minimum wait between retries
        max_wait: Maximum wait between retries

    Returns:
        Wrapped function with retry logic
    """
    decorator = create_retry_decorator(
        max_attempts=max_attempts,
        min_wait=min_wait,
        max_wait=max_wait
    )
    return decorator(func)
