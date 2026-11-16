"""
Unit Tests for Ticket 5: Job Discovery Engine - Remote Tech Portals
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from Guffy.core.database import Job
from Guffy.searchers.base import BaseSearcher, JobPosting
from Guffy.searchers.remote_portals import (
    RemoteOKSearcher,
    WeWorkRemotelySearcher,
    YCStartupSearcher,
)


def test_job_posting_schema_and_model_conversion():
    posting = JobPosting(
        title="Senior Python Backend Engineer",
        company="FastCloud Inc",
        location="Remote - US",
        remote_type="Remote",
        portal="remoteok",
        job_url="https://remoteok.com/remote-jobs/12345",
        description="Looking for an experienced Python and FastAPI developer.",
        salary_range="$130,000 - $160,000",
        tags=["python", "fastapi", "remote"],
    )

    # Post init ID check
    assert posting.id is not None
    assert len(posting.id) == 16

    # Convert to SQLAlchemy Job model
    job = posting.to_job_model()
    assert isinstance(job, Job)
    assert job.id == posting.id
    assert job.title == "Senior Python Backend Engineer"
    assert job.company == "FastCloud Inc"
    assert job.portal == "remoteok"
    assert job.status == "discovered"
    assert job.salary_range == "$130,000 - $160,000"


def test_base_searcher_clean_html():
    raw_html = """
    <div>
        <p>Hello <b>World</b>!</p>
        <script>alert('bad');</script>
        <p>Join us &amp; build the future &lt;now&gt;.</p>
    </div>
    """
    cleaned = BaseSearcher.clean_html(raw_html)
    assert "Hello World!" in cleaned
    assert "Join us & build the future <now>." in cleaned
    assert "alert" not in cleaned
    assert "<p>" not in cleaned


@patch("requests.get")
def test_remoteok_searcher_success(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"legal": "Notice..."},  # legal disclaimer header item
        {
            "id": "1001",
            "position": "Staff Python Engineer",
            "company": "SuperData",
            "location": "Worldwide",
            "url": "https://remoteok.com/remote-jobs/1001",
            "description": "<p>Building high-throughput FastAPI systems with PostgreSQL.</p>",
            "tags": ["python", "fastapi", "postgresql"],
            "salary_min": 140000,
            "salary_max": 180000,
            "date": "2026-11-15T12:00:00Z",
        },
        {
            "id": "1002",
            "position": "Frontend React Engineer",
            "company": "DesignUI",
            "location": "USA",
            "url": "https://remoteok.com/remote-jobs/1002",
            "description": "<p>React TypeScript expert wanted.</p>",
            "tags": ["react", "typescript"],
            "date": "2026-11-15T14:00:00Z",
        },
    ]
    mock_get.return_value = mock_response

    searcher = RemoteOKSearcher()
    # Filter by keyword "python"
    jobs = searcher.search(keywords=["python"], limit=10)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Staff Python Engineer"
    assert job.company == "SuperData"
    assert job.portal == "remoteok"
    assert job.salary_range == "$140,000 - $180,000"
    assert "fastapi" in job.tags
    assert "<p>" not in job.description


@patch("requests.get")
def test_remoteok_searcher_network_error(mock_get):
    mock_get.side_effect = Exception("Connection timed out")
    searcher = RemoteOKSearcher()
    jobs = searcher.search(keywords=["python"])
    assert jobs == []


@patch("requests.get")
def test_weworkremotely_searcher_success(mock_get):
    mock_rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>We Work Remotely - Programming Jobs</title>
        <item>
          <title>Stripe: Senior Backend Software Engineer</title>
          <link>https://weworkremotely.com/remote-jobs/stripe-senior-backend</link>
          <description><![CDATA[<p>Join Stripe backend engineering team to scale payment infrastructure using Ruby, Go, and Python.</p>]]></description>
          <category>Backend</category>
          <category>Full-Time</category>
          <pubDate>Mon, 16 Nov 2026 10:00:00 +0000</pubDate>
        </item>
        <item>
          <title>DesignCo: Senior Product Designer</title>
          <link>https://weworkremotely.com/remote-jobs/designco-designer</link>
          <description><![CDATA[<p>Figma designer for web apps.</p>]]></description>
          <category>Design</category>
        </item>
      </channel>
    </rss>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_rss_xml
    mock_get.return_value = mock_response

    searcher = WeWorkRemotelySearcher()
    jobs = searcher.search(keywords=["backend", "python"], limit=5)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "Stripe"
    assert job.title == "Senior Backend Software Engineer"
    assert job.portal == "weworkremotely"
    assert "Stripe backend engineering" in job.description
    assert job.remote_type == "Remote"
    assert job.job_url == "https://weworkremotely.com/remote-jobs/stripe-senior-backend"


@patch("requests.get")
def test_yc_startup_searcher_success(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "hits": [
            {
                "objectID": "334455",
                "comment_text": "Retool | Full Stack Engineer | Remote (US/Canada) | Full-time | $150k-$200k<br>We are building internal developer tools. Seeking engineers with TypeScript, React, and Python experience. Apply at: https://retool.com/careers",
            },
            {
                "objectID": "334456",
                "comment_text": "MarketingPro | Growth Marketer | New York, NY | Onsite<br>Seeking SEO & content marketer.",
            },
        ]
    }
    mock_get.return_value = mock_response

    searcher = YCStartupSearcher()
    jobs = searcher.search(keywords=["engineer", "python"], limit=5)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "Retool"
    assert "Full Stack Engineer" in job.title
    assert job.portal == "yc_startup"
    assert job.job_url == "https://retool.com/careers"
    assert job.remote_type == "Remote"
