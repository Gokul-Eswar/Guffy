"""
Wellfound (AngelList) Startup Applier (Ticket 9)

Implements:
- WellfoundApplier:
  Handles Wellfound apply drawer, tailored pitch note insertion,
  screening questions, and staging review snapshot before final submission.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from guffy.automation.browser import BrowserController
from guffy.automation.form_filler import UniversalFormFiller
from guffy.automation.staging_engine import StagingResult
from guffy.core.database import Job
from guffy.core.profile_manager import CandidateProfile

logger = logging.getLogger(__name__)


class WellfoundApplier:
    """
    Automates Wellfound / AngelList startup applications with custom pitch insertion.
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
        Navigates to Wellfound job page, triggers Apply drawer,
        fills customized pitch note and screening questions, and saves staging snapshot.
        """
        driver = self.browser.start()
        driver.get(job.job_url)

        # 1. Click Apply button to open drawer/modal
        if not self._open_apply_drawer(driver):
            logger.info("Apply drawer trigger not clicked or already open.")

        time.sleep(1)

        # 2. Insert tailored pitch note into pitch textarea
        note_to_use = pitch_note or cover_letter or ""
        pitch_inserted = self._insert_pitch_note(driver, note_to_use)

        # 3. Fill any other form inputs/questions in drawer
        report = self.form_filler.fill_all_fields(
            cover_letter=cover_letter,
            pitch_note=pitch_note,
        )

        filled_fields = report.get("filled_fields", [])
        if pitch_inserted:
            filled_fields.append({"type": "pitch_note", "value": note_to_use[:60] + "..."})

        # 4. Capture staging screenshot before 'Send application'
        if screenshot_path:
            try:
                self.browser.take_screenshot(screenshot_path)
            except Exception as e:
                logger.warning(f"Could not take Wellfound screenshot: {e}")

        return StagingResult(
            job_id=job.id,
            portal="wellfound",
            status="staged",
            success=True,
            fields_filled=filled_fields,
            unfilled_fields=report.get("unfilled_fields", []),
            screenshot_path=screenshot_path,
            tailored_cover_letter=cover_letter,
            tailored_pitch=pitch_note,
        )

    def _open_apply_drawer(self, driver: Any) -> bool:
        """Finds and clicks Wellfound 'Apply' button."""
        apply_selectors = [
            "//button[contains(., 'Apply')]",
            "//a[contains(., 'Apply')]",
            "//button[contains(@data-test, 'ApplyButton')]",
        ]
        for sel in apply_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False

    def _insert_pitch_note(self, driver: Any, pitch: str) -> bool:
        """Finds pitch textarea and inserts pitch using browser controller."""
        if not pitch:
            return False

        pitch_selectors = [
            "//textarea[contains(@name, 'note') or contains(@id, 'note')]",
            "//textarea[contains(@placeholder, 'note') or contains(@placeholder, 'pitch')]",
            "//textarea[contains(@placeholder, 'hiring manager')]",
            "//textarea",
        ]
        for sel in pitch_selectors:
            elems = driver.find_elements("xpath", sel)
            for elem in elems:
                if elem.is_displayed():
                    try:
                        self.browser.human_type(elem, pitch)
                        return True
                    except Exception:
                        pass
        return False

    def submit(self, job: Job) -> bool:
        """Clicks final 'Send application' button on Wellfound."""
        driver = self.browser.driver
        if not driver:
            return False

        submit_selectors = [
            "//button[contains(., 'Send application')]",
            "//button[contains(., 'Send Application')]",
            "//button[contains(@data-test, 'SubmitButton')]",
        ]
        for sel in submit_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False
