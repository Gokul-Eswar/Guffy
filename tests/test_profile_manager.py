"""
Unit Tests for Candidate Profile & Resume Ingestion Engine (Ticket 2)
"""

import os
from pathlib import Path
import pytest
import docx
from pypdf import PdfWriter

from huntflow.core.profile_manager import (
    CandidateProfile,
    ProfileManager,
    ResumeParser,
    COMMON_SKILLS_CATALOG,
)


@pytest.fixture
def sample_profile_yaml(tmp_path: Path) -> Path:
    yaml_content = """
personal_info:
  full_name: "Jane Doe"
  email: "jane.doe@example.com"
  phone: "+1 555-0199"
  location: "New York, NY"
  linkedin_url: "https://linkedin.com/in/janedoe"
  github_url: "https://github.com/janedoe"
  portfolio_url: "https://janedoe.dev"
  resume_path: ""

preferences:
  target_titles:
    - "Senior Python Developer"
    - "Backend Engineer"
  excluded_titles:
    - "Intern"
  target_locations:
    - "Remote"
    - "New York"
  remote_only: true
  min_base_salary_usd: 140000
  blacklisted_companies:
    - "ToxicCorp"

skills:
  languages:
    - "Python"
    - "SQL"
  frameworks:
    - "FastAPI"
    - "Django"
  cloud_and_tools:
    - "Docker"
    - "AWS"
    - "PostgreSQL"

screening_answers:
  work_authorization: "Yes"
  require_sponsorship: "No"
  notice_period: "2 weeks"
  expected_salary: "$150,000"
  years_of_experience:
    python: 5
    fastapi: 3
    sql: 5
  custom_qa:
    "Why us?": "Because of your mission and tech stack."
"""
    file_path = tmp_path / "test_profile.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")
    return file_path


@pytest.fixture
def sample_docx_resume(tmp_path: Path) -> Path:
    doc = docx.Document()
    doc.add_heading("Jane Doe - Senior Software Engineer", level=1)
    doc.add_paragraph("Experienced software engineer specializing in Python, FastAPI, Docker, and PostgreSQL.")
    doc.add_paragraph("Architected scalable cloud microservices on AWS with CI/CD and Redis caching.")
    
    # Add a table with skills
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Languages: Python, TypeScript"
    table.rows[0].cells[1].text = "Databases: PostgreSQL, Redis"

    docx_path = tmp_path / "resume.docx"
    doc.save(str(docx_path))
    return docx_path


@pytest.fixture
def sample_txt_resume(tmp_path: Path) -> Path:
    content = """
    Jane Doe
    Full Stack Developer
    
    Summary:
    5 years experience with Python, React, Next.js, FastAPI, Docker, Kubernetes, and AWS.
    Proficient with MySQL, Redis, and Linux system design.
    """
    txt_path = tmp_path / "resume.txt"
    txt_path.write_text(content, encoding="utf-8")
    return txt_path


def test_load_candidate_profile_success(sample_profile_yaml: Path):
    profile = CandidateProfile.load_from_yaml(sample_profile_yaml)
    assert profile.personal_info.full_name == "Jane Doe"
    assert profile.personal_info.email == "jane.doe@example.com"
    assert "Senior Python Developer" in profile.preferences.target_titles
    assert profile.preferences.remote_only is True
    assert profile.preferences.min_base_salary_usd == 140000
    assert "Python" in profile.skills.languages
    assert "FastAPI" in profile.skills.frameworks
    assert "PostgreSQL" in profile.skills.cloud_and_tools
    assert profile.screening_answers.years_of_experience["python"] == 5


def test_load_profile_example_yaml():
    """Verify that the repository's profile.example.yaml is valid."""
    profile_example = Path("profile.example.yaml")
    assert profile_example.exists()
    profile = CandidateProfile.load_from_yaml(profile_example)
    assert profile.personal_info.full_name == "Gokul Eswar"
    assert "Python" in profile.skills.languages
    assert profile.screening_answers.years_of_experience["fastapi"] == 3


def test_invalid_email_validation():
    with pytest.raises(ValueError, match="Invalid email address"):
        CandidateProfile(
            personal_info={
                "full_name": "Test User",
                "email": "not-an-email"
            }
        )


def test_profile_manager_skill_aggregation(sample_profile_yaml: Path):
    pm = ProfileManager(sample_profile_yaml)
    assert pm.profile is not None
    skills = pm.profile.skills.all_skills()
    assert set(skills) == {"Python", "SQL", "FastAPI", "Django", "Docker", "AWS", "PostgreSQL"}


def test_extract_docx_resume_and_skills(sample_docx_resume: Path):
    text = ResumeParser.extract_text(sample_docx_resume)
    assert "Jane Doe" in text
    assert "FastAPI" in text
    assert "PostgreSQL" in text

    skills = ResumeParser.extract_skills(text)
    assert "python" in skills
    assert "fastapi" in skills
    assert "docker" in skills
    assert "aws" in skills
    assert "redis" in skills
    assert "postgresql" in skills
    assert "typescript" in skills


def test_extract_txt_resume_and_skills(sample_txt_resume: Path):
    text = ResumeParser.extract_text(sample_txt_resume)
    skills = ResumeParser.extract_skills(text)
    assert "python" in skills
    assert "react" in skills
    assert "next.js" in skills
    assert "fastapi" in skills
    assert "kubernetes" in skills
    assert "docker" in skills


def test_profile_manager_get_parsed_resume(sample_profile_yaml: Path, sample_docx_resume: Path):
    pm = ProfileManager(sample_profile_yaml)
    parsed = pm.get_parsed_resume(sample_docx_resume)
    assert parsed["word_count"] > 10
    assert "python" in parsed["detected_skills"]
    assert "Python" in parsed["explicit_skills"]
