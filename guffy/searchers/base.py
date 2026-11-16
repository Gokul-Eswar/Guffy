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

from Guffy.core.database import Job


class JobPosting(BaseModel):
    """Normalized schema representing a discovered job across any search source."""
    id: str = ""
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
        """Generates deterministic unique ID from portal and job_url if not provided."""
        if not self.id:
            raw = f"{self.portal}:{self.job_url.strip()}".lower()
            self.id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_job_model(self) -> Job:
        """Converts JobPosting schema into an instance of SQLAlchemy Job model."""
        return Job(
            id=self.id,
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
