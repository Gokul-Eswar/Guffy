"""
Job Discovery Engine: Remote Tech Portals (Ticket 5)

Implementations for:
- RemoteOKSearcher (RemoteOK JSON API / endpoints)
- WeWorkRemotelySearcher (WWR RSS & HTML feeds)
- YCStartupSearcher (Work at a Startup / Hacker News Who Is Hiring / YC discovery)
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import requests

from Guffy.searchers.base import BaseSearcher, JobPosting

logger = logging.getLogger(__name__)


class RemoteOKSearcher(BaseSearcher):
    """
    Discovers remote tech positions using RemoteOK's public JSON API.
    URL: https://remoteok.com/api
    """

    name: str = "remoteok"
    API_URL: str = "https://remoteok.com/api"

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        try:
            resp = requests.get(self.API_URL, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"RemoteOK API returned status {resp.status_code}")
                return results

            items = resp.json()
            # First item in remoteok API response is often metadata / legal notice
            if items and isinstance(items, list) and not isinstance(items[0], dict) or "legal" in str(items[0].get("id", "")):
                items = items[1:]
        except Exception as e:
            logger.error(f"Error fetching from RemoteOK: {e}")
            return results

        normalized_keywords = [k.strip().lower() for k in keywords if k.strip()]

        for item in items:
            if not isinstance(item, dict):
                continue

            title = item.get("position", "") or item.get("title", "")
            company = item.get("company", "")
            url = item.get("url", "")
            if not url and item.get("id"):
                url = f"https://remoteok.com/remote-jobs/{item.get('id')}"

            if not title or not company or not url:
                continue

            raw_desc = item.get("description", "")
            clean_desc = self.clean_html(raw_desc)
            tags = item.get("tags", []) or []

            # Check keyword match
            search_blob = f"{title} {clean_desc} {' '.join(tags)}".lower()
            if normalized_keywords and not any(kw in search_blob for kw in normalized_keywords):
                continue

            location = item.get("location", "") or "Remote"
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary_range = None
            if salary_min or salary_max:
                if salary_min and salary_max:
                    salary_range = f"${salary_min:,} - ${salary_max:,}"
                elif salary_min:
                    salary_range = f"${salary_min:,}+"
                else:
                    salary_range = f"Up to ${salary_max:,}"

            # RemoteOK jobs are remote by definition
            remote_type = "Remote"
            date_str = item.get("date")
            posted_at = None
            if date_str:
                try:
                    posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:
                    posted_at = None

            posting = JobPosting(
                title=title,
                company=company,
                location=location,
                remote_type=remote_type,
                portal=self.name,
                job_url=url,
                description=clean_desc,
                salary_range=salary_range,
                tags=tags if isinstance(tags, list) else [],
                posted_at=posted_at,
            )
            results.append(posting)

            if len(results) >= limit:
                break

        return results


class WeWorkRemotelySearcher(BaseSearcher):
    """
    Discovers remote positions from We Work Remotely (WWR) RSS feed.
    Feed: https://weworkremotely.com/categories/remote-programming-jobs.rss
    """

    name: str = "weworkremotely"
    RSS_URL: str = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

    def __init__(self, rss_url: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        super().__init__(headers=headers)
        self.rss_url = rss_url or self.RSS_URL

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        try:
            resp = requests.get(self.rss_url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"WWR RSS returned status {resp.status_code}")
                return results

            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.error(f"Error fetching/parsing WWR RSS: {e}")
            return results

        normalized_keywords = [k.strip().lower() for k in keywords if k.strip()]

        for item in root.findall(".//item"):
            title_node = item.find("title")
            raw_title = title_node.text if title_node is not None and title_node.text else ""
            
            # WWR title format is usually: "Company: Job Title"
            company = ""
            title = raw_title
            if ":" in raw_title:
                parts = raw_title.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip()

            link_node = item.find("link")
            job_url = link_node.text.strip() if link_node is not None and link_node.text else ""

            desc_node = item.find("description")
            raw_desc = desc_node.text if desc_node is not None and desc_node.text else ""
            clean_desc = self.clean_html(raw_desc)

            if not title or not job_url:
                continue

            # Category / Region tags
            tags = []
            for cat in item.findall("category"):
                if cat.text:
                    tags.append(cat.text.strip())

            # Keyword filtering
            search_blob = f"{title} {clean_desc} {' '.join(tags)}".lower()
            if normalized_keywords and not any(kw in search_blob for kw in normalized_keywords):
                continue

            # Date parsing
            pubdate_node = item.find("pubDate")
            posted_at = None
            if pubdate_node is not None and pubdate_node.text:
                try:
                    # RFC 822 / 2822 format (e.g. "Mon, 16 Nov 2026 05:00:00 +0000")
                    from email.utils import parsedate_to_datetime
                    posted_at = parsedate_to_datetime(pubdate_node.text)
                except Exception:
                    posted_at = None

            posting = JobPosting(
                title=title,
                company=company or "WeWorkRemotely Employer",
                location="Remote",
                remote_type="Remote",
                portal=self.name,
                job_url=job_url,
                description=clean_desc,
                tags=tags,
                posted_at=posted_at,
            )
            results.append(posting)

            if len(results) >= limit:
                break

        return results


class YCStartupSearcher(BaseSearcher):
    """
    Discovers Y Combinator backed startups and jobs via Work at a Startup
    and YC Job listings / Algolia HN hiring feeds.
    URL: https://hn.algolia.com/api/v1/search_by_date
    """

    name: str = "yc_startup"
    HN_ALGOLIA_URL: str = "https://hn.algolia.com/api/v1/search_by_date"

    def search(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 25,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        normalized_keywords = [k.strip().lower() for k in keywords if k.strip()]

        try:
            # Query Hacker News Who Is Hiring posts (YC's monthly hiring forum)
            query_str = f"Ask HN: Who is hiring? {keywords[0] if keywords else 'remote'}"
            params = {
                "query": query_str,
                "tags": "comment",
                "hitsPerPage": min(limit * 2, 50),
            }
            resp = requests.get(self.HN_ALGOLIA_URL, headers=self.headers, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"YC / Algolia returned status {resp.status_code}")
                return results

            data = resp.json()
            hits = data.get("hits", [])
        except Exception as e:
            logger.error(f"Error querying YC searcher: {e}")
            return results

        for hit in hits:
            comment_text = hit.get("comment_text", "")
            if not comment_text:
                continue

            clean_text = self.clean_html(comment_text)
            lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
            if not lines:
                continue

            header_line = lines[0]
            # Standard HN Who is Hiring top line format:
            # "Company | Role | Location | Remote/Onsite | Salary/Equity"
            parts = [p.strip() for p in header_line.split("|")]
            if len(parts) >= 2:
                company = parts[0]
                title = parts[1]
                loc = parts[2] if len(parts) >= 3 else "Remote"
            else:
                company = "YC Startup"
                title = header_line[:60]
                loc = "Remote"

            # Check keyword match
            search_blob = f"{title} {clean_text}".lower()
            if normalized_keywords and not any(kw in search_blob for kw in normalized_keywords):
                continue

            remote_type = "Remote" if "remote" in clean_text.lower() else "Hybrid/Onsite"
            
            # Extract links or fallback to HN item URL
            story_id = hit.get("story_id") or hit.get("parent_id") or hit.get("objectID")
            item_id = hit.get("objectID")
            job_url = f"https://news.ycombinator.com/item?id={item_id}"

            # Check if there is a direct company url or careers link inside the text
            urls = re.findall(r"https?://[^\s<>\"']+", clean_text)
            if urls:
                # Prefer external company link over hn link if available
                direct_url = next((u for u in urls if "ycombinator.com" not in u), None)
                if direct_url:
                    job_url = direct_url

            posting = JobPosting(
                title=title,
                company=company,
                location=loc,
                remote_type=remote_type,
                portal=self.name,
                job_url=job_url,
                description=clean_text,
                tags=["yc", "startup"],
            )
            results.append(posting)

            if len(results) >= limit:
                break

        return results
