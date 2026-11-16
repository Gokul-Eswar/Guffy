"""
Official Company Career Page & Direct ATS Crawler (Ticket 6)

Provides:
- TargetCompanyManager: Loads and syncs target companies from YAML or DB.
- ATSSignatureDetector: Detects ATS type (Greenhouse, Lever, Ashby, Workday, SmartRecruiters)
  from career URLs or HTML content.
- Direct Job Parsers:
  - GreenhouseParser: Leverages Greenhouse job board API or HTML.
  - LeverParser: Leverages Lever postings API or HTML.
  - AshbyParser: Leverages Ashby posting API / HTML.
  - Generic/Fallback Parser.
- CompanyCrawler: Orchestrates crawling target companies and returning JobPostings.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import yaml
import requests
from sqlalchemy.orm import Session

from Guffy.core.database import Company, Job
from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class ATSSignatureDetector:
    """
    Detects ATS provider from URLs and HTML content.
    Supported signatures: greenhouse, lever, ashby, workday, smartrecruiters, custom/unknown.
    """

    PATTERNS = {
        "greenhouse": [
            r"boards\.greenhouse\.io",
            r"job-boards\.greenhouse\.io",
            r"api\.greenhouse\.io",
            r"greenhouse\.io/embed",
            r"grnh\.se",
            r"gh_jid",
        ],
        "lever": [
            r"jobs\.lever\.co",
            r"api\.lever\.co",
            r"lever-analytics",
            r"lever-job",
        ],
        "ashby": [
            r"jobs\.ashbyhq\.com",
            r"ashbyhq\.com/api",
            r"api\.ashbyhq\.com",
            r"ashby-job",
        ],
        "workday": [
            r"myworkdayjobs\.com",
            r"workday\.com",
            r"wd1\.myworkdaysite\.com",
            r"wd3\.myworkdaysite\.com",
            r"wd5\.myworkdaysite\.com",
        ],
        "smartrecruiters": [
            r"smartrecruiters\.com",
            r"smrtr\.io",
            r"api\.smartrecruiters\.com",
        ],
    }

    @classmethod
    def detect_from_url(cls, url: str) -> Optional[str]:
        """Detect ATS from career or job URL."""
        if not url:
            return None
        lowered = url.lower()
        for ats_name, patterns in cls.PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lowered):
                    return ats_name
        return None

    @classmethod
    def detect_from_html(cls, html: str) -> Optional[str]:
        """Detect ATS signatures embedded in HTML (iframes, links, scripts)."""
        if not html:
            return None
        lowered = html.lower()
        for ats_name, patterns in cls.PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lowered):
                    return ats_name
        return None

    @classmethod
    def detect(cls, url: str, html: Optional[str] = None) -> str:
        """Combined detection with fallback to 'custom' or 'unknown'."""
        detected = cls.detect_from_url(url)
        if detected:
            return detected
        if html:
            detected = cls.detect_from_html(html)
            if detected:
                return detected
        return "custom"


class TargetCompanyManager:
    """Manages target company registry, synchronization between YAML and DB."""

    def __init__(self, yaml_path: str = "companies.yaml"):
        self.yaml_path = yaml_path

    def load_from_yaml(self) -> List[Dict[str, Any]]:
        """Load company definitions from companies.yaml."""
        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("companies", []) if data else []
        except FileNotFoundError:
            logger.warning(f"File {self.yaml_path} not found.")
            return []
        except Exception as e:
            logger.error(f"Error reading {self.yaml_path}: {e}")
            return []

    def sync_to_db(self, session: Session) -> List[Company]:
        """Syncs companies from YAML into SQLite database table."""
        companies_data = self.load_from_yaml()
        synced_records = []

        for item in companies_data:
            name = item.get("name")
            if not name:
                continue

            existing = session.query(Company).filter(Company.name == name).first()
            if existing:
                existing.domain = item.get("domain", existing.domain)
                existing.careers_url = item.get("careers_url", existing.careers_url)
                existing.ats = item.get("ats", existing.ats) or "unknown"
                existing.priority = item.get("priority", existing.priority) or "medium"
                synced_records.append(existing)
            else:
                new_comp = Company(
                    name=name,
                    domain=item.get("domain"),
                    careers_url=item.get("careers_url"),
                    ats=item.get("ats") or "unknown",
                    priority=item.get("priority", "medium"),
                )
                session.add(new_comp)
                synced_records.append(new_comp)

        session.commit()
        return synced_records

    def get_companies(self, session: Session, priority: Optional[str] = None) -> List[Company]:
        """Query target companies from database with optional priority filter."""
        query = session.query(Company)
        if priority:
            query = query.filter(Company.priority == priority.lower())
        return query.all()


class GreenhouseParser:
    """
    Parses jobs from Greenhouse boards.
    Supports either Greenhouse public API or board URLs.
    API: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    """

    @staticmethod
    def extract_board_token(url: str) -> Optional[str]:
        """Extracts greenhouse board token from URL."""
        if not url:
            return None
        # e.g., boards.greenhouse.io/openai or job-boards.greenhouse.io/datadog or ?for=token
        m = re.search(r"greenhouse\.io(?:/embed/job_board)?/(?:jobs/)?([a-zA-Z0-9_\-]+)", url)
        if m:
            token = m.group(1)
            if token not in ("embed", "jobs", "job_board", "api"):
                return token
        query_m = re.search(r"[?&]for=([a-zA-Z0-9_\-]+)", url)
        if query_m:
            return query_m.group(1)
        return None

    @classmethod
    def fetch_jobs(
        cls,
        company_name: str,
        careers_url: str,
        headers: Dict[str, str],
        timeout: int = 15,
    ) -> List[JobPosting]:
        postings: List[JobPosting] = []
        token = cls.extract_board_token(careers_url)

        if token:
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
            try:
                resp = requests.get(api_url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_jobs = data.get("jobs", [])
                    for item in raw_jobs:
                        title = item.get("title", "").strip()
                        job_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{token}/jobs/{item.get('id')}"
                        location_obj = item.get("location", {})
                        location = location_obj.get("name", "Remote") if isinstance(location_obj, dict) else str(location_obj)
                        content_html = item.get("content", "")
                        desc = BaseSearcher.clean_html(content_html) if content_html else title

                        # Determine remote type
                        remote_type = "Remote" if "remote" in f"{title} {location}".lower() else "Onsite"

                        postings.append(
                            JobPosting(
                                title=title,
                                company=company_name,
                                location=location,
                                remote_type=remote_type,
                                portal="company_ats",
                                job_url=job_url,
                                description=desc,
                                tags=["greenhouse", "direct_ats"],
                            )
                        )
                    return postings
            except Exception as e:
                logger.warning(f"Greenhouse API fetch failed for {token}: {e}")

        # Fallback HTML scraping
        try:
            resp = requests.get(careers_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                postings.extend(cls.parse_html(resp.text, company_name, careers_url))
        except Exception as e:
            logger.error(f"Greenhouse HTML fetch failed for {careers_url}: {e}")

        return postings

    @staticmethod
    def parse_html(html: str, company_name: str, base_url: str) -> List[JobPosting]:
        postings = []
        # Pattern for greenhouse job links: <a href=".../jobs/12345...">Job Title</a>
        matches = re.findall(
            r'<a[^>]+href=["\']([^"\']*/jobs/([0-9]+)[^"\']*)["\'][^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        seen_urls = set()
        for href, job_id, inner_html in matches:
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            title = BaseSearcher.clean_html(inner_html).strip()
            if not title or len(title) < 2:
                continue
            postings.append(
                JobPosting(
                    title=title,
                    company=company_name,
                    location="Remote",
                    remote_type="Remote" if "remote" in title.lower() else "Onsite",
                    portal="company_ats",
                    job_url=full_url,
                    description=f"Greenhouse job opening at {company_name}: {title}",
                    tags=["greenhouse", "direct_ats"],
                )
            )
        return postings


class LeverParser:
    """
    Parses jobs from Lever boards.
    Supports Lever postings public API: https://api.lever.co/v0/postings/{site}
    """

    @staticmethod
    def extract_site(url: str) -> Optional[str]:
        """Extracts lever site name from URL."""
        if not url:
            return None
        m = re.search(r"lever\.co/([a-zA-Z0-9_\-]+)", url)
        if m:
            site = m.group(1)
            if site not in ("v0", "postings", "apply"):
                return site
        return None

    @classmethod
    def fetch_jobs(
        cls,
        company_name: str,
        careers_url: str,
        headers: Dict[str, str],
        timeout: int = 15,
    ) -> List[JobPosting]:
        postings: List[JobPosting] = []
        site = cls.extract_site(careers_url)

        if site:
            api_url = f"https://api.lever.co/v0/postings/{site}?mode=json"
            try:
                resp = requests.get(api_url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data:
                        title = item.get("text", "").strip()
                        job_url = item.get("hostedUrl") or item.get("applyUrl") or ""
                        categories = item.get("categories", {})
                        location = categories.get("location", "Remote") if isinstance(categories, dict) else "Remote"
                        desc_plain = item.get("descriptionPlain") or BaseSearcher.clean_html(item.get("description", ""))
                        
                        # Check workplaceType or remote
                        workplace = categories.get("workplaceType", "").lower() if isinstance(categories, dict) else ""
                        is_remote = "remote" in workplace or "remote" in f"{title} {location}".lower()
                        remote_type = "Remote" if is_remote else "Onsite"

                        postings.append(
                            JobPosting(
                                title=title,
                                company=company_name,
                                location=location or "Remote",
                                remote_type=remote_type,
                                portal="company_ats",
                                job_url=job_url,
                                description=desc_plain or f"{title} at {company_name}",
                                tags=["lever", "direct_ats"],
                            )
                        )
                    return postings
            except Exception as e:
                logger.warning(f"Lever API fetch failed for {site}: {e}")

        # HTML fallback
        try:
            resp = requests.get(careers_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                postings.extend(cls.parse_html(resp.text, company_name, careers_url))
        except Exception as e:
            logger.error(f"Lever HTML fetch failed for {careers_url}: {e}")

        return postings

    @staticmethod
    def parse_html(html: str, company_name: str, base_url: str) -> List[JobPosting]:
        postings = []
        # Lever posting link pattern: href="https://jobs.lever.co/anthropic/uuid"
        matches = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:jobs\.lever\.co/[^/]+/[0-9a-f\-]+)[^"\']*)["\'][^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        seen_urls = set()
        for href, inner_html in matches:
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            title = BaseSearcher.clean_html(inner_html).strip()
            if not title or len(title) < 2:
                continue
            postings.append(
                JobPosting(
                    title=title,
                    company=company_name,
                    location="Remote",
                    remote_type="Remote" if "remote" in title.lower() else "Onsite",
                    portal="company_ats",
                    job_url=full_url,
                    description=f"Lever job opening at {company_name}: {title}",
                    tags=["lever", "direct_ats"],
                )
            )
        return postings


class AshbyParser:
    """
    Parses jobs from Ashby boards.
    Supports Ashby posting public API or HTML scraping.
    API: https://api.ashbyhq.com/posting-api/job-board/{board_name}
    """

    @staticmethod
    def extract_board_name(url: str) -> Optional[str]:
        """Extracts ashby board name from URL."""
        if not url:
            return None
        m = re.search(r"ashbyhq\.com/([a-zA-Z0-9_\-]+)", url)
        if m:
            board = m.group(1)
            if board not in ("api", "posting-api"):
                return board
        return None

    @classmethod
    def fetch_jobs(
        cls,
        company_name: str,
        careers_url: str,
        headers: Dict[str, str],
        timeout: int = 15,
    ) -> List[JobPosting]:
        postings: List[JobPosting] = []
        board = cls.extract_board_name(careers_url)

        if board:
            api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
            try:
                resp = requests.get(api_url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    jobs_list = data.get("jobs", [])
                    for item in jobs_list:
                        title = item.get("title", "").strip()
                        job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{board}/{item.get('id')}"
                        location = item.get("location", "Remote")
                        is_remote = item.get("isRemote", False) or "remote" in f"{title} {location}".lower()
                        remote_type = "Remote" if is_remote else "Onsite"
                        desc = BaseSearcher.clean_html(item.get("descriptionHtml", ""))

                        compensation = item.get("compensation")
                        salary_range = None
                        if compensation and isinstance(compensation, dict):
                            summary = compensation.get("compensationSummary")
                            if summary:
                                salary_range = str(summary)

                        postings.append(
                            JobPosting(
                                title=title,
                                company=company_name,
                                location=location,
                                remote_type=remote_type,
                                portal="company_ats",
                                job_url=job_url,
                                description=desc or f"{title} at {company_name}",
                                salary_range=salary_range,
                                tags=["ashby", "direct_ats"],
                            )
                        )
                    return postings
            except Exception as e:
                logger.warning(f"Ashby API fetch failed for {board}: {e}")

        # HTML fallback
        try:
            resp = requests.get(careers_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                postings.extend(cls.parse_html(resp.text, company_name, careers_url))
        except Exception as e:
            logger.error(f"Ashby HTML fetch failed for {careers_url}: {e}")

        return postings

    @staticmethod
    def parse_html(html: str, company_name: str, base_url: str) -> List[JobPosting]:
        postings = []
        matches = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:jobs\.ashbyhq\.com/[^/]+/[0-9a-f\-]+)[^"\']*)["\'][^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        seen_urls = set()
        for href, inner_html in matches:
            full_url = urljoin(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            title = BaseSearcher.clean_html(inner_html).strip()
            if not title or len(title) < 2:
                continue
            postings.append(
                JobPosting(
                    title=title,
                    company=company_name,
                    location="Remote",
                    remote_type="Remote" if "remote" in title.lower() else "Onsite",
                    portal="company_ats",
                    job_url=full_url,
                    description=f"Ashby job opening at {company_name}: {title}",
                    tags=["ashby", "direct_ats"],
                )
            )
        return postings


class GenericCareerParser:
    """
    Fallback parser for custom / unmanaged career pages.
    Finds job-like anchors matching keywords (e.g. engineer, developer, designer, manager).
    """

    JOB_KEYWORDS = [
        "engineer",
        "developer",
        "architect",
        "designer",
        "product",
        "data",
        "scientist",
        "devops",
        "manager",
        "lead",
        "analyst",
        "director",
        "intern",
    ]

    @classmethod
    def parse_html(cls, html: str, company_name: str, base_url: str) -> List[JobPosting]:
        postings: List[JobPosting] = []
        # Match links that have job-like keywords in text or href
        link_pattern = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        seen = set()

        for href, inner in link_pattern.findall(html):
            clean_text = BaseSearcher.clean_html(inner).strip()
            if not clean_text or len(clean_text) < 4 or len(clean_text) > 120:
                continue

            lowered_text = clean_text.lower()
            lowered_href = href.lower()

            # Must contain at least one job keyword in title and look like a career/job link
            is_job_title = any(kw in lowered_text for kw in cls.JOB_KEYWORDS)
            is_career_link = any(kw in lowered_href for kw in ["job", "career", "position", "opening", "role"]) or is_job_title

            if is_job_title and is_career_link:
                full_url = urljoin(base_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)

                postings.append(
                    JobPosting(
                        title=clean_text,
                        company=company_name,
                        location="Remote",
                        remote_type="Remote" if "remote" in lowered_text else "Onsite",
                        portal="company_ats",
                        job_url=full_url,
                        description=f"Direct opening at {company_name}: {clean_text}",
                        tags=["custom_career_page", "direct_ats"],
                    )
                )

        return postings


class CompanyCrawler(BaseSearcher):
    """
    Orchestrates target company career page crawling and ATS extraction.
    """

    name: str = "company_ats"

    def __init__(
        self,
        target_manager: Optional[TargetCompanyManager] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(headers=headers)
        self.target_manager = target_manager or TargetCompanyManager()

    def discover_careers_url(self, domain: str) -> Optional[str]:
        """
        Attempts to discover careers URL for a domain (e.g. careers.domain.com, domain.com/careers).
        """
        if not domain:
            return None
        clean_domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")
        candidates = [
            f"https://{clean_domain}/careers",
            f"https://{clean_domain}/jobs",
            f"https://careers.{clean_domain}",
            f"https://jobs.{clean_domain}",
        ]
        for url in candidates:
            try:
                resp = requests.head(url, headers=self.headers, timeout=5, allow_redirects=True)
                if resp.status_code in (200, 301, 302, 307, 308):
                    return resp.url or url
            except Exception:
                continue
        return None

    def crawl_company(self, company: Company, limit_per_company: int = 50) -> List[JobPosting]:
        """
        Crawls a single company based on its ATS signature and careers URL.
        """
        careers_url = company.careers_url
        if not careers_url and company.domain:
            careers_url = self.discover_careers_url(company.domain)
            if careers_url:
                company.careers_url = careers_url

        if not careers_url:
            logger.warning(f"No careers URL discovered for company {company.name}")
            return []

        # Detect ATS if unknown or custom
        ats_type = (company.ats or "").lower()
        if ats_type in ("unknown", "", "custom"):
            detected = ATSSignatureDetector.detect_from_url(careers_url)
            if detected:
                ats_type = detected
                company.ats = detected

        postings: List[JobPosting] = []

        if ats_type == "greenhouse":
            postings = GreenhouseParser.fetch_jobs(company.name, careers_url, self.headers)
        elif ats_type == "lever":
            postings = LeverParser.fetch_jobs(company.name, careers_url, self.headers)
        elif ats_type == "ashby":
            postings = AshbyParser.fetch_jobs(company.name, careers_url, self.headers)
        else:
            # Custom / SmartRecruiters / Workday / Generic fallback
            try:
                resp = requests.get(careers_url, headers=self.headers, timeout=15)
                if resp.status_code == 200:
                    html_detected = ATSSignatureDetector.detect_from_html(resp.text)
                    if html_detected == "greenhouse":
                        postings = GreenhouseParser.fetch_jobs(company.name, careers_url, self.headers)
                    elif html_detected == "lever":
                        postings = LeverParser.fetch_jobs(company.name, careers_url, self.headers)
                    elif html_detected == "ashby":
                        postings = AshbyParser.fetch_jobs(company.name, careers_url, self.headers)
                    else:
                        postings = GenericCareerParser.parse_html(resp.text, company.name, careers_url)
            except Exception as e:
                logger.error(f"Failed crawling generic career page for {company.name}: {e}")

        # Update last crawled timestamp and active jobs count
        company.last_crawled_at = datetime.now(timezone.utc)
        company.active_jobs_count = len(postings)

        return postings[:limit_per_company]

    def crawl_all(
        self,
        session: Session,
        priority: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        limit_per_company: int = 50,
    ) -> List[JobPosting]:
        """
        Crawls all target companies from database, saves newly discovered jobs to DB,
        and returns the list of discovered JobPosting instances.
        """
        companies = self.target_manager.get_companies(session, priority=priority)
        all_postings: List[JobPosting] = []

        for comp in companies:
            postings = self.crawl_company(comp, limit_per_company=limit_per_company)

            # Filter by keywords if specified
            if keywords:
                kw_lower = [k.lower() for k in keywords]
                filtered = []
                for p in postings:
                    content_to_check = f"{p.title} {p.description}".lower()
                    if any(k in content_to_check for k in kw_lower):
                        filtered.append(p)
                postings = filtered

            for p in postings:
                # Deduplicate against database
                existing = session.query(Job).filter(Job.job_url == p.job_url).first()
                if not existing:
                    job_model = p.to_job_model()
                    session.add(job_model)
                all_postings.append(p)

        session.commit()
        return all_postings

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        """
        Implements BaseSearcher interface using YAML companies.
        """
        from Guffy.core.database import get_db_manager

        db_manager = get_db_manager()
        for session in db_manager.get_session():
            self.target_manager.sync_to_db(session)
            return self.crawl_all(session, keywords=keywords, limit_per_company=limit)[:limit]
        return []
