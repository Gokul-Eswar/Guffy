"""
Tailored Content & Screening Q&A Synthesizer (Ticket 4)

Provides:
- CoverLetterGenerator: Generates highly tailored, professional cover letters
  aligning candidate skills/experience with specific job requirements.
- PitchSynthesizer: Generates concise (3-4 sentences / 100-150 words) pitches
  optimized for Wellfound / AngelList or startup outreach notes.
- QASynthesizer: Resolves and answers job application screening questions using
  both exact and fuzzy semantic heuristics based on CandidateProfile data.
- stage_application_content: Helper to create or populate an Application record
  with generated cover letter, pitch, and answered screening questions.
"""

from difflib import SequenceMatcher
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from huntflow.core.database import Application, Job
from huntflow.core.matcher import MatchEngine, MatchResult
from huntflow.core.profile_manager import CandidateProfile


class CoverLetterGenerator:
    """
    Generates professional, personalized cover letters tailored to a job posting
    and matched candidate qualifications.
    """

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def generate(
        self,
        job_title: str,
        company_name: str,
        job_description: str = "",
        matched_skills: Optional[List[str]] = None,
        missing_skills: Optional[List[str]] = None,
        custom_tone: str = "professional",
    ) -> str:
        """
        Synthesizes a structured 3-4 paragraph tailored cover letter.
        """
        person = self.profile.personal_info
        all_skills = self.profile.skills.all_skills()

        # If matched skills not explicitly passed, infer via MatchEngine
        if matched_skills is None:
            engine = MatchEngine(self.profile)
            extracted = engine.extract_job_skills(job_title, job_description)
            candidate_set = engine._candidate_skills
            matched_skills = [s for s in extracted if s in candidate_set]

        # Select top skills for highlight
        highlight_skills = [s.title() for s in matched_skills[:5]] if matched_skills else [s.title() for s in all_skills[:4]]
        skills_str = ", ".join(highlight_skills) if highlight_skills else "modern software engineering practices"

        # Years of experience synthesis
        yoe_dict = self.profile.screening_answers.years_of_experience
        max_yoe = max(yoe_dict.values(), default=3.0)
        yoe_str = f"{int(max_yoe)}+" if max_yoe >= 1 else "several"

        # Salutation
        salutation = f"Dear Hiring Team at {company_name},"

        # Opening paragraph
        opening = (
            f"I am writing to express my strong enthusiasm for the {job_title} role at {company_name}. "
            f"With over {yoe_str} years of engineering experience specializing in {skills_str}, "
            f"I am eager to contribute to your team's mission and engineering excellence."
        )

        # Body paragraph 1: Technical alignment & impact
        if matched_skills:
            body_1 = (
                f"Throughout my career, I have focused on designing scalable architectures and delivering robust solutions. "
                f"My background directly aligns with your tech stack, notably with hands-on expertise in {skills_str}. "
                f"I take pride in writing clean, well-tested code and architecting reliable distributed services that drive measurable business outcomes."
            )
        else:
            body_1 = (
                f"Throughout my background in software engineering, I have focused on solving complex technical challenges "
                f"and delivering scalable, high-quality applications. My core expertise in {skills_str} allows me "
                f"to quickly master domain problems and ship impactful features."
            )

        # Body paragraph 2: Custom narrative / Project highlight if available
        custom_proj = self.profile.screening_answers.custom_qa.get("Tell us about a recent project you built")
        if custom_proj:
            body_2 = (
                f"In my recent work, {custom_proj.strip()} "
                f"I bring this same problem-solving mindset and dedication to operational excellence to {company_name}."
            )
        else:
            body_2 = (
                f"I thrive in collaborative, high-ownership environments where engineers actively contribute to product direction "
                f"and technical standards. I am excited by what {company_name} is building and would love the opportunity "
                f"to bring my expertise and passion to your engineering team."
            )

        # Closing paragraph & sign-off
        closing = (
            f"Thank you for your time and consideration. I welcome the opportunity to discuss how my experience and skills "
            f"align with {company_name}'s goals. You can reach me via email at {person.email}"
            + (f" or by phone at {person.phone}." if person.phone else ".")
        )

        signoff = f"Sincerely,\n{person.full_name}"

        # Combine paragraphs
        letter = f"{salutation}\n\n{opening}\n\n{body_1}\n\n{body_2}\n\n{closing}\n\n{signoff}"
        return letter


class PitchSynthesizer:
    """
    Synthesizes punchy, high-conversion startup pitches (3-4 sentences / 100-150 words)
    specifically designed for Wellfound (AngelList), Y Combinator Work at a Startup,
    and direct recruiter outreach.
    """

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def generate_pitch(
        self,
        job_title: str,
        company_name: str,
        matched_skills: Optional[List[str]] = None,
        max_sentences: int = 4,
    ) -> str:
        """
        Produces a concise 3-4 sentence pitch tailored to the role and company.
        """
        person = self.profile.personal_info
        all_skills = self.profile.skills.all_skills()

        highlight_skills = [s.title() for s in matched_skills[:3]] if matched_skills else [s.title() for s in all_skills[:3]]
        skills_str = "/".join(highlight_skills) if highlight_skills else "Full-Stack Development"

        yoe_dict = self.profile.screening_answers.years_of_experience
        max_yoe = max(yoe_dict.values(), default=3.0)
        yoe_str = f"{int(max_yoe)}+" if max_yoe >= 1 else "3+"

        # Sentence 1: Strong hook with candidate role & relevant skillset
        s1 = f"Hi {company_name} team — I am a {skills_str} engineer with {yoe_str} years of experience building scalable, high-impact systems."

        # Sentence 2: Specific alignment / value proposition
        if matched_skills:
            top_tech = ", ".join(s.title() for s in matched_skills[:3])
            s2 = f"My hands-on background in {top_tech} aligns directly with what you are seeking for the {job_title} role."
        else:
            s2 = f"I am deeply impressed by what {company_name} is building and would love to bring my software engineering background to the {job_title} role."

        # Sentence 3: Impact / speed of delivery
        s3 = "I pride myself on rapid execution, strong product intuition, and writing maintainable code from day one."

        # Sentence 4: Low-friction call to action
        s4 = f"I'd love to connect briefly to discuss how I can help accelerate your engineering roadmap!"

        sentences = [s1, s2, s3, s4][:max_sentences]
        return " ".join(sentences)


class QASynthesizer:
    """
    Resolves job application screening questions using a combination of:
    1. Exact key match from CandidateProfile.screening_answers
    2. Heuristic regex and semantic pattern matching for common job form questions:
       - Work authorization & Sponsorship (visa, legal right to work)
       - Years of experience with specific technologies (e.g., Python, React, AWS)
       - Salary expectations (currency, range, floor)
       - Notice period / start date availability
       - Links (LinkedIn, GitHub, Portfolio)
    3. Fuzzy string matching against profile.screening_answers.custom_qa
    """

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def answer_question(self, question: str, default: Optional[str] = None) -> str:
        """
        Returns the best matched answer for a given screening question string.
        """
        q_clean = question.strip()
        q_lower = q_clean.lower()
        answers = self.profile.screening_answers
        person = self.profile.personal_info

        # -------------------------------------------------------------
        # 1. Direct / Fuzzy custom Q&A match
        # -------------------------------------------------------------
        if answers.custom_qa:
            # Check exact match
            for saved_q, ans in answers.custom_qa.items():
                if q_lower == saved_q.strip().lower():
                    return ans

            # Check similarity matching (> 0.70 ratio)
            best_match_q = None
            highest_ratio = 0.0
            for saved_q in answers.custom_qa.keys():
                ratio = SequenceMatcher(None, q_lower, saved_q.strip().lower()).ratio()
                if ratio > highest_ratio:
                    highest_ratio = ratio
                    best_match_q = saved_q

            if highest_ratio >= 0.70 and best_match_q:
                return answers.custom_qa[best_match_q]

        # -------------------------------------------------------------
        # 2. Sponsorship / Visa requirements
        # e.g., "Will you now or in the future require visa sponsorship?", "Do you require sponsorship?"
        # -------------------------------------------------------------
        if any(keyword in q_lower for keyword in ["require sponsorship", "require visa", "visa sponsorship", "need sponsorship"]):
            return answers.require_sponsorship

        # -------------------------------------------------------------
        # 3. Work Authorization / Legal Right to Work
        # e.g., "Are you legally authorized to work in the US?", "Authorized to work in..."
        # -------------------------------------------------------------
        if any(keyword in q_lower for keyword in ["legally authorized", "authorized to work", "work authorization", "legal right to work"]):
            return answers.work_authorization

        # -------------------------------------------------------------
        # 4. Notice Period & Availability / Start Date
        # e.g., "What is your notice period?", "When can you start?", "Availability"
        # -------------------------------------------------------------
        if any(keyword in q_lower for keyword in ["notice period", "when can you start", "start date", "availability", "earliest start"]):
            return answers.notice_period

        # -------------------------------------------------------------
        # 5. Salary Expectations
        # e.g., "What is your expected salary?", "Desired compensation", "Salary expectations", "Expected compensation?"
        # -------------------------------------------------------------
        salary_keywords = [
            "expected salary", "desired salary", "compensation expectation",
            "desired compensation", "salary expectation", "expected compensation",
            "compensation", "salary"
        ]
        if any(keyword in q_lower for keyword in salary_keywords):
            if answers.expected_salary:
                return answers.expected_salary
            if self.profile.preferences.min_base_salary_usd:
                return f"${self.profile.preferences.min_base_salary_usd:,}"
            return "Negotiable / Open"

        # -------------------------------------------------------------
        # 6. Contact / Link questions
        # e.g. "LinkedIn profile", "GitHub profile", "Portfolio URL"
        # -------------------------------------------------------------
        if "linkedin" in q_lower:
            return person.linkedin_url or ""
        if "github" in q_lower:
            return person.github_url or ""
        if "portfolio" in q_lower or "personal website" in q_lower:
            return person.portfolio_url or ""

        # -------------------------------------------------------------
        # 7. Years of Experience (Specific skill or overall)
        # e.g. "How many years of experience do you have with Python?", "Years of React experience?", "How many years have you used React?"
        # -------------------------------------------------------------
        if "years" in q_lower or "experience" in q_lower or "exp" in q_lower:
            # Check individual skills in years_of_experience dict
            for skill, yoe in answers.years_of_experience.items():
                pattern = rf"(?<![\w#+]){re.escape(skill.lower())}(?![\w#+])"
                if re.search(pattern, q_lower):
                    # Format as integer if whole number, else float
                    val = int(yoe) if yoe == int(yoe) else yoe
                    return str(val)

            # Check if general overall years of experience question
            # e.g., "How many years of total software engineering experience do you have?"
            overall_patterns = ["overall", "total", "software engineer", "developer", "engineering"]
            if any(p in q_lower for p in overall_patterns) or ("years" in q_lower and ("experience" in q_lower or "exp" in q_lower)):
                max_yoe = max(answers.years_of_experience.values(), default=3.0)
                val = int(max_yoe) if max_yoe == int(max_yoe) else max_yoe
                return str(val)

        # -------------------------------------------------------------
        # 8. Relocation / Remote preference
        # -------------------------------------------------------------
        if "relocate" in q_lower or "willing to relocate" in q_lower:
            return "No" if self.profile.preferences.remote_only else "Yes"

        if "remote" in q_lower and ("comfortable" in q_lower or "preference" in q_lower or "work remotely" in q_lower):
            return "Yes"

        # Fallback to default or empty string
        return default if default is not None else ""

    def answer_batch(self, questions: List[str]) -> Dict[str, str]:
        """
        Batch processes a list of screening questions and returns a dict mapping
        question -> synthesized answer.
        """
        return {q: self.answer_question(q) for q in questions}


def stage_application_content(
    job: Job,
    profile: CandidateProfile,
    screening_questions: Optional[List[str]] = None,
    custom_tone: str = "professional",
) -> Application:
    """
    Creates or populates an Application database record for a Job with:
    - Tailored Cover Letter
    - Wellfound / Startup Pitch Note
    - Answered Screening Q&A (stored as JSON)
    - Status set to 'staged'
    """
    letter_gen = CoverLetterGenerator(profile)
    pitch_gen = PitchSynthesizer(profile)
    qa_gen = QASynthesizer(profile)

    # Parse matched skills from job if stored as JSON
    matched_skills = []
    if job.matched_skills:
        try:
            matched_skills = json.loads(job.matched_skills)
        except (json.JSONDecodeError, TypeError):
            matched_skills = [s.strip() for s in job.matched_skills.split(",") if s.strip()]

    cover_letter = letter_gen.generate(
        job_title=job.title,
        company_name=job.company,
        job_description=job.description or "",
        matched_skills=matched_skills,
        custom_tone=custom_tone,
    )

    pitch = pitch_gen.generate_pitch(
        job_title=job.title,
        company_name=job.company,
        matched_skills=matched_skills,
    )

    qa_answers: Dict[str, str] = {}
    if screening_questions:
        qa_answers = qa_gen.answer_batch(screening_questions)

    # Use existing application if attached, otherwise create new
    app = job.application if job.application else Application(job_id=job.id, portal=job.portal)
    app.portal = job.portal
    app.status = "staged"
    app.tailored_cover_letter = cover_letter
    app.tailored_pitch = pitch
    app.submitted_qa = json.dumps(qa_answers)

    # Associate with job
    job.application = app
    job.status = "staged"

    return app
