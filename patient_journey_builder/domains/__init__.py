"""
Domain definitions for the 7 patient journey research domains.
"""

from .base_domain import BaseDomain, BASE_SYNTHESIS_PROMPT
from .domain_implementations import (
    EpidemiologyDomain,
    HealthcareFinancesDomain,
    CompetitiveLandscapeDomain,
    ClinicalPathwaysDomain,
    PatientExperienceDomain,
    SegmentationDomain,
    StakeholdersDomain,
    DOMAINS,
    get_domain,
    get_all_domains,
)

__all__ = [
    "BaseDomain",
    "BASE_SYNTHESIS_PROMPT",
    "EpidemiologyDomain",
    "HealthcareFinancesDomain",
    "CompetitiveLandscapeDomain",
    "ClinicalPathwaysDomain",
    "PatientExperienceDomain",
    "SegmentationDomain",
    "StakeholdersDomain",
    "DOMAINS",
    "get_domain",
    "get_all_domains",
]
