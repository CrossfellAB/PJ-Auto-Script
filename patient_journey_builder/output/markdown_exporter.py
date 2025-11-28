"""
Enhanced markdown exporter for patient journey databases.

Produces reference-quality output with:
- Search logs per domain
- Named entities (KOLs, institutions, payers)
- Data gaps documentation
- Quality summary tables
- Sources for validation
"""

from pathlib import Path
from typing import Union, List, Dict, Any, Optional
from datetime import datetime
import logging

from ..models import PatientJourneyDatabase, DomainData, DataTable

logger = logging.getLogger(__name__)


def export_to_markdown(
    database: PatientJourneyDatabase,
    output_path: Union[str, Path]
) -> Path:
    """
    Export database to Markdown file with reference-quality formatting.

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
    country_upper = database.country.upper()
    disease_upper = database.disease_area.upper()
    lines.append(f"# {country_upper} {disease_upper} - PATIENT JOURNEY DATABASE")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Metadata
    lines.append("## Database Information")
    lines.append("")
    lines.append(f"| Attribute | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Disease | {database.disease_area} |")
    lines.append(f"| Country | {database.country} |")
    lines.append(f"| Generated | {database.updated_at.strftime('%Y-%m-%d %H:%M')} |")
    lines.append(f"| Completeness | {database.completeness_score:.1f}% |")
    if database.total_cost_usd > 0:
        lines.append(f"| Estimated Cost | ${database.total_cost_usd:.2f} |")
    lines.append(f"| Domains Completed | {len([d for d in database.domains.values() if d.status.value == 'completed'])}/7 |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        anchor = domain.domain_name.lower().replace(' ', '-')
        lines.append(f"- [Domain {domain_id}: {domain.domain_name}](#domain-{domain_id}-{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Each domain
    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        lines.extend(_format_domain_enhanced(domain, database.country))
        lines.append("")

    # Global Data Gaps Summary
    if database.data_gaps_summary:
        lines.append("---")
        lines.append("")
        lines.append("## Global Data Gaps Summary")
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


def _format_domain_enhanced(domain: DomainData, country: str) -> List[str]:
    """Format a domain section with enhanced reference-quality output."""
    lines = []

    # Domain header
    country_upper = country.upper()
    lines.append(f"# {country_upper} - DOMAIN {domain.domain_id}: {domain.domain_name.upper()}")
    lines.append("")

    # Search Log (if available in raw_response)
    search_log = _extract_search_log(domain)
    if search_log:
        lines.append("## Search Log")
        lines.append("")
        lines.append("| # | Query | Source Found | Key Data Points |")
        lines.append("|---|-------|--------------|-----------------|")
        for entry in search_log:
            query_num = entry.get('query_number', entry.get('#', ''))
            query = _escape_pipe(str(entry.get('query', '')))[:80]
            source = _escape_pipe(str(entry.get('source_found', entry.get('Source Found', ''))))[:60]
            data_points = _escape_pipe(str(entry.get('key_data_points', entry.get('Key Data Points', ''))))[:100]
            lines.append(f"| {query_num} | {query} | {source} | {data_points} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # All Tables
    for table in domain.tables:
        lines.extend(_format_table_enhanced(table))
        lines.append("")

    # Named Entities (if available)
    named_entities = _extract_named_entities(domain)
    if named_entities:
        lines.append("---")
        lines.append("")
        lines.extend(_format_named_entities(named_entities))

    # Sources for Validation
    sources = _extract_sources_for_validation(domain)
    if sources:
        lines.append("---")
        lines.append("")
        lines.append("## Sources for Validation")
        lines.append("")
        for i, source in enumerate(sources, 1):
            lines.append(f"{i}. {source}")
        lines.append("")

    # Data Gaps
    data_gaps = _extract_data_gaps(domain)
    if data_gaps:
        lines.append("---")
        lines.append("")
        lines.append("## Data Gaps Identified")
        lines.append("")
        for gap in data_gaps:
            lines.append(f"- {gap}")
        lines.append("")

    # Quality Summary Table
    lines.append("---")
    lines.append("")
    lines.append(f"## Domain {domain.domain_id} Quality Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    if domain.quality_summary:
        qs = domain.quality_summary
        lines.append(f"| Searches completed | {qs.tables_populated if hasattr(qs, 'tables_populated') else 'N/A'} |")
        lines.append(f"| Tables populated | {len(domain.tables)} |")
        lines.append(f"| Key stats cross-validated | {'Yes' if getattr(qs, 'key_stats_cross_validated', False) else 'Partial'} |")
        lines.append(f"| Confidence level | {qs.confidence_level} |")
        lines.append(f"| Primary data source quality | {getattr(qs, 'primary_source_quality', qs.confidence_level)} |")
        lines.append(f"| Data recency | {qs.data_recency} |")
    else:
        lines.append(f"| Tables populated | {len(domain.tables)} |")
        lines.append(f"| Confidence level | MEDIUM |")

    lines.append("")
    lines.append("---")

    return lines


def _format_table_enhanced(table: DataTable) -> List[str]:
    """Format a data table with enhanced formatting."""
    lines = []

    # Section header with table name
    section_num = f"### {table.table_name.replace('_', ' ').title()}"
    lines.append(section_num)
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
                value = _escape_pipe(value)
                # Truncate long values
                if len(value) > 150:
                    value = value[:147] + "..."
                values.append(value)
            lines.append("| " + " | ".join(values) + " |")

        lines.append("")
    else:
        lines.append("*No data available*")
        lines.append("")

    return lines


def _format_named_entities(entities: Dict[str, List[Dict]]) -> List[str]:
    """Format named entities section."""
    lines = []

    lines.append("## Named Entities Identified")
    lines.append("")

    # KOLs
    if entities.get('kols'):
        lines.append("### Key Opinion Leaders")
        lines.append("")
        lines.append("| Name | Institution | Role | Expertise |")
        lines.append("|------|-------------|------|-----------|")
        for kol in entities['kols']:
            name = _escape_pipe(str(kol.get('name', '')))
            inst = _escape_pipe(str(kol.get('institution', '')))
            role = _escape_pipe(str(kol.get('role', kol.get('position', ''))))
            expertise = _escape_pipe(str(kol.get('expertise', kol.get('specialty', ''))))
            lines.append(f"| {name} | {inst} | {role} | {expertise} |")
        lines.append("")

    # Institutions
    if entities.get('institutions'):
        lines.append("### Institutions")
        lines.append("")
        lines.append("| Name | Location | Type | Specialization |")
        lines.append("|------|----------|------|----------------|")
        for inst in entities['institutions']:
            name = _escape_pipe(str(inst.get('name', '')))
            loc = _escape_pipe(str(inst.get('location', '')))
            inst_type = _escape_pipe(str(inst.get('type', '')))
            spec = _escape_pipe(str(inst.get('specialization', '')))
            lines.append(f"| {name} | {loc} | {inst_type} | {spec} |")
        lines.append("")

    # Payer Bodies
    if entities.get('payer_bodies'):
        lines.append("### Payer Bodies")
        lines.append("")
        lines.append("| Organization | Role | Key Decisions |")
        lines.append("|--------------|------|---------------|")
        for payer in entities['payer_bodies']:
            name = _escape_pipe(str(payer.get('name', '')))
            role = _escape_pipe(str(payer.get('role', '')))
            decisions = _escape_pipe(str(payer.get('decisions', '')))
            lines.append(f"| {name} | {role} | {decisions} |")
        lines.append("")

    # Professional Societies
    if entities.get('professional_societies'):
        lines.append("### Professional Societies")
        lines.append("")
        lines.append("| Organization | Abbreviation | Focus |")
        lines.append("|--------------|--------------|-------|")
        for soc in entities['professional_societies']:
            name = _escape_pipe(str(soc.get('name', '')))
            abbr = _escape_pipe(str(soc.get('abbreviation', '')))
            focus = _escape_pipe(str(soc.get('focus', '')))
            lines.append(f"| {name} | {abbr} | {focus} |")
        lines.append("")

    # Patient Organizations
    if entities.get('patient_organizations'):
        lines.append("### Patient Organizations")
        lines.append("")
        lines.append("| Organization | Focus | Activities |")
        lines.append("|--------------|-------|------------|")
        for org in entities['patient_organizations']:
            name = _escape_pipe(str(org.get('name', '')))
            focus = _escape_pipe(str(org.get('focus', '')))
            activities = _escape_pipe(str(org.get('activities', '')))
            lines.append(f"| {name} | {focus} | {activities} |")
        lines.append("")

    return lines


def _extract_search_log(domain: DomainData) -> Optional[List[Dict]]:
    """Extract search log from domain raw response."""
    if not domain.raw_response:
        return None

    if isinstance(domain.raw_response, dict):
        return domain.raw_response.get('search_log', [])

    return None


def _extract_named_entities(domain: DomainData) -> Optional[Dict[str, List[Dict]]]:
    """Extract named entities from domain raw response."""
    if not domain.raw_response:
        return None

    if isinstance(domain.raw_response, dict):
        return domain.raw_response.get('named_entities', None)

    return None


def _extract_sources_for_validation(domain: DomainData) -> Optional[List[str]]:
    """Extract sources for validation from domain raw response."""
    if not domain.raw_response:
        return None

    if isinstance(domain.raw_response, dict):
        return domain.raw_response.get('sources_for_validation', [])

    return None


def _extract_data_gaps(domain: DomainData) -> List[str]:
    """Extract data gaps from domain."""
    gaps = []

    # From raw response
    if domain.raw_response and isinstance(domain.raw_response, dict):
        raw_gaps = domain.raw_response.get('data_gaps', [])
        if raw_gaps:
            gaps.extend(raw_gaps)

    # From quality summary
    if domain.quality_summary and domain.quality_summary.validation_gaps:
        gaps.extend(domain.quality_summary.validation_gaps)

    # From tables
    for table in domain.tables:
        if table.data_gaps:
            gaps.extend(table.data_gaps)

    # Remove duplicates while preserving order
    seen = set()
    unique_gaps = []
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            unique_gaps.append(gap)

    return unique_gaps


def _escape_pipe(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|").replace("\n", " ")


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
    lines.append(f"| Attribute | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Disease | {database.disease_area} |")
    lines.append(f"| Country | {database.country} |")
    lines.append(f"| Completeness | {database.completeness_score:.1f}% |")
    lines.append(f"| Domains Completed | {len([d for d in database.domains.values() if d.status.value == 'completed'])}/7 |")
    if database.total_cost_usd > 0:
        lines.append(f"| Estimated Cost | ${database.total_cost_usd:.2f} |")
    lines.append("")

    # Domain summaries
    lines.append("## Domain Summary")
    lines.append("")
    lines.append("| Domain | Status | Tables | Confidence |")
    lines.append("|--------|--------|--------|------------|")

    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        status_emoji = '✅' if domain.status.value == 'completed' else '❌'
        confidence = domain.quality_summary.confidence_level if domain.quality_summary else "N/A"
        lines.append(f"| {domain_id}. {domain.domain_name} | {status_emoji} | {len(domain.tables)} | {confidence} |")

    lines.append("")

    # Data tables per domain
    for domain_id in sorted(database.domains.keys()):
        domain = database.domains[domain_id]
        lines.append(f"### {domain_id}. {domain.domain_name}")
        lines.append("")

        if domain.tables:
            for table in domain.tables:
                row_count = len(table.rows)
                confidence = table.confidence_level or "MEDIUM"
                lines.append(f"- {table.table_name.replace('_', ' ').title()} ({row_count} rows) - {confidence}")
        else:
            lines.append("- *No data collected*")

        lines.append("")

    # Write file
    content = "\n".join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Exported summary Markdown: {output_path}")
    return output_path
