"""
Indeed Quick Apply Applier (Ticket 9)

Implements:
- IndeedApplier:
  Handles Indeed 'Apply now' / Quick Apply modal flows, candidate contact/resume selection,
  screening questions progression, and staging review snapshot before final submission.
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


class IndeedApplier:
    """
    Automates Indeed Quick Apply modal flows while enforcing HITL review before final submit.
    """

    def __init__(self, browser: BrowserController, profile: CandidateProfile, max_steps: int = 8):
        self.browser = browser
        self.profile = profile
        self.max_steps = max_steps
        self.form_filler = UniversalFormFiller(browser=self.browser, profile=self.profile)

    def fill_and_stage(
        self,
        job: Job,
        cover_letter: Optional[str] = None,
        pitch_note: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> StagingResult:
        """
        Navigates to Indeed job, triggers 'Apply now', navigates multi-step dialogs,
        populates screening questions and halts at review screen.
        """
        driver = self.browser.start()
        driver.get(job.job_url)

        # 1. Click 'Apply now' or 'Easily apply'
        if not self._click_apply_now(driver):
            return StagingResult(
                job_id=job.id,
                portal="indeed",
                status="failed",
                success=False,
                error_message="Indeed 'Apply now' button not found.",
            )

        all_filled: List[Dict[str, Any]] = []
        step = 0

        # 2. Iterate through form steps
        while step < self.max_steps:
            step += 1
            report = self.form_filler.fill_all_fields(
                cover_letter=cover_letter,
                pitch_note=pitch_note,
            )
            all_filled.extend(report.get("filled_fields", []))

            # Stop if we are on the final Review / Submit page
            if self._is_final_step(driver):
                logger.info(f"Indeed Quick Apply reached review screen at step {step}.")
                break

            # Click Continue / Next
            advanced = self._click_continue(driver)
            if not advanced:
                break
            time.sleep(1)

        # 3. Capture staging screenshot
        if screenshot_path:
            try:
                self.browser.take_screenshot(screenshot_path)
            except Exception as e:
                logger.warning(f"Could not take Indeed screenshot: {e}")

        return StagingResult(
            job_id=job.id,
            portal="indeed",
            status="staged",
            success=True,
            fields_filled=all_filled,
            screenshot_path=screenshot_path,
            tailored_cover_letter=cover_letter,
            tailored_pitch=pitch_note,
        )

    def _click_apply_now(self, driver: Any) -> bool:
        """Finds and clicks 'Apply now' button."""
        apply_selectors = [
            "//button[contains(., 'Apply now')]",
            "//span[contains(., 'Apply now')]/parent::button",
            "//div[contains(@id, 'indeedApplyButton')]",
            "//button[contains(@class, 'indeed-apply-button')]",
        ]
        for sel in apply_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False

    def _is_final_step(self, driver: Any) -> bool:
        """Detects if currently at 'Submit your application' review screen."""
        submit_selectors = [
            "//button[contains(., 'Submit your application')]",
            "//button[contains(., 'Submit application')]",
            "//span[contains(., 'Submit your application')]",
        ]
        for sel in submit_selectors:
            elems = driver.find_elements("xpath", sel)
            if any(e.is_displayed() for e in elems):
                return True
        return False

    def _click_continue(self, driver: Any) -> bool:
        """Clicks 'Continue' button on intermediate wizard pages."""
        continue_selectors = [
            "//button[contains(., 'Continue')]",
            "//button[contains(., 'Review your application')]",
            "//button[contains(@class, 'ia-continueButton')]",
        ]
        for sel in continue_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                text = btn.text.strip().lower()
                if "submit" in text:
                    return False
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False

    def submit(self, job: Job) -> bool:
        """Clicks final 'Submit your application' button."""
        driver = self.browser.driver
        if not driver:
            return False

        submit_selectors = [
            "//button[contains(., 'Submit your application')]",
            "//button[contains(., 'Submit application')]",
            "//span[contains(., 'Submit your application')]/parent::button",
        ]
        for sel in submit_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False
