"""
Unit Tests for Database Models and Configuration Setup (Ticket 1)
"""

import os
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from Guffy.config import Settings, get_settings
from Guffy.core.database import DatabaseManager, Job, Company, Application, ProfileSetting


@pytest.fixture
def test_db_manager(tmp_path: Path):
    test_db_file = tmp_path / "test_Guffy.db"
    db_url = f"sqlite:///{test_db_file}"
    db = DatabaseManager(db_url)
    db.init_db()
    return db


def test_load_default_settings():
    settings = Settings.load_from_yaml("config.yaml")
    assert settings.app.name == "Guffy"
    assert "Software Engineer" in settings.search.keywords
    assert settings.search.remote_only is True
    assert settings.search.min_match_score == 75


def test_job_and_application_lifecycle(test_db_manager: DatabaseManager):
    session: Session = next(test_db_manager.get_session())

    # 1. Create a Job
    job = Job(
        id="job-stripe-001",
        title="Full Stack Engineer",
        company="Stripe",
        location="Remote",
        remote_type="Remote",
        portal="company_ats",
        job_url="https://stripe.com/jobs/001",
        description="Looking for an experienced Python/React engineer.",
        salary_range="$140k - $180k",
        easy_apply=False,
        status="discovered"
    )
    session.add(job)
    session.commit()

    # 2. Query Job
    saved_job = session.query(Job).filter_by(id="job-stripe-001").first()
    assert saved_job is not None
    assert saved_job.company == "Stripe"
    assert saved_job.status == "discovered"

    # 3. Score Job
    saved_job.match_score = 88.5
    saved_job.matched_skills = "Python, FastAPI, React"
    saved_job.status = "scored"
    session.commit()

    # 4. Create Staged Application
    application = Application(
        job_id=saved_job.id,
        portal="company_ats",
        status="staged",
        tailored_cover_letter="Dear Hiring Manager at Stripe, ...",
        tailored_pitch="Proven track record in high-scale payment systems."
    )
    session.add(application)
    session.commit()

    # 5. Verify relationship
    refreshed_job = session.query(Job).filter_by(id="job-stripe-001").first()
    assert refreshed_job.application is not None
    assert refreshed_job.application.status == "staged"
    assert refreshed_job.application.tailored_cover_letter.startswith("Dear Hiring Manager")

    session.close()


def test_company_registry(test_db_manager: DatabaseManager):
    session: Session = next(test_db_manager.get_session())

    company = Company(
        name="OpenAI",
        domain="openai.com",
        careers_url="https://openai.com/careers",
        ats="greenhouse",
        priority="high"
    )
    session.add(company)
    session.commit()

    saved_company = session.query(Company).filter_by(name="OpenAI").first()
    assert saved_company is not None
    assert saved_company.ats == "greenhouse"
    assert saved_company.priority == "high"

    session.close()


def test_profile_setting(test_db_manager: DatabaseManager):
    session: Session = next(test_db_manager.get_session())

    setting = ProfileSetting(
        key="screening_answers",
        value_json='{"work_auth": true, "notice_period": "2 weeks"}'
    )
    session.add(setting)
    session.commit()

    saved_setting = session.query(ProfileSetting).filter_by(key="screening_answers").first()
    assert saved_setting is not None
    assert "notice_period" in saved_setting.value_json

    session.close()
