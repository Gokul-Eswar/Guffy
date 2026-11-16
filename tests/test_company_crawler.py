"""
Unit Tests for Official Company Career Page & Direct ATS Crawler (Ticket 6)
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Guffy.core.database import Base, Company, Job
from Guffy.searchers.company_crawler import (
    ATSSignatureDetector,
    AshbyParser,
    CompanyCrawler,
    GenericCareerParser,
    GreenhouseParser,
    LeverParser,
    TargetCompanyManager,
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


def test_ats_signature_detector():
    # URL detection
    assert ATSSignatureDetector.detect_from_url("https://boards.greenhouse.io/openai") == "greenhouse"
    assert ATSSignatureDetector.detect_from_url("https://jobs.lever.co/anthropic") == "lever"
    assert ATSSignatureDetector.detect_from_url("https://jobs.ashbyhq.com/linear") == "ashby"
    assert ATSSignatureDetector.detect_from_url("https://stripe.wd1.myworkdaysite.com/recruiting") == "workday"
    assert ATSSignatureDetector.detect_from_url("https://jobs.smartrecruiters.com/shopify") == "smartrecruiters"
    assert ATSSignatureDetector.detect_from_url("https://example.com/careers") is None

    # HTML detection
    greenhouse_html = '<div><iframe src="https://boards.greenhouse.io/embed/job_board?for=example"></iframe></div>'
    lever_html = '<script src="https://assets.lever.co/lever-analytics.js"></script>'
    ashby_html = '<a href="https://jobs.ashbyhq.com/company/uuid">View Job</a>'
    
    assert ATSSignatureDetector.detect_from_html(greenhouse_html) == "greenhouse"
    assert ATSSignatureDetector.detect_from_html(lever_html) == "lever"
    assert ATSSignatureDetector.detect_from_html(ashby_html) == "ashby"
    assert ATSSignatureDetector.detect("https://example.com/careers", greenhouse_html) == "greenhouse"
    assert ATSSignatureDetector.detect("https://example.com/careers", "<html><body>No ATS</body></html>") == "custom"


def test_target_company_manager_load_and_sync(test_db):
    sample_yaml = """
companies:
  - name: "Acme Corp"
    domain: "acme.com"
    careers_url: "https://boards.greenhouse.io/acme"
    ats: "greenhouse"
    priority: "high"
  - name: "Beta Labs"
    domain: "betalabs.io"
    careers_url: "https://jobs.lever.co/betalabs"
    ats: "lever"
    priority: "medium"
"""
    with patch("builtins.open", pytest.MonkeyPatch().context()) as _:
        pass  # Just create a manager with mock
    
    manager = TargetCompanyManager(yaml_path="dummy.yaml")
    with patch("yaml.safe_load", return_value={
        "companies": [
            {
                "name": "Acme Corp",
                "domain": "acme.com",
                "careers_url": "https://boards.greenhouse.io/acme",
                "ats": "greenhouse",
                "priority": "high",
            },
            {
                "name": "Beta Labs",
                "domain": "betalabs.io",
                "careers_url": "https://jobs.lever.co/betalabs",
                "ats": "lever",
                "priority": "medium",
            },
        ]
    }):
        with patch("builtins.open", MagicMock()):
            synced = manager.sync_to_db(test_db)
            assert len(synced) == 2

            # Query from DB
            companies_in_db = test_db.query(Company).all()
            assert len(companies_in_db) == 2
            assert companies_in_db[0].name == "Acme Corp"
            assert companies_in_db[0].ats == "greenhouse"
            assert companies_in_db[0].priority == "high"

            # Filter high priority
            high_pri = manager.get_companies(test_db, priority="high")
            assert len(high_pri) == 1
            assert high_pri[0].name == "Acme Corp"


def test_greenhouse_parser_api_mock():
    mock_gh_response = {
        "jobs": [
            {
                "id": 101,
                "title": "Senior Backend Engineer - Distributed Systems",
                "absolute_url": "https://boards.greenhouse.io/openai/jobs/101",
                "location": {"name": "San Francisco, CA / Remote"},
                "content": "<p>Build high scale systems with <b>Python</b> and distributed infrastructure.</p>",
            },
            {
                "id": 102,
                "title": "Frontend Engineer",
                "absolute_url": "https://boards.greenhouse.io/openai/jobs/102",
                "location": {"name": "New York, NY"},
                "content": "<p>React and Next.js specialist.</p>",
            },
        ]
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gh_response
        mock_get.return_value = mock_resp

        postings = GreenhouseParser.fetch_jobs(
            company_name="OpenAI",
            careers_url="https://boards.greenhouse.io/openai",
            headers={},
        )

        assert len(postings) == 2
        p1 = postings[0]
        assert p1.title == "Senior Backend Engineer - Distributed Systems"
        assert p1.company == "OpenAI"
        assert p1.remote_type == "Remote"
        assert "Python" in p1.description
        assert p1.portal == "company_ats"
        assert p1.job_url == "https://boards.greenhouse.io/openai/jobs/101"
        assert "greenhouse" in p1.tags


def test_lever_parser_api_mock():
    mock_lever_response = [
        {
            "id": "abc-123",
            "text": "Machine Learning Platform Engineer",
            "hostedUrl": "https://jobs.lever.co/anthropic/abc-123",
            "categories": {
                "location": "Remote",
                "workplaceType": "remote",
            },
            "description": "<div>Build resilient training clusters for foundation models.</div>",
            "descriptionPlain": "Build resilient training clusters for foundation models.",
        }
    ]

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_lever_response
        mock_get.return_value = mock_resp

        postings = LeverParser.fetch_jobs(
            company_name="Anthropic",
            careers_url="https://jobs.lever.co/anthropic",
            headers={},
        )

        assert len(postings) == 1
        p = postings[0]
        assert p.title == "Machine Learning Platform Engineer"
        assert p.company == "Anthropic"
        assert p.remote_type == "Remote"
        assert p.portal == "company_ats"
        assert p.job_url == "https://jobs.lever.co/anthropic/abc-123"
        assert "lever" in p.tags


def test_ashby_parser_api_mock():
    mock_ashby_response = {
        "jobs": [
            {
                "id": "ashby-xyz",
                "title": "Full Stack Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/linear/ashby-xyz",
                "location": "Remote - Worldwide",
                "isRemote": True,
                "descriptionHtml": "<p>Join our core product engineering team building fast apps.</p>",
                "compensation": {
                    "compensationSummary": "$150k - $200k + Equity"
                },
            }
        ]
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_ashby_response
        mock_get.return_value = mock_resp

        postings = AshbyParser.fetch_jobs(
            company_name="Linear",
            careers_url="https://jobs.ashbyhq.com/linear",
            headers={},
        )

        assert len(postings) == 1
        p = postings[0]
        assert p.title == "Full Stack Engineer"
        assert p.company == "Linear"
        assert p.remote_type == "Remote"
        assert p.salary_range == "$150k - $200k + Equity"
        assert p.job_url == "https://jobs.ashbyhq.com/linear/ashby-xyz"
        assert "ashby" in p.tags


def test_generic_career_parser_html():
    html_page = """
    <html>
      <body>
        <nav><a href="/about">About Us</a></nav>
        <div class="careers">
          <h2>Open Positions</h2>
          <ul>
            <li><a href="/jobs/senior-staff-engineer">Senior Staff Engineer - Cloud Infrastructure</a></li>
            <li><a href="/jobs/product-designer">Lead Product Designer (Remote)</a></li>
            <li><a href="/privacy-policy">Privacy Policy</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    postings = GenericCareerParser.parse_html(html_page, "Acme", "https://acme.com/careers")
    assert len(postings) == 2
    titles = [p.title for p in postings]
    assert "Senior Staff Engineer - Cloud Infrastructure" in titles
    assert "Lead Product Designer (Remote)" in titles

    designer_job = next(p for p in postings if "Designer" in p.title)
    assert designer_job.remote_type == "Remote"
    assert designer_job.job_url == "https://acme.com/jobs/product-designer"


def test_company_crawler_integration_crawl_all(test_db):
    company = Company(
        name="TestCorp",
        domain="testcorp.com",
        careers_url="https://boards.greenhouse.io/testcorp",
        ats="greenhouse",
        priority="high",
    )
    test_db.add(company)
    test_db.commit()

    manager = TargetCompanyManager()
    crawler = CompanyCrawler(target_manager=manager)

    mock_gh_response = {
        "jobs": [
            {
                "id": 999,
                "title": "Senior Python Developer",
                "absolute_url": "https://boards.greenhouse.io/testcorp/jobs/999",
                "location": {"name": "Remote"},
                "content": "<p>FastAPI, PostgreSQL, Microservices</p>",
            }
        ]
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gh_response
        mock_get.return_value = mock_resp

        results = crawler.crawl_all(test_db, keywords=["Python"])

        assert len(results) == 1
        assert results[0].title == "Senior Python Developer"
        assert results[0].company == "TestCorp"

        # Check DB was populated with Job record
        saved_job = test_db.query(Job).filter(Job.job_url == results[0].job_url).first()
        assert saved_job is not None
        assert saved_job.title == "Senior Python Developer"
        assert saved_job.portal == "company_ats"

        # Check Company updated active_jobs_count and last_crawled_at
        updated_comp = test_db.query(Company).filter(Company.name == "TestCorp").first()
        assert updated_comp.active_jobs_count == 1
        assert updated_comp.last_crawled_at is not None
