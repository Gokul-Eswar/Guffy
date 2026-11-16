"""
Dice and Glassdoor Tech Aggregator Searchers (Ticket 7)

Provides:
- DiceSearcher: Searches tech jobs on Dice using public API / board queries.
- GlassdoorSearcher: Standardizes Glassdoor job search parsing.
"""

import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus
import requests
from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class DiceSearcher(BaseSearcher):
    """
    Searcher for technology and engineering positions on Dice.com.
    """

    name: str = "dice"
    BASE_API_URL: str = "https://application.dice.com/api/jobsearch/paged"
    BASE_SEARCH_URL: str = "https://www.dice.com/jobs"

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        kw_str = " ".join(keywords) if keywords else "software engineer"
        loc_str = locations[0] if locations else "Remote"

        # Dice query format
        payload = {
            "q": kw_str,
            "location": loc_str,
            "pageSize": limit,
            "filters": {
                "workplaceTypes": ["Remote"],
            },
        }

        try:
            # First attempt public JSON endpoint
            resp = requests.post(
                "https://job-search-api.dice.com/v1/jobs/search",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", []) or data.get("jobListings", [])
                for item in items:
                    title = item.get("title")
                    company = item.get("companyName") or item.get("company", {}).get("name")
                    detail_url = item.get("detailUrl") or f"https://www.dice.com/job-detail/{item.get('id')}"
                    location = item.get("summaryLocation", "Remote")
                    salary = item.get("salary")
                    easy_apply = item.get("isEasyApply", False) or item.get("easyApply", False)

                    if title and company:
                        results.append(
                            JobPosting(
                                title=title,
                                company=company,
                                location=location,
                                remote_type="Remote",
                                portal="dice",
                                job_url=detail_url,
                                description=f"Dice technology role: {title} at {company}",
                                salary_range=str(salary) if salary else None,
                                easy_apply=bool(easy_apply),
                                tags=["dice", "tech_only"],
                            )
                        )
                if results:
                    return results[:limit]
        except Exception as e:
            logger.debug(f"Dice API error: {e}")

        # Fallback HTML scraping
        url = f"{self.BASE_SEARCH_URL}?q={quote_plus(kw_str)}&location={quote_plus(loc_str)}&filters.workplaceTypes=Remote"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                results.extend(self.parse_html(resp.text, limit=limit))
        except Exception as e:
            logger.error(f"Dice HTML error: {e}")

        return results[:limit]

    def parse_html(self, html: str, limit: int = 25) -> List[JobPosting]:
        postings: List[JobPosting] = []
        # Look for dice card elements
        card_matches = re.finditer(
            r'<dhi-search-card[^>]*>(.*?)</dhi-search-card>|<div[^>]+class=["\'][^"\']*card-title-link[^"\']*["\'][^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        # Also search for link patterns /job-detail/
        link_matches = re.findall(
            r'<a[^>]+href=["\']([^"\']*/job-detail/[^"\'?]+)[^"\']*["\'][^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        seen = set()
        for href, inner in link_matches:
            full_url = href if href.startswith("http") else f"https://www.dice.com{href}"
            if full_url in seen:
                continue
            seen.add(full_url)
            title = self.clean_html(inner).strip()
            if not title or len(title) < 3:
                continue

            postings.append(
                JobPosting(
                    title=title,
                    company="Dice Employer",
                    location="Remote",
                    remote_type="Remote",
                    portal="dice",
                    job_url=full_url,
                    description=f"Dice tech position: {title}",
                    tags=["dice", "tech_only"],
                )
            )
            if len(postings) >= limit:
                break

        return postings


class GlassdoorSearcher(BaseSearcher):
    """
    Searcher for Glassdoor job listings with salary and review insights.
    """

    name: str = "glassdoor"
    BASE_URL: str = "https://www.glassdoor.com/Job/jobs.htm"

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        kw_str = " ".join(keywords) if keywords else "software engineer"
        loc_str = locations[0] if locations else "Remote"

        url = f"{self.BASE_URL}?sc.keyword={quote_plus(kw_str)}&locT=C&locId=1147401&remoteWorkType=1"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                results.extend(self.parse_html(resp.text, limit=limit))
        except Exception as e:
            logger.error(f"Glassdoor query error: {e}")

        return results[:limit]

    def parse_html(self, html: str, limit: int = 25) -> List[JobPosting]:
        postings: List[JobPosting] = []

        # Try Apollo cache state / JSON
        json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                apollo = data.get("props", {}).get("pageProps", {}).get("apolloCache", {})
                for key, val in apollo.items():
                    if key.startswith("JobListing:") and isinstance(val, dict):
                        header = val.get("jobview", {}).get("header", {})
                        title = header.get("jobTitleText")
                        employer = header.get("employer", {}).get("name")
                        location = header.get("locationName", "Remote")
                        job_id = val.get("jobListingId")
                        if title and employer and job_id:
                            postings.append(
                                JobPosting(
                                    title=title,
                                    company=employer,
                                    location=location,
                                    remote_type="Remote",
                                    portal="glassdoor",
                                    job_url=f"https://www.glassdoor.com/partner/jobListing.htm?pos=101&jobListingId={job_id}",
                                    description=f"Glassdoor posting: {title} at {employer}",
                                    tags=["glassdoor"],
                                )
                            )
                if postings:
                    return postings[:limit]
            except Exception as e:
                logger.debug(f"Glassdoor Next.js parse error: {e}")

        # Regex fallback
        matches = re.finditer(
            r'<a[^>]+href=["\']([^"\']*(?:/partner/jobListing\.htm\?[^"\']*jobListingId=[0-9]+|/job-listing/[^"\'?]+)[^"\']*)["\'][^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        seen = set()
        for m in matches:
            href = m.group(1)
            title = self.clean_html(m.group(2)).strip()
            full_url = href if href.startswith("http") else f"https://www.glassdoor.com{href}"
            if full_url in seen or not title or len(title) < 3:
                continue
            seen.add(full_url)

            postings.append(
                JobPosting(
                    title=title,
                    company="Glassdoor Employer",
                    location="Remote",
                    remote_type="Remote",
                    portal="glassdoor",
                    job_url=full_url,
                    description=f"Glassdoor position: {title}",
                    tags=["glassdoor"],
                )
            )
            if len(postings) >= limit:
                break

        return postings
