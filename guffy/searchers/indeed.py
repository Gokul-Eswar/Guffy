"""
Indeed Job Searcher with Quick Apply Detection (Ticket 7)

Queries Indeed job search endpoints and parses job postings,
company names, locations, estimated salary, and 'Easily apply' indicators.
"""

import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin
import requests
from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class IndeedSearcher(BaseSearcher):
    """
    Searcher for Indeed job listings with Quick Apply / Easily apply detection.
    """

    name: str = "indeed"
    BASE_URL: str = "https://www.indeed.com/jobs"

    def __init__(self, headers: Optional[Dict[str, str]] = None):
        super().__init__(headers=headers)
        self.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.indeed.com/",
        })

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
        remote_only: bool = True,
        quick_apply_only: bool = False,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        kw_str = " ".join(keywords) if keywords else "software engineer"
        loc_str = locations[0] if locations else ("Remote" if remote_only else "")

        params = [
            f"q={quote_plus(kw_str)}",
            f"l={quote_plus(loc_str)}",
            "sort=date",
        ]
        if remote_only and "remote" not in loc_str.lower():
            params.append("sc=0kf%3Aattr%28DSQF7%29%3B")  # Indeed filter for Remote

        url = f"{self.BASE_URL}?{'&'.join(params)}"

        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                results.extend(self.parse_html(resp.text, limit=limit))
            else:
                logger.warning(f"Indeed search returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"Error querying Indeed: {e}")

        if quick_apply_only:
            results = [j for j in results if j.easy_apply]

        return results[:limit]

    def parse_html(self, html: str, limit: int = 25) -> List[JobPosting]:
        """
        Parses Indeed mosaic job cards / HTML structures.
        """
        postings: List[JobPosting] = []

        # Check for window._initialData or mosaic-provider-jobcards
        json_match = re.search(r'window\._initialData\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                job_cards = (
                    data.get("jobCards", [])
                    or data.get("results", [])
                    or data.get("metaData", {}).get("mosaicProviderJobCardsModel", {}).get("results", [])
                )
                for item in job_cards:
                    title = item.get("displayTitle") or item.get("title")
                    company = item.get("company")
                    jobkey = item.get("jobkey")
                    location = item.get("formattedLocation", "Remote")
                    salary = item.get("estimatedSalary", {}).get("formatted") or item.get("salary", {}).get("formatted")
                    quick_apply = item.get("indeedApplyEnabled", False) or item.get("isEasilyApplyable", False)

                    if title and jobkey:
                        job_url = f"https://www.indeed.com/viewjob?jk={jobkey}"
                        postings.append(
                            JobPosting(
                                title=title,
                                company=company or "Confidential",
                                location=location,
                                remote_type="Remote" if "remote" in f"{title} {location}".lower() else "Onsite",
                                portal="indeed",
                                job_url=job_url,
                                description=f"Indeed position: {title} at {company}",
                                salary_range=str(salary) if salary else None,
                                easy_apply=bool(quick_apply),
                                tags=["indeed", "quick_apply" if quick_apply else "standard_apply"],
                            )
                        )
                if postings:
                    return postings[:limit]
            except Exception as e:
                logger.debug(f"Could not parse window._initialData from Indeed: {e}")

        # Regex card parsing fallback
        # Indeed card container typically has class containing job_seen_beacon or tapItem or cardOutline
        card_chunks = re.split(r'<div[^>]+class=["\'][^"\']*(?:job_seen_beacon|tapItem|resultContent)[^"\']*["\']', html)
        seen = set()

        for chunk in card_chunks:
            if not chunk.strip():
                continue

            # Link or jk
            jk_match = re.search(r'data-jk=["\']([a-zA-Z0-9]+)["\']', chunk)
            url_match = re.search(r'href=["\'](/viewjob\?jk=[a-zA-Z0-9]+|/rc/clk\?jk=[a-zA-Z0-9]+)[^"\']*["\']', chunk)

            if jk_match:
                job_url = f"https://www.indeed.com/viewjob?jk={jk_match.group(1)}"
            elif url_match:
                job_url = f"https://www.indeed.com{url_match.group(1)}"
            else:
                continue

            if job_url in seen:
                continue

            # Title
            title_m = re.search(
                r'<(?:h2|span|a)[^>]+class=["\'][^"\']*(?:jobTitle|heading)[^"\']*["\'][^>]*>(.*?)</(?:h2|span|a)>',
                chunk,
                re.DOTALL | re.IGNORECASE,
            )
            title = self.clean_html(title_m.group(1)).strip() if title_m else ""

            # Company
            comp_m = re.search(
                r'<span[^>]+class=["\'][^"\']*(?:companyName|company_location)[^"\']*["\'][^>]*>(.*?)</span>',
                chunk,
                re.DOTALL | re.IGNORECASE,
            )
            company = self.clean_html(comp_m.group(1)).strip() if comp_m else ""

            # Location
            loc_m = re.search(
                r'<div[^>]+class=["\'][^"\']*(?:companyLocation)[^"\']*["\'][^>]*>(.*?)</div>',
                chunk,
                re.DOTALL | re.IGNORECASE,
            )
            location = self.clean_html(loc_m.group(1)).strip() if loc_m else "Remote"

            # Quick Apply / Easily apply flag
            quick_apply = bool(re.search(r'Easily apply|iaIcon|indeedApply', chunk, re.IGNORECASE))

            # Salary
            salary_m = re.search(
                r'<div[^>]+class=["\'][^"\']*(?:salary-snippet-container|metadata)[^"\']*["\'][^>]*>(.*?)</div>',
                chunk,
                re.DOTALL | re.IGNORECASE,
            )
            salary = self.clean_html(salary_m.group(1)).strip() if salary_m else None

            if not title or not company:
                continue

            seen.add(job_url)
            remote_type = "Remote" if "remote" in f"{title} {location}".lower() else "Onsite"

            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    remote_type=remote_type,
                    portal="indeed",
                    job_url=job_url,
                    description=f"{title} at {company}. Location: {location}",
                    salary_range=salary,
                    easy_apply=quick_apply,
                    tags=["indeed", "quick_apply" if quick_apply else "standard_apply"],
                )
            )
            if len(postings) >= limit:
                break

        return postings
