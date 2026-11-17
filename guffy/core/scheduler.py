"""
Guffy Background Scheduler & Job Engine

Features:
- Stores job definitions and run history in a local JSON file (data/schedules.json).
- Checks every 15 minutes for due jobs (crawl, search, match).
- High-match detection: triggers alerts for jobs with match score > 85%.
- In-process background runner with start/stop lifecycle management.
- Completely optional: scans can still be executed manually via CLI or Web UI.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("guffy.scheduler")

DEFAULT_SCHEDULES_FILE = Path("data/schedules.json")


class ScheduledJob:
    """Represents a scheduled task configuration and history."""

    def __init__(
        self,
        job_id: str,
        name: str,
        task_type: str,  # 'search', 'crawl', 'match'
        interval_minutes: int = 15,
        enabled: bool = True,
        params: Optional[Dict[str, Any]] = None,
        last_run: Optional[str] = None,
        last_status: Optional[str] = None,
        last_error: Optional[str] = None,
        run_count: int = 0,
    ):
        self.job_id = job_id
        self.name = name
        self.task_type = task_type
        self.interval_minutes = interval_minutes
        self.enabled = enabled
        self.params = params or {}
        self.last_run = last_run
        self.last_status = last_status
        self.last_error = last_error
        self.run_count = run_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "task_type": self.task_type,
            "interval_minutes": self.interval_minutes,
            "enabled": self.enabled,
            "params": self.params,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledJob":
        return cls(
            job_id=data.get("job_id", ""),
            name=data.get("name", ""),
            task_type=data.get("task_type", "search"),
            interval_minutes=int(data.get("interval_minutes", 15)),
            enabled=data.get("enabled", True),
            params=data.get("params", {}),
            last_run=data.get("last_run"),
            last_status=data.get("last_status"),
            last_error=data.get("last_error"),
            run_count=int(data.get("run_count", 0)),
        )

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """Determines if the job is due to execute."""
        if not self.enabled:
            return False
        if not self.last_run:
            return True

        if now is None:
            now = datetime.now(timezone.utc)

        try:
            last_dt = datetime.fromisoformat(self.last_run)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now - last_dt).total_seconds()
            return elapsed_seconds >= (self.interval_minutes * 60)
        except Exception:
            return True


class ScheduleManager:
    """Manages reading, writing, and executing scheduled tasks using a JSON file."""

    def __init__(self, storage_path: Path = DEFAULT_SCHEDULES_FILE):
        self.storage_path = Path(storage_path)
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensures the parent directory and schedules.json file exist with defaults."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists() or self.storage_path.stat().st_size == 0:
            default_data = {
                "version": "1.0",
                "settings": {
                    "scheduler_enabled": True,
                    "check_interval_seconds": 900,  # 15 minutes
                    "min_alert_match_score": 85,
                },
                "jobs": [
                    {
                        "job_id": "auto_portal_search",
                        "name": "Auto Search Remote Portals",
                        "task_type": "search",
                        "interval_minutes": 60,
                        "enabled": True,
                        "params": {"sources": ["remoteok", "weworkremotely"]},
                        "last_run": None,
                        "last_status": None,
                        "last_error": None,
                        "run_count": 0,
                    },
                    {
                        "job_id": "auto_company_crawl",
                        "name": "Auto Target Company Crawler",
                        "task_type": "crawl",
                        "interval_minutes": 120,
                        "enabled": True,
                        "params": {},
                        "last_run": None,
                        "last_status": None,
                        "last_error": None,
                        "run_count": 0,
                    },
                ],
                "run_history": [],
                "notifications": [],
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2)

    def load_data(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {self.storage_path}: {e}")
                return {"settings": {}, "jobs": [], "run_history": [], "notifications": []}

    def save_data(self, data: Dict[str, Any]) -> None:
        with self._lock:
            try:
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving {self.storage_path}: {e}")

    def list_jobs(self) -> List[ScheduledJob]:
        data = self.load_data()
        return [ScheduledJob.from_dict(j) for j in data.get("jobs", [])]

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        jobs = self.list_jobs()
        for j in jobs:
            if j.job_id == job_id:
                return j
        return None

    def upsert_job(self, job: ScheduledJob) -> None:
        data = self.load_data()
        jobs = data.get("jobs", [])
        updated = False
        for idx, item in enumerate(jobs):
            if item.get("job_id") == job.job_id:
                jobs[idx] = job.to_dict()
                updated = True
                break
        if not updated:
            jobs.append(job.to_dict())
        data["jobs"] = jobs
        self.save_data(data)

    def record_run(
        self,
        job_id: str,
        status: str,
        result_summary: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """Updates job status and appends to run history."""
        data = self.load_data()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update specific job
        for item in data.get("jobs", []):
            if item.get("job_id") == job_id:
                item["last_run"] = now_iso
                item["last_status"] = status
                item["last_error"] = error
                item["run_count"] = item.get("run_count", 0) + 1
                break

        # Record history entry (keep last 50)
        history_entry = {
            "job_id": job_id,
            "timestamp": now_iso,
            "status": status,
            "result_summary": result_summary,
            "error": error,
        }
        history = data.get("run_history", [])
        history.insert(0, history_entry)
        data["run_history"] = history[:50]

        self.save_data(data)

    def add_notification(self, title: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Adds an in-app dashboard notification (e.g. for high-match jobs)."""
        data = self.load_data()
        notifications = data.get("notifications", [])
        notification_entry = {
            "id": f"notif_{int(time.time() * 1000)}",
            "title": title,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "meta": meta or {},
        }
        notifications.insert(0, notification_entry)
        data["notifications"] = notifications[:100]  # retain 100
        self.save_data(data)

    def get_notifications(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        data = self.load_data()
        notifications = data.get("notifications", [])
        if unread_only:
            return [n for n in notifications if not n.get("read", False)]
        return notifications

    def mark_notifications_read(self, notif_id: Optional[str] = None) -> None:
        data = self.load_data()
        for item in data.get("notifications", []):
            if notif_id is None or item.get("id") == notif_id:
                item["read"] = True
        self.save_data(data)


class GuffySchedulerService:
    """Background service that periodically checks and runs due tasks."""

    def __init__(
        self,
        manager: Optional[ScheduleManager] = None,
        check_interval_seconds: int = 900,  # 15 minutes
        task_executor: Optional[Callable[[ScheduledJob], Dict[str, Any]]] = None,
    ):
        self.manager = manager or ScheduleManager()
        self.check_interval_seconds = check_interval_seconds
        self.task_executor = task_executor
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def is_running(self) -> bool:
        return self._is_running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Starts the background scheduler loop in a daemon thread."""
        if self.is_running():
            logger.info("Scheduler service is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="GuffyBackgroundScheduler",
            daemon=True,
        )
        self._thread.start()
        self._is_running = True
        logger.info("Guffy background scheduler started (checking every 15 min).")

    def stop(self) -> None:
        """Stops the scheduler loop."""
        if not self.is_running():
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._is_running = False
        logger.info("Guffy background scheduler stopped.")

    def run_due_jobs_once(self) -> List[Dict[str, Any]]:
        """Checks for all due jobs and executes them sequentially."""
        due_jobs = [j for j in self.manager.list_jobs() if j.is_due()]
        results = []
        for job in due_jobs:
            logger.info(f"Executing scheduled job: {job.name} ({job.job_id})")
            try:
                if self.task_executor:
                    res = self.task_executor(job)
                else:
                    res = self._default_execute(job)
                self.manager.record_run(job.job_id, status="success", result_summary=res)
                results.append({"job_id": job.job_id, "status": "success", "result": res})
            except Exception as e:
                logger.error(f"Error running job {job.job_id}: {e}", exc_info=True)
                self.manager.record_run(job.job_id, status="error", result_summary={}, error=str(e))
                results.append({"job_id": job.job_id, "status": "error", "error": str(e)})
        return results

    def _run_loop(self) -> None:
        """The loop that runs every 15 minutes (or stops when requested)."""
        while not self._stop_event.is_set():
            try:
                self.run_due_jobs_once()
            except Exception as e:
                logger.error(f"Unhandled error in scheduler loop: {e}", exc_info=True)

            # Sleep in small slices to allow rapid shutdown response
            slept = 0
            while slept < self.check_interval_seconds and not self._stop_event.is_set():
                time.sleep(1)
                slept += 1

    def _default_execute(self, job: ScheduledJob) -> Dict[str, Any]:
        """Default task executor dispatching to Guffy core search & crawl modules."""
        from guffy.core.database import get_db_manager
        from guffy.core.matcher import MatchEngine, score_job
        from guffy.core.profile_manager import ProfileManager
        from guffy.searchers import (
            CompanyCrawler,
            DiceSearcher,
            GlassdoorSearcher,
            IndeedSearcher,
            LinkedInSearcher,
            RemoteOKSearcher,
            TargetCompanyManager,
            WeWorkRemotelySearcher,
            WellfoundSearcher,
            YCStartupSearcher,
        )

        db = get_db_manager()
        profile_mgr = ProfileManager()
        candidate = profile_mgr.get_profile()
        matcher = MatchEngine(candidate=candidate)

        new_jobs_count = 0
        high_match_jobs = []

        if job.task_type == "search":
            sources = job.params.get("sources", ["remoteok", "weworkremotely"])
            searchers = []
            if "remoteok" in sources:
                searchers.append(RemoteOKSearcher())
            if "weworkremotely" in sources:
                searchers.append(WeWorkRemotelySearcher())
            if "yc" in sources:
                searchers.append(YCStartupSearcher())

            for searcher in searchers:
                try:
                    jobs = searcher.search(keywords=candidate.preferences.target_titles or ["Software Engineer"])
                    for j in jobs:
                        created, db_job = db.upsert_job(j.to_dict())
                        if created:
                            new_jobs_count += 1
                            # Score fit
                            score = matcher.score(db_job.to_dict())
                            db_job.match_score = score.overall_score
                            db.session.commit()

                            if score.overall_score >= 85:
                                high_match_jobs.append(db_job)
                except Exception as ex:
                    logger.warning(f"Error in scheduled searcher {searcher.source_name}: {ex}")

        elif job.task_type == "crawl":
            crawler = CompanyCrawler(db_manager=db)
            crawled = crawler.crawl_all()
            new_jobs_count = len(crawled)
            for db_job in crawled:
                score = matcher.score(db_job.to_dict())
                db_job.match_score = score.overall_score
                db.session.commit()
                if score.overall_score >= 85:
                    high_match_jobs.append(db_job)

        # Notify dashboard if high-match jobs found
        if high_match_jobs:
            for hj in high_match_jobs:
                self.manager.add_notification(
                    title=f"High Fit Match: {hj.title} at {hj.company}",
                    message=f"Score: {hj.match_score}% | Location: {hj.location or 'Remote'}",
                    meta={"job_id": hj.id, "match_score": hj.match_score, "url": hj.url},
                )

        return {
            "new_jobs_found": new_jobs_count,
            "high_match_count": len(high_match_jobs),
        }


# Global singleton instance for easy import across FastAPI and CLI
_global_scheduler: Optional[GuffySchedulerService] = None


def get_scheduler_service() -> GuffySchedulerService:
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = GuffySchedulerService()
    return _global_scheduler
