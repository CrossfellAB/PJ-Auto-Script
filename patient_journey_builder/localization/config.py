"""
Localization configuration for country-specific settings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Try to import YAML support
try:
    import yaml
    YAML_SUPPORT = True
except ImportError:
    YAML_SUPPORT = False


@dataclass
class CountryConfig:
    """Configuration for a specific country."""

    country_code: str
    country_name: str
    language_code: str
    search_language: str = "en"

    # Local terminology for medical concepts
    medical_terms: Dict[str, str] = field(default_factory=dict)

    # Preferred data sources for this country
    priority_sources: List[str] = field(default_factory=list)

    # Government health authority domains
    health_authority_domains: List[str] = field(default_factory=list)

    # Population data
    population: Optional[int] = None
    major_cities: List[str] = field(default_factory=list)

    # Healthcare system specifics
    healthcare_system_type: str = ""
    currency: str = "USD"

    def localize_query(self, query_template: str, disease: str) -> str:
        """
        Localize a search query for this country.

        Args:
            query_template: Query with placeholders
            disease: Disease name

        Returns:
            Localized query string
        """
        query = query_template.format(
            disease=disease,
            country=self.country_name,
            major_city=self.major_cities[0] if self.major_cities else ""
        )

        # Add local language variant if available
        local_disease = self.medical_terms.get(disease.lower())
        if local_disease and local_disease.lower() != disease.lower():
            query = f"{query} OR {local_disease}"

        return query


class LocalizationManager:
    """Manages country-specific configurations."""

    # Built-in configurations for common markets
    BUILTIN_CONFIGS = {
        'sweden': CountryConfig(
            country_code='SE',
            country_name='Sweden',
            language_code='sv',
            search_language='en',
            medical_terms={
                'chronic spontaneous urticaria': 'kronisk spontan urtikaria',
                'atopic dermatitis': 'atopisk dermatit',
                'psoriasis': 'psoriasis',
                'asthma': 'astma',
            },
            priority_sources=[
                'socialstyrelsen.se',
                'folkhalsomyndigheten.se',
                'lakemedelsverket.se',
                'sbu.se',
                'tlv.se',
            ],
            health_authority_domains=[
                'socialstyrelsen.se',
                'folkhalsomyndigheten.se'
            ],
            population=10_500_000,
            major_cities=['Stockholm', 'Gothenburg', 'Malmö'],
            healthcare_system_type='single-payer',
            currency='SEK'
        ),
        'germany': CountryConfig(
            country_code='DE',
            country_name='Germany',
            language_code='de',
            search_language='en',
            medical_terms={
                'chronic spontaneous urticaria': 'chronische spontane Urtikaria',
                'atopic dermatitis': 'atopische Dermatitis',
                'psoriasis': 'Schuppenflechte',
            },
            priority_sources=[
                'rki.de',
                'g-ba.de',
                'iqwig.de',
                'awmf.org',
                'bfarm.de',
            ],
            health_authority_domains=[
                'rki.de',
                'bundesgesundheitsministerium.de'
            ],
            population=84_000_000,
            major_cities=['Berlin', 'Munich', 'Hamburg', 'Frankfurt'],
            healthcare_system_type='insurance-based',
            currency='EUR'
        ),
        'uk': CountryConfig(
            country_code='GB',
            country_name='United Kingdom',
            language_code='en',
            search_language='en',
            medical_terms={},
            priority_sources=[
                'nice.org.uk',
                'nhs.uk',
                'gov.uk',
                'bnf.nice.org.uk',
                'medicines.org.uk',
            ],
            health_authority_domains=[
                'nhs.uk',
                'gov.uk'
            ],
            population=67_000_000,
            major_cities=['London', 'Manchester', 'Birmingham', 'Edinburgh'],
            healthcare_system_type='single-payer',
            currency='GBP'
        ),
        'france': CountryConfig(
            country_code='FR',
            country_name='France',
            language_code='fr',
            search_language='en',
            medical_terms={
                'chronic spontaneous urticaria': 'urticaire chronique spontanée',
                'atopic dermatitis': 'dermatite atopique',
            },
            priority_sources=[
                'has-sante.fr',
                'ansm.sante.fr',
                'santepubliquefrance.fr',
            ],
            population=67_500_000,
            major_cities=['Paris', 'Lyon', 'Marseille'],
            healthcare_system_type='insurance-based',
            currency='EUR'
        ),
    }

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the localization manager.

        Args:
            config_dir: Optional directory for custom YAML configs
        """
        self.config_dir = Path(config_dir) if config_dir else None
        self._configs: Dict[str, CountryConfig] = dict(self.BUILTIN_CONFIGS)

        # Load custom configs
        if self.config_dir and self.config_dir.exists():
            self._load_custom_configs()

    def _load_custom_configs(self) -> None:
        """Load custom country configs from YAML files."""
        if not YAML_SUPPORT:
            logger.warning("YAML support not available - custom configs not loaded")
            return

        for yaml_file in self.config_dir.glob('*.yaml'):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                    config = CountryConfig(**data)
                    self._configs[config.country_name.lower()] = config
                    logger.info(f"Loaded custom config: {config.country_name}")
            except Exception as e:
                logger.warning(f"Failed to load {yaml_file}: {e}")

    def get_config(self, country: str) -> CountryConfig:
        """
        Get configuration for a country.

        Args:
            country: Country name

        Returns:
            CountryConfig for the country (or generic if not found)
        """
        country_lower = country.lower()

        if country_lower in self._configs:
            return self._configs[country_lower]

        # Return generic config
        return CountryConfig(
            country_code='XX',
            country_name=country,
            language_code='en',
            search_language='en'
        )

    def get_major_city(self, country: str) -> str:
        """
        Get the major city for a country.

        Args:
            country: Country name

        Returns:
            Major city name or empty string
        """
        config = self.get_config(country)
        return config.major_cities[0] if config.major_cities else ""

    def generate_localized_queries(
        self,
        base_queries: List[str],
        disease: str,
        country: str
    ) -> List[str]:
        """
        Generate localized search queries.

        Args:
            base_queries: List of query templates
            disease: Disease name
            country: Target country

        Returns:
            List of localized queries
        """
        config = self.get_config(country)

        localized = []
        for query in base_queries:
            localized.append(config.localize_query(query, disease))

        # Add country-specific source queries
        for source in config.priority_sources[:3]:
            localized.append(f"site:{source} {disease}")

        return localized

    def list_countries(self) -> List[str]:
        """Get list of configured countries."""
        return list(self._configs.keys())
