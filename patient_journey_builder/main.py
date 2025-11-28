"""
CLI entry point for Patient Journey Builder.
"""

import click
import sys
from pathlib import Path

from .config import Settings
from .core import PatientJourneyOrchestrator, SessionManager, list_sessions
from .output import export_to_json, export_to_markdown
from .utils import configure_logging, ProgressLogger, CostTracker, estimate_run_cost
from .localization import LocalizationManager


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    Patient Journey Database Builder

    Automates pharmaceutical patient journey research across 7 domains.
    """
    pass


@cli.command()
@click.option('--disease', '-d', required=True, help='Disease area (e.g., "Chronic Spontaneous Urticaria")')
@click.option('--country', '-c', required=True, help='Target country (e.g., "Sweden")')
@click.option('--start-domain', '-s', default=1, type=click.IntRange(1, 7), help='Domain to start from (1-7)')
@click.option('--end-domain', '-e', default=7, type=click.IntRange(1, 7), help='Domain to end at (1-7)')
@click.option('--output-format', '-o', type=click.Choice(['json', 'markdown', 'both']), default='both')
@click.option('--intelligent/--standard', default=True,
              help='Use intelligent Claude search (recommended) vs standard Brave API search')
@click.option('--strict', is_flag=True, help='Fail on validation errors instead of continuing')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), default='INFO')
@click.option('--log-file', type=click.Path(), help='Optional log file path')
@click.option('--json-logs', is_flag=True, help='Output logs as JSON (for production)')
@click.option('--dry-run', is_flag=True, help='Estimate costs without making API calls')
@click.option('--no-cache', is_flag=True, help='Disable caching (always fetch fresh data)')
def run(
    disease: str,
    country: str,
    start_domain: int,
    end_domain: int,
    output_format: str,
    intelligent: bool,
    strict: bool,
    log_level: str,
    log_file: str,
    json_logs: bool,
    dry_run: bool,
    no_cache: bool
):
    """
    Run patient journey research.

    \b
    Research Modes:
        --intelligent (default): Uses Claude's web search for intelligent, iterative research.
                                 Higher quality but higher cost. No Brave API key needed.

        --standard:              Uses Brave API + fetch + Claude synthesis.
                                 Lower cost but shallower results. Requires Brave API key.

    \b
    Examples:
        # Full run with intelligent search (recommended)
        pj-builder run --disease "Atopic Dermatitis" --country "Germany"

        # Use standard Brave API search (cheaper)
        pj-builder run -d "Psoriasis" -c "UK" --standard

        # Resume from Domain 4
        pj-builder run -d "Atopic Dermatitis" -c "Germany" -s 4

        # Estimate costs without running
        pj-builder run -d "Psoriasis" -c "UK" --dry-run
    """
    # Configure logging
    configure_logging(
        log_level=log_level,
        log_file=log_file,
        json_logs=json_logs
    )

    progress = ProgressLogger()

    try:
        # Load configuration
        config = Settings()

        # Override config with CLI flags
        if strict:
            config.strict_mode = True

        # Determine research mode (CLI flag overrides config)
        use_intelligent = intelligent

        # Validate Brave API key for standard mode
        if not use_intelligent and not config.brave_api_key:
            click.echo("❌ Standard mode requires BRAVE_API_KEY. Either:", err=True)
            click.echo("   1. Set BRAVE_API_KEY in .env file, or", err=True)
            click.echo("   2. Use --intelligent mode (recommended)", err=True)
            sys.exit(1)

        # Show research mode
        mode_name = "Intelligent (Claude web search)" if use_intelligent else "Standard (Brave API)"
        click.echo(f"🔬 Research Mode: {mode_name}")

        # Get major city from localization
        localization = LocalizationManager(config.localization_dir)
        major_city = localization.get_major_city(country)

        # Initialize cost tracker
        session_id = f"{country.lower()}_{disease.lower().replace(' ', '_')}"
        cost_tracker = CostTracker(
            session_id,
            config.cost_dir,
            disease=disease,
            country=country
        ) if config.enable_cost_tracking else None

        # Dry run mode - estimate costs only
        if dry_run:
            _show_cost_estimate(disease, country, start_domain, end_domain, config, use_intelligent)
            return

        # Initialize orchestrator
        orchestrator = PatientJourneyOrchestrator(
            config=config,
            cost_tracker=cost_tracker,
            use_cache=not no_cache,
            intelligent_mode=use_intelligent
        )

        # Run research
        database = orchestrator.run(
            disease=disease,
            country=country,
            start_domain=start_domain,
            end_domain=end_domain,
            major_city=major_city
        )

        # Export results
        output_base = Path(config.output_dir) / session_id

        if output_format in ['json', 'both']:
            json_path = export_to_json(database, f"{output_base}_database.json")
            click.echo(f"📄 JSON exported: {json_path}")

        if output_format in ['markdown', 'both']:
            md_path = export_to_markdown(database, f"{output_base}_database.md")
            click.echo(f"📝 Markdown exported: {md_path}")

        # Save cost report
        if cost_tracker:
            cost_tracker.save()

        # Clean up
        orchestrator.close()

    except ValueError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n⚠️  Interrupted by user. Progress has been saved.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        if log_level == 'DEBUG':
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--session-id', '-s', help='Session ID to check (optional)')
@click.option('--session-dir', default='data/sessions', help='Session directory')
def status(session_id: str, session_dir: str):
    """Check status of sessions."""
    if session_id:
        # Show specific session
        sessions = list_sessions(session_dir)
        session = next((s for s in sessions if s['session_id'] == session_id), None)

        if not session:
            click.echo(f"❌ Session not found: {session_id}")
            return

        click.echo(f"\n📋 Session: {session_id}")
        click.echo(f"  Disease: {session.get('disease')}")
        click.echo(f"  Country: {session.get('country')}")
        click.echo(f"  Status: {session.get('status')}")
        click.echo(f"  Completeness: {session.get('completeness', 0):.1f}%")
        click.echo(f"  Updated: {session.get('updated_at')}")
    else:
        # List all sessions
        sessions = list_sessions(session_dir)

        if not sessions:
            click.echo("No sessions found.")
            return

        click.echo(f"\n📋 Available Sessions ({len(sessions)}):\n")

        for s in sessions:
            status_icon = {
                'completed': '✅',
                'in_progress': '🔄',
                'failed': '❌'
            }.get(s.get('status'), '❓')

            click.echo(f"  {status_icon} {s['session_id']}")
            click.echo(f"     {s.get('disease')} / {s.get('country')}")
            click.echo(f"     Completeness: {s.get('completeness', 0):.1f}%")
            click.echo()


@cli.command()
@click.option('--disease', '-d', required=True, help='Disease area')
@click.option('--country', '-c', required=True, help='Target country')
@click.option('--start-domain', '-s', default=1, type=int, help='Start domain')
@click.option('--end-domain', '-e', default=7, type=int, help='End domain')
@click.option('--intelligent/--standard', default=True, help='Research mode')
def estimate(disease: str, country: str, start_domain: int, end_domain: int, intelligent: bool):
    """Estimate costs for a run."""
    try:
        config = Settings()
        _show_cost_estimate(disease, country, start_domain, end_domain, config, intelligent)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)


def _show_cost_estimate(
    disease: str,
    country: str,
    start_domain: int,
    end_domain: int,
    config: Settings,
    intelligent_mode: bool = True
):
    """Show cost estimation."""
    click.echo("\n🔮 Cost Estimation\n")
    click.echo(f"Disease: {disease}")
    click.echo(f"Country: {country}")
    click.echo(f"Domains: {start_domain} to {end_domain}")
    click.echo(f"Mode: {'Intelligent Search' if intelligent_mode else 'Standard (Brave API)'}")
    click.echo()

    domains_to_run = end_domain - start_domain + 1

    if intelligent_mode:
        # Intelligent mode estimates
        searches_per_domain = 10  # Approximate searches Claude makes
        input_tokens_per_domain = 15000
        output_tokens_per_domain = 8000

        total_searches = domains_to_run * searches_per_domain
        total_input = domains_to_run * input_tokens_per_domain
        total_output = domains_to_run * output_tokens_per_domain

        # Web search cost (included in API pricing for Claude)
        # Claude Sonnet pricing: $3/1M input, $15/1M output
        input_cost = total_input * 0.003 / 1000
        output_cost = total_output * 0.015 / 1000
        search_cost = total_searches * 0.01  # Approximate web search cost

        total_cost = input_cost + output_cost + search_cost

        click.echo("📊 Estimated API Usage (Intelligent Mode):")
        click.echo(f"  • Web searches: ~{total_searches}")
        click.echo(f"  • Claude input tokens: ~{total_input:,}")
        click.echo(f"  • Claude output tokens: ~{total_output:,}")
        click.echo()
        click.echo("💰 Estimated Costs:")
        click.echo(f"  • Claude API (input):   ${input_cost:.2f}")
        click.echo(f"  • Claude API (output):  ${output_cost:.2f}")
        click.echo(f"  • Web search:           ${search_cost:.2f}")
        click.echo(f"  • Total:                ${total_cost:.2f}")
        click.echo()
        click.echo(f"⏱️  Estimated Time: ~{domains_to_run * 8} minutes")
        click.echo()
        click.echo("Note: Intelligent mode produces higher quality output with better data extraction.")
    else:
        # Standard mode estimates
        estimate = estimate_run_cost(
            domains=domains_to_run,
            searches_per_domain=config.searches_per_domain,
            model=config.claude_model
        )

        click.echo("📊 Estimated API Usage (Standard Mode):")
        click.echo(f"  • Brave searches: {estimate['total_searches']}")
        click.echo(f"  • Claude input tokens: ~{estimate['total_input_tokens']:,}")
        click.echo(f"  • Claude output tokens: ~{estimate['total_output_tokens']:,}")
        click.echo()
        click.echo("💰 Estimated Costs:")
        click.echo(f"  • Brave Search: ${estimate['search_cost']:.2f}")
        click.echo(f"  • Claude API:   ${estimate['claude_cost']:.2f}")
        click.echo(f"  • Total:        ${estimate['total_cost']:.2f}")
        click.echo()
        click.echo(f"⏱️  Estimated Time: ~{domains_to_run * 5} minutes")
        click.echo()
        click.echo("Note: Standard mode is cheaper but produces shallower results.")


@cli.command()
def countries():
    """List supported countries with localization."""
    localization = LocalizationManager()
    countries = localization.list_countries()

    click.echo("\n🌍 Supported Countries:\n")
    for country in sorted(countries):
        config = localization.get_config(country)
        click.echo(f"  • {config.country_name} ({config.country_code})")
        click.echo(f"    Currency: {config.currency}, Healthcare: {config.healthcare_system_type}")
        if config.major_cities:
            click.echo(f"    Major cities: {', '.join(config.major_cities[:3])}")
        click.echo()


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
