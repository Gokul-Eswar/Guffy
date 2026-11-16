"""
Unit and Integration Tests for Portal-Specific Appliers and Staging Engine (Ticket 9)
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from guffy.automation.ats_applier import ATSApplier
from guffy.automation.indeed_applier import IndeedApplier
from guffy.automation.linkedin_applier import LinkedInApplier
from guffy.automation.staging_engine import ApplicationStagingEngine, StagingResult
from guffy.automation.wellfound_applier import WellfoundApplier
from guffy.core.database import Application, DatabaseManager, Job
from guffy.core.profile_manager import CandidateProfile


@pytest.fixture
def sample_profile():
    return CandidateProfile(
        personal_info={
            "full_name": "Gokul Eswar",
            "email": "gokul@example.com",
            "phone": "+1-555-0199",
            "location": "San Francisco, CA",
            "linkedin_url": "https://linkedin.com/in/gokuleswar",
            "github_url": "https://github.com/gokuleswar",
            "portfolio_url": "https://gokul.dev",
            "resume_path": "",
        },
        preferences={
            "target_titles": ["Senior Python Engineer"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "min_base_salary_usd": 160000,
        },
        skills={
            "languages": ["Python", "Go"],
            "frameworks": ["FastAPI", "React"],
            "cloud_and_tools": ["Docker", "AWS"],
        },
        screening_answers={
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "notice_period": "2 weeks",
            "expected_salary": "$170,000",
            "years_of_experience": {"python": 6.0},
        },
    )


@pytest.fixture
def sample_job():
    return Job(
        id="job_test_123",
        title="Senior Backend Engineer",
        company="Stripe",
        location="Remote",
        portal="greenhouse",
        job_url="https://boards.greenhouse.io/stripe/jobs/12345",
        description="Looking for Python and distributed systems engineers.",
        matched_skills="Python,AWS,FastAPI",
        status="discovered",
    )


@pytest.fixture
def mock_browser():
    browser = MagicMock()
    mock_driver = MagicMock()
    browser.driver = mock_driver
    browser.start.return_value = mock_driver
    return browser


@pytest.fixture
def in_memory_session():
    import tempfile
    from pathlib import Path
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_appliers.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
    manager.init_db()
    return manager


# -------------------------------------------------------------
# Test 1: ATS Applier Staging & Submit
# -------------------------------------------------------------
def test_ats_applier_fill_and_stage(mock_browser, sample_profile, sample_job):
    applier = ATSApplier(browser=mock_browser, profile=sample_profile)

    with patch.object(applier.form_filler, "fill_all_fields") as mock_fill:
        mock_fill.return_value = {
            "filled_fields": [{"type": "first_name", "value": "Gokul"}],
            "unfilled_fields": [],
        }
        result = applier.fill_and_stage(
            job=sample_job,
            cover_letter="Cover letter text",
            pitch_note="Pitch note text",
            screenshot_path="test_shot.png",
        )

        assert result.success is True
        assert result.status == "staged"
        assert len(result.fields_filled) == 1
        assert result.tailored_cover_letter == "Cover letter text"
        mock_browser.start.assert_called_once()
        mock_browser.take_screenshot.assert_called_once_with("test_shot.png")


def test_ats_applier_submit(mock_browser, sample_profile, sample_job):
    applier = ATSApplier(browser=mock_browser, profile=sample_profile)
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_browser.driver.find_elements.return_value = [mock_btn]

    success = applier.submit(sample_job)
    assert success is True
    mock_btn.click.assert_called_once()


# -------------------------------------------------------------
# Test 2: LinkedIn Easy Apply Multi-Step Progression
# -------------------------------------------------------------
def test_linkedin_applier_multistep(mock_browser, sample_profile, sample_job):
    sample_job.portal = "linkedin"
    sample_job.job_url = "https://linkedin.com/jobs/view/999"

    applier = LinkedInApplier(browser=mock_browser, profile=sample_profile, max_steps=4)

    # Mock Easy Apply click
    easy_apply_btn = MagicMock()
    easy_apply_btn.is_displayed.return_value = True
    easy_apply_btn.is_enabled.return_value = True

    # Next button
    next_btn = MagicMock()
    next_btn.text = "Next"
    next_btn.is_displayed.return_value = True
    next_btn.is_enabled.return_value = True

    # Submit button indicator
    submit_btn = MagicMock()
    submit_btn.is_displayed.return_value = True

    call_state = {"step": 0}

    def mock_find_elements(by, query):
        if "jobs-apply-button" in query or "Easy Apply" in query:
            return [easy_apply_btn]
        if "Submit application" in query:
            # appear on step 2
            return [submit_btn] if call_state["step"] >= 2 else []
        if "Next" in query:
            return [next_btn]
        return []

    mock_browser.driver.find_elements.side_effect = mock_find_elements

    def on_fill(*args, **kwargs):
        call_state["step"] += 1
        return {"filled_fields": [{"step": call_state["step"]}]}

    with patch.object(applier.form_filler, "fill_all_fields", side_effect=on_fill):
        result = applier.fill_and_stage(
            job=sample_job,
            cover_letter="LinkedIn cover",
            screenshot_path="linkedin_test.png",
        )

        assert result.success is True
        assert result.status == "staged"
        assert result.portal == "linkedin"
        assert len(result.fields_filled) >= 2


def test_linkedin_applier_submit(mock_browser, sample_profile, sample_job):
    applier = LinkedInApplier(browser=mock_browser, profile=sample_profile)
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_browser.driver.find_elements.return_value = [mock_btn]

    success = applier.submit(sample_job)
    assert success is True
    mock_btn.click.assert_called_once()


# -------------------------------------------------------------
# Test 3: Wellfound Pitch Insertion & Staging
# -------------------------------------------------------------
def test_wellfound_applier_stage(mock_browser, sample_profile, sample_job):
    sample_job.portal = "wellfound"
    sample_job.job_url = "https://wellfound.com/jobs/555"

    applier = WellfoundApplier(browser=mock_browser, profile=sample_profile)

    # Mock drawer button
    drawer_btn = MagicMock()
    drawer_btn.is_displayed.return_value = True
    drawer_btn.is_enabled.return_value = True

    # Mock pitch textarea
    textarea = MagicMock()
    textarea.is_displayed.return_value = True

    def mock_find_elements(by, query):
        if "Apply" in query:
            return [drawer_btn]
        if "textarea" in query:
            return [textarea]
        return []

    mock_browser.driver.find_elements.side_effect = mock_find_elements

    with patch.object(applier.form_filler, "fill_all_fields") as mock_fill:
        mock_fill.return_value = {"filled_fields": [], "unfilled_fields": []}
        result = applier.fill_and_stage(
            job=sample_job,
            pitch_note="Excited to join this early-stage team!",
            screenshot_path="wellfound_test.png",
        )

        assert result.success is True
        assert result.status == "staged"
        assert any(f.get("type") == "pitch_note" for f in result.fields_filled)
        mock_browser.human_type.assert_called_once()


def test_wellfound_applier_submit(mock_browser, sample_profile, sample_job):
    applier = WellfoundApplier(browser=mock_browser, profile=sample_profile)
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_browser.driver.find_elements.return_value = [mock_btn]

    success = applier.submit(sample_job)
    assert success is True
    mock_btn.click.assert_called_once()


# -------------------------------------------------------------
# Test 4: Indeed Quick Apply Staging & Submit
# -------------------------------------------------------------
def test_indeed_applier_stage(mock_browser, sample_profile, sample_job):
    sample_job.portal = "indeed"
    sample_job.job_url = "https://indeed.com/viewjob?jk=123"

    applier = IndeedApplier(browser=mock_browser, profile=sample_profile, max_steps=3)

    apply_btn = MagicMock()
    apply_btn.is_displayed.return_value = True
    apply_btn.is_enabled.return_value = True

    continue_btn = MagicMock()
    continue_btn.text = "Continue"
    continue_btn.is_displayed.return_value = True
    continue_btn.is_enabled.return_value = True

    submit_text = MagicMock()
    submit_text.is_displayed.return_value = True

    call_count = {"count": 0}

    def mock_find_elements(by, query):
        if "Apply now" in query:
            return [apply_btn]
        if "Submit your application" in query:
            return [submit_text] if call_count["count"] >= 1 else []
        if "Continue" in query:
            return [continue_btn]
        return []

    mock_browser.driver.find_elements.side_effect = mock_find_elements

    def on_fill(*args, **kwargs):
        call_count["count"] += 1
        return {"filled_fields": [{"field": "test"}]}

    with patch.object(applier.form_filler, "fill_all_fields", side_effect=on_fill):
        result = applier.fill_and_stage(
            job=sample_job,
            screenshot_path="indeed_test.png",
        )

        assert result.success is True
        assert result.status == "staged"
        assert result.portal == "indeed"


def test_indeed_applier_submit(mock_browser, sample_profile, sample_job):
    applier = IndeedApplier(browser=mock_browser, profile=sample_profile)
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_browser.driver.find_elements.return_value = [mock_btn]

    success = applier.submit(sample_job)
    assert success is True
    mock_btn.click.assert_called_once()


# -------------------------------------------------------------
# Test 5: Application Staging Engine Lifecycle (HITL DB persistence & Approval)
# -------------------------------------------------------------
def test_staging_engine_full_lifecycle(mock_browser, sample_profile, in_memory_session):
    job = Job(
        id="job_test_123",
        title="Senior Backend Engineer",
        company="Stripe",
        location="Remote",
        portal="greenhouse",
        job_url="https://boards.greenhouse.io/stripe/jobs/12345",
        description="Looking for Python and distributed systems engineers.",
        matched_skills="Python,AWS,FastAPI",
        status="discovered",
    )

    for session in in_memory_session.get_session():
        session.add(job)
        session.commit()
        session.expunge_all()

    engine = ApplicationStagingEngine(
        browser=mock_browser,
        profile=sample_profile,
        db_manager=in_memory_session,
    )

    # Mock default staging
    with patch.object(engine.form_filler, "fill_all_fields") as mock_fill:
        mock_fill.return_value = {
            "filled_fields": [{"type": "first_name", "value": "Gokul"}],
            "unfilled_fields": [],
        }

        # Stage application
        staging_result = engine.stage_job_application(job)

        assert staging_result.success is True
        assert staging_result.status == "staged"
        assert staging_result.tailored_cover_letter is not None

        # Verify DB records updated
        for session in in_memory_session.get_session():
            job_in_db = session.query(Job).filter_by(id=job.id).first()
            assert job_in_db.status == "staged"

            app_in_db = session.query(Application).filter_by(job_id=job.id).first()
            assert app_in_db is not None
            assert app_in_db.status == "staged"
            assert app_in_db.tailored_cover_letter is not None
            assert "Gokul" in app_in_db.submitted_qa

    # Test 1-click Approval & Submit
    mock_submit_btn = MagicMock()
    mock_submit_btn.is_displayed.return_value = True
    mock_submit_btn.is_enabled.return_value = True
    mock_browser.driver.find_elements.return_value = [mock_submit_btn]

    submitted = engine.approve_and_submit(job)
    assert submitted is True

    # Verify transition to 'submitted' in DB
    for session in in_memory_session.get_session():
        job_in_db = session.query(Job).filter_by(id=job.id).first()
        assert job_in_db.status == "submitted"

        app_in_db = session.query(Application).filter_by(job_id=job.id).first()
        assert app_in_db.status == "submitted"
