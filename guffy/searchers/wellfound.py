"""
Wellfound (formerly AngelList Talent) Searcher (Ticket 7)

Extracts high-growth startup openings, founding engineer roles,
and tech opportunities from Wellfound public boards and search endpoints.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import requests
from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class WellfoundSearcher(BaseSearcher):
    """
    Searcher for startup jobs on Wellfound (AngelList Talent).
    Parses startup job listings, equity/salary compensation info, and direct pitch apply links.
    """

    name: str = "wellfound"
    BASE_URL: str = "https://wellfound.com/jobs"

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        kw = "-".join(keywords).lower() if keywords else "software-engineer"
        # Standard wellfound URL pattern: https://wellfound.com/role/l/remote/{role}
        url = f"https://wellfound.com/role/l/remote/{kw}"

        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                results.extend(self.parse_html(resp.text, limit=limit))
            else:
                logger.warning(f"Wellfound returned status {resp.status_code}")
        except Exception as e:
            logger.error(f"Error querying Wellfound: {e}")

        return results[:limit]

    def parse_html(self, html: str, limit: int = 25) -> List[JobPosting]:
        """
        Parses Next.js JSON state (__NEXT_DATA__) or HTML markup from Wellfound.
        """
        postings: List[JobPosting] = []

        # Try extracting Next.js hydration data first
        next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if next_data_match:
            try:
                data = json.loads(next_data_match.group(1))
                props = data.get("props", {}).get("pageProps", {})
                job_listings = props.get("jobListings", []) or props.get("listings", [])
                for item in job_listings:
                    title = item.get("title") or item.get("jobTitle")
                    startup = item.get("startup", {}) or item.get("company", {})
                    company = startup.get("name") if isinstance(startup, dict) else "Startup"
                    slug = item.get("slug") or item.get("id")
                    job_url = f"https://wellfound.com/jobs/{slug}" if slug else "https://wellfound.com/jobs"
                    location = item.get("locationVal", "Remote")
                    salary_str = item.get("compensation") or item.get("salary")

                    if title and company:
                        postings.append(
                            JobPosting(
                                title=title,
                                company=company,
                                location=str(location),
                                remote_type="Remote",
                                portal="wellfound",
                                job_url=job_url,
                                description=f"Wellfound Startup role: {title} at {company}",
                                salary_range=str(salary_str) if salary_str else None,
                                easy_apply=True,  # Wellfound pitch apply
                                tags=["wellfound", "startup", "equity"],
                            )
                        )
                if postings:
                    return postings[:limit]
            except Exception as e:
                logger.debug(f"Could not parse Next.js data from Wellfound: {e}")

        # Fallback HTML scraping
        # Wellfound cards typically have links to /jobs/... or /company/.../jobs/...
        job_card_matches = re.finditer(
            r'<div[^>]+class=["\'][^"\']*(?:styles_jobListing|job-listing|styles_component)[^"\']*["\'][^>]*>(.*?)</div>\s*</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        seen = set()
        for m in job_card_matches:
            card_html = m.group(1)
            link_m = re.search(r'href=["\'](/jobs/[^"\'?]+|/company/[^/]+/jobs/[^"\'?]+)["\']', card_html)
            title_m = re.search(r'<(?:h2|h3|a)[^>]+class=["\'][^"\']*(?:title|roleTitle)[^"\']*["\'][^>]*>(.*?)</(?:h2|h3|a)>', card_html, re.DOTALL)
            company_m = re.search(r'<(?:h3|h4|span|a)[^>]+class=["\'][^"\']*(?:companyName|name)[^"\']*["\'][^>]*>(.*?)</(?:h3|h4|span|a)>', card_html, re.DOTALL)

            if link_m and title_m:
                full_url = f"https://wellfound.com{link_m.group(1)}"
                if full_url in seen:
                    continue
                seen.add(full_url)
                title = self.clean_html(title_m.group(1)).strip()
                company = self.clean_html(company_m.group(1)).strip() if company_m else "Startup"

                # Compensation / Equity
                comp_m = re.search(r'(\$\d+k?\s*-\s*\$\d+k?(?:[•·,\s]*\d+(\.\d+)?%?)?)', card_html, re.IGNORECASE)
                salary = comp_m.group(1).strip() if comp_m else None

                postings.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location="Remote",
                        remote_type="Remote",
                        portal="wellfound",
                        job_url=full_url,
                        description=f"Startup opening at {company}: {title}",
                        salary_range=salary,
                        easy_apply=True,
                        tags=["wellfound", "startup"],
                    )
                )
                if len(postings) >= limit:
                    break

        return postings
