from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import pytest

from guffy.core.scheduler import ScheduleManager, ScheduledJob, GuffySchedulerService


@pytest.fixture
def temp_schedules_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_schedule_manager_initialization(temp_schedules_file):
    if temp_schedules_file.exists():
        temp_schedules_file.unlink()
    
    mgr = ScheduleManager(storage_path=temp_schedules_file)
    jobs = mgr.list_jobs()
    assert len(jobs) >= 2
    assert any(j.task_type == "search" for j in jobs)
    assert any(j.task_type == "crawl" for j in jobs)


def test_scheduled_job_is_due(temp_schedules_file):
    mgr = ScheduleManager(storage_path=temp_schedules_file)
    job = ScheduledJob(
        job_id="test_due",
        name="Test Due Job",
        task_type="search",
        interval_minutes=15,
        enabled=True,
    )
    # Never run before -> is due
    assert job.is_due() is True

    # Run 5 minutes ago -> not due for a 15m interval
    now = datetime.now(timezone.utc)
    job.last_run = (now - timedelta(minutes=5)).isoformat()
    assert job.is_due(now=now) is False

    # Run 20 minutes ago -> is due
    job.last_run = (now - timedelta(minutes=20)).isoformat()
    assert job.is_due(now=now) is True


def test_notifications_and_record_run(temp_schedules_file):
    mgr = ScheduleManager(storage_path=temp_schedules_file)
    mgr.add_notification("Match Alert", "Found 90% match job", meta={"job_id": 123})
    
    notifs = mgr.get_notifications(unread_only=True)
    assert len(notifs) == 1
    assert notifs[0]["title"] == "Match Alert"

    # Mark as read
    mgr.mark_notifications_read(notifs[0]["id"])
    assert len(mgr.get_notifications(unread_only=True)) == 0
    assert len(mgr.get_notifications(unread_only=False)) == 1

    # Record run
    mgr.record_run("auto_portal_search", status="success", result_summary={"new_jobs_found": 3})
    data = mgr.load_data()
    assert len(data["run_history"]) == 1
    assert data["run_history"][0]["result_summary"]["new_jobs_found"] == 3


def test_scheduler_service_lifecycle(temp_schedules_file):
    mgr = ScheduleManager(storage_path=temp_schedules_file)
    executed = []

    def mock_executor(job):
        executed.append(job.job_id)
        return {"count": 1}

    service = GuffySchedulerService(
        manager=mgr,
        check_interval_seconds=1,
        task_executor=mock_executor,
    )

    results = service.run_due_jobs_once()
    assert len(results) >= 2
    assert len(executed) >= 2
    assert service.is_running() is False
