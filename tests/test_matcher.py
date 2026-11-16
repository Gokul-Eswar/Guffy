"""
Unit Tests for Ticket 3: Semantic Fit Scoring & Match Engine
"""

import json
import pytest

from huntflow.core.database import Job
from huntflow.core.profile_manager import CandidateProfile
from huntflow.core.matcher import MatchEngine, MatchResult, score_job


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        personal_info={
            "full_name": "Test Candidate",
            "email": "test@example.com",
            "location": "San Francisco, CA",
        },
        preferences={
            "target_titles": [
                "Full Stack Software Engineer",
                "Backend Engineer",
                "Python Developer",
            ],
            "excluded_titles": [
                "Intern",
                "Data Entry",
                "Sales Representative",
            ],
            "target_locations": ["Remote", "San Francisco, CA"],
            "remote_only": True,
            "min_base_salary_usd": 100000,
            "blacklisted_companies": ["SpamCorp", "UnwantedOrg"],
        },
        skills={
            "languages": ["Python", "TypeScript", "SQL"],
            "frameworks": ["FastAPI", "React", "Django"],
            "cloud_and_tools": ["Docker", "AWS", "PostgreSQL", "Git"],
        },
        screening_answers={
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "years_of_experience": {
                "python": 4.0,
                "fastapi": 3.0,
                "react": 2.0,
            },
        },
    )


def test_hard_filter_company_blacklist(sample_profile):
    matcher = MatchEngine(sample_profile)
    passed, reasons = matcher.check_hard_filters(
        job_title="Senior Python Developer",
        company_name="SpamCorp International",
    )
    assert not passed
    assert any("matches blacklisted employer" in r for r in reasons)


def test_hard_filter_excluded_title(sample_profile):
    matcher = MatchEngine(sample_profile)
    passed, reasons = matcher.check_hard_filters(
        job_title="Software Engineer Intern",
        company_name="Acme Inc",
    )
    assert not passed
    assert any("excluded keyword 'Intern'" in r for r in reasons)


def test_hard_filter_remote_only_enforcement(sample_profile):
    matcher = MatchEngine(sample_profile)
    # Onsite job should fail when remote_only is True
    passed, reasons = matcher.check_hard_filters(
        job_title="Backend Engineer",
        company_name="Acme Inc",
        location="Austin, TX",
        remote_type="Onsite",
    )
    assert not passed
    assert any("requires remote-only" in r for r in reasons)

    # Remote job should pass
    passed_remote, _ = matcher.check_hard_filters(
        job_title="Backend Engineer",
        company_name="Acme Inc",
        location="Remote - US",
        remote_type="Remote",
    )
    assert passed_remote


def test_hard_filter_salary_floor(sample_profile):
    matcher = MatchEngine(sample_profile)
    passed, reasons = matcher.check_hard_filters(
        job_title="Backend Engineer",
        company_name="Acme Inc",
        remote_type="Remote",
        min_salary=80000,  # candidate min floor is 100000
    )
    assert not passed
    assert any("below candidate minimum floor" in r for r in reasons)


def test_high_fit_job_scoring(sample_profile):
    matcher = MatchEngine(sample_profile)
    description = """
    We are seeking a Full Stack Software Engineer to join our fast-growing startup.
    Requirements:
    - 3+ years of experience with Python and FastAPI building high-throughput REST APIs.
    - Strong knowledge of TypeScript, React, PostgreSQL, Docker, and AWS.
    - Passion for clean code, automated testing, and Git workflows.
    """
    result = matcher.match(
        job_title="Full Stack Software Engineer",
        company_name="TechFlow Inc",
        description=description,
        location="Remote",
        remote_type="Remote",
    )

    assert result.passed_hard_filters is True
    assert result.score >= 80.0  # Should score very high
    assert "python" in result.matched_skills
    assert "fastapi" in result.matched_skills
    assert "react" in result.matched_skills
    assert "aws" in result.matched_skills
    assert len(result.missing_skills) == 0 or len(result.missing_skills) < len(result.matched_skills)
    assert len(result.pros) > 0


def test_medium_fit_job_scoring(sample_profile):
    matcher = MatchEngine(sample_profile)
    description = """
    We need an experienced Python developer with knowledge of Ruby on Rails and MongoDB.
    Knowledge of Kubernetes and Terraform is a huge plus. 3+ years experience.
    """
    result = matcher.match(
        job_title="Python Developer",
        company_name="MidFit LLC",
        description=description,
        location="Remote",
        remote_type="Remote",
    )

    assert result.passed_hard_filters is True
    assert 40.0 <= result.score < 80.0
    assert "python" in result.matched_skills
    assert "mongodb" in result.missing_skills or "ruby on rails" in result.missing_skills


def test_low_fit_unmatched_job_scoring(sample_profile):
    matcher = MatchEngine(sample_profile)
    description = """
    Seeking an iOS Swift mobile app engineer with Kotlin and Scala experience.
    Must have 7+ years of experience in mobile telecommunications.
    """
    result = matcher.match(
        job_title="Senior iOS Mobile Developer",
        company_name="AppWorks",
        description=description,
        location="Remote",
        remote_type="Remote",
    )

    assert result.passed_hard_filters is True
    assert result.score < 50.0
    assert "swift" in result.missing_skills
    assert len(result.cons) > 0


def test_score_job_database_integration(sample_profile):
    job = Job(
        id="job-12345",
        title="Backend Engineer",
        company="Innovative Soft",
        location="Remote",
        remote_type="Remote",
        portal="remoteok",
        job_url="https://remoteok.com/j/12345",
        description="Looking for a Backend Engineer with Python, FastAPI, Docker, and PostgreSQL expertise.",
    )

    result = score_job(job, sample_profile)

    assert job.status == "scored"
    assert job.match_score >= 70.0
    assert "python" in job.matched_skills
    assert "fastapi" in job.matched_skills

    pros_cons = json.loads(job.pros_cons)
    assert "pros" in pros_cons
    assert "cons" in pros_cons


def test_score_job_rejected_on_hard_filter(sample_profile):
    job = Job(
        id="job-99999",
        title="Data Entry Clerk Intern",
        company="SpamCorp International",
        location="Onsite",
        remote_type="Onsite",
        portal="indeed",
        job_url="https://indeed.com/j/99999",
        description="Entry level data entry.",
    )

    result = score_job(job, sample_profile)

    assert job.status == "rejected"
    assert job.match_score == 0.0
    assert not result.passed_hard_filters
    assert len(result.filter_reasons) >= 2  # blacklist and intern and onsite
