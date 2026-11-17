"""
Guffy FastAPI Backend & REST API (Ticket 10)

Provides REST endpoints for:
- Job discovery & filtering (/api/jobs)
- Job searches across remote & aggregator portals (/api/search)
- Target company career crawling (/api/crawl-companies)
- Semantic fit scoring (/api/match)
- Application staging (/api/stage/{job_id})
- Human-in-the-loop application approval (/api/approve/{job_id})
- Candidate profile management (/api/profile, /api/profile/resume)
- Target dream companies (/api/companies)
- Application & search pipeline analytics (/api/analytics)
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import yaml

from guffy.automation.browser import BrowserController
from guffy.automation.staging_engine import ApplicationStagingEngine
from guffy.config import Settings, get_settings
from guffy.core.database import (
    Application,
    Company,
    DatabaseManager,
    Job,
    ProfileSetting,
    get_db_manager,
)
from guffy.core.matcher import MatchEngine, score_job
from guffy.core.profile_manager import (
    CandidateProfile,
    ProfileManager,
    ResumeParser,
)
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

from guffy.core.scheduler import ScheduleManager, ScheduledJob, get_scheduler_service

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Guffy Job Automation API",
    version="0.1.0",
    description="Intelligent Multi-Portal Job Search & Tailored Application Engine",
)

@app.on_event("startup")
def startup_event():
    """Starts the optional background scheduler on web startup if enabled."""
    mgr = ScheduleManager()
    data = mgr.load_data()
    if data.get("settings", {}).get("scheduler_enabled", True):
        service = get_scheduler_service()
        service.start()


@app.on_event("shutdown")
def shutdown_event():
    """Stops the scheduler when FastAPI shuts down."""
    service = get_scheduler_service()
    service.stop()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency Injection
# ---------------------------------------------------------------------------

def get_db() -> Session:
    manager = get_db_manager()
    session = manager.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_profile() -> CandidateProfile:
    """Loads current CandidateProfile from profile.yaml or profile.example.yaml."""
    candidates = ["profile.yaml", "profile.example.yaml"]
    for p in candidates:
        if os.path.exists(p):
            try:
                return CandidateProfile.load_from_yaml(p)
            except Exception as e:
                logger.warning(f"Failed to load profile from {p}: {e}")
    # Default minimal profile fallback
    return CandidateProfile(
        personal_info={
            "full_name": "Job Seeker",
            "email": "seeker@example.com",
            "location": "Remote",
        }
    )


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    keywords: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    portals: Optional[List[str]] = Field(
        default=None,
        description="Portals to query: remoteok, weworkremotely, yc, linkedin, indeed, wellfound, dice, glassdoor",
    )
    remote_only: Optional[bool] = None
    max_results: Optional[int] = 30


class CompanyCreateRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    careers_url: Optional[str] = None
    ats: Optional[str] = "unknown"
    priority: Optional[str] = "medium"


class MatchRequest(BaseModel):
    job_ids: Optional[List[str]] = None
    force_rescore: bool = False


# ---------------------------------------------------------------------------
# Helper Discovery Worker
# ---------------------------------------------------------------------------

def run_job_search_task(
    keywords: List[str],
    locations: List[str],
    portals: List[str],
    remote_only: bool,
    max_results: int,
):
    """Executes multi-portal discovery in background or sync and saves to DB."""
    db_mgr = get_db_manager()
    session = db_mgr.SessionLocal()
    try:
        searchers_map = {
            "remoteok": RemoteOKSearcher,
            "weworkremotely": WeWorkRemotelySearcher,
            "yc": YCStartupSearcher,
            "linkedin": LinkedInSearcher,
            "wellfound": WellfoundSearcher,
            "indeed": IndeedSearcher,
            "dice": DiceSearcher,
            "glassdoor": GlassdoorSearcher,
        }

        active_portals = [p.lower() for p in portals if p.lower() in searchers_map]
        if not active_portals:
            active_portals = list(searchers_map.keys())

        for p_name in active_portals:
            searcher_cls = searchers_map[p_name]
            searcher = searcher_cls()
            for kw in keywords:
                for loc in locations:
                    try:
                        results = searcher.search(
                            keywords=kw,
                            location=loc,
                            remote_only=remote_only,
                            limit=max_results,
                        )
                        for posting in results:
                            existing = session.query(Job).filter_by(id=posting.id).first()
                            if not existing:
                                existing_url = session.query(Job).filter_by(job_url=posting.job_url).first()
                                if not existing_url:
                                    job_model = posting.to_job_model()
                                    session.add(job_model)
                        session.commit()
                    except Exception as e:
                        logger.error(f"Error searching {p_name} for {kw}: {e}")
                        session.rollback()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "Guffy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/jobs")
def get_jobs(
    status: Optional[str] = Query(None, description="Filter by status (discovered, scored, staged, submitted, rejected)"),
    portal: Optional[str] = Query(None, description="Filter by portal"),
    company: Optional[str] = Query(None, description="Filter by company name substring"),
    min_score: Optional[float] = Query(None, description="Minimum match score (0-100)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List and filter jobs with pagination."""
    query = db.query(Job)

    if status:
        query = query.filter(Job.status == status)
    if portal:
        query = query.filter(Job.portal == portal)
    if company:
        query = query.filter(Job.company.ilike(f"%{company}%"))
    if min_score is not None:
        query = query.filter(Job.match_score >= min_score)

    total_count = query.count()
    jobs = query.order_by(Job.match_score.desc(), Job.discovered_at.desc()).offset(offset).limit(limit).all()

    items = []
    for j in jobs:
        matched = []
        missing = []
        pros_cons = {}
        try:
            if j.matched_skills:
                matched = json.loads(j.matched_skills) if j.matched_skills.startswith("[") else [s.strip() for s in j.matched_skills.split(",")]
        except Exception:
            matched = []
        try:
            if j.missing_skills:
                missing = json.loads(j.missing_skills) if j.missing_skills.startswith("[") else [s.strip() for s in j.missing_skills.split(",")]
        except Exception:
            missing = []
        try:
            if j.pros_cons:
                pros_cons = json.loads(j.pros_cons)
        except Exception:
            pros_cons = {}

        items.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "remote_type": j.remote_type,
            "portal": j.portal,
            "job_url": j.job_url,
            "description": j.description,
            "salary_range": j.salary_range,
            "easy_apply": j.easy_apply,
            "match_score": j.match_score,
            "matched_skills": matched,
            "missing_skills": missing,
            "pros_cons": pros_cons,
            "status": j.status,
            "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        })

    return {
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "jobs": items,
    }


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str, db: Session = Depends(get_db)):
    """Fetch complete detail for a single job including application stage if exists."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    app_record = db.query(Application).filter_by(job_id=job.id).first()
    application_data = None
    if app_record:
        application_data = {
            "id": app_record.id,
            "status": app_record.status,
            "tailored_cover_letter": app_record.tailored_cover_letter,
            "tailored_pitch": app_record.tailored_pitch,
            "screenshot_path": app_record.screenshot_path,
            "error_message": app_record.error_message,
            "staged_at": app_record.staged_at.isoformat() if app_record.staged_at else None,
            "submitted_at": app_record.submitted_at.isoformat() if app_record.submitted_at else None,
            "submitted_qa": json.loads(app_record.submitted_qa) if app_record.submitted_qa else [],
        }

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote_type": job.remote_type,
        "portal": job.portal,
        "job_url": job.job_url,
        "description": job.description,
        "salary_range": job.salary_range,
        "easy_apply": job.easy_apply,
        "match_score": job.match_score,
        "matched_skills": json.loads(job.matched_skills) if job.matched_skills and job.matched_skills.startswith("[") else [],
        "missing_skills": json.loads(job.missing_skills) if job.missing_skills and job.missing_skills.startswith("[") else [],
        "pros_cons": json.loads(job.pros_cons) if job.pros_cons else {},
        "status": job.status,
        "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
        "application": application_data,
    }


@app.post("/api/search")
def trigger_search(
    request: Optional[SearchRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    sync: bool = Query(False, description="Whether to execute synchronously"),
):
    """Trigger multi-portal job search."""
    settings = get_settings()
    req = request or SearchRequest()
    keywords = req.keywords or settings.search.keywords
    locations = req.locations or settings.search.locations
    remote_only = req.remote_only if req.remote_only is not None else settings.search.remote_only
    portals = req.portals or ["remoteok", "weworkremotely", "yc"]
    max_results = req.max_results or settings.search.max_jobs_per_source

    if sync:
        run_job_search_task(keywords, locations, portals, remote_only, max_results)
        return {
            "status": "completed",
            "message": f"Synchronous search completed across {len(portals)} portal(s).",
            "portals": portals,
            "keywords": keywords,
        }
    else:
        background_tasks.add_task(
            run_job_search_task,
            keywords,
            locations,
            portals,
            remote_only,
            max_results,
        )
        return {
            "status": "queued",
            "message": f"Search started in background across {len(portals)} portal(s).",
            "portals": portals,
            "keywords": keywords,
        }


@app.post("/api/crawl-companies")
def trigger_company_crawl(
    keywords: Optional[List[str]] = Query(None),
    priority: Optional[str] = Query(None),
    sync: bool = Query(True, description="Whether to execute synchronously"),
    db: Session = Depends(get_db),
):
    """Trigger career page crawling for all registered target companies."""
    crawler = CompanyCrawler()

    if sync:
        discovered_jobs = crawler.crawl_all(session=db, priority=priority, keywords=keywords)
        return {
            "status": "completed",
            "crawled_count": len(discovered_jobs),
            "message": f"Successfully crawled target companies and discovered {len(discovered_jobs)} active jobs.",
        }
    else:
        # Background execution
        def _bg_crawl(kw, prio):
            db_mgr = get_db_manager()
            sess = db_mgr.SessionLocal()
            try:
                crawler.crawl_all(session=sess, priority=prio, keywords=kw)
            finally:
                sess.close()

        bg = BackgroundTasks()
        bg.add_task(_bg_crawl, keywords, priority)
        return {
            "status": "queued",
            "message": "Company career crawl started in background.",
        }


@app.post("/api/match")
def run_match(
    request: Optional[MatchRequest] = None,
    db: Session = Depends(get_db),
):
    """Score jobs against current candidate profile."""
    profile = get_current_profile()
    req = request or MatchRequest()

    query = db.query(Job)
    if req.job_ids:
        query = query.filter(Job.id.in_(req.job_ids))
    elif not req.force_rescore:
        # Only score unreviewed or discovered jobs
        query = query.filter(Job.status == "discovered")

    jobs_to_score = query.all()
    scored_count = 0
    passed_count = 0

    for job in jobs_to_score:
        result = score_job(job, profile)
        scored_count += 1
        if result.passed_hard_filters:
            passed_count += 1

    db.commit()

    return {
        "status": "success",
        "total_scored": scored_count,
        "passed_filter_count": passed_count,
        "rejected_count": scored_count - passed_count,
    }


@app.post("/api/stage/{job_id}")
def stage_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Stage an application with pre-filled fields and tailored assets for human review."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = get_current_profile()
    browser = BrowserController()
    staging_engine = ApplicationStagingEngine(browser=browser, profile=profile, db_manager=get_db_manager())

    result = staging_engine.stage_job_application(job=job, db_session=db)

    return {
        "status": result.status,
        "success": result.success,
        "job_id": result.job_id,
        "portal": result.portal,
        "screenshot_path": result.screenshot_path,
        "tailored_cover_letter": result.tailored_cover_letter,
        "tailored_pitch": result.tailored_pitch,
        "fields_filled_count": len(result.fields_filled),
        "unfilled_fields_count": len(result.unfilled_fields),
        "error_message": result.error_message,
    }


@app.post("/api/approve/{job_id}")
def approve_job_application(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Confirm and execute 1-click submission for a staged application."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = get_current_profile()
    browser = BrowserController()
    staging_engine = ApplicationStagingEngine(browser=browser, profile=profile, db_manager=get_db_manager())

    success = staging_engine.approve_and_submit(job=job, db_session=db)

    return {
        "job_id": job.id,
        "status": "submitted" if success else "failed",
        "success": success,
        "message": "Application submitted successfully." if success else "Failed to finalize submission.",
    }


@app.get("/api/profile")
def get_profile():
    """Retrieve candidate profile."""
    profile = get_current_profile()
    return profile.model_dump()


@app.put("/api/profile")
def update_profile(profile_data: Dict[str, Any]):
    """Update and persist candidate profile to profile.yaml."""
    try:
        updated = CandidateProfile(**profile_data)
        target_path = Path("profile.yaml")
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(updated.model_dump(), f, default_flow_style=False, sort_keys=False)
        return {"status": "success", "message": "Profile updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid profile schema: {str(e)}")


@app.post("/api/profile/resume")
def upload_resume(file: UploadFile = File(...)):
    """Upload resume document (.pdf, .docx, .txt), parse skills, and update profile."""
    data_dir = Path("data/resumes")
    data_dir.mkdir(parents=True, exist_ok=True)

    dest_path = data_dir / file.filename
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    try:
        text = ResumeParser.extract_text(dest_path)
        skills = ResumeParser.extract_skills(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {str(e)}")

    # Update candidate profile resume path
    profile = get_current_profile()
    profile.personal_info.resume_path = str(dest_path)
    with open("profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(profile.model_dump(), f, default_flow_style=False)

    return {
        "status": "success",
        "resume_path": str(dest_path),
        "word_count": len(text.split()),
        "detected_skills": skills,
    }


@app.get("/api/companies")
def list_companies(db: Session = Depends(get_db)):
    """List target dream companies."""
    comps = db.query(Company).order_by(Company.priority.asc(), Company.name.asc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "careers_url": c.careers_url,
            "ats": c.ats,
            "priority": c.priority,
            "active_jobs_count": c.active_jobs_count,
            "last_crawled_at": c.last_crawled_at.isoformat() if c.last_crawled_at else None,
        }
        for c in comps
    ]


@app.post("/api/companies")
def create_company(
    comp_data: CompanyCreateRequest,
    db: Session = Depends(get_db),
):
    """Add a new company to track."""
    existing = db.query(Company).filter_by(name=comp_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Company '{comp_data.name}' is already tracked.")

    company = Company(
        name=comp_data.name,
        domain=comp_data.domain,
        careers_url=comp_data.careers_url,
        ats=comp_data.ats or "unknown",
        priority=comp_data.priority or "medium",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    return {
        "status": "created",
        "company": {
            "id": company.id,
            "name": company.name,
            "ats": company.ats,
            "priority": company.priority,
        },
    }


@app.delete("/api/companies/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db)):
    """Remove a company from tracking."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    db.delete(company)
    db.commit()
    return {"status": "deleted", "id": company_id}


@app.get("/api/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """Application statistics, conversion funnel, and portal breakdown."""
    total_discovered = db.query(Job).count()
    total_scored = db.query(Job).filter(Job.status != "discovered").count()
    total_staged = db.query(Job).filter(Job.status == "staged").count()
    total_submitted = db.query(Job).filter(Job.status == "submitted").count()
    total_rejected = db.query(Job).filter(Job.status == "rejected").count()

    # Portal distribution
    jobs = db.query(Job.portal).all()
    portal_counts = {}
    for (portal,) in jobs:
        portal_counts[portal] = portal_counts.get(portal, 0) + 1

    # Average match score
    scored_jobs = db.query(Job.match_score).filter(Job.match_score > 0).all()
    avg_score = round(sum(s[0] for s in scored_jobs) / len(scored_jobs), 1) if scored_jobs else 0.0

    return {
        "pipeline": {
            "total_discovered": total_discovered,
            "total_scored": total_scored,
            "total_staged": total_staged,
            "total_submitted": total_submitted,
            "total_rejected": total_rejected,
        },
        "average_match_score": avg_score,
        "portal_distribution": portal_counts,
        "tracked_companies_count": db.query(Company).count(),
    }


# ---------------------------------------------------------------------------
# Scheduler & Notification Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/scheduler", tags=["Scheduler"])
def get_scheduler_status():
    """Returns scheduler configuration, jobs, and running status."""
    service = get_scheduler_service()
    mgr = service.manager
    data = mgr.load_data()
    return {
        "is_running": service.is_running(),
        "settings": data.get("settings", {}),
        "jobs": data.get("jobs", []),
        "run_history": data.get("run_history", [])[:10],
    }


@app.post("/api/scheduler/toggle", tags=["Scheduler"])
def toggle_scheduler(enable: bool = Query(...)):
    """Enables or disables the background scheduler."""
    service = get_scheduler_service()
    mgr = service.manager
    data = mgr.load_data()
    data.setdefault("settings", {})["scheduler_enabled"] = enable
    mgr.save_data(data)

    if enable and not service.is_running():
        service.start()
    elif not enable and service.is_running():
        service.stop()

    return {"is_running": service.is_running(), "scheduler_enabled": enable}


@app.post("/api/scheduler/run-now", tags=["Scheduler"])
def run_scheduler_now(background_tasks: BackgroundTasks):
    """Triggers an immediate scan for due jobs."""
    service = get_scheduler_service()
    background_tasks.add_task(service.run_due_jobs_once)
    return {"message": "Scheduled scan triggered in background"}


@app.get("/api/notifications", tags=["Notifications"])
def get_notifications(unread_only: bool = Query(False)):
    """Retrieves web dashboard alerts (e.g. for high-match jobs)."""
    mgr = ScheduleManager()
    return {"notifications": mgr.get_notifications(unread_only=unread_only)}


@app.post("/api/notifications/mark-read", tags=["Notifications"])
def mark_notifications_read(notification_id: Optional[str] = Query(None)):
    """Marks one or all notifications as read."""
    mgr = ScheduleManager()
    mgr.mark_notifications_read(notif_id=notification_id)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Static SPA Mount & Root Route (Ticket 11)
# ---------------------------------------------------------------------------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serves the Tailwind SPA dashboard single-page application."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Guffy Dashboard UI (index.html not found). API is active."}

