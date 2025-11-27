"""
Database models for Patient Journey data structures.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class DomainStatus(str, Enum):
    """Status of a domain research session."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchLogEntry(BaseModel):
    """Log entry for a single search operation."""

    query: str = Field(description="Search query executed")
    source_found: str = Field(default="", description="Primary source found")
    key_data_points: str = Field(default="", description="Key data extracted")
    timestamp: datetime = Field(default_factory=datetime.now)
    cached: bool = Field(default=False, description="Whether result was cached")
    results_count: int = Field(default=0, description="Number of results returned")


class DataTable(BaseModel):
    """Represents a structured data table."""

    table_name: str = Field(description="Name/identifier of the table")
    headers: List[str] = Field(default_factory=list, description="Column headers")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Table rows as dicts")
    sources: List[str] = Field(default_factory=list, description="Source URLs/references")
    confidence_level: str = Field(default="MEDIUM", description="HIGH, MEDIUM, or LOW")
    data_gaps: List[str] = Field(default_factory=list, description="Identified data gaps")
    notes: Optional[str] = Field(default=None, description="Additional notes")

    @property
    def row_count(self) -> int:
        """Get number of rows in the table."""
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        """Check if table has no data."""
        return len(self.rows) == 0


class QualitySummary(BaseModel):
    """Quality metrics for a domain or database."""

    searches_completed: int = Field(default=0)
    tables_populated: int = Field(default=0)
    confidence_level: str = Field(default="MEDIUM")
    primary_source_quality: str = Field(default="MEDIUM")
    data_recency: str = Field(default="Unknown")
    validation_gaps: List[str] = Field(default_factory=list)
    parse_method: Optional[str] = Field(default=None)


class DomainData(BaseModel):
    """Data collected for a single research domain."""

    domain_id: int = Field(description="Domain number (1-7)")
    domain_name: str = Field(description="Human-readable domain name")
    status: DomainStatus = Field(default=DomainStatus.NOT_STARTED)

    # Research data
    search_log: List[SearchLogEntry] = Field(default_factory=list)
    tables: List[DataTable] = Field(default_factory=list)
    raw_synthesis_output: Optional[str] = Field(default=None, description="Raw Claude output")

    # Quality metrics
    quality_summary: QualitySummary = Field(default_factory=QualitySummary)

    # Timing
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    # Cost tracking
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate domain processing duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_table(self, name: str) -> Optional[DataTable]:
        """Get a table by name."""
        for table in self.tables:
            if table.table_name == name:
                return table
        return None


class PatientJourneyDatabase(BaseModel):
    """Complete patient journey database."""

    # Metadata
    disease_area: str = Field(description="Disease/condition being researched")
    country: str = Field(description="Target country")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    version: str = Field(default="1.0")

    # Session tracking
    session_id: Optional[str] = Field(default=None)
    current_domain: int = Field(default=1, ge=1, le=8)
    total_domains: int = Field(default=7)
    overall_status: str = Field(default="in_progress")

    # Domain data
    domains: Dict[int, DomainData] = Field(default_factory=dict)

    # Validation
    completeness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    data_gaps_summary: List[str] = Field(default_factory=list)

    # Cost tracking
    total_cost_usd: float = Field(default=0.0)

    def get_domain(self, domain_id: int) -> Optional[DomainData]:
        """Get domain data by ID."""
        return self.domains.get(domain_id)

    def set_domain(self, domain_data: DomainData) -> None:
        """Set domain data."""
        self.domains[domain_data.domain_id] = domain_data
        self.updated_at = datetime.now()

    def calculate_completeness(self) -> float:
        """Calculate overall completeness percentage."""
        if not self.domains:
            return 0.0

        completed = sum(
            1 for d in self.domains.values()
            if d.status == DomainStatus.COMPLETED
        )
        return (completed / self.total_domains) * 100

    def get_all_tables(self) -> List[DataTable]:
        """Get all tables from all domains."""
        tables = []
        for domain in self.domains.values():
            tables.extend(domain.tables)
        return tables

    def to_session_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for session storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_session_dict(cls, data: Dict[str, Any]) -> "PatientJourneyDatabase":
        """Create from session dictionary."""
        return cls.model_validate(data)
