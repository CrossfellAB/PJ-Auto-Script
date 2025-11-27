"""
Session management for persistent state and resumption.
"""

import json
import fcntl
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

from ..models import PatientJourneyDatabase, DomainStatus

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Handles session persistence and resumption.

    Provides:
    - Session creation and loading
    - Checkpoint saving after each domain
    - Resume point detection
    - File locking for safe concurrent access
    """

    def __init__(
        self,
        disease: str,
        country: str,
        session_dir: str = "data/sessions"
    ):
        """
        Initialize the session manager.

        Args:
            disease: Disease/condition name
            country: Target country
            session_dir: Directory for session files
        """
        self.disease = disease
        self.country = country
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Generate session ID
        self.session_id = self._generate_session_id(country, disease)
        self.session_file = self.session_dir / f"{self.session_id}_session.json"

    def _generate_session_id(self, country: str, disease: str) -> str:
        """
        Generate a session ID from country and disease.

        Args:
            country: Target country
            disease: Disease name

        Returns:
            Session ID string
        """
        # Normalize: lowercase, replace spaces with underscores
        country_norm = country.lower().replace(' ', '_').replace('-', '_')
        disease_norm = disease.lower().replace(' ', '_').replace('-', '_')

        # Remove special characters
        import re
        country_norm = re.sub(r'[^\w]', '', country_norm)
        disease_norm = re.sub(r'[^\w]', '', disease_norm)

        return f"{country_norm}_{disease_norm}"

    def load_or_create(self) -> PatientJourneyDatabase:
        """
        Load existing session or create new one.

        Returns:
            PatientJourneyDatabase instance
        """
        if self.session_file.exists():
            return self._load_session()

        return self._create_session()

    def _load_session(self) -> PatientJourneyDatabase:
        """
        Load session from file.

        Returns:
            PatientJourneyDatabase instance
        """
        try:
            with open(self.session_file, 'r') as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            database = PatientJourneyDatabase.from_session_dict(data)
            logger.info(f"Loaded session: {self.session_id}")
            logger.info(f"  Disease: {database.disease_area}")
            logger.info(f"  Country: {database.country}")
            logger.info(f"  Current domain: {database.current_domain}")
            logger.info(f"  Completeness: {database.completeness_score:.1f}%")

            return database

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load session, creating new: {e}")
            return self._create_session()

    def _create_session(self) -> PatientJourneyDatabase:
        """
        Create a new session.

        Returns:
            New PatientJourneyDatabase instance
        """
        database = PatientJourneyDatabase(
            disease_area=self.disease,
            country=self.country,
            session_id=self.session_id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        logger.info(f"Created new session: {self.session_id}")
        return database

    def save(self, database: PatientJourneyDatabase) -> None:
        """
        Persist session state to disk.

        Uses file locking for safe concurrent access.

        Args:
            database: Database to save
        """
        database.updated_at = datetime.now()
        database.completeness_score = database.calculate_completeness()

        try:
            with open(self.session_file, 'w') as f:
                # Acquire exclusive lock for writing
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(database.to_session_dict(), f, indent=2, default=str)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            logger.debug(f"Session saved: {self.session_file}")

        except IOError as e:
            logger.error(f"Failed to save session: {e}")
            raise

    def get_resume_point(self, database: PatientJourneyDatabase) -> int:
        """
        Determine which domain to resume from.

        Args:
            database: Database to check

        Returns:
            Domain ID to resume from (1-7, or 8 if all complete)
        """
        for domain_id in range(1, 8):
            if domain_id not in database.domains:
                return domain_id

            domain = database.domains[domain_id]
            if domain.status not in [DomainStatus.COMPLETED]:
                return domain_id

        return 8  # All complete

    def get_session_status(self) -> Optional[dict]:
        """
        Get status of the current session without loading full database.

        Returns:
            Status dict or None if session doesn't exist
        """
        if not self.session_file.exists():
            return None

        try:
            with open(self.session_file, 'r') as f:
                data = json.load(f)

            return {
                'session_id': self.session_id,
                'disease': data.get('disease_area'),
                'country': data.get('country'),
                'current_domain': data.get('current_domain', 1),
                'overall_status': data.get('overall_status', 'unknown'),
                'completeness': data.get('completeness_score', 0),
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
                'domains_completed': sum(
                    1 for d in data.get('domains', {}).values()
                    if d.get('status') == 'completed'
                )
            }

        except (json.JSONDecodeError, IOError):
            return None

    def delete_session(self) -> bool:
        """
        Delete the session file.

        Returns:
            True if session was deleted
        """
        if self.session_file.exists():
            self.session_file.unlink()
            logger.info(f"Deleted session: {self.session_id}")
            return True
        return False

    def backup_session(self) -> Optional[Path]:
        """
        Create a backup of the current session.

        Returns:
            Path to backup file or None if session doesn't exist
        """
        if not self.session_file.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.session_dir / f"{self.session_id}_backup_{timestamp}.json"

        import shutil
        shutil.copy2(self.session_file, backup_file)

        logger.info(f"Created session backup: {backup_file}")
        return backup_file


def list_sessions(session_dir: str = "data/sessions") -> list[dict]:
    """
    List all available sessions.

    Args:
        session_dir: Directory containing session files

    Returns:
        List of session status dictionaries
    """
    sessions = []
    session_path = Path(session_dir)

    if not session_path.exists():
        return sessions

    for session_file in session_path.glob("*_session.json"):
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)

            sessions.append({
                'session_id': session_file.stem.replace('_session', ''),
                'disease': data.get('disease_area'),
                'country': data.get('country'),
                'status': data.get('overall_status'),
                'completeness': data.get('completeness_score', 0),
                'updated_at': data.get('updated_at')
            })

        except (json.JSONDecodeError, IOError):
            continue

    # Sort by update time (most recent first)
    sessions.sort(key=lambda x: x.get('updated_at', ''), reverse=True)

    return sessions
