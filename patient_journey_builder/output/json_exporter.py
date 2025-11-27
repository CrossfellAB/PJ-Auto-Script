"""
JSON exporter for patient journey databases.
"""

import json
from pathlib import Path
from typing import Union
import logging

from ..models import PatientJourneyDatabase

logger = logging.getLogger(__name__)


def export_to_json(
    database: PatientJourneyDatabase,
    output_path: Union[str, Path],
    indent: int = 2,
    include_raw_output: bool = False
) -> Path:
    """
    Export database to JSON file.

    Args:
        database: Database to export
        output_path: Path for output file
        indent: JSON indentation level
        include_raw_output: Whether to include raw synthesis output

    Returns:
        Path to exported file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict
    data = database.model_dump(mode='json')

    # Optionally remove raw output to reduce size
    if not include_raw_output:
        for domain_data in data.get('domains', {}).values():
            domain_data.pop('raw_synthesis_output', None)

    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False, default=str)

    logger.info(f"Exported JSON: {output_path}")
    return output_path


def export_tables_to_json(
    database: PatientJourneyDatabase,
    output_path: Union[str, Path]
) -> Path:
    """
    Export only tables to JSON (compact format).

    Args:
        database: Database to export
        output_path: Path for output file

    Returns:
        Path to exported file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract tables by domain
    tables_by_domain = {}

    for domain_id, domain_data in database.domains.items():
        tables_by_domain[domain_data.domain_name] = {
            table.table_name: {
                'headers': table.headers,
                'rows': table.rows,
                'confidence': table.confidence_level
            }
            for table in domain_data.tables
        }

    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tables_by_domain, f, indent=2, ensure_ascii=False)

    logger.info(f"Exported tables JSON: {output_path}")
    return output_path
