"""
Search result models.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SearchResult(BaseModel):
    """Represents a single search result from Brave Search API."""

    title: str = Field(description="Page title")
    url: str = Field(description="Page URL")
    description: str = Field(default="", description="Search snippet/description")
    source: str = Field(default="", description="Domain/hostname")

    # Optional metadata
    published_date: Optional[str] = Field(default=None, description="Publication date if available")
    language: Optional[str] = Field(default=None, description="Content language")

    def __str__(self) -> str:
        return f"{self.title} ({self.source})"


class SearchQuery(BaseModel):
    """Represents a search query with metadata."""

    query: str = Field(description="The search query string")
    country: Optional[str] = Field(default=None, description="Target country for search")
    language: Optional[str] = Field(default="en", description="Search language")
    executed_at: Optional[datetime] = Field(default=None, description="When query was executed")
    result_count: int = Field(default=0, description="Number of results returned")
    cached: bool = Field(default=False, description="Whether results were from cache")


class FetchedContent(BaseModel):
    """Represents fetched page content."""

    url: str = Field(description="Source URL")
    content: Optional[str] = Field(default=None, description="Extracted text content")
    content_type: str = Field(default="text/html", description="Content MIME type")
    fetch_time_ms: int = Field(default=0, description="Time to fetch in milliseconds")
    truncated: bool = Field(default=False, description="Whether content was truncated")
    error: Optional[str] = Field(default=None, description="Error message if fetch failed")

    @property
    def success(self) -> bool:
        """Check if content was successfully fetched."""
        return self.content is not None and self.error is None
