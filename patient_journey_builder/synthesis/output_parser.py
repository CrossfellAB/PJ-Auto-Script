"""
Robust output parsing for Claude synthesis results.
"""

import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing Claude's output."""

    success: bool
    data: Optional[Dict[str, Any]]
    errors: List[str] = field(default_factory=list)
    raw_output: str = ""
    parse_method: str = ""

    @property
    def tables(self) -> Dict:
        """Get tables from parsed data."""
        return self.data.get('tables', {}) if self.data else {}

    @property
    def search_log(self) -> List:
        """Get search log from parsed data."""
        return self.data.get('search_log', []) if self.data else []

    @property
    def data_gaps(self) -> List:
        """Get data gaps from parsed data."""
        return self.data.get('data_gaps', []) if self.data else []

    @property
    def quality_summary(self) -> Dict:
        """Get quality summary from parsed data."""
        return self.data.get('quality_summary', {}) if self.data else {}


class OutputParser:
    """
    Robust parser for Claude's domain synthesis output.

    Handles multiple output formats and provides graceful degradation:
    1. JSON code block extraction
    2. Raw JSON parsing
    3. Markdown table extraction (fallback)
    """

    def parse(self, output: str) -> ParseResult:
        """
        Parse Claude's output into structured data.

        Attempts multiple parsing strategies in order.

        Args:
            output: Raw Claude output text

        Returns:
            ParseResult with parsed data or errors
        """
        errors = []

        # Strategy 1: Extract JSON from code block
        json_data = self._extract_json_block(output)
        if json_data:
            validation_errors = self._validate_structure(json_data)
            if not validation_errors:
                return ParseResult(
                    success=True,
                    data=json_data,
                    errors=[],
                    raw_output=output,
                    parse_method="json_block"
                )
            errors.extend(validation_errors)

        # Strategy 2: Try parsing entire output as JSON
        try:
            json_data = json.loads(output)
            validation_errors = self._validate_structure(json_data)
            if not validation_errors:
                return ParseResult(
                    success=True,
                    data=json_data,
                    errors=[],
                    raw_output=output,
                    parse_method="raw_json"
                )
            errors.extend(validation_errors)
        except json.JSONDecodeError:
            pass

        # Strategy 3: Extract markdown tables as fallback
        tables = self._extract_markdown_tables(output)
        if tables:
            logger.warning(
                f"JSON parse failed, using markdown fallback. Found {len(tables)} tables."
            )
            return ParseResult(
                success=True,
                data={
                    'tables': tables,
                    'search_log': [],
                    'data_gaps': ['Structured output parsing failed - extracted from markdown'],
                    'quality_summary': {'parse_method': 'markdown_fallback'}
                },
                errors=errors,
                raw_output=output,
                parse_method="markdown_fallback"
            )

        # All strategies failed
        logger.error(f"Output parse failed with errors: {errors}")
        return ParseResult(
            success=False,
            data=None,
            errors=errors + ['All parsing strategies failed'],
            raw_output=output,
            parse_method="failed"
        )

    def _extract_json_block(self, text: str) -> Optional[Dict]:
        """
        Extract JSON from markdown code block.

        Args:
            text: Text containing potential JSON block

        Returns:
            Parsed JSON dict or None
        """
        # Match ```json ... ``` or ``` ... ```
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*(\{[\s\S]*?\})\s*```',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict) and 'tables' in data:
                        return data
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_structure(self, data: Dict) -> List[str]:
        """
        Validate the parsed data has expected structure.

        Args:
            data: Parsed data dictionary

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not isinstance(data, dict):
            errors.append("Root must be a dictionary")
            return errors

        # Check for required top-level keys
        if 'tables' not in data:
            errors.append("Missing 'tables' key")
        elif not isinstance(data['tables'], dict):
            errors.append("'tables' must be a dictionary")

        # Validate table structure
        if 'tables' in data and isinstance(data['tables'], dict):
            for table_name, table_data in data['tables'].items():
                if not isinstance(table_data, dict):
                    errors.append(f"Table '{table_name}' must be a dictionary")
                    continue

                if 'headers' not in table_data:
                    errors.append(f"Table '{table_name}' missing 'headers'")

                if 'rows' not in table_data:
                    errors.append(f"Table '{table_name}' missing 'rows'")
                elif not isinstance(table_data['rows'], list):
                    errors.append(f"Table '{table_name}' rows must be a list")

        return errors

    def _extract_markdown_tables(self, text: str) -> Dict[str, Dict]:
        """
        Extract tables from markdown format as fallback.

        Parses tables like:
        | Header1 | Header2 |
        |---------|---------|
        | Value1  | Value2  |

        Args:
            text: Text containing markdown tables

        Returns:
            Dictionary of extracted tables
        """
        tables = {}

        # Find all markdown tables
        table_pattern = r'(?:^|\n)(\|[^\n]+\|)\n(\|[-:| ]+\|)\n((?:\|[^\n]+\|\n?)+)'
        matches = re.findall(table_pattern, text)

        for i, (header_row, separator, body) in enumerate(matches):
            # Parse headers
            headers = [h.strip() for h in header_row.strip('|').split('|')]
            headers = [h for h in headers if h]  # Remove empty

            # Parse rows
            rows = []
            for row_text in body.strip().split('\n'):
                if row_text.strip():
                    values = [v.strip() for v in row_text.strip('|').split('|')]
                    values = [v for v in values if v or values.index(v) < len(headers)]

                    if len(values) >= len(headers):
                        row_dict = dict(zip(headers, values[:len(headers)]))
                        rows.append(row_dict)

            # Generate table name from preceding text or use index
            table_name = self._infer_table_name(text, header_row) or f"table_{i+1}"

            if headers and rows:
                tables[table_name] = {
                    'headers': headers,
                    'rows': rows,
                    'sources': [],
                    'confidence_level': 'LOW'  # Markdown fallback = lower confidence
                }

        return tables

    def _infer_table_name(self, text: str, header_row: str) -> Optional[str]:
        """
        Try to infer table name from text preceding the table.

        Args:
            text: Full text
            header_row: Table header row

        Returns:
            Inferred table name or None
        """
        # Find position of header row
        pos = text.find(header_row)
        if pos <= 0:
            return None

        # Look for a heading in the 200 chars before
        preceding = text[max(0, pos-200):pos]

        # Match markdown heading
        heading_match = re.search(r'#+\s*([^\n]+)\n*$', preceding)
        if heading_match:
            name = heading_match.group(1).strip()
            # Convert to snake_case
            name = re.sub(r'[^\w\s]', '', name.lower())
            name = re.sub(r'\s+', '_', name)
            return name[:50]  # Limit length

        return None


class OutputValidator:
    """
    Validates synthesized domain data for completeness and quality.
    """

    def __init__(self, min_rows_per_table: int = 2):
        """
        Initialize the validator.

        Args:
            min_rows_per_table: Minimum rows required per table
        """
        self.min_rows = min_rows_per_table

    def validate(
        self,
        parse_result: ParseResult,
        required_tables: List[str],
        critical_fields: Optional[Dict[str, List[str]]] = None
    ) -> tuple[bool, List[str]]:
        """
        Validate parsed output against requirements.

        Args:
            parse_result: The parsed output
            required_tables: List of table names that must be present
            critical_fields: Dict mapping table names to required field names

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        if not parse_result.success:
            issues.append("Output parsing failed")
            return False, issues

        tables = parse_result.tables

        # Check required tables exist
        for table_name in required_tables:
            if table_name not in tables:
                issues.append(f"Missing required table: {table_name}")
            elif len(tables[table_name].get('rows', [])) < self.min_rows:
                row_count = len(tables[table_name].get('rows', []))
                issues.append(
                    f"Table '{table_name}' has insufficient data "
                    f"({row_count} rows, minimum {self.min_rows})"
                )

        # Check critical fields
        if critical_fields:
            for table_name, fields in critical_fields.items():
                if table_name not in tables:
                    continue

                table_rows = tables[table_name].get('rows', [])
                for field_name in fields:
                    has_field = any(
                        field_name.lower() in str(row).lower()
                        for row in table_rows
                    )
                    if not has_field:
                        issues.append(
                            f"Missing critical data '{field_name}' in table '{table_name}'"
                        )

        # Check for NOT_FOUND markers (data gaps)
        not_found_count = 0
        for table in tables.values():
            for row in table.get('rows', []):
                if 'NOT_FOUND' in str(row).upper():
                    not_found_count += 1

        if not_found_count > 10:
            issues.append(f"High number of missing data points: {not_found_count}")

        return len(issues) == 0, issues

    def get_completeness_score(self, parse_result: ParseResult) -> float:
        """
        Calculate a completeness score for the output.

        Args:
            parse_result: The parsed output

        Returns:
            Score from 0.0 to 1.0
        """
        if not parse_result.success:
            return 0.0

        tables = parse_result.tables
        if not tables:
            return 0.0

        total_score = 0.0
        table_count = len(tables)

        for table in tables.values():
            rows = table.get('rows', [])
            headers = table.get('headers', [])

            if not rows or not headers:
                continue

            # Score based on row count
            row_score = min(len(rows) / 5, 1.0)  # Max at 5 rows

            # Score based on filled cells
            filled_cells = 0
            total_cells = len(rows) * len(headers)

            for row in rows:
                for header in headers:
                    value = str(row.get(header, ''))
                    if value and value.upper() not in ['', 'N/A', 'NOT_FOUND', '-']:
                        filled_cells += 1

            fill_score = filled_cells / total_cells if total_cells > 0 else 0

            # Combine scores
            table_score = (row_score * 0.4) + (fill_score * 0.6)
            total_score += table_score

        return total_score / table_count if table_count > 0 else 0.0
