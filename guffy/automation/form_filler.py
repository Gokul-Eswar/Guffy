"""
Universal Form Filler & Heuristic Field Detector (Ticket 8)

Features:
- Heuristic field classification for:
  - First Name, Last Name, Full Name
  - Email Address
  - Phone Number
  - Resume / CV file upload
  - LinkedIn Profile, GitHub, Portfolio URLs
  - Current Company, Headline / Title
  - Cover Letter / Pitch Textarea
  - Work Authorization & Sponsorship Questions (Radio/Dropdown/Checkbox)
- Intelligent Dropdown option selector (by text, value, or regex match).
- Form filler execution engine bridging CandidateProfile + QASynthesizer to DOM elements.
"""

from enum import Enum
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select

from guffy.automation.browser import BrowserController
from guffy.core.generator import QASynthesizer
from guffy.core.profile_manager import CandidateProfile

logger = logging.getLogger(__name__)


class FieldType(str, Enum):
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    RESUME = "resume"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    PORTFOLIO = "portfolio"
    LOCATION = "location"
    COMPANY = "company"
    HEADLINE = "headline"
    COVER_LETTER = "cover_letter"
    SALARY = "salary"
    NOTICE_PERIOD = "notice_period"
    WORK_AUTH = "work_authorization"
    SPONSORSHIP = "sponsorship"
    EXPERIENCE_YEARS = "experience_years"
    CUSTOM_QUESTION = "custom_question"
    UNKNOWN = "unknown"


class FormFieldDetector:
    """
    Analyzes DOM element attributes (name, id, placeholder, aria-label, label text)
    to classify field purpose.
    """

    PATTERNS: Dict[FieldType, List[str]] = {
        FieldType.FIRST_NAME: [
            r"first[_\-\s]*name",
            r"given[_\-\s]*name",
            r"fname",
            r"first",
        ],
        FieldType.LAST_NAME: [
            r"last[_\-\s]*name",
            r"sur[_\-\s]*name",
            r"family[_\-\s]*name",
            r"lname",
            r"last",
        ],
        FieldType.FULL_NAME: [
            r"full[_\-\s]*name",
            r"^name$",
            r"your[_\-\s]*name",
            r"candidate[_\-\s]*name",
        ],
        FieldType.EMAIL: [
            r"email",
            r"e-mail",
            r"mail",
        ],
        FieldType.PHONE: [
            r"phone",
            r"mobile",
            r"cell",
            r"tel",
            r"contact[_\-\s]*number",
        ],
        FieldType.RESUME: [
            r"resume",
            r"cv",
            r"curriculum[_\-\s]*vitae",
            r"attach[_\-\s]*resume",
        ],
        FieldType.LINKEDIN: [
            r"linkedin",
            r"linked[_\-\s]*in",
        ],
        FieldType.GITHUB: [
            r"github",
            r"git[_\-\s]*hub",
        ],
        FieldType.PORTFOLIO: [
            r"portfolio",
            r"website",
            r"personal[_\-\s]*site",
            r"web[_\-\s]*page",
        ],
        FieldType.LOCATION: [
            r"city",
            r"location",
            r"address",
            r"state",
            r"residence",
        ],
        FieldType.COMPANY: [
            r"current[_\-\s]*company",
            r"employer",
            r"organization",
        ],
        FieldType.HEADLINE: [
            r"headline",
            r"current[_\-\s]*title",
            r"current[_\-\s]*role",
            r"summary",
        ],
        FieldType.COVER_LETTER: [
            r"cover[_\-\s]*letter",
            r"pitch",
            r"additional[_\-\s]*information",
            r"why[_\-\s]*us",
            r"note",
            r"message[_\-\s]*to[_\-\s]*hiring[_\-\s]*manager",
        ],
        FieldType.SALARY: [
            r"salary",
            r"compensation",
            r"pay",
            r"rate",
            r"expectation",
        ],
        FieldType.NOTICE_PERIOD: [
            r"notice[_\-\s]*period",
            r"start[_\-\s]*date",
            r"available[_\-\s]*to[_\-\s]*start",
            r"availability",
        ],
        FieldType.WORK_AUTH: [
            r"authorized[_\-\s]*to[_\-\s]*work",
            r"work[_\-\s]*authorization",
            r"legally[_\-\s]*authorized",
            r"right[_\-\s]*to[_\-\s]*work",
        ],
        FieldType.SPONSORSHIP: [
            r"sponsorship",
            r"require[_\-\s]*visa",
            r"visa[_\-\s]*sponsorship",
            r"future[_\-\s]*sponsorship",
        ],
        FieldType.EXPERIENCE_YEARS: [
            r"years[_\-\s]*of[_\-\s]*experience",
            r"experience[_\-\s]*in[_\-\s]*years",
            r"how[_\-\s]*many[_\-\s]*years",
        ],
    }

    @classmethod
    def extract_element_context(cls, element: WebElement) -> str:
        """Collects tag name, attributes, placeholders, labels, and aria values."""
        context_parts = []
        try:
            tag = element.tag_name
            context_parts.append(tag)
        except Exception:
            pass

        for attr in ["name", "id", "placeholder", "aria-label", "aria-describedby", "class", "title"]:
            try:
                val = element.get_attribute(attr)
                if val:
                    context_parts.append(val)
            except Exception:
                pass

        # Check associated <label>
        try:
            elem_id = element.get_attribute("id")
            if elem_id:
                driver = element.parent
                labels = driver.find_elements(By.XPATH, f"//label[@for='{elem_id}']")
                for lbl in labels:
                    context_parts.append(lbl.text)
        except Exception:
            pass

        # Check parent label or ancestor text
        try:
            parent_text = element.find_element(By.XPATH, "./ancestor::label[1]").text
            if parent_text:
                context_parts.append(parent_text)
        except Exception:
            pass

        return " ".join(context_parts).lower()

    @classmethod
    def classify_field(cls, context_text: str, element_type: str = "text") -> FieldType:
        """Matches context string against field patterns with precedence."""
        lowered = context_text.lower()

        # Check file input first
        if "file" in element_type.lower() or "resume" in lowered or "cv" in lowered:
            for pat in cls.PATTERNS[FieldType.RESUME]:
                if re.search(pat, lowered):
                    return FieldType.RESUME

        # Check work auth & sponsorship early (multi-word phrases)
        for pat in cls.PATTERNS[FieldType.WORK_AUTH]:
            if re.search(pat, lowered):
                return FieldType.WORK_AUTH
        for pat in cls.PATTERNS[FieldType.SPONSORSHIP]:
            if re.search(pat, lowered):
                return FieldType.SPONSORSHIP
        for pat in cls.PATTERNS[FieldType.NOTICE_PERIOD]:
            if re.search(pat, lowered):
                return FieldType.NOTICE_PERIOD
        for pat in cls.PATTERNS[FieldType.EXPERIENCE_YEARS]:
            if re.search(pat, lowered):
                return FieldType.EXPERIENCE_YEARS

        # Check specific identity/social fields
        for field_type in [
            FieldType.LINKEDIN,
            FieldType.GITHUB,
            FieldType.PORTFOLIO,
            FieldType.FIRST_NAME,
            FieldType.LAST_NAME,
            FieldType.FULL_NAME,
            FieldType.EMAIL,
            FieldType.PHONE,
            FieldType.SALARY,
            FieldType.LOCATION,
            FieldType.COMPANY,
            FieldType.HEADLINE,
            FieldType.COVER_LETTER,
        ]:
            for pat in cls.PATTERNS[field_type]:
                if re.search(pat, lowered):
                    return field_type

        return FieldType.CUSTOM_QUESTION if "?" in lowered or len(lowered) > 20 else FieldType.UNKNOWN


class UniversalFormFiller:
    """
    Inspects application forms and fills candidate information into inputs, textareas,
    dropdowns, radios, and file upload fields.
    """

    def __init__(
        self,
        browser: BrowserController,
        profile: CandidateProfile,
        resume_path: Optional[str] = None,
        qa_synthesizer: Optional[QASynthesizer] = None,
    ):
        self.browser = browser
        self.profile = profile
        self.resume_path = resume_path or getattr(profile.personal_info, "resume_path", None)
        self.qa_synthesizer = qa_synthesizer or QASynthesizer(profile)

    def fill_all_fields(
        self,
        cover_letter: Optional[str] = None,
        pitch_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detects and fills all reachable input fields on the current page.
        Returns a summary report of filled fields.
        """
        driver = self.browser.driver
        if not driver:
            raise RuntimeError("Browser is not active.")

        report = {
            "filled_fields": [],
            "skipped_fields": [],
            "resume_uploaded": False,
        }

        # 1. Handle file upload (Resume/CV)
        if self.resume_path and Path(self.resume_path).exists():
            file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
            for file_elem in file_inputs:
                try:
                    ctx = FormFieldDetector.extract_element_context(file_elem)
                    field_type = FormFieldDetector.classify_field(ctx, element_type="file")
                    if field_type == FieldType.RESUME or not file_inputs or len(file_inputs) == 1:
                        file_elem.send_keys(str(Path(self.resume_path).resolve()))
                        report["resume_uploaded"] = True
                        report["filled_fields"].append({"type": "resume", "path": self.resume_path})
                        self.browser.random_delay(0.3, 0.7)
                        break
                except Exception as e:
                    logger.debug(f"File upload attempt failed: {e}")

        # 2. Text inputs & textareas
        inputs = driver.find_elements(By.XPATH, "//input[not(@type='hidden') and not(@type='file') and not(@type='submit') and not(@type='button')] | //textarea")
        for elem in inputs:
            try:
                if not elem.is_displayed():
                    continue

                ctx = FormFieldDetector.extract_element_context(elem)
                elem_type = elem.get_attribute("type") or "text"
                field_type = FormFieldDetector.classify_field(ctx, element_type=elem_type)

                # Skip if already filled
                current_val = elem.get_attribute("value") or ""
                if current_val.strip() and field_type not in (FieldType.COVER_LETTER,):
                    continue

                value_to_fill = self._resolve_value_for_field(
                    field_type=field_type,
                    context=ctx,
                    cover_letter=cover_letter,
                    pitch_note=pitch_note,
                )

                if value_to_fill:
                    self.browser.scroll_into_view(elem)
                    self.browser.human_type(elem, value_to_fill)
                    report["filled_fields"].append({"type": field_type.value, "value": value_to_fill})
                else:
                    report["skipped_fields"].append({"type": field_type.value, "context": ctx[:60]})
            except Exception as e:
                logger.debug(f"Error filling element: {e}")

        # 3. Handle Select / Dropdown elements
        selects = driver.find_elements(By.TAG_NAME, "select")
        for sel_elem in selects:
            try:
                if not sel_elem.is_displayed():
                    continue
                ctx = FormFieldDetector.extract_element_context(sel_elem)
                field_type = FormFieldDetector.classify_field(ctx, element_type="select")
                matched_opt = self._resolve_select_option(sel_elem, field_type, ctx)
                if matched_opt:
                    report["filled_fields"].append({"type": field_type.value, "select_option": matched_opt})
            except Exception as e:
                logger.debug(f"Error resolving select dropdown: {e}")

        return report

    def _resolve_value_for_field(
        self,
        field_type: FieldType,
        context: str,
        cover_letter: Optional[str] = None,
        pitch_note: Optional[str] = None,
    ) -> Optional[str]:
        """Maps FieldType and candidate profile data to input text."""
        info = self.profile.personal_info
        name_parts = info.full_name.split() if info.full_name else ["", ""]
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        if field_type == FieldType.FIRST_NAME:
            return first_name
        elif field_type == FieldType.LAST_NAME:
            return last_name
        elif field_type == FieldType.FULL_NAME:
            return info.full_name
        elif field_type == FieldType.EMAIL:
            return info.email
        elif field_type == FieldType.PHONE:
            return info.phone
        elif field_type == FieldType.LINKEDIN:
            return info.linkedin_url or ""
        elif field_type == FieldType.GITHUB:
            return info.github_url or ""
        elif field_type == FieldType.PORTFOLIO:
            return info.portfolio_url or ""
        elif field_type == FieldType.LOCATION:
            return info.location or "Remote"
        elif field_type == FieldType.HEADLINE:
            return self.profile.preferences.target_titles[0] if self.profile.preferences.target_titles else "Software Engineer"
        elif field_type == FieldType.COVER_LETTER:
            return cover_letter or pitch_note or ""
        elif field_type == FieldType.SALARY:
            return self.qa_synthesizer.resolve_question("salary expectation")
        elif field_type == FieldType.NOTICE_PERIOD:
            return self.qa_synthesizer.resolve_question("notice period")
        elif field_type in (FieldType.WORK_AUTH, FieldType.SPONSORSHIP, FieldType.EXPERIENCE_YEARS, FieldType.CUSTOM_QUESTION):
            return self.qa_synthesizer.resolve_question(context)
        return None

    def _resolve_select_option(self, select_elem: WebElement, field_type: FieldType, context: str) -> Optional[str]:
        """Chooses best matching option in a <select> element."""
        sel = Select(select_elem)
        options = [opt.text.strip() for opt in sel.options if opt.text.strip()]

        if not options:
            return None

        desired_answer = ""
        if field_type == FieldType.WORK_AUTH:
            desired_answer = self.profile.screening_answers.work_authorization or "Yes"
        elif field_type == FieldType.SPONSORSHIP:
            desired_answer = self.profile.screening_answers.require_sponsorship or "No"
        elif field_type == FieldType.NOTICE_PERIOD:
            desired_answer = self.profile.screening_answers.notice_period or "Immediate"
        else:
            desired_answer = self.qa_synthesizer.resolve_question(context)

        # Match option containing or equating to desired_answer
        for opt in sel.options:
            text = opt.text.strip().lower()
            if desired_answer.lower() == text or (desired_answer.lower() in text and len(desired_answer) > 2):
                sel.select_by_visible_text(opt.text.strip())
                return opt.text.strip()

        # Fallback to Yes/No matching if desired answer is Yes/No
        if desired_answer.lower() in ("yes", "y", "true"):
            for opt in sel.options:
                if opt.text.strip().lower() in ("yes", "y", "authorized", "eligible"):
                    sel.select_by_visible_text(opt.text.strip())
                    return opt.text.strip()
        elif desired_answer.lower() in ("no", "n", "false"):
            for opt in sel.options:
                if opt.text.strip().lower() in ("no", "n", "none"):
                    sel.select_by_visible_text(opt.text.strip())
                    return opt.text.strip()

        return None
