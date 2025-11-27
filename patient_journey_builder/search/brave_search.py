"""
Brave Search API client with caching and retry support.
"""

import httpx
import time
from typing import List, Optional
import logging

from ..models import SearchResult
from ..utils import retry_search, handle_http_error, RateLimitError, AdaptiveRateLimiter
from .search_cache import SearchCache

logger = logging.getLogger(__name__)


class BraveSearchClient:
    """
    Brave Search API client with caching support.

    Provides web search functionality with automatic caching,
    retry logic, and rate limiting.
    """

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        api_key: str,
        cache: Optional[SearchCache] = None,
        rate_limiter: Optional[AdaptiveRateLimiter] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the Brave Search client.

        Args:
            api_key: Brave Search API key
            cache: Optional cache instance
            rate_limiter: Optional rate limiter
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.cache = cache or SearchCache(enabled=False)
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter(base_delay=1.0)
        self.client = httpx.Client(timeout=timeout)

    def search(
        self,
        query: str,
        country: Optional[str] = None,
        count: int = 10,
        freshness: Optional[str] = None
    ) -> tuple[List[SearchResult], bool]:
        """
        Execute a search query.

        Args:
            query: Search query string
            country: Optional country code (e.g., 'SE', 'DE', 'GB')
            count: Number of results to return (max 20)
            freshness: Optional freshness filter ('pd', 'pw', 'pm', 'py')

        Returns:
            Tuple of (list of SearchResult, was_cached boolean)
        """
        # Build cache key
        cache_key = f"search:{query}:{country}:{count}"

        # Check cache first
        cached = self.cache.get(cache_key, cache_type="search")
        if cached:
            logger.debug(f"Cache hit for query: {query[:50]}...")
            results = [SearchResult(**r) for r in cached]
            return results, True

        # Execute search with retry
        start_time = time.time()
        results = self._execute_search(query, country, count, freshness)
        duration_ms = int((time.time() - start_time) * 1000)

        # Cache results
        if results:
            self.cache.set(
                cache_key,
                [r.model_dump() for r in results],
                cache_type="search"
            )

        logger.info(f"Search completed: {len(results)} results in {duration_ms}ms")
        return results, False

    @retry_search
    def _execute_search(
        self,
        query: str,
        country: Optional[str],
        count: int,
        freshness: Optional[str]
    ) -> List[SearchResult]:
        """
        Execute the actual search API call.

        Decorated with retry logic for transient failures.
        """
        # Apply rate limiting
        self.rate_limiter.wait_sync()

        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json"
        }

        params = {
            "q": query,
            "count": min(count, 20),  # Brave max is 20
            "search_lang": "en",
            "text_decorations": False
        }

        # Add optional parameters
        if country:
            params["country"] = country.upper()
        if freshness:
            params["freshness"] = freshness

        try:
            response = self.client.get(
                self.BASE_URL,
                headers=headers,
                params=params
            )

            if response.status_code != 200:
                handle_http_error(response)

            self.rate_limiter.on_success()
            return self._parse_results(response.json())

        except httpx.TimeoutException:
            logger.warning(f"Search timeout for query: {query[:50]}...")
            raise
        except Exception as e:
            if isinstance(e, RateLimitError):
                self.rate_limiter.on_rate_limit(e.retry_after)
            raise

    def _parse_results(self, data: dict) -> List[SearchResult]:
        """
        Parse Brave API response into SearchResult objects.

        Args:
            data: Raw API response

        Returns:
            List of SearchResult objects
        """
        results = []

        web_results = data.get("web", {}).get("results", [])

        for item in web_results:
            try:
                # Extract hostname from URL
                url = item.get("url", "")
                source = ""
                if "://" in url:
                    source = url.split("://")[1].split("/")[0]

                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    description=item.get("description", ""),
                    source=source,
                    published_date=item.get("page_age"),
                    language=item.get("language")
                ))
            except Exception as e:
                logger.warning(f"Failed to parse search result: {e}")
                continue

        return results

    def search_batch(
        self,
        queries: List[str],
        country: Optional[str] = None,
        count: int = 10,
        delay_between: float = 1.0
    ) -> List[tuple[str, List[SearchResult], bool]]:
        """
        Execute multiple search queries.

        Args:
            queries: List of search queries
            country: Optional country code
            count: Results per query
            delay_between: Delay between queries in seconds

        Returns:
            List of (query, results, was_cached) tuples
        """
        results = []

        for i, query in enumerate(queries):
            search_results, cached = self.search(query, country, count)
            results.append((query, search_results, cached))

            # Add delay between non-cached queries
            if not cached and i < len(queries) - 1:
                time.sleep(delay_between)

        return results

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
