"""
LinkedIn Job Searcher with Easy Apply Detection (Ticket 7)

Queries LinkedIn public job search endpoints / guest job search API.
URL: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
"""

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin
import requests
from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class LinkedInSearcher(BaseSearcher):
    """
    Discovers job openings from LinkedIn public search endpoints.
    Detects easy_apply, location, seniority, and extracts clean job descriptions.
    """

    name: str = "linkedin"
    BASE_SEARCH_URL: str = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    BASE_JOB_URL: str = "https://www.linkedin.com/jobs/view/"

    def __init__(self, headers: Optional[Dict[str, str]] = None):
        super().__init__(headers=headers)
        self.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.linkedin.com/jobs",
        })

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
        remote_only: bool = True,
        easy_apply_only: bool = False,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        kw_query = " ".join(keywords) if keywords else "software engineer"
        loc_query = locations[0] if locations else "United States"

        # f_WT=2 is LinkedIn filter for Remote, f_AL=true is Easy Apply
        params = [
            f"keywords={quote_plus(kw_query)}",
            f"location={quote_plus(loc_query)}",
            "start=0",
        ]
        if remote_only:
            params.append("f_WT=2")
        if easy_apply_only:
            params.append("f_AL=true")

        query_url = f"{self.BASE_SEARCH_URL}?{'&'.join(params)}"

        try:
            resp = requests.get(query_url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                results.extend(self.parse_search_html(resp.text, limit=limit))
            else:
                logger.warning(f"LinkedIn search returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"Error querying LinkedIn: {e}")

        return results[:limit]

    def parse_search_html(self, html: str, limit: int = 25) -> List[JobPosting]:
        """
        Parses LinkedIn guest search HTML snippets containing <li> cards or <div> job cards.
        """
        postings: List[JobPosting] = []
        # Pattern to capture job card containers or anchors
        # LinkedIn guest jobs HTML structure:
        # <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/123456789...">
        # <h3 class="base-search-card__title"> Title </h3>
        # <h4 class="base-search-card__subtitle"><a ...>Company</a></h4>
        # <span class="job-search-card__location">Location</span>
        
        # We can split by <li> or <div class="base-card
        cards = re.split(r'<li[^>]*>|<div[^>]+class=["\'][^"\']*base-card[^"\']*["\']', html)
        seen_urls = set()

        for card in cards:
            if not card.strip():
                continue

            # Extract job url
            url_match = re.search(r'href=["\'](https://[a-z]{2,3}\.linkedin\.com/jobs/view/[^"\'?]+)', card)
            if not url_match:
                url_match = re.search(r'href=["\'](/jobs/view/[^"\'?]+)', card)
                if url_match:
                    full_url = f"https://www.linkedin.com{url_match.group(1)}"
                else:
                    continue
            else:
                full_url = url_match.group(1)

            if full_url in seen_urls:
                continue

            # Extract title
            title_match = re.search(
                r'<(?:h3|span)[^>]+class=["\'][^"\']*(?:base-search-card__title|job-title)[^"\']*["\'][^>]*>(.*?)</(?:h3|span)>',
                card,
                re.DOTALL | re.IGNORECASE,
            )
            title = self.clean_html(title_match.group(1)).strip() if title_match else ""

            # Extract company
            company_match = re.search(
                r'<(?:h4|span|a)[^>]+class=["\'][^"\']*(?:base-search-card__subtitle|job-search-card__company-name)[^"\']*["\'][^>]*>(.*?)</(?:h4|span|a)>',
                card,
                re.DOTALL | re.IGNORECASE,
            )
            company = self.clean_html(company_match.group(1)).strip() if company_match else ""

            # Extract location
            loc_match = re.search(
                r'<span[^>]+class=["\'][^"\']*(?:job-search-card__location)[^"\']*["\'][^>]*>(.*?)</span>',
                card,
                re.DOTALL | re.IGNORECASE,
            )
            location = self.clean_html(loc_match.group(1)).strip() if loc_match else "Remote"

            # Easy Apply flag
            easy_apply = bool(re.search(r'Easy Apply|job-search-card__easy-apply-label', card, re.IGNORECASE))

            # Salary range if listed
            salary_match = re.search(
                r'<span[^>]+class=["\'][^"\']*(?:job-search-card__salary-info)[^"\']*["\'][^>]*>(.*?)</span>',
                card,
                re.DOTALL | re.IGNORECASE,
            )
            salary = self.clean_html(salary_match.group(1)).strip() if salary_match else None

            if not title or not company:
                continue

            seen_urls.add(full_url)
            remote_type = "Remote" if "remote" in f"{title} {location}".lower() else "Onsite"

            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location or "Remote",
                    remote_type=remote_type,
                    portal="linkedin",
                    job_url=full_url,
                    description=f"{title} position at {company}. Location: {location}",
                    salary_range=salary,
                    easy_apply=easy_apply,
                    tags=["linkedin", "easy_apply" if easy_apply else "standard_apply"],
                )
            )
            if len(postings) >= limit:
                break

        return postings
