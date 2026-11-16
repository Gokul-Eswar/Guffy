"""
Unit Tests for Browser Controller & Universal Form Filler (Ticket 8)
"""

from unittest.mock import MagicMock, patch
import pytest

from Guffy.automation.browser import BrowserController
from Guffy.automation.form_filler import (
    FieldType,
    FormFieldDetector,
    UniversalFormFiller,
)
from Guffy.config import BrowserConfig
from Guffy.core.profile_manager import CandidateProfile


@pytest.fixture
def sample_profile():
    return CandidateProfile(
        personal_info={
            "full_name": "Gokul Eswar",
            "email": "gokul@example.com",
            "phone": "+1-555-0199",
            "location": "San Francisco, CA",
            "linkedin_url": "https://linkedin.com/in/gokuleswar",
            "github_url": "https://github.com/gokuleswar",
            "portfolio_url": "https://gokul.dev",
            "resume_path": "",
        },
        preferences={
            "target_titles": ["Senior Python Engineer"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "min_base_salary_usd": 160000,
        },
        skills={
            "languages": ["Python", "Go"],
            "frameworks": ["FastAPI", "React"],
            "cloud_and_tools": ["Docker", "AWS"],
        },
        screening_answers={
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "notice_period": "2 weeks",
            "expected_salary": "$170,000",
            "years_of_experience": {"python": 6.0},
            "custom_qa": {
                "What is your favorite programming language?": "Python",
            },
        },
    )


def test_form_field_detector_classification():
    # Identity & contact
    assert FormFieldDetector.classify_field("first_name text input") == FieldType.FIRST_NAME
    assert FormFieldDetector.classify_field("applicant lname") == FieldType.LAST_NAME
    assert FormFieldDetector.classify_field("user full_name") == FieldType.FULL_NAME
    assert FormFieldDetector.classify_field("enter your email address") == FieldType.EMAIL
    assert FormFieldDetector.classify_field("mobile phone number") == FieldType.PHONE

    # Links
    assert FormFieldDetector.classify_field("linkedin profile url") == FieldType.LINKEDIN
    assert FormFieldDetector.classify_field("github repository link") == FieldType.GITHUB
    assert FormFieldDetector.classify_field("personal portfolio site") == FieldType.PORTFOLIO

    # File / Resume
    assert FormFieldDetector.classify_field("attach resume or cv", element_type="file") == FieldType.RESUME

    # Screening & Auth
    assert FormFieldDetector.classify_field("are you legally authorized to work in the united states?") == FieldType.WORK_AUTH
    assert FormFieldDetector.classify_field("will you now or in the future require visa sponsorship?") == FieldType.SPONSORSHIP
    assert FormFieldDetector.classify_field("how many years of experience do you have with python?") == FieldType.EXPERIENCE_YEARS
    assert FormFieldDetector.classify_field("what is your notice period in weeks?") == FieldType.NOTICE_PERIOD
    assert FormFieldDetector.classify_field("salary expectations (annual usd)") == FieldType.SALARY


def test_browser_controller_options_build():
    config = BrowserConfig(
        headless=True,
        user_data_dir="./test_browser_profile",
        implicit_wait_seconds=3,
        page_load_timeout_seconds=20,
    )
    controller = BrowserController(config=config)
    options = controller.build_chrome_options()

    args = options.arguments
    assert any("--user-data-dir=" in arg for arg in args)
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--headless=new" in args


def test_universal_form_filler_value_resolution(sample_profile):
    mock_browser = MagicMock(spec=BrowserController)
    filler = UniversalFormFiller(browser=mock_browser, profile=sample_profile)

    # Text resolutions
    assert filler._resolve_value_for_field(FieldType.FIRST_NAME, "first_name") == "Gokul"
    assert filler._resolve_value_for_field(FieldType.LAST_NAME, "last_name") == "Eswar"
    assert filler._resolve_value_for_field(FieldType.EMAIL, "email") == "gokul@example.com"
    assert filler._resolve_value_for_field(FieldType.PHONE, "phone") == "+1-555-0199"
    assert filler._resolve_value_for_field(FieldType.LINKEDIN, "linkedin") == "https://linkedin.com/in/gokuleswar"
    assert filler._resolve_value_for_field(FieldType.GITHUB, "github") == "https://github.com/gokuleswar"

    # Cover letter
    assert filler._resolve_value_for_field(FieldType.COVER_LETTER, "cover_letter", cover_letter="My tailored letter") == "My tailored letter"

    # Screening questions
    auth_val = filler._resolve_value_for_field(FieldType.WORK_AUTH, "are you authorized to work in us?")
    assert auth_val == "Yes"

    spons_val = filler._resolve_value_for_field(FieldType.SPONSORSHIP, "do you require visa sponsorship?")
    assert spons_val == "No"


def test_universal_form_filler_dom_fill(sample_profile):
    mock_browser = MagicMock(spec=BrowserController)
    mock_driver = MagicMock()
    mock_browser.driver = mock_driver

    # Mock elements in DOM
    def create_mock_elem(tag, elem_type, name, initial_val=""):
        elem = MagicMock()
        elem.tag_name = tag
        elem.is_displayed.return_value = True
        elem.get_attribute.side_effect = lambda attr: {
            "type": elem_type,
            "name": name,
            "id": name,
            "placeholder": name,
            "value": initial_val,
        }.get(attr, "")
        elem.parent = mock_driver
        elem.find_element.side_effect = Exception("no ancestor label")
        return elem

    first_name_input = create_mock_elem("input", "text", "first_name")
    last_name_input = create_mock_elem("input", "text", "last_name")
    email_input = create_mock_elem("input", "email", "email_address")
    mock_driver.find_elements.side_effect = lambda by, query: {
        "//input[@type='file']": [],
        "//input[not(@type='hidden') and not(@type='file') and not(@type='submit') and not(@type='button')] | //textarea": [
            first_name_input,
            last_name_input,
            email_input,
        ],
        "//label[@for='first_name']": [],
        "//label[@for='last_name']": [],
        "//label[@for='email_address']": [],
    }.get(query, [])

    filler = UniversalFormFiller(browser=mock_browser, profile=sample_profile)
    report = filler.fill_all_fields()

    assert len(report["filled_fields"]) == 3
    types_filled = [f["type"] for f in report["filled_fields"]]
    assert "first_name" in types_filled
    assert "last_name" in types_filled
    assert "email" in types_filled

    # Verify browser human_type was called for elements
    assert mock_browser.human_type.call_count == 3
