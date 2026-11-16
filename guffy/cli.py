"""
Guffy Unified CLI Suite (Ticket 12)

Commands:
- init: Initialize project configuration, database schema, and profile templates.
- search: Discover job postings across remote and aggregator portals.
- crawl-companies: Scrape active job postings directly from target company career boards.
- match: Run semantic fit scoring against candidate profile.
- review: Interactive human-in-the-loop review queue for staged applications.
- serve: Launch FastAPI backend server and modern Tailwind SPA dashboard.
- status: Display pipeline summary, active tracked companies, and analytics.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from guffy.automation.browser import BrowserController
from guffy.automation.staging_engine import ApplicationStagingEngine
from guffy.config import Settings, get_settings
from guffy.core.database import Application, Company, DatabaseManager, Job, get_db_manager
from guffy.core.matcher import MatchEngine, score_job
from guffy.core.profile_manager import CandidateProfile, ProfileManager, ResumeParser
from guffy.searchers import (
    CompanyCrawler,
    DiceSearcher,
    GlassdoorSearcher,
    IndeedSearcher,
    LinkedInSearcher,
    RemoteOKSearcher,
    TargetCompanyManager,
    WeWorkRemotelySearcher,
    WellfoundSearcher,
    YCStartupSearcher,
)

console = Console()
logger = logging.getLogger("guffy.cli")


# ---------------------------------------------------------------------------
# Helper: Profile Loader
# ---------------------------------------------------------------------------
def load_candidate_profile() -> CandidateProfile:
    candidates = ["profile.yaml", "profile.example.yaml"]
    for c in candidates:
        p = Path(c)
        if p.exists():
            try:
                return CandidateProfile.load_from_yaml(p)
            except Exception as e:
                console.print(f"[yellow]Warning loading {c}: {e}[/yellow]")
    raise FileNotFoundError("Could not find a valid profile.yaml or profile.example.yaml. Run 'guffy init' first.")


# ---------------------------------------------------------------------------
# Command: init
# ---------------------------------------------------------------------------
def cmd_init(args: argparse.Namespace):
    """Initialize project structure, configuration files, and SQLite database."""
    console.print(Panel("[bold green]Initializing Guffy Workspace[/bold green]", expand=False))

    db_manager = get_db_manager()
    db_manager.init_db()
    console.print("[green]✔ Database schema initialized.[/green]")

    # Ensure profile.yaml exists
    p_yaml = Path("profile.yaml")
    p_example = Path("profile.example.yaml")
    if not p_yaml.exists() and p_example.exists():
        import shutil
        shutil.copy(p_example, p_yaml)
        console.print("[green]✔ Created profile.yaml from template profile.example.yaml[/green]")
    elif p_yaml.exists():
        console.print("[dim]ℹ profile.yaml already exists.[/dim]")

    # Ensure companies.yaml exists
    c_yaml = Path("companies.yaml")
    if not c_yaml.exists():
        with open(c_yaml, "w", encoding="utf-8") as f:
            f.write("# Guffy Target Companies\ncompanies: []\n")
        console.print("[green]✔ Created empty companies.yaml[/green]")
    else:
        # Load into DB
        session = db_manager.SessionLocal()
        try:
            mgr = TargetCompanyManager(yaml_path=str(c_yaml))
            comps = mgr.sync_to_db(session)
            console.print(f"[green]✔ Synced {len(comps)} companies from companies.yaml into database.[/green]")
        finally:
            session.close()

    console.print("\n[bold cyan]Guffy setup complete! Run 'guffy search' or 'guffy serve' to begin.[/bold cyan]\n")


# ---------------------------------------------------------------------------
# Command: search
# ---------------------------------------------------------------------------
def cmd_search(args: argparse.Namespace):
    """Search job boards and portals for new opportunities."""
    portal_map = {
        "remoteok": RemoteOKSearcher,
        "wwr": WeWorkRemotelySearcher,
        "yc": YCStartupSearcher,
        "linkedin": LinkedInSearcher,
        "wellfound": WellfoundSearcher,
        "indeed": IndeedSearcher,
        "dice": DiceSearcher,
        "glassdoor": GlassdoorSearcher,
    }

    selected_portals = [p.strip().lower() for p in args.portals.split(",") if p.strip()]
    invalid = [p for p in selected_portals if p not in portal_map]
    if invalid:
        console.print(f"[red]Error: Unknown portals: {', '.join(invalid)}[/red]")
        console.print(f"Supported: {', '.join(portal_map.keys())}")
        sys.exit(1)

    keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]
    location = args.location or "Remote"
    remote_only = args.remote_only
    limit = args.limit

    console.print(
        Panel(
            f"[bold]Target Portals:[/bold] {', '.join(selected_portals)}\n"
            f"[bold]Keywords:[/bold] {', '.join(keywords)}\n"
            f"[bold]Location:[/bold] {location} (Remote Only: {remote_only})\n"
            f"[bold]Limit Per Query:[/bold] {limit}",
            title="[bold blue]Job Discovery Search[/bold blue]",
            expand=False,
        )
    )

    db_manager = get_db_manager()
    session = db_manager.SessionLocal()
    total_discovered = 0
    new_jobs_count = 0

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for p_name in selected_portals:
                task = progress.add_task(f"Searching {p_name}...", total=None)
                searcher_cls = portal_map[p_name]
                searcher = searcher_cls()

                for kw in keywords:
                    try:
                        results = searcher.search(
                            keywords=[kw],
                            locations=[location] if location else None,
                            limit=limit,
                        )
                        for posting in results:
                            total_discovered += 1
                            existing = session.query(Job).filter_by(id=posting.id).first()
                            if not existing:
                                existing_url = session.query(Job).filter_by(job_url=posting.job_url).first()
                                if not existing_url:
                                    session.add(posting.to_job_model())
                                    new_jobs_count += 1
                        session.commit()
                    except Exception as e:
                        console.print(f"[yellow]Warning searching {p_name} for '{kw}': {e}[/yellow]")
                        session.rollback()
                progress.remove_task(task)

        console.print(
            f"\n[green]✔ Discovery complete: {total_discovered} fetched, "
            f"[bold]{new_jobs_count} new postings[/bold] saved to database.[/green]"
        )

        if args.auto_match and new_jobs_count > 0:
            console.print("\n[cyan]Triggering automatic semantic fit scoring...[/cyan]")
            cmd_match(argparse.Namespace(force=False, min_score=0.0))

    finally:
        session.close()


# ---------------------------------------------------------------------------
# Command: crawl-companies
# ---------------------------------------------------------------------------
def cmd_crawl_companies(args: argparse.Namespace):
    """Crawl official company career pages and ATS endpoints."""
    db_manager = get_db_manager()
    session = db_manager.SessionLocal()

    keywords = [kw.strip() for kw in args.keywords.split(",")] if args.keywords else None
    priority = args.priority if args.priority else None

    console.print(
        Panel(
            f"[bold]Priority Filter:[/bold] {priority or 'All'}\n"
            f"[bold]Keyword Filter:[/bold] {', '.join(keywords) if keywords else 'None (All Postings)'}",
            title="[bold green]Direct Company & ATS Crawler[/bold green]",
            expand=False,
        )
    )

    try:
        crawler = CompanyCrawler()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Crawling target company job boards...", total=None)
            results = crawler.crawl_all(session=session, priority=priority, keywords=keywords)
            progress.remove_task(task)

        console.print(
            f"\n[green]✔ Crawl complete: [bold]{len(results)} active postings[/bold] discovered and synced.[/green]"
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Command: match
# ---------------------------------------------------------------------------
def cmd_match(args: argparse.Namespace):
    """Run multi-factor composite match scoring against candidate profile."""
    profile = load_candidate_profile()
    db_manager = get_db_manager()
    session = db_manager.SessionLocal()

    try:
        query = session.query(Job)
        if not getattr(args, "force", False):
            query = query.filter(Job.status == "discovered")

        jobs_to_score = query.all()
        if not jobs_to_score:
            console.print("[dim]No unscored jobs found. Use --force to rescore all.[/dim]")
            return

        console.print(f"[bold]Scoring {len(jobs_to_score)} jobs against candidate profile...[/bold]")

        passed_count = 0
        scored_count = 0

        table = Table(title="Semantic Scoring Highlights (Top Matches)", expand=True)
        table.add_column("Title", style="bold white", no_wrap=False)
        table.add_column("Company", style="cyan")
        table.add_column("Portal", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("Status")

        for job in jobs_to_score:
            res = score_job(job, profile)
            scored_count += 1
            if res.passed_hard_filters:
                passed_count += 1
                if res.score >= getattr(args, "min_score", 60.0):
                    color = "green" if res.score >= 80 else "yellow"
                    table.add_row(
                        job.title[:45],
                        job.company[:20],
                        job.portal,
                        f"[{color}]{res.score:.1f}%[/{color}]",
                        job.status,
                    )

        session.commit()

        if table.row_count > 0:
            console.print(table)

        console.print(
            f"\n[green]✔ Scored {scored_count} jobs: [bold]{passed_count} qualified[/bold], "
            f"{scored_count - passed_count} filtered out.[/green]"
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Command: review
# ---------------------------------------------------------------------------
def cmd_review(args: argparse.Namespace):
    """Interactive human-in-the-loop review queue for staged applications."""
    db_manager = get_db_manager()
    session = db_manager.SessionLocal()

    try:
        staged_jobs = session.query(Job).filter(Job.status == "staged").all()
        if not staged_jobs:
            console.print(
                Panel(
                    "[bold green]The HITL Review Queue is empty![/bold green]\n"
                    "No applications are currently awaiting human review.\n"
                    "Stage high-fit jobs using the dashboard or API to review them here.",
                    expand=False,
                )
            )
            return

        console.print(f"\n[bold yellow]Found {len(staged_jobs)} applications in the Review Queue:[/bold yellow]\n")

        for idx, job in enumerate(staged_jobs, 1):
            app_rec = session.query(Application).filter_by(job_id=job.id).first()

            console.rule(f"[bold cyan]Application {idx} of {len(staged_jobs)}: {job.title} @ {job.company}[/bold cyan]")
            console.print(f"[bold]Portal:[/bold] {job.portal.upper()} | [bold]Match Score:[/bold] {job.match_score}% | [bold]URL:[/bold] {job.job_url}")

            if app_rec:
                if app_rec.pitch_note:
                    console.print(Panel(app_rec.pitch_note, title="[dim]Tailored Pitch Note[/dim]", expand=False))
                if app_rec.screenshot_path and Path(app_rec.screenshot_path).exists():
                    console.print(f"[dim]Screenshot snapshot saved at: {app_rec.screenshot_path}[/dim]")

            # Interactive action
            action = Prompt.ask(
                "Action",
                choices=["submit", "skip", "reject", "quit"],
                default="submit"
            )

            if action == "quit":
                console.print("[dim]Exiting review queue.[/dim]")
                break
            elif action == "skip":
                console.print("[yellow]Skipped for later review.[/yellow]\n")
                continue
            elif action == "reject":
                job.status = "rejected"
                if app_rec:
                    app_rec.status = "rejected"
                session.commit()
                console.print(f"[rose]Application marked rejected.[/rose]\n")
            elif action == "submit":
                profile = load_candidate_profile()
                browser = BrowserController()
                staging_engine = ApplicationStagingEngine(browser=browser, profile=profile, db_manager=db_manager)
                console.print("[dim]Finalizing submission...[/dim]")
                success = staging_engine.approve_and_submit(job=job, db_session=session)
                if success:
                    console.print("[bold green]✔ Successfully submitted application![/bold green]\n")
                else:
                    console.print("[bold red]✖ Submission failed. Keeping in review queue.[/bold red]\n")

    finally:
        session.close()


# ---------------------------------------------------------------------------
# Command: serve
# ---------------------------------------------------------------------------
def cmd_serve(args: argparse.Namespace):
    """Launch FastAPI backend server and modern Tailwind SPA dashboard."""
    import uvicorn
    host = args.host or "127.0.0.1"
    port = args.port or 8000

    console.print(
        Panel(
            f"[bold green]Guffy Web Dashboard & REST API[/bold green]\n\n"
            f"➜  [bold]Local App:[/bold]      http://{host}:{port}/\n"
            f"➜  [bold]API Docs:[/bold]       http://{host}:{port}/docs\n"
            f"➜  [bold]Interactive SPA:[/bold] http://{host}:{port}/static/index.html\n\n"
            f"[dim]Press Ctrl+C to stop the server[/dim]",
            expand=False,
        )
    )

    uvicorn.run("guffy.web.app:app", host=host, port=port, reload=args.reload)


# ---------------------------------------------------------------------------
# Command: status
# ---------------------------------------------------------------------------
def cmd_status(args: argparse.Namespace):
    """Display system status, metrics, and application pipeline summary."""
    db_manager = get_db_manager()
    session = db_manager.SessionLocal()

    try:
        total_discovered = session.query(Job).count()
        total_scored = session.query(Job).filter(Job.status != "discovered").count()
        total_staged = session.query(Job).filter(Job.status == "staged").count()
        total_submitted = session.query(Job).filter(Job.status == "submitted").count()
        total_rejected = session.query(Job).filter(Job.status == "rejected").count()

        companies_count = session.query(Company).count()

        # Score average
        scored_jobs = session.query(Job.match_score).filter(Job.match_score > 0).all()
        avg_score = round(sum(s[0] for s in scored_jobs) / len(scored_jobs), 1) if scored_jobs else 0.0

        table = Table(title="Guffy Application Pipeline Status", expand=False)
        table.add_column("Pipeline Stage", style="bold white")
        table.add_column("Count", justify="right", style="cyan")
        table.add_column("Description", style="dim")

        table.add_row("Discovered Postings", str(total_discovered), "Total jobs scraped across all portals")
        table.add_row("Scored & Filtered", str(total_scored), f"Jobs matched (Average fit: {avg_score}%)")
        table.add_row("HITL Review Queue", str(total_staged), "Staged applications awaiting human approval")
        table.add_row("Submitted Applications", str(total_submitted), "Applications successfully delivered")
        table.add_row("Rejected / Filtered", str(total_rejected), "Blacklisted or unqualified postings")
        table.add_row("Tracked Dream Companies", str(companies_count), "Direct ATS targets (Greenhouse, Lever, Ashby)")

        console.print(table)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Parser Entrypoint
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guffy",
        description="Guffy: Autonomous AI Job Search & Auto-Apply Suite",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize workspace configuration and database")
    p_init.set_defaults(func=cmd_init)

    # search
    p_search = subparsers.add_parser("search", help="Search job boards and portals")
    p_search.add_argument("--keywords", "-k", default="Python,Backend Engineer", help="Comma-separated keywords")
    p_search.add_argument("--location", "-l", default="Remote", help="Target location")
    p_search.add_argument("--portals", "-p", default="remoteok,wwr,yc", help="Comma-separated portals to search")
    p_search.add_argument("--remote-only", action="store_true", default=True, help="Filter for remote only")
    p_search.add_argument("--limit", type=int, default=20, help="Max results per searcher")
    p_search.add_argument("--auto-match", "-m", action="store_true", default=False, help="Automatically run match scoring on new jobs")
    p_search.set_defaults(func=cmd_search)

    # crawl-companies
    p_crawl = subparsers.add_parser("crawl-companies", help="Crawl target company career boards")
    p_crawl.add_argument("--keywords", "-k", help="Optional comma-separated keywords to filter")
    p_crawl.add_argument("--priority", choices=["high", "medium", "low"], help="Filter companies by priority")
    p_crawl.set_defaults(func=cmd_crawl_companies)

    # match
    p_match = subparsers.add_parser("match", help="Run semantic match scoring")
    p_match.add_argument("--force", "-f", action="store_true", help="Force rescore all jobs including previously scored")
    p_match.add_argument("--min-score", type=float, default=60.0, help="Minimum score to display in summary")
    p_match.set_defaults(func=cmd_match)

    # review
    p_review = subparsers.add_parser("review", help="Interactive human-in-the-loop review queue")
    p_review.set_defaults(func=cmd_review)

    # serve
    p_serve = subparsers.add_parser("serve", help="Launch FastAPI REST server and Tailwind SPA dashboard")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    p_serve.set_defaults(func=cmd_serve)

    # status
    p_status = subparsers.add_parser("status", help="Show pipeline statistics and metrics")
    p_status.set_defaults(func=cmd_status)

    return parser


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
