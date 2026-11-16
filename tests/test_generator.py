"""
Unit Tests for Ticket 4: Tailored Content & Screening Q&A Synthesizer
"""

import json
import pytest

from huntflow.core.database import Job, Application
from huntflow.core.profile_manager import CandidateProfile
from huntflow.core.generator import (
    CoverLetterGenerator,
    PitchSynthesizer,
    QASynthesizer,
    stage_application_content,
)


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        personal_info={
            "full_name": "Gokul Eswar",
            "email": "gokul@example.com",
            "phone": "+1 555-0199",
            "location": "San Francisco, CA",
            "linkedin_url": "https://www.linkedin.com/in/gokul-eswar",
            "github_url": "https://github.com/gokul-eswar",
            "portfolio_url": "https://gokul-eswar.dev",
        },
        preferences={
            "target_titles": [
                "Full Stack Software Engineer",
                "Backend Engineer",
                "Python Developer",
            ],
            "excluded_titles": ["Intern"],
            "target_locations": ["Remote"],
            "remote_only": True,
            "min_base_salary_usd": 120000,
            "blacklisted_companies": ["SpamCorp"],
        },
        skills={
            "languages": ["Python", "TypeScript", "SQL"],
            "frameworks": ["FastAPI", "React", "Django"],
            "cloud_and_tools": ["Docker", "AWS", "PostgreSQL", "Git"],
        },
        screening_answers={
            "work_authorization": "Yes, I am authorized to work in the US.",
            "require_sponsorship": "No, I do not require sponsorship now or in the future.",
            "notice_period": "2 weeks",
            "expected_salary": "$135,000",
            "years_of_experience": {
                "python": 4.0,
                "fastapi": 3.0,
                "react": 3.0,
                "sql": 4.0,
                "aws": 2.5,
            },
            "custom_qa": {
                "Why do you want to work here?": "I am passionate about high-impact distributed systems and developer tooling.",
                "Tell us about a recent project you built": "I architected and built an automated high-throughput data processing pipeline using FastAPI, Celery, and PostgreSQL.",
            },
        },
    )


def test_cover_letter_generation(sample_profile):
    generator = CoverLetterGenerator(sample_profile)
    cover_letter = generator.generate(
        job_title="Senior Backend Engineer",
        company_name="CloudScale Technologies",
        job_description="We need a strong backend engineer experienced in Python, FastAPI, and PostgreSQL.",
        matched_skills=["python", "fastapi", "postgresql"],
    )

    assert "Dear Hiring Team at CloudScale Technologies," in cover_letter
    assert "Senior Backend Engineer" in cover_letter
    assert "CloudScale Technologies" in cover_letter
    assert "Gokul Eswar" in cover_letter
    assert "gokul@example.com" in cover_letter
    assert "+1 555-0199" in cover_letter
    # Verify technical skills inclusion
    assert "Python" in cover_letter or "Fastapi" in cover_letter or "Postgresql" in cover_letter
    # Verify project highlight inclusion from custom_qa
    assert "automated high-throughput data processing pipeline" in cover_letter


def test_cover_letter_inferred_skills(sample_profile):
    generator = CoverLetterGenerator(sample_profile)
    # Don't pass matched_skills directly; generator should infer them from description
    job_desc = "Looking for a Python Developer with Docker and AWS experience."
    cover_letter = generator.generate(
        job_title="Python Developer",
        company_name="InnovateLab",
        job_description=job_desc,
    )

    assert "Python Developer" in cover_letter
    assert "InnovateLab" in cover_letter
    assert "Python" in cover_letter


def test_pitch_synthesizer_wellfound(sample_profile):
    synthesizer = PitchSynthesizer(sample_profile)
    pitch = synthesizer.generate_pitch(
        job_title="Full Stack Engineer",
        company_name="NextGen AI",
        matched_skills=["python", "react", "fastapi"],
    )

    assert "NextGen AI" in pitch
    assert "Full Stack Engineer" in pitch
    assert "4+ years" in pitch or "3+ years" in pitch
    assert "Python" in pitch or "React" in pitch
    assert len(pitch.split()) <= 100  # Should be concise (around 40-70 words)


def test_qa_synthesizer_exact_and_fuzzy_custom_qa(sample_profile):
    qa = QASynthesizer(sample_profile)

    # Exact custom Q&A
    ans1 = qa.answer_question("Why do you want to work here?")
    assert "distributed systems" in ans1

    # Slightly altered / fuzzy custom Q&A
    ans2 = qa.answer_question("Why do you want to work at this company?")
    assert "distributed systems" in ans2

    ans3 = qa.answer_question("Tell us about a recent project you built")
    assert "automated high-throughput data processing pipeline" in ans3


def test_qa_synthesizer_work_authorization_and_sponsorship(sample_profile):
    qa = QASynthesizer(sample_profile)

    # Sponsorship questions
    assert "No" in qa.answer_question("Will you now or in the future require visa sponsorship?")
    assert "No" in qa.answer_question("Do you require sponsorship for an employment visa?")

    # Work authorization questions
    assert "Yes" in qa.answer_question("Are you legally authorized to work in the United States?")
    assert "Yes" in qa.answer_question("Do you have legal right to work in the US?")


def test_qa_synthesizer_notice_period_and_salary(sample_profile):
    qa = QASynthesizer(sample_profile)

    # Notice period
    assert qa.answer_question("What is your notice period?") == "2 weeks"
    assert qa.answer_question("When can you start?") == "2 weeks"

    # Salary expectations
    assert "$135,000" in qa.answer_question("What is your desired salary expectation?")
    assert "$135,000" in qa.answer_question("Expected compensation?")


def test_qa_synthesizer_years_of_experience(sample_profile):
    qa = QASynthesizer(sample_profile)

    # Specific technology YoE
    assert qa.answer_question("How many years of experience do you have with Python?") == "4"
    assert qa.answer_question("Years of FastAPI experience?") == "3"
    assert qa.answer_question("How many years have you used React?") == "3"
    assert qa.answer_question("AWS experience in years?") == "2.5"

    # Total / general software engineering experience
    total_yoe = qa.answer_question("Total years of software engineering experience?")
    assert total_yoe == "4"


def test_qa_synthesizer_links_and_remote(sample_profile):
    qa = QASynthesizer(sample_profile)

    # Links
    assert qa.answer_question("LinkedIn Profile URL") == "https://www.linkedin.com/in/gokul-eswar"
    assert qa.answer_question("GitHub profile link") == "https://github.com/gokul-eswar"
    assert qa.answer_question("Portfolio URL / Website") == "https://gokul-eswar.dev"

    # Remote preference
    assert qa.answer_question("Are you comfortable working remotely?") == "Yes"
    assert qa.answer_question("Are you willing to relocate?") == "No"


def test_stage_application_content_helper(sample_profile):
    job = Job(
        id="job-abc-123",
        title="Full Stack Software Engineer",
        company="RocketShip Inc",
        location="Remote",
        remote_type="Remote",
        portal="wellfound",
        job_url="https://wellfound.com/jobs/123",
        description="Looking for Full Stack engineer with Python, FastAPI, and React.",
        matched_skills=json.dumps(["python", "fastapi", "react"]),
    )

    questions = [
        "Will you now or in the future require visa sponsorship?",
        "Are you legally authorized to work in the US?",
        "How many years of experience do you have with Python?",
        "What is your expected salary?",
    ]

    app = stage_application_content(
        job=job,
        profile=sample_profile,
        screening_questions=questions,
    )

    assert job.status == "staged"
    assert app.status == "staged"
    assert app.job_id == job.id
    assert app.portal == "wellfound"
    assert "RocketShip Inc" in app.tailored_cover_letter
    assert "Full Stack Software Engineer" in app.tailored_cover_letter
    assert "RocketShip Inc" in app.tailored_pitch
    
    # Verify submitted_qa
    answers = json.loads(app.submitted_qa)
    assert len(answers) == 4
    assert "No" in answers["Will you now or in the future require visa sponsorship?"]
    assert "Yes" in answers["Are you legally authorized to work in the US?"]
    assert answers["How many years of experience do you have with Python?"] == "4"
    assert "$135,000" in answers["What is your expected salary?"]
