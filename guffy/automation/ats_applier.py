"""
ATS Specific Applier (Greenhouse, Lever, Ashby, Workday) (Ticket 9)

Implements tailored form filling, resume attachment, and staging for direct ATS career portals.
"""

import logging
from typing import Any, Dict, List, Optional

from guffy.automation.browser import BrowserController
from guffy.automation.form_filler import UniversalFormFiller
from guffy.automation.staging_engine import StagingResult
from guffy.core.database import Job
from guffy.core.profile_manager import CandidateProfile

logger = logging.getLogger(__name__)


class ATSApplier:
    """
    Handles applications for standard ATS platforms: Greenhouse, Lever, Ashby, Workday, SmartRecruiters.
    Fills out the application form, verifies fields, and pauses before submission for HITL review.
    """

    def __init__(self, browser: BrowserController, profile: CandidateProfile):
        self.browser = browser
        self.profile = profile
        self.form_filler = UniversalFormFiller(browser=self.browser, profile=self.profile)

    def fill_and_stage(
        self,
        job: Job,
        cover_letter: Optional[str] = None,
        pitch_note: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> StagingResult:
        """
        Navigates to ATS job posting, detects application section/frame,
        fills inputs, attaches resume, and takes review screenshot.
        """
        driver = self.browser.start()
        driver.get(job.job_url)

        # Some ATS boards (like Greenhouse embedded) require scrolling down or clicking "Apply" button
        self._ensure_form_visible(driver)

        # Run universal form filler
        fill_report = self.form_filler.fill_all_fields(
            cover_letter=cover_letter,
            pitch_note=pitch_note,
        )

        # Take staging snapshot
        if screenshot_path:
            try:
                self.browser.take_screenshot(screenshot_path)
            except Exception as e:
                logger.warning(f"Could not take ATS screenshot: {e}")

        return StagingResult(
            job_id=job.id,
            portal=job.portal or "ats",
            status="staged",
            success=True,
            fields_filled=fill_report.get("filled_fields", []),
            unfilled_fields=fill_report.get("unfilled_fields", []),
            screenshot_path=screenshot_path,
            tailored_cover_letter=cover_letter,
            tailored_pitch=pitch_note,
        )

    def _ensure_form_visible(self, driver: Any):
        """Scrolls down or clicks apply button if form is collapsed."""
        try:
            apply_triggers = driver.find_elements(
                "xpath",
                "//a[contains(translate(text(), 'APPLY', 'apply'), 'apply')] | "
                "//button[contains(translate(text(), 'APPLY', 'apply'), 'apply')]"
            )
            for trigger in apply_triggers:
                if trigger.is_displayed():
                    trigger.click()
                    break
        except Exception:
            pass

    def submit(self, job: Job) -> bool:
        """Finds and clicks the final submit button for ATS."""
        driver = self.browser.driver
        if not driver:
            return False

        submit_xpaths = [
            "//input[@id='submit_app']",
            "//button[@id='submit_app']",
            "//button[contains(@class, 'postings-btn')]",
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(., 'SUBMIT', 'submit'), 'submit')]",
        ]

        for xpath in submit_xpaths:
            try:
                elems = driver.find_elements("xpath", xpath)
                for elem in elems:
                    if elem.is_displayed() and elem.is_enabled():
                        elem.click()
                        return True
            except Exception:
                continue

        return False
