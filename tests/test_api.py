"""
Integration & Unit Tests for FastAPI Backend REST API (Ticket 10)
"""

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, mock_open, patch
import pytest
from starlette.testclient import TestClient
import yaml

from guffy.automation.staging_engine import ApplicationStagingEngine
from guffy.core.database import Application, Company, DatabaseManager, Job
from guffy.core.profile_manager import CandidateProfile
from guffy.searchers.base import JobPosting
from guffy.web.app import app, get_current_profile, get_db


@pytest.fixture
def test_db_manager():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_api.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
    manager.init_db()
    return manager


@pytest.fixture
def sample_profile():
    return CandidateProfile(
        personal_info={
            "full_name": "Gokul Eswar",
            "email": "gokul@example.com",
            "phone": "+1-555-0199",
            "location": "Remote",
            "linkedin_url": "https://linkedin.com/in/gokuleswar",
            "github_url": "https://github.com/gokuleswar",
            "portfolio_url": "https://gokul.dev",
            "resume_path": "",
        },
        preferences={
            "target_titles": ["Senior Backend Engineer", "Python Engineer"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "min_base_salary_usd": 150000,
            "blacklisted_companies": ["BlacklistedCorp"],
        },
        skills={
            "languages": ["Python", "Go"],
            "frameworks": ["FastAPI", "React"],
            "cloud_and_tools": ["Docker", "AWS", "PostgreSQL"],
        },
        screening_answers={
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "notice_period": "Immediate",
            "expected_salary": "$160,000",
            "years_of_experience": {"python": 5.0},
        },
    )


@pytest.fixture
def client(test_db_manager, sample_profile):
    def override_get_db():
        session = test_db_manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_profile():
        return sample_profile

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_profile] = override_get_profile

    with patch("guffy.web.app.get_db_manager", return_value=test_db_manager):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def populated_jobs(test_db_manager):
    session = test_db_manager.SessionLocal()
    j1 = Job(
        id="job_remote_1",
        title="Senior Python Backend Engineer",
        company="RemoteCorp",
        location="Remote",
        remote_type="Remote",
        portal="remoteok",
        job_url="https://remoteok.com/j/1",
        description="We are hiring a senior Python engineer with FastAPI and AWS.",
        match_score=92.5,
        matched_skills=json.dumps(["python", "fastapi", "aws"]),
        missing_skills=json.dumps([]),
        pros_cons=json.dumps({"pros": ["Great match"], "cons": []}),
        status="scored",
    )
    j2 = Job(
        id="job_remote_2",
        title="Junior Frontend Developer",
        company="DesignStudio",
        location="Remote",
        remote_type="Remote",
        portal="wellfound",
        job_url="https://wellfound.com/j/2",
        description="Looking for junior frontend developer with CSS.",
        match_score=40.0,
        status="discovered",
    )
    j3 = Job(
        id="job_remote_3",
        title="DevOps Architect",
        company="CloudNatives",
        location="Remote",
        remote_type="Remote",
        portal="greenhouse",
        job_url="https://boards.greenhouse.io/cloudnatives/123",
        description="Kubernetes, Terraform, AWS.",
        match_score=85.0,
        status="staged",
    )
    app3 = Application(
        job_id=j3.id,
        portal="greenhouse",
        status="staged",
        tailored_cover_letter="Sample cover letter",
        tailored_pitch="Sample pitch",
    )

    session.add_all([j1, j2, j3, app3])
    session.commit()
    session.close()
    return [j1, j2, j3]


# ---------------------------------------------------------------------------
# Test 1: Health check
# ---------------------------------------------------------------------------
def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Guffy"


# ---------------------------------------------------------------------------
# Test 2: Jobs list & filtering
# ---------------------------------------------------------------------------
def test_get_jobs_list_and_filters(client, populated_jobs):
    # Fetch all
    res = client.get("/api/jobs")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["jobs"]) == 3

    # Filter by status
    res = client.get("/api/jobs?status=scored")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["jobs"][0]["id"] == "job_remote_1"

    # Filter by portal
    res = client.get("/api/jobs?portal=wellfound")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["jobs"][0]["portal"] == "wellfound"

    # Filter by min_score
    res = client.get("/api/jobs?min_score=80")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2

    # Filter by company
    res = client.get("/api/jobs?company=remote")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1


# ---------------------------------------------------------------------------
# Test 3: Single job detail with application stage
# ---------------------------------------------------------------------------
def test_get_job_detail(client, populated_jobs):
    res = client.get("/api/jobs/job_remote_3")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "job_remote_3"
    assert data["status"] == "staged"
    assert data["application"] is not None
    assert data["application"]["status"] == "staged"
    assert "Sample cover letter" in data["application"]["tailored_cover_letter"]

    # 404 for non-existent job
    res404 = client.get("/api/jobs/non_existent_id")
    assert res404.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: Multi-portal Search trigger (sync & queued)
# ---------------------------------------------------------------------------
def test_trigger_search_sync(client, test_db_manager):
    mock_postings = [
        JobPosting(
            title="Backend Lead",
            company="TechCorp",
            portal="remoteok",
            job_url="https://remoteok.com/j/999",
            description="Python FastAPI engineer",
            remote_type="Remote",
            location="Remote",
        )
    ]

    with patch("guffy.web.app.RemoteOKSearcher.search", return_value=mock_postings):
        payload = {
            "keywords": ["Python"],
            "locations": ["Remote"],
            "portals": ["remoteok"],
            "remote_only": True,
            "max_results": 10,
        }
        res = client.post("/api/search?sync=true", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "completed"

        # Verify job was inserted into DB
        session = test_db_manager.SessionLocal()
        job = session.query(Job).filter_by(job_url="https://remoteok.com/j/999").first()
        assert job is not None
        assert job.company == "TechCorp"
        session.close()


def test_trigger_search_async(client):
    res = client.post("/api/search?sync=false", json={"portals": ["remoteok"]})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"


# ---------------------------------------------------------------------------
# Test 5: Company career crawler trigger
# ---------------------------------------------------------------------------
def test_trigger_company_crawl(client, test_db_manager):
    mock_job = Job(
        id="crawled_job_1",
        title="Founding Engineer",
        company="Stripe",
        portal="greenhouse",
        job_url="https://boards.greenhouse.io/stripe/jobs/99",
    )
    with patch("guffy.web.app.CompanyCrawler.crawl_all", return_value=[mock_job]):
        res = client.post("/api/crawl-companies?sync=true")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["crawled_count"] == 1


# ---------------------------------------------------------------------------
# Test 6: Fit match trigger
# ---------------------------------------------------------------------------
def test_run_match_endpoint(client, test_db_manager, populated_jobs):
    # Job 2 is currently in 'discovered' status
    res = client.post("/api/match", json={"job_ids": ["job_remote_2"]})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["total_scored"] == 1

    session = test_db_manager.SessionLocal()
    j2 = session.query(Job).filter_by(id="job_remote_2").first()
    assert j2.status in ["scored", "rejected"]
    session.close()


# ---------------------------------------------------------------------------
# Test 7: Staging and Approval Endpoints (HITL)
# ---------------------------------------------------------------------------
def test_stage_and_approve_endpoints(client, test_db_manager, populated_jobs):
    mock_staging_result = MagicMock()
    mock_staging_result.status = "staged"
    mock_staging_result.success = True
    mock_staging_result.job_id = "job_remote_1"
    mock_staging_result.portal = "remoteok"
    mock_staging_result.screenshot_path = "staging_screenshots/stage_job_remote_1.png"
    mock_staging_result.tailored_cover_letter = "Dear RemoteCorp Hiring Team..."
    mock_staging_result.tailored_pitch = "Concise pitch note"
    mock_staging_result.fields_filled = [{"name": "email", "value": "gokul@example.com"}]
    mock_staging_result.unfilled_fields = []
    mock_staging_result.error_message = None

    with patch.object(ApplicationStagingEngine, "stage_job_application", return_value=mock_staging_result):
        res = client.post("/api/stage/job_remote_1")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "staged"
        assert data["success"] is True
        assert data["fields_filled_count"] == 1

    # Now test approve endpoint
    with patch.object(ApplicationStagingEngine, "approve_and_submit", return_value=True):
        res_approve = client.post("/api/approve/job_remote_1")
        assert res_approve.status_code == 200
        data_app = res_approve.json()
        assert data_app["status"] == "submitted"
        assert data_app["success"] is True


# ---------------------------------------------------------------------------
# Test 8: Profile endpoints (Get, Update, Resume Upload)
# ---------------------------------------------------------------------------
def test_profile_endpoints(client, tmp_path):
    # GET profile
    res = client.get("/api/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["personal_info"]["full_name"] == "Gokul Eswar"

    # PUT profile
    data["personal_info"]["phone"] = "+1-800-TEST"
    with patch("builtins.open", mock_open()):
        with patch("yaml.dump", return_value=""):
            res_put = client.put("/api/profile", json=data)
            assert res_put.status_code == 200
            assert res_put.json()["status"] == "success"

    # POST resume upload
    fake_resume_content = b"Gokul Eswar. Skills: Python, FastAPI, Docker, PostgreSQL."
    with patch("guffy.web.app.ResumeParser.extract_text", return_value="Python FastAPI Docker PostgreSQL"):
        with patch("guffy.web.app.ResumeParser.extract_skills", return_value=["python", "fastapi", "docker"]):
            with patch("pathlib.Path.mkdir", return_value=None):
                with patch("builtins.open", mock_open()):
                    with patch("yaml.dump", return_value=""):
                        files = {"file": ("resume.pdf", fake_resume_content, "application/pdf")}
                        res_upload = client.post("/api/profile/resume", files=files)
                        assert res_upload.status_code == 200
                        upload_data = res_upload.json()
                        assert upload_data["status"] == "success"
                        assert "python" in upload_data["detected_skills"]


# ---------------------------------------------------------------------------
# Test 9: Companies endpoints (List, Create, Delete)
# ---------------------------------------------------------------------------
def test_companies_endpoints(client, test_db_manager):
    # Create company
    comp_payload = {
        "name": "Datadog",
        "domain": "datadog.com",
        "careers_url": "https://boards.greenhouse.io/datadog",
        "ats": "greenhouse",
        "priority": "high",
    }
    res_create = client.post("/api/companies", json=comp_payload)
    assert res_create.status_code == 200
    created = res_create.json()
    assert created["company"]["name"] == "Datadog"
    comp_id = created["company"]["id"]

    # List companies
    res_list = client.get("/api/companies")
    assert res_list.status_code == 200
    companies = res_list.json()
    assert len(companies) == 1
    assert companies[0]["name"] == "Datadog"

    # Delete company
    res_del = client.delete(f"/api/companies/{comp_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # List again should be empty
    res_list2 = client.get("/api/companies")
    assert len(res_list2.json()) == 0


# ---------------------------------------------------------------------------
# Test 10: Analytics pipeline
# ---------------------------------------------------------------------------
def test_analytics_endpoint(client, populated_jobs):
    res = client.get("/api/analytics")
    assert res.status_code == 200
    data = res.json()
    assert data["pipeline"]["total_discovered"] == 3
    assert data["pipeline"]["total_staged"] == 1
    assert "remoteok" in data["portal_distribution"]
    assert data["average_match_score"] > 0
