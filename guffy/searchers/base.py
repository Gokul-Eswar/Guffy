"""
Base Interfaces and Schemas for Job Searchers (Ticket 5)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from Guffy.core.database import Job, JobOutlet


def normalize_company(company: str) -> str:
    """Normalizes company name by removing legal identifiers and extra whitespace."""
    if not company:
        return ""
    c = company.strip().lower()
    c = re.sub(r"\b(inc|incorporated|llc|corp|corporation|ltd|limited|co|company|gmbh|sa|pvt)\b[\.]?", "", c)
    c = re.sub(r"[^\w\s]", "", c)
    return " ".join(c.split())


def normalize_title(title: str) -> str:
    """Normalizes job title by stripping bracketed qualifiers, remote tags, and punctuation."""
    if not title:
        return ""
    t = title.strip().lower()
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)  # strip bracketed notes e.g. [Remote], (US only)
    t = re.sub(r"\b(remote|hybrid|onsite|full-time|part-time|contract|urgent|urgently hiring)\b", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def compute_canonical_id(company: str, title: str) -> str:
    """Computes a deterministic canonical fingerprint for cross-source grouping."""
    c = normalize_company(company)
    t = normalize_title(title)
    raw = f"{c}:{t}".strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_outlet_directness_score(portal: str, easy_apply: bool = False) -> int:
    """
    Computes a directness score (0-100) indicating closeness to the hiring recruiter:
    100 = Official Company ATS (Greenhouse, Lever, Ashby, Workday, SmartRecruiters)
     80 = Direct 1-Click / Easy Apply (LinkedIn Easy Apply, Wellfound startup direct)
     60 = Standard Job Board (Indeed, LinkedIn Standard, Glassdoor, Dice)
     40 = Third-Party Remote Aggregators (RemoteOK, WeWorkRemotely, YC Work at a Startup)
    """
    p = (portal or "").lower()
    if p in ("company_ats", "greenhouse", "lever", "ashby", "workday", "smartrecruiters", "direct"):
        return 100
    if easy_apply or p == "wellfound":
        return 80
    if p in ("linkedin", "indeed", "glassdoor", "dice"):
        return 60
    return 40


def get_outlet_badge_and_label(portal: str, directness_score: int) -> Dict[str, str]:
    """Returns human-friendly route descriptor and recommendation rationale."""
    if directness_score >= 100:
        return {
            "tier": "direct_ats",
            "label": "Direct to Recruiter (Official ATS)",
            "rationale": "Direct submission into employer ATS without aggregator latency or middlemen.",
        }
    elif directness_score >= 80:
        return {
            "tier": "direct_apply",
            "label": "Direct / Easy Apply",
            "rationale": "High visibility direct submission or 1-click startup outreach.",
        }
    elif directness_score >= 60:
        return {
            "tier": "job_board",
            "label": "Standard Job Board Listing",
            "rationale": "Public listing on high-volume board.",
        }
    else:
        return {
            "tier": "aggregator",
            "label": "Syndicated Aggregator",
            "rationale": "Syndicated remote tech aggregator.",
        }


class JobPosting(BaseModel):
    """Normalized schema representing a discovered job across any search source."""
    id: str = ""
    canonical_id: str = ""
    title: str
    company: str
    location: str = "Remote"
    remote_type: str = "Remote"  # Remote, Hybrid, Onsite
    portal: str                  # remoteok, weworkremotely, yc_startup, etc.
    job_url: str
    description: str = ""
    salary_range: Optional[str] = None
    easy_apply: bool = False
    tags: List[str] = Field(default_factory=list)
    posted_at: Optional[datetime] = None

    def model_post_init(self, __context: Any) -> None:
        """Generates deterministic unique ID and canonical ID."""
        if not self.id:
            raw = f"{self.portal}:{self.job_url.strip()}".lower()
            self.id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        if not self.canonical_id:
            self.canonical_id = compute_canonical_id(self.company, self.title)

    def to_job_model(self) -> Job:
        """Converts JobPosting schema into an instance of SQLAlchemy Job model."""
        return Job(
            id=self.id,
            canonical_id=self.canonical_id,
            is_canonical_primary=True,
            title=self.title.strip(),
            company=self.company.strip(),
            location=self.location.strip() or "Remote",
            remote_type=self.remote_type.strip() or "Remote",
            portal=self.portal.strip().lower(),
            job_url=self.job_url.strip(),
            description=self.description.strip(),
            salary_range=self.salary_range.strip() if self.salary_range else None,
            easy_apply=self.easy_apply,
            status="discovered",
        )


class BaseSearcher(ABC):
    """Abstract Base Class that every job discovery searcher implements."""

    name: str = "base"

    def __init__(self, headers: Optional[Dict[str, str]] = None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        }

    @abstractmethod
    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        """
        Executes job search querying the target portal.
        Returns a list of normalized JobPosting objects.
        """
        pass

    @staticmethod
    def clean_html(html_content: str) -> str:
        """Helper to strip HTML tags and decode clean readable plain text."""
        if not html_content:
            return ""
        # Remove script and style elements
        text = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        # Replace line breaks and block tag ends with newlines
        text = re.sub(r"<(br|/p|/div|/li|tr)>", "\n", text, flags=re.IGNORECASE)
        # Inline tags like <b>, </b>, <i>, </i>, <span>, </a> should be removed without introducing spaces
        text = re.sub(r"<(/?(b|i|u|strong|em|span|a|small|sub|sup)[^>]*)>", "", text, flags=re.IGNORECASE)
        # Strip all other HTML tags (replacing with space to preserve separation)
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape common entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        # Collapse spaces within lines
        lines = []
        for line in text.splitlines():
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
            if cleaned_line:
                lines.append(cleaned_line)
        return "\n\n".join(lines)
