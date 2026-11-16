"""
LinkedIn Easy Apply Multi-Step Modal Applier (Ticket 9)

Implements:
- LinkedInApplier:
  Handles LinkedIn's multi-step Easy Apply dialog (Contact info, Resume, Additional questions, Review),
  fills each step sequentially using UniversalFormFiller, advances using 'Next' / 'Review',
  halts at the final review step before 'Submit application', and captures staging screenshot.
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


class LinkedInApplier:
    """
    Automates multi-step LinkedIn Easy Apply modal flows while preserving HITL safety.
    """

    def __init__(self, browser: BrowserController, profile: CandidateProfile, max_steps: int = 10):
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
        Navigates to LinkedIn job, clicks 'Easy Apply', steps through the wizard
        until the final review step, and halts without submitting.
        """
        driver = self.browser.start()
        driver.get(job.job_url)

        # 1. Click Easy Apply button
        if not self._click_easy_apply(driver):
            return StagingResult(
                job_id=job.id,
                portal="linkedin",
                status="failed",
                success=False,
                error_message="Easy Apply button not found or not active.",
            )

        all_filled_fields: List[Dict[str, Any]] = []
        step = 0

        # 2. Loop through modal steps until Review or Submit button is reached
        while step < self.max_steps:
            step += 1
            # Fill inputs in current step
            report = self.form_filler.fill_all_fields(
                cover_letter=cover_letter,
                pitch_note=pitch_note,
            )
            all_filled_fields.extend(report.get("filled_fields", []))

            # Check if we reached final submission step
            if self._is_review_or_submit_step(driver):
                logger.info(f"LinkedIn Easy Apply reached final step at iteration {step}.")
                break

            # Click Next / Continue button to proceed to next step
            advanced = self._click_next(driver)
            if not advanced:
                # No Next button found, we might already be on the final screen
                break
            time.sleep(1)

        # 3. Capture staging screenshot before submitting
        if screenshot_path:
            try:
                self.browser.take_screenshot(screenshot_path)
            except Exception as e:
                logger.warning(f"Could not save LinkedIn screenshot: {e}")

        return StagingResult(
            job_id=job.id,
            portal="linkedin",
            status="staged",
            success=True,
            fields_filled=all_filled_fields,
            screenshot_path=screenshot_path,
            tailored_cover_letter=cover_letter,
            tailored_pitch=pitch_note,
        )

    def _click_easy_apply(self, driver: Any) -> bool:
        """Finds and clicks LinkedIn Easy Apply trigger button."""
        apply_selectors = [
            "//button[contains(@class, 'jobs-apply-button')]",
            "//button[contains(., 'Easy Apply')]",
            "//button[contains(., 'Apply now')]",
        ]
        for sel in apply_selectors:
            buttons = driver.find_elements("xpath", sel)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False

    def _is_review_or_submit_step(self, driver: Any) -> bool:
        """Checks if current modal screen contains 'Submit application' or Review stage."""
        submit_selectors = [
            "//button[contains(., 'Submit application')]",
            "//button[@aria-label='Submit application']",
            "//footer//button[contains(., 'Submit')]",
        ]
        for sel in submit_selectors:
            elems = driver.find_elements("xpath", sel)
            if any(e.is_displayed() for e in elems):
                return True
        return False

    def _click_next(self, driver: Any) -> bool:
        """Finds and clicks 'Next' or 'Continue to next step' button."""
        next_selectors = [
            "//button[contains(., 'Next')]",
            "//button[contains(., 'Continue to next step')]",
            "//button[contains(., 'Review')]",
            "//button[@aria-label='Continue to next step']",
            "//footer//button[contains(@class, 'artdeco-button--primary')]",
        ]
        for sel in next_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                text = btn.text.strip().lower()
                # Stop if it's the submit application button
                if "submit" in text:
                    return False
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False

    def submit(self, job: Job) -> bool:
        """Executes final click on 'Submit application'."""
        driver = self.browser.driver
        if not driver:
            return False

        submit_selectors = [
            "//button[contains(., 'Submit application')]",
            "//button[@aria-label='Submit application']",
            "//footer//button[contains(., 'Submit')]",
        ]
        for sel in submit_selectors:
            elems = driver.find_elements("xpath", sel)
            for btn in elems:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    return True
        return False
