"""
Candidate Profile & Resume Ingestion Engine (Ticket 2)

Handles:
- Resume text extraction from PDF and DOCX documents
- Keyword and skill catalog extraction from resumes
- Candidate Profile data modeling and YAML validation
"""

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
import docx
from pypdf import PdfReader
from pydantic import BaseModel, EmailStr, Field, field_validator
import yaml


COMMON_SKILLS_CATALOG = {
    # Programming Languages
    "python", "javascript", "typescript", "golang", "go", "java", "c++", "c#", "ruby", "rust",
    "php", "swift", "kotlin", "scala", "sql", "html", "css", "bash", "shell",
    
    # Frameworks & Libraries
    "fastapi", "django", "flask", "react", "next.js", "vue", "angular", "node.js", "express",
    "spring", "spring boot", "ruby on rails", "asp.net", "tailwind", "bootstrap", "graphql",
    "rest", "pytorch", "tensorflow", "pandas", "numpy", "scikit-learn",
    
    # Databases & Caching
    "postgresql", "postgres", "mysql", "sqlite", "mongodb", "redis", "elasticsearch", "cassandra",
    "dynamodb", "supabase", "firebase",
    
    # DevOps, Cloud & Infrastructure
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible", "ci/cd", "github actions",
    "gitlab ci", "jenkins", "linux", "git", "nginx", "prometheus", "grafana",
    
    # Methodologies & Architecture
    "microservices", "serverless", "agile", "scrum", "tdd", "system design", "distributed systems"
}


class PersonalInfo(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    location: str = ""
    linkedin_url: Optional[str] = ""
    github_url: Optional[str] = ""
    portfolio_url: Optional[str] = ""
    resume_path: Optional[str] = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_pattern, v.strip()):
            raise ValueError(f"Invalid email address: {v}")
        return v.strip()


class JobPreferences(BaseModel):
    target_titles: List[str] = Field(default_factory=list)
    excluded_titles: List[str] = Field(default_factory=list)
    target_locations: List[str] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = True
    min_base_salary_usd: Optional[int] = 0
    blacklisted_companies: List[str] = Field(default_factory=list)


class SkillsSection(BaseModel):
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    cloud_and_tools: List[str] = Field(default_factory=list)

    def all_skills(self) -> List[str]:
        """Returns flattened list of all defined skills."""
        combined = []
        for s in self.languages + self.frameworks + self.cloud_and_tools:
            if s and s.strip() not in combined:
                combined.append(s.strip())
        return combined


class ScreeningAnswers(BaseModel):
    work_authorization: str = "Yes"
    require_sponsorship: str = "No"
    notice_period: str = "Immediate"
    expected_salary: str = ""
    years_of_experience: Dict[str, float] = Field(default_factory=dict)
    custom_qa: Dict[str, str] = Field(default_factory=dict)


class CandidateProfile(BaseModel):
    personal_info: PersonalInfo
    preferences: JobPreferences = Field(default_factory=JobPreferences)
    skills: SkillsSection = Field(default_factory=SkillsSection)
    screening_answers: ScreeningAnswers = Field(default_factory=ScreeningAnswers)

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> "CandidateProfile":
        profile_path = Path(path)
        if not profile_path.exists():
            raise FileNotFoundError(f"Profile file not found at: {profile_path}")

        with open(profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)


class ResumeParser:
    """Extracts raw text and identifies key skills from resume files (PDF, DOCX, TXT)."""

    @staticmethod
    def extract_text(file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume file does not exist: {path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return ResumeParser._extract_pdf(path)
        elif suffix in [".docx", ".doc"]:
            return ResumeParser._extract_docx(path)
        elif suffix in [".txt", ".md"]:
            return path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported resume file format: {suffix}. Supported formats: .pdf, .docx, .txt")

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        text_parts = []
        with open(path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
        return "\n".join(text_parts).strip()

    @staticmethod
    def _extract_docx(path: Path) -> str:
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        # Also extract table text if present
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        paragraphs.append(cell.text.strip())
        return "\n".join(paragraphs).strip()

    @staticmethod
    def extract_skills(text: str, custom_catalog: Optional[Set[str]] = None) -> List[str]:
        """
        Scans resume text against a known skill catalog and returns matched skills.
        Case-insensitive word boundary matching.
        """
        catalog = custom_catalog if custom_catalog is not None else COMMON_SKILLS_CATALOG
        lowered_text = text.lower()
        matched: List[str] = []

        for skill in sorted(catalog):
            # Use regex word boundaries for accurate matching (e.g. avoid matching "c" in "cloud" or "go" in "good")
            pattern = rf"(?<![\w#+]){re.escape(skill)}(?![\w#+])"
            if re.search(pattern, lowered_text):
                matched.append(skill)

        return matched


class ProfileManager:
    """Coordinates candidate profile validation and resume ingestion."""

    def __init__(self, profile_path: Optional[str | Path] = None):
        self.profile_path = Path(profile_path) if profile_path else None
        self.profile: Optional[CandidateProfile] = None
        if self.profile_path and self.profile_path.exists():
            self.load_profile(self.profile_path)

    def load_profile(self, path: str | Path) -> CandidateProfile:
        self.profile = CandidateProfile.load_from_yaml(path)
        self.profile_path = Path(path)
        return self.profile

    def get_parsed_resume(self, resume_path: Optional[str | Path] = None) -> Dict[str, Any]:
        """
        Extracts resume content and discovered skills.
        Uses resume_path provided or fallback to profile.personal_info.resume_path.
        """
        target_path = resume_path
        if not target_path and self.profile and self.profile.personal_info.resume_path:
            target_path = self.profile.personal_info.resume_path

        if not target_path:
            raise ValueError("No resume path specified or found in candidate profile.")

        raw_text = ResumeParser.extract_text(target_path)
        detected_skills = ResumeParser.extract_skills(raw_text)

        # Merge with explicitly listed profile skills if profile is loaded
        explicit_skills = self.profile.skills.all_skills() if self.profile else []

        # Return structured resume data
        return {
            "resume_path": str(target_path),
            "text": raw_text,
            "detected_skills": detected_skills,
            "explicit_skills": explicit_skills,
            "word_count": len(raw_text.split()),
        }
