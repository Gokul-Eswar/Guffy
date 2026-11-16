"""
Portal-Specific Application Staging and Review Engine (Ticket 9)

Implements:
- ApplicationStagingEngine:
    Orchestrates form-filling on candidate job applications, extracts review metadata,
    captures DOM screenshots, creates/updates Application DB records in "staged" status,
    and supports 1-click human-in-the-loop (HITL) final submission approval.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from guffy.automation.browser import BrowserController
from guffy.automation.form_filler import UniversalFormFiller
from guffy.core.database import Application, DatabaseManager, Job, get_db_manager
from guffy.core.generator import CoverLetterGenerator, PitchSynthesizer, QASynthesizer
from guffy.core.profile_manager import CandidateProfile

logger = logging.getLogger(__name__)


@dataclass
class StagingResult:
    job_id: str
    portal: str
    status: str  # staged, failed, submitted
    success: bool
    fields_filled: List[Dict[str, Any]] = field(default_factory=list)
    unfilled_fields: List[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    tailored_cover_letter: Optional[str] = None
    tailored_pitch: Optional[str] = None
    error_message: Optional[str] = None


class ApplicationStagingEngine:
    """
    Coordinates browser navigation, applier selection, field population,
    screenshot generation, and human review staging in the database.
    """

    def __init__(
        self,
        browser: BrowserController,
        profile: CandidateProfile,
        db_manager: Optional[DatabaseManager] = None,
        screenshots_dir: str = "staging_screenshots",
    ):
        self.browser = browser
        self.profile = profile
        self.db_manager = db_manager
        self.screenshots_dir = Path(screenshots_dir)
        try:
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self.form_filler = UniversalFormFiller(browser=self.browser, profile=self.profile)
        self.cover_letter_gen = CoverLetterGenerator(profile=self.profile)
        self.pitch_gen = PitchSynthesizer(profile=self.profile)
        self.qa_synthesizer = QASynthesizer(profile=self.profile)

    def stage_job_application(
        self,
        job: Job,
        db_session: Optional[Session] = None,
        applier: Optional[Any] = None,
    ) -> StagingResult:
        """
        Navigates to job apply URL or portal applier, fills fields, halts before final submit,
        captures screenshot for human review, and stages record in database.
        """
        # If job is detached or session manager is available, ensure we have an attached instance or plain data
        job_id = job.id
        job_title = job.title
        job_company = job.company
        job_portal = job.portal
        job_url = job.job_url
        job_description = job.description or ""
        job_matched_skills = job.matched_skills

        logger.info(f"Staging application for job: {job_title} at {job_company} ({job_portal})")

        # 1. Generate tailored assets
        cover_letter = self.cover_letter_gen.generate(
            job_title=job_title,
            company_name=job_company,
            job_description=job_description,
            matched_skills=job_matched_skills.split(",") if job_matched_skills else None,
        )
        pitch_note = self.pitch_gen.generate_pitch(
            job_title=job_title,
            company_name=job_company,
            matched_skills=job_matched_skills.split(",") if job_matched_skills else None,
        )

        screenshot_path = str(self.screenshots_dir / f"stage_{job_id}.png")

        # 2. Run applier or default staging workflow
        try:
            if applier:
                result = applier.fill_and_stage(
                    job=job,
                    cover_letter=cover_letter,
                    pitch_note=pitch_note,
                    screenshot_path=screenshot_path,
                )
            else:
                result = self._default_stage(
                    job=job,
                    cover_letter=cover_letter,
                    pitch_note=pitch_note,
                    screenshot_path=screenshot_path,
                )
        except Exception as e:
            logger.error(f"Failed to stage job {job_id}: {e}", exc_info=True)
            result = StagingResult(
                job_id=job_id,
                portal=job_portal,
                status="failed",
                success=False,
                tailored_cover_letter=cover_letter,
                tailored_pitch=pitch_note,
                error_message=str(e),
            )

        # 3. Persist staging state in SQLite DB
        self._persist_application_record(job, result, db_session)
        return result

    def _default_stage(
        self,
        job: Job,
        cover_letter: str,
        pitch_note: str,
        screenshot_path: str,
    ) -> StagingResult:
        """Default staging routine navigating to job URL and filling standard forms."""
        driver = self.browser.start()
        driver.get(job.job_url)

        # Fill DOM fields without submitting
        fill_report = self.form_filler.fill_all_fields(
            cover_letter=cover_letter,
            pitch_note=pitch_note,
        )

        # Capture review snapshot
        try:
            self.browser.take_screenshot(screenshot_path)
        except Exception as e:
            logger.warning(f"Could not save staging screenshot: {e}")
            screenshot_path = ""

        return StagingResult(
            job_id=job.id,
            portal=job.portal,
            status="staged",
            success=True,
            fields_filled=fill_report.get("filled_fields", []),
            unfilled_fields=fill_report.get("unfilled_fields", []),
            screenshot_path=screenshot_path,
            tailored_cover_letter=cover_letter,
            tailored_pitch=pitch_note,
        )

    def _persist_application_record(
        self,
        job: Job,
        result: StagingResult,
        db_session: Optional[Session] = None,
    ):
        """Updates or creates an Application DB model record."""
        def _update(session: Session):
            app = session.query(Application).filter_by(job_id=job.id).first()
            if not app:
                app = Application(
                    job_id=job.id,
                    portal=job.portal,
                )
                session.add(app)

            app.status = result.status
            app.tailored_cover_letter = result.tailored_cover_letter
            app.tailored_pitch = result.tailored_pitch
            app.screenshot_path = result.screenshot_path
            app.error_message = result.error_message
            if result.fields_filled:
                app.submitted_qa = json.dumps(result.fields_filled)

            job_rec = session.query(Job).filter_by(id=job.id).first()
            if job_rec:
                job_rec.status = result.status

            session.commit()

        if db_session:
            _update(db_session)
        elif self.db_manager:
            for session in self.db_manager.get_session():
                _update(session)

    def approve_and_submit(
        self,
        job: Job,
        applier: Optional[Any] = None,
        db_session: Optional[Session] = None,
    ) -> bool:
        """
        Executes human-approved submission for a staged application.
        Transitions Application and Job status to 'submitted'.
        """
        logger.info(f"Submitting approved application for {job.title} at {job.company}")
        success = False
        error_msg = None

        try:
            if applier:
                success = applier.submit(job=job)
            else:
                # Default submit attempts to click submit button
                success = self._default_submit()
        except Exception as e:
            logger.error(f"Error during application submit: {e}")
            error_msg = str(e)
            success = False

        status_str = "submitted" if success else "failed"

        def _update(session: Session):
            app = session.query(Application).filter_by(job_id=job.id).first()
            if app:
                app.status = status_str
                if error_msg:
                    app.error_message = error_msg
                app.submitted_at = datetime.now(timezone.utc) if success else None

            job_rec = session.query(Job).filter_by(id=job.id).first()
            if job_rec:
                job_rec.status = status_str

            session.commit()

        if db_session:
            _update(db_session)
        elif self.db_manager:
            for session in self.db_manager.get_session():
                _update(session)

        return success

    def _default_submit(self) -> bool:
        """Locates and clicks a standard submission button."""
        driver = self.browser.driver
        if not driver:
            return False

        submit_selectors = [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(), 'SUBMIT', 'submit'), 'submit')]",
            "//button[contains(translate(text(), 'APPLY', 'apply'), 'apply')]",
        ]

        for sel in submit_selectors:
            buttons = driver.find_elements("xpath", sel)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False
