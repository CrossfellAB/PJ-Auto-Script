"""
Web content fetcher with HTML extraction and PDF support.
"""

import httpx
import time
from typing import Optional
from bs4 import BeautifulSoup
import logging

from ..models import FetchedContent
from ..utils import retry_fetch, handle_http_error, AdaptiveRateLimiter
from .search_cache import SearchCache

logger = logging.getLogger(__name__)

# Try to import PDF support
try:
    import PyPDF2
    from io import BytesIO
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logger.warning("PyPDF2 not installed - PDF extraction disabled")


class WebFetcher:
    """
    Fetches and extracts content from web pages.

    Supports HTML and PDF extraction with caching
    and automatic truncation to token limits.
    """

    # User agent for requests
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Content types to process
    SUPPORTED_TYPES = [
        'text/html',
        'application/xhtml+xml',
        'text/plain',
        'application/pdf'
    ]

    def __init__(
        self,
        cache: Optional[SearchCache] = None,
        rate_limiter: Optional[AdaptiveRateLimiter] = None,
        timeout: float = 30.0,
        max_content_length: int = 5_000_000,  # 5MB
        enable_pdf: bool = True
    ):
        """
        Initialize the web fetcher.

        Args:
            cache: Optional cache instance
            rate_limiter: Optional rate limiter
            timeout: Request timeout in seconds
            max_content_length: Maximum content size to download
            enable_pdf: Whether to enable PDF extraction
        """
        self.cache = cache or SearchCache(enabled=False)
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter(base_delay=0.5)
        self.max_content_length = max_content_length
        self.enable_pdf = enable_pdf and PDF_SUPPORT

        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT}
        )

    def fetch(
        self,
        url: str,
        max_chars: int = 16000
    ) -> FetchedContent:
        """
        Fetch and extract content from URL.

        Args:
            url: URL to fetch
            max_chars: Maximum characters to return

        Returns:
            FetchedContent object with extracted text
        """
        # Build cache key
        cache_key = f"content:{url}"

        # Check cache first
        cached = self.cache.get(cache_key, cache_type="content")
        if cached:
            logger.debug(f"Cache hit for URL: {url[:50]}...")
            return FetchedContent(
                url=url,
                content=cached.get('content'),
                content_type=cached.get('content_type', 'text/html'),
                fetch_time_ms=0,
                truncated=cached.get('truncated', False)
            )

        # Fetch content
        start_time = time.time()
        result = self._fetch_url(url, max_chars)
        result.fetch_time_ms = int((time.time() - start_time) * 1000)

        # Cache successful fetches
        if result.success:
            self.cache.set(
                cache_key,
                {
                    'content': result.content,
                    'content_type': result.content_type,
                    'truncated': result.truncated
                },
                cache_type="content"
            )

        return result

    @retry_fetch
    def _fetch_url(self, url: str, max_chars: int) -> FetchedContent:
        """
        Execute the actual fetch operation.

        Decorated with retry logic for transient failures.
        """
        # Apply rate limiting
        self.rate_limiter.wait_sync()

        try:
            response = self.client.get(url)

            if response.status_code != 200:
                handle_http_error(response)

            self.rate_limiter.on_success()

            # Check content type
            content_type = response.headers.get('content-type', '').lower()

            # Check content length
            content_length = int(response.headers.get('content-length', 0))
            if content_length > self.max_content_length:
                return FetchedContent(
                    url=url,
                    error=f"Content too large: {content_length} bytes"
                )

            # Handle PDF
            if 'application/pdf' in content_type:
                if self.enable_pdf:
                    content = self._extract_pdf(response.content, max_chars)
                    return FetchedContent(
                        url=url,
                        content=content,
                        content_type='application/pdf',
                        truncated=len(content) >= max_chars
                    )
                else:
                    return FetchedContent(
                        url=url,
                        error="PDF extraction not available"
                    )

            # Handle HTML/text
            content = self._extract_html(response.text, max_chars)
            truncated = len(content) >= max_chars

            return FetchedContent(
                url=url,
                content=content,
                content_type=content_type.split(';')[0],
                truncated=truncated
            )

        except httpx.TimeoutException:
            logger.warning(f"Fetch timeout for URL: {url[:50]}...")
            return FetchedContent(url=url, error="Request timeout")
        except Exception as e:
            logger.warning(f"Fetch error for {url[:50]}: {e}")
            return FetchedContent(url=url, error=str(e))

    def _extract_html(self, html: str, max_chars: int) -> str:
        """
        Extract main text content from HTML.

        Args:
            html: Raw HTML content
            max_chars: Maximum characters to return

        Returns:
            Extracted text content
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove non-content elements
            for element in soup([
                'script', 'style', 'nav', 'footer', 'header',
                'aside', 'noscript', 'iframe', 'form', 'button',
                'input', 'select', 'textarea', 'meta', 'link'
            ]):
                element.decompose()

            # Remove hidden elements
            for element in soup.find_all(style=lambda x: x and 'display:none' in x):
                element.decompose()

            # Try to find main content
            main_content = (
                soup.find('main') or
                soup.find('article') or
                soup.find(class_=['content', 'main-content', 'post-content', 'entry-content']) or
                soup.find(id=['content', 'main-content', 'main']) or
                soup.body or
                soup
            )

            # Get text with spacing
            text = main_content.get_text(separator='\n', strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            text = '\n'.join(lines)

            # Truncate if needed
            if len(text) > max_chars:
                text = text[:max_chars] + "\n[...truncated]"

            return text

        except Exception as e:
            logger.warning(f"HTML extraction error: {e}")
            # Fall back to basic extraction
            return html[:max_chars] if len(html) > max_chars else html

    def _extract_pdf(self, content: bytes, max_chars: int) -> str:
        """
        Extract text from PDF content.

        Args:
            content: Raw PDF bytes
            max_chars: Maximum characters to return

        Returns:
            Extracted text content
        """
        if not PDF_SUPPORT:
            return "[PDF extraction not available]"

        try:
            pdf_file = BytesIO(content)
            reader = PyPDF2.PdfReader(pdf_file)

            text_parts = []
            total_chars = 0

            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                total_chars += len(page_text)

                if total_chars >= max_chars:
                    break

            text = '\n'.join(text_parts)

            if len(text) > max_chars:
                text = text[:max_chars] + "\n[...truncated]"

            return text

        except Exception as e:
            logger.warning(f"PDF extraction error: {e}")
            return f"[PDF extraction failed: {e}]"

    def fetch_batch(
        self,
        urls: list[str],
        max_chars: int = 16000,
        delay_between: float = 0.5
    ) -> list[FetchedContent]:
        """
        Fetch multiple URLs.

        Args:
            urls: List of URLs to fetch
            max_chars: Maximum characters per page
            delay_between: Delay between non-cached fetches

        Returns:
            List of FetchedContent objects
        """
        results = []

        for i, url in enumerate(urls):
            result = self.fetch(url, max_chars)
            results.append(result)

            # Add delay between non-cached fetches
            if result.error is None and i < len(urls) - 1:
                time.sleep(delay_between)

        return results

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
