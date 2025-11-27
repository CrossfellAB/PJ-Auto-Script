"""
Patient Journey Builder

Automates pharmaceutical patient journey database creation by orchestrating
web searches and Claude API synthesis across 7 research domains.
"""

__version__ = "1.0.0"
__author__ = "Patient Journey Builder Team"

from .config import Settings
from .core import PatientJourneyOrchestrator, SessionManager
from .models import PatientJourneyDatabase, DomainData

__all__ = [
    "Settings",
    "PatientJourneyOrchestrator",
    "SessionManager",
    "PatientJourneyDatabase",
    "DomainData",
    "__version__",
]
