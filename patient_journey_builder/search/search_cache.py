"""
Search result cache with TTL support.
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class SearchCache:
    """
    File-based cache for search results and fetched content.

    Supports TTL (time-to-live) for cache entries and
    automatic cleanup of expired entries.
    """

    def __init__(
        self,
        cache_dir: str = "data/cache",
        default_ttl_hours: int = 24 * 7,  # 1 week default
        enabled: bool = True
    ):
        """
        Initialize the cache.

        Args:
            cache_dir: Directory to store cache files
            default_ttl_hours: Default TTL in hours
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl_hours * 3600  # Convert to seconds
        self.enabled = enabled

        # Create subdirectories for different cache types
        (self.cache_dir / "search").mkdir(exist_ok=True)
        (self.cache_dir / "content").mkdir(exist_ok=True)

    def _get_cache_key(self, key: str) -> str:
        """
        Generate a cache key hash.

        Args:
            key: Original key string

        Returns:
            MD5 hash of the key
        """
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, key: str, cache_type: str = "search") -> Path:
        """
        Get the cache file path for a key.

        Args:
            key: Cache key
            cache_type: Type of cache (search or content)

        Returns:
            Path to cache file
        """
        hashed_key = self._get_cache_key(key)
        return self.cache_dir / cache_type / f"{hashed_key}.json"

    def get(self, key: str, cache_type: str = "search") -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: Cache key
            cache_type: Type of cache

        Returns:
            Cached value or None if not found/expired
        """
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(key, cache_type)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                entry = json.load(f)

            # Check TTL
            if entry.get('expires_at', 0) < time.time():
                logger.debug(f"Cache expired for key: {key[:50]}...")
                cache_path.unlink(missing_ok=True)
                return None

            logger.debug(f"Cache hit for key: {key[:50]}...")
            return entry.get('data')

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Cache read error: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        cache_type: str = "search",
        ttl_hours: Optional[int] = None
    ) -> None:
        """
        Store a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            cache_type: Type of cache
            ttl_hours: Optional TTL override in hours
        """
        if not self.enabled:
            return

        cache_path = self._get_cache_path(key, cache_type)

        ttl = (ttl_hours * 3600) if ttl_hours else self.default_ttl

        entry = {
            'key': key,
            'data': value,
            'created_at': time.time(),
            'expires_at': time.time() + ttl
        }

        try:
            with open(cache_path, 'w') as f:
                json.dump(entry, f)
            logger.debug(f"Cached value for key: {key[:50]}...")
        except IOError as e:
            logger.warning(f"Cache write error: {e}")

    def delete(self, key: str, cache_type: str = "search") -> bool:
        """
        Delete a cache entry.

        Args:
            key: Cache key
            cache_type: Type of cache

        Returns:
            True if entry was deleted
        """
        cache_path = self._get_cache_path(key, cache_type)

        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def clear(self, cache_type: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            cache_type: Optional type to clear (None = all)

        Returns:
            Number of entries cleared
        """
        count = 0

        if cache_type:
            cache_dirs = [self.cache_dir / cache_type]
        else:
            cache_dirs = [self.cache_dir / "search", self.cache_dir / "content"]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                for cache_file in cache_dir.glob("*.json"):
                    cache_file.unlink()
                    count += 1

        logger.info(f"Cleared {count} cache entries")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        count = 0
        current_time = time.time()

        for cache_type in ["search", "content"]:
            cache_dir = self.cache_dir / cache_type
            if not cache_dir.exists():
                continue

            for cache_file in cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        entry = json.load(f)

                    if entry.get('expires_at', 0) < current_time:
                        cache_file.unlink()
                        count += 1

                except (json.JSONDecodeError, IOError):
                    # Remove corrupted cache files
                    cache_file.unlink()
                    count += 1

        logger.info(f"Cleaned up {count} expired cache entries")
        return count

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        stats = {
            'enabled': self.enabled,
            'cache_dir': str(self.cache_dir),
            'search_entries': 0,
            'content_entries': 0,
            'total_size_mb': 0.0
        }

        for cache_type in ["search", "content"]:
            cache_dir = self.cache_dir / cache_type
            if cache_dir.exists():
                files = list(cache_dir.glob("*.json"))
                stats[f'{cache_type}_entries'] = len(files)
                stats['total_size_mb'] += sum(f.stat().st_size for f in files) / (1024 * 1024)

        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        return stats
