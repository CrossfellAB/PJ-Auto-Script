"""
Markdown exporter for patient journey databases.
"""

from pathlib import Path
from typing import Union, List, Dict, Any
from datetime import datetime
import logging

from ..models import PatientJourneyDatabase, DomainData, DataTable

logger = logging.getLogger(__name__)


def export_to_markdown(
    database: PatientJourneyDatabase,
    output_path: Union[str, Path]
) -> Path:
    """
    Export database to Markdown file.

    Args:
        database: Database to export
        output_path: Path for output file

    Returns:
        Path to exported file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # Header
    lines.append(f"# Patient Journey Database: {database.disease_area}")
    lines.append(f"")
    lines.append(f"**Country:** {database.country}")
    lines.append(f"**Generated:** {database.updated_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Completeness:** {database.completeness_score:.1f}%")
    if database.total_cost_usd > 0:
        lines.append(f"**Estimated Cost:** ${database.total_cost_usd:.2f}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        anchor = domain.domain_name.lower().replace(' ', '-')
        lines.append(f"- [{domain_id}. {domain.domain_name}](#{domain_id}-{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Each domain
    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        lines.extend(_format_domain(domain))
        lines.append("")
        lines.append("---")
        lines.append("")

    # Data Gaps Summary
    if database.data_gaps_summary:
        lines.append("## Data Gaps Summary")
        lines.append("")
        for gap in database.data_gaps_summary:
            lines.append(f"- {gap}")
        lines.append("")

    # Write file
    content = "\n".join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Exported Markdown: {output_path}")
    return output_path


def _format_domain(domain: DomainData) -> List[str]:
    """Format a domain section."""
    lines = []

    # Domain header
    lines.append(f"## {domain.domain_id}. {domain.domain_name}")
    lines.append("")

    # Status
    status_emoji = {
        'completed': '✅',
        'in_progress': '🔄',
        'failed': '❌',
        'not_started': '⬜'
    }.get(domain.status.value, '❓')

    lines.append(f"**Status:** {status_emoji} {domain.status.value}")

    if domain.started_at:
        lines.append(f"**Started:** {domain.started_at.strftime('%Y-%m-%d %H:%M')}")
    if domain.completed_at:
        lines.append(f"**Completed:** {domain.completed_at.strftime('%Y-%m-%d %H:%M')}")

    lines.append("")

    # Quality summary
    if domain.quality_summary:
        qs = domain.quality_summary
        lines.append("### Quality Summary")
        lines.append("")
        lines.append(f"- Tables populated: {qs.tables_populated}")
        lines.append(f"- Confidence: {qs.confidence_level}")
        lines.append(f"- Data recency: {qs.data_recency}")

        if qs.validation_gaps:
            lines.append(f"- Validation gaps: {len(qs.validation_gaps)}")
            for gap in qs.validation_gaps[:5]:
                lines.append(f"  - {gap}")

        lines.append("")

    # Tables
    for table in domain.tables:
        lines.extend(_format_table(table))
        lines.append("")

    return lines


def _format_table(table: DataTable) -> List[str]:
    """Format a data table as markdown."""
    lines = []

    # Table title
    title = table.table_name.replace('_', ' ').title()
    lines.append(f"### {title}")
    lines.append("")

    # Confidence badge
    confidence_badge = {
        'HIGH': '🟢 High',
        'MEDIUM': '🟡 Medium',
        'LOW': '🔴 Low'
    }.get(table.confidence_level, table.confidence_level)

    lines.append(f"*Confidence: {confidence_badge}*")
    lines.append("")

    # Table content
    if table.headers and table.rows:
        # Header row
        lines.append("| " + " | ".join(table.headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(table.headers)) + " |")

        # Data rows
        for row in table.rows:
            values = []
            for header in table.headers:
                value = str(row.get(header, ""))
                # Escape pipe characters
                value = value.replace("|", "\\|")
                # Truncate long values
                if len(value) > 100:
                    value = value[:97] + "..."
                values.append(value)
            lines.append("| " + " | ".join(values) + " |")

        lines.append("")

    # Sources
    if table.sources:
        lines.append("**Sources:**")
        for source in table.sources[:5]:
            lines.append(f"- {source}")
        lines.append("")

    # Data gaps
    if table.data_gaps:
        lines.append("**Data Gaps:**")
        for gap in table.data_gaps:
            lines.append(f"- {gap}")
        lines.append("")

    return lines


def export_summary_markdown(
    database: PatientJourneyDatabase,
    output_path: Union[str, Path]
) -> Path:
    """
    Export a summary-only markdown (no detailed tables).

    Args:
        database: Database to export
        output_path: Path for output file

    Returns:
        Path to exported file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # Header
    lines.append(f"# Patient Journey Summary: {database.disease_area} in {database.country}")
    lines.append("")
    lines.append(f"*Generated: {database.updated_at.strftime('%Y-%m-%d')}*")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Disease:** {database.disease_area}")
    lines.append(f"- **Country:** {database.country}")
    lines.append(f"- **Completeness:** {database.completeness_score:.1f}%")
    lines.append(f"- **Domains Completed:** {len([d for d in database.domains.values() if d.status.value == 'completed'])}/7")
    lines.append("")

    # Domain summaries
    lines.append("## Domain Summary")
    lines.append("")

    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        status_emoji = '✅' if domain.status.value == 'completed' else '❌'

        lines.append(f"### {domain_id}. {domain.domain_name} {status_emoji}")
        lines.append("")
        lines.append(f"- Tables: {len(domain.tables)}")
        lines.append(f"- Confidence: {domain.quality_summary.confidence_level}")

        # List table names
        if domain.tables:
            lines.append(f"- Data collected:")
            for table in domain.tables:
                lines.append(f"  - {table.table_name.replace('_', ' ').title()} ({len(table.rows)} rows)")

        lines.append("")

    # Write file
    content = "\n".join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Exported summary Markdown: {output_path}")
    return output_path
