"""
Unit Tests for Aggregator & Board Searchers (Ticket 7)
Covers LinkedIn, Wellfound, Indeed, Dice, and Glassdoor searchers.
"""

from unittest.mock import MagicMock, patch
import pytest

from Guffy.searchers.glassdoor_dice import DiceSearcher, GlassdoorSearcher
from Guffy.searchers.indeed import IndeedSearcher
from Guffy.searchers.linkedin import LinkedInSearcher
from Guffy.searchers.wellfound import WellfoundSearcher


def test_linkedin_searcher_html_parsing():
    sample_html = """
    <ul class="jobs-search__results-list">
      <li>
        <div class="base-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3891029100">
            <h3 class="base-search-card__title">Senior Python Backend Engineer</h3>
          </a>
          <h4 class="base-search-card__subtitle"><a href="#">Scale AI</a></h4>
          <span class="job-search-card__location">San Francisco, CA (Remote)</span>
          <span class="job-search-card__salary-info">$160,000 - $210,000</span>
          <span class="job-search-card__easy-apply-label">Easy Apply</span>
        </div>
      </li>
      <li>
        <div class="base-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/3891029200">
            <h3 class="base-search-card__title">Full Stack Developer</h3>
          </a>
          <h4 class="base-search-card__subtitle">Cloudflare</h4>
          <span class="job-search-card__location">Austin, TX</span>
        </div>
      </li>
    </ul>
    """
    searcher = LinkedInSearcher()
    postings = searcher.parse_search_html(sample_html)

    assert len(postings) == 2
    p1 = postings[0]
    assert p1.title == "Senior Python Backend Engineer"
    assert p1.company == "Scale AI"
    assert p1.portal == "linkedin"
    assert p1.remote_type == "Remote"
    assert p1.easy_apply is True
    assert p1.salary_range == "$160,000 - $210,000"
    assert "https://www.linkedin.com/jobs/view/3891029100" in p1.job_url

    p2 = postings[1]
    assert p2.title == "Full Stack Developer"
    assert p2.company == "Cloudflare"
    assert p2.easy_apply is False


def test_linkedin_search_network_mock():
    sample_html = """
    <div class="base-card">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/999888">
        <h3 class="base-search-card__title">AI Research Engineer</h3>
      </a>
      <h4 class="base-search-card__subtitle">Anthropic</h4>
      <span class="job-search-card__location">Remote</span>
    </div>
    """
    searcher = LinkedInSearcher()
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_html
        mock_get.return_value = mock_resp

        results = searcher.search(keywords=["AI", "Engineer"], limit=10)
        assert len(results) == 1
        assert results[0].title == "AI Research Engineer"
        assert results[0].company == "Anthropic"


def test_wellfound_searcher_json_hydration():
    sample_html = """
    <html>
      <script id="__NEXT_DATA__" type="application/json">
      {
        "props": {
          "pageProps": {
            "jobListings": [
              {
                "title": "Founding Engineer (Backend / Python)",
                "slug": "founding-engineer-backend-python",
                "startup": {"name": "Nexus AI"},
                "locationVal": "Remote - US",
                "compensation": "$140k – $180k • 0.5% – 1.5%"
              }
            ]
          }
        }
      }
      </script>
    </html>
    """
    searcher = WellfoundSearcher()
    postings = searcher.parse_html(sample_html)

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Founding Engineer (Backend / Python)"
    assert p.company == "Nexus AI"
    assert p.portal == "wellfound"
    assert p.salary_range == "$140k – $180k • 0.5% – 1.5%"
    assert p.easy_apply is True
    assert p.remote_type == "Remote"


def test_wellfound_searcher_html_fallback():
    sample_html = """
    <div class="styles_jobListing__abc">
      <div>
        <a class="title" href="/jobs/12345-senior-backend-engineer">Senior Backend Engineer</a>
        <span class="companyName">Ramp</span>
        <span class="salary">$175k - $220k • 0.1%</span>
      </div>
    </div>
    """
    searcher = WellfoundSearcher()
    postings = searcher.parse_html(sample_html)

    assert len(postings) == 1
    assert postings[0].title == "Senior Backend Engineer"
    assert postings[0].company == "Ramp"
    assert postings[0].portal == "wellfound"
    assert postings[0].job_url == "https://wellfound.com/jobs/12345-senior-backend-engineer"


def test_indeed_searcher_mosaic_data_parsing():
    sample_html = """
    <script>
    window._initialData = {
      "results": [
        {
          "title": "Lead Software Engineer",
          "company": "Datadog",
          "jobkey": "d41d8cd98f00b204",
          "formattedLocation": "Remote in New York, NY",
          "isEasilyApplyable": true,
          "estimatedSalary": {"formatted": "$180,000 - $230,000 a year"}
        }
      ]
    };
    </script>
    """
    searcher = IndeedSearcher()
    postings = searcher.parse_html(sample_html)

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Lead Software Engineer"
    assert p.company == "Datadog"
    assert p.portal == "indeed"
    assert p.easy_apply is True
    assert p.salary_range == "$180,000 - $230,000 a year"
    assert p.job_url == "https://www.indeed.com/viewjob?jk=d41d8cd98f00b204"


def test_indeed_searcher_html_fallback():
    sample_html = """
    <div class="job_seen_beacon" data-jk="fe9876543210">
      <h2 class="jobTitle"><a href="/viewjob?jk=fe9876543210">Python Data Engineer</a></h2>
      <span class="companyName">Stripe</span>
      <div class="companyLocation">Remote</div>
      <div class="salary-snippet-container">$150,000 - $200,000 a year</div>
      <span>Easily apply</span>
    </div>
    """
    searcher = IndeedSearcher()
    postings = searcher.parse_html(sample_html)

    assert len(postings) == 1
    assert postings[0].title == "Python Data Engineer"
    assert postings[0].company == "Stripe"
    assert postings[0].easy_apply is True
    assert postings[0].job_url == "https://www.indeed.com/viewjob?jk=fe9876543210"


def test_dice_searcher_api_mock():
    mock_dice_api = {
        "data": [
            {
                "id": "dice-001",
                "title": "Cloud Platform Architect",
                "companyName": "TechCorp Global",
                "detailUrl": "https://www.dice.com/job-detail/dice-001",
                "summaryLocation": "Remote, US",
                "salary": "$170,000 - $210,000",
                "isEasyApply": True,
            }
        ]
    }
    searcher = DiceSearcher()
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_dice_api
        mock_post.return_value = mock_resp

        results = searcher.search(keywords=["Cloud", "Architect"], limit=5)
        assert len(results) == 1
        p = results[0]
        assert p.title == "Cloud Platform Architect"
        assert p.company == "TechCorp Global"
        assert p.portal == "dice"
        assert p.easy_apply is True
        assert p.salary_range == "$170,000 - $210,000"


def test_dice_searcher_html_fallback():
    sample_html = """
    <div class="card-title-link">
      <a href="/job-detail/sec-999">Security Operations Specialist</a>
    </div>
    """
    searcher = DiceSearcher()
    postings = searcher.parse_html(sample_html)
    assert len(postings) == 1
    assert postings[0].title == "Security Operations Specialist"
    assert postings[0].portal == "dice"
    assert postings[0].job_url == "https://www.dice.com/job-detail/sec-999"


def test_glassdoor_searcher_parsing():
    sample_html = """
    <html>
      <a href="/partner/jobListing.htm?pos=101&jobListingId=456789">Senior Site Reliability Engineer</a>
    </html>
    """
    searcher = GlassdoorSearcher()
    postings = searcher.parse_html(sample_html)
    assert len(postings) == 1
    assert postings[0].title == "Senior Site Reliability Engineer"
    assert postings[0].portal == "glassdoor"
    assert "jobListingId=456789" in postings[0].job_url
