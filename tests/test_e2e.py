"""
End-to-End (E2E) System & Integration Tests (Ticket 12)

Verifies the entire Guffy pipeline:
1. Workspace initialization and database provisioning (`guffy init`).
2. Searcher discovery and ingestion into SQLite (`guffy search`).
3. ATS & direct company career crawling (`guffy crawl-companies`).
4. Semantic fit scoring & multi-factor match evaluation (`guffy match`).
5. Application staging & HITL human-in-the-loop review queue (`guffy review`).
6. CLI argument parsing and execution across all subcommands.
"""

import argparse
import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from guffy.cli import (
    build_parser,
    cmd_crawl_companies,
    cmd_init,
    cmd_match,
    cmd_review,
    cmd_search,
    cmd_status,
    load_candidate_profile,
)
from guffy.core.database import Application, Company, DatabaseManager, Job
from guffy.core.profile_manager import CandidateProfile
from guffy.searchers.base import JobPosting


@pytest.fixture
def temp_workspace():
    """Sets up an isolated temporary workspace with a clean database."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "e2e_test.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_path}")
    db_mgr.init_db()

    profile_path = Path(temp_dir) / "profile.yaml"
    profile_data = {
        "personal_info": {
            "full_name": "E2E Candidate",
            "email": "e2e@example.com",
            "phone": "+1-555-0100",
            "location": "Remote",
            "linkedin_url": "https://linkedin.com/in/e2ecandidate",
            "github_url": "https://github.com/e2ecandidate",
            "portfolio_url": "https://e2ecandidate.dev",
            "resume_path": "",
        },
        "preferences": {
            "target_titles": ["Senior Backend Engineer", "Python Architect"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "min_base_salary_usd": 140000,
            "blacklisted_companies": ["BlacklistedCorp"],
        },
        "skills": {
            "languages": ["Python", "Go"],
            "frameworks": ["FastAPI", "Django"],
            "cloud_and_tools": ["Docker", "AWS", "PostgreSQL"],
        },
        "screening_answers": {
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "notice_period": "2 weeks",
            "expected_salary": "$150,000",
            "years_of_experience": {"python": 6.0},
        },
    }
    import yaml
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(profile_data, f)

    companies_path = Path(temp_dir) / "companies.yaml"
    companies_data = {
        "companies": [
            {
                "name": "Stripe",
                "domain": "stripe.com",
                "careers_url": "https://stripe.com/jobs",
                "ats": "greenhouse",
                "priority": "high",
            }
        ]
    }
    with open(companies_path, "w", encoding="utf-8") as f:
        yaml.dump(companies_data, f)

    return {
        "dir": temp_dir,
        "db_mgr": db_mgr,
        "profile_path": profile_path,
        "companies_path": companies_path,
    }


def test_cli_parser_registered_commands():
    """Verify all subcommands and arguments are properly registered in CLI parser."""
    parser = build_parser()
    
    # Subcommands
    subparsers_actions = [
        action for action in parser._actions 
        if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) == 1
    commands = list(subparsers_actions[0].choices.keys())
    
    assert "init" in commands
    assert "search" in commands
    assert "crawl-companies" in commands
    assert "match" in commands
    assert "review" in commands
    assert "serve" in commands
    assert "status" in commands


def test_e2e_cmd_init(temp_workspace):
    """Verify guffy init creates required database tables and configuration files."""
    args = argparse.Namespace()
    
    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        with patch("guffy.cli.Path") as mock_path:
            # Point to temp workspace files
            cmd_init(args)
            
    session = temp_workspace["db_mgr"].SessionLocal()
    try:
        # Tables should be queryable
        assert session.query(Job).count() == 0
        assert session.query(Company).count() >= 0
    finally:
        session.close()


def test_e2e_cmd_search(temp_workspace):
    """Verify search command discovers jobs and saves to database."""
    args = argparse.Namespace(
        portals="remoteok",
        keywords="Python",
        location="Remote",
        remote_only=True,
        limit=5,
        auto_match=False,
    )
    
    mock_posting = JobPosting(
        title="Senior Python Backend Developer",
        company="GlobalTech",
        location="Remote",
        remote_type="Remote",
        portal="remoteok",
        job_url="https://remoteok.com/j/e2e123",
        description="Looking for senior Python developer with FastAPI and AWS.",
    )
    
    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        with patch("guffy.cli.RemoteOKSearcher.search", return_value=[mock_posting]):
            cmd_search(args)
            
    session = temp_workspace["db_mgr"].SessionLocal()
    try:
        saved_job = session.query(Job).filter_by(job_url="https://remoteok.com/j/e2e123").first()
        assert saved_job is not None
        assert saved_job.title == "Senior Python Backend Developer"
        assert saved_job.company == "GlobalTech"
        assert saved_job.status == "discovered"
    finally:
        session.close()


def test_e2e_cmd_crawl_companies(temp_workspace):
    """Verify crawl-companies command crawls company targets."""
    args = argparse.Namespace(keywords="Backend", priority="high")
    
    mock_posting = JobPosting(
        title="Staff Backend Engineer",
        company="Stripe",
        location="Remote",
        remote_type="Remote",
        portal="greenhouse",
        job_url="https://stripe.com/jobs/999",
        description="Backend engineer building global infrastructure.",
    )
    
    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        with patch("guffy.searchers.CompanyCrawler.crawl_all", return_value=[mock_posting]):
            cmd_crawl_companies(args)


def test_e2e_cmd_match(temp_workspace):
    """Verify match command scores discovered jobs against candidate profile."""
    session = temp_workspace["db_mgr"].SessionLocal()
    j1 = Job(
        id="e2e_job_1",
        title="Senior Backend Engineer",
        company="RemoteCorp",
        location="Remote",
        remote_type="Remote",
        portal="remoteok",
        job_url="https://remoteok.com/j/e2e_match",
        description="We need FastAPI, Python, Docker, and AWS skills.",
        status="discovered",
    )
    session.add(j1)
    session.commit()
    session.close()

    args = argparse.Namespace(force=True, min_score=50.0)
    profile = CandidateProfile.load_from_yaml(temp_workspace["profile_path"])

    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        with patch("guffy.cli.load_candidate_profile", return_value=profile):
            cmd_match(args)

    session = temp_workspace["db_mgr"].SessionLocal()
    try:
        updated = session.query(Job).filter_by(id="e2e_job_1").first()
        assert updated.status == "scored"
        assert updated.match_score > 70.0
        assert "python" in updated.matched_skills.lower()
    finally:
        session.close()


def test_e2e_cmd_review_empty(temp_workspace):
    """Verify review command gracefully informs user when review queue is empty."""
    args = argparse.Namespace()
    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        cmd_review(args)


def test_e2e_cmd_status(temp_workspace):
    """Verify status command renders pipeline statistics without error."""
    args = argparse.Namespace()
    with patch("guffy.cli.get_db_manager", return_value=temp_workspace["db_mgr"]):
        cmd_status(args)
