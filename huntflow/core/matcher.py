"""
Semantic Fit Scoring & Match Engine (Ticket 3)

Evaluates candidate fit against job requirements across three distinct stages:
1. Hard Rule Filtering (company blacklists, excluded job title keywords, remote/location mismatch)
2. Keyword & Skill Overlap (required & preferred skill matching, detected vs missing skills)
3. Fit Scoring & Rationale (0-100% composite score, pros and cons reasoning)
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from huntflow.core.profile_manager import (
    COMMON_SKILLS_CATALOG,
    CandidateProfile,
    ResumeParser,
)


class MatchResult(BaseModel):
    """Encapsulates the output of the matching process for a single job."""
    passed_hard_filters: bool
    filter_reasons: List[str] = Field(default_factory=list)
    score: float = 0.0  # Normalized 0.0 - 100.0
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)

    def to_db_dict(self) -> Dict[str, Any]:
        """Returns values ready to update a Job database model."""
        return {
            "match_score": round(self.score, 1),
            "matched_skills": json.dumps(self.matched_skills),
            "missing_skills": json.dumps(self.missing_skills),
            "pros_cons": json.dumps({"pros": self.pros, "cons": self.cons, "filter_reasons": self.filter_reasons}),
            "status": "scored" if self.passed_hard_filters else "rejected",
        }


class MatchEngine:
    """Multi-stage matcher that scores jobs against a CandidateProfile."""

    def __init__(self, profile: CandidateProfile, skill_catalog: Optional[Set[str]] = None):
        self.profile = profile
        self.catalog = skill_catalog if skill_catalog is not None else COMMON_SKILLS_CATALOG
        self._candidate_skills = self._extract_candidate_skills()

    def _extract_candidate_skills(self) -> Set[str]:
        """Combines explicit profile skills and standardizes them to lowercase."""
        skills: Set[str] = set()
        for s in self.profile.skills.all_skills():
            cleaned = s.strip().lower()
            if cleaned:
                # Handle compound entries like "HTML/CSS"
                if "/" in cleaned:
                    for sub in cleaned.split("/"):
                        if sub.strip():
                            skills.add(sub.strip())
                skills.add(cleaned)
        return skills

    # -------------------------------------------------------------
    # Stage 1: Hard Rule Filters
    # -------------------------------------------------------------
    def check_hard_filters(
        self,
        job_title: str,
        company_name: str,
        location: str = "",
        remote_type: str = "Remote",
        min_salary: Optional[int] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Applies non-negotiable filters.
        Returns: (passed, list_of_rejection_reasons)
        """
        reasons: List[str] = []
        prefs = self.profile.preferences

        # 1. Company Blacklist Filter
        normalized_company = company_name.strip().lower()
        for blacklisted in prefs.blacklisted_companies:
            if blacklisted.strip().lower() in normalized_company or normalized_company in blacklisted.strip().lower():
                reasons.append(f"Company '{company_name}' matches blacklisted employer '{blacklisted}'.")

        # 2. Excluded Titles / Negative Keywords
        normalized_title = job_title.strip().lower()
        for excluded in prefs.excluded_titles:
            pattern = rf"(?<![\w]){re.escape(excluded.strip().lower())}(?![\w])"
            if re.search(pattern, normalized_title):
                reasons.append(f"Job title '{job_title}' contains excluded keyword '{excluded}'.")

        # 3. Remote-Only Enforcement
        if prefs.remote_only:
            combined_loc = f"{location} {remote_type}".lower()
            is_remote = "remote" in combined_loc or "anywhere" in combined_loc or "virtual" in combined_loc
            if not is_remote and remote_type.lower() not in ["remote", ""]:
                reasons.append(f"User requires remote-only, but job specifies '{remote_type}' in '{location}'.")

        # 4. Salary Floor Check (if provided in job)
        if min_salary is not None and prefs.min_base_salary_usd and prefs.min_base_salary_usd > 0:
            if min_salary < prefs.min_base_salary_usd:
                reasons.append(
                    f"Job salary (${min_salary:,.0f}) is below candidate minimum floor (${prefs.min_base_salary_usd:,.0f})."
                )

        passed = len(reasons) == 0
        return passed, reasons

    # -------------------------------------------------------------
    # Stage 2: Keyword & Skill Extraction
    # -------------------------------------------------------------
    def extract_job_skills(self, title: str, description: str) -> List[str]:
        """Extracts recognized technical skills from job title and description."""
        combined_text = f"{title}\n{description}"
        return ResumeParser.extract_skills(combined_text, custom_catalog=self.catalog)

    # -------------------------------------------------------------
    # Stage 3: Fit Scoring & Rationale Generation
    # -------------------------------------------------------------
    def match(
        self,
        job_title: str,
        company_name: str,
        description: str,
        location: str = "Remote",
        remote_type: str = "Remote",
        min_salary: Optional[int] = None,
    ) -> MatchResult:
        """
        Executes complete multi-stage evaluation of a job against candidate profile.
        """
        # Run Stage 1 Hard Filters
        passed, filter_reasons = self.check_hard_filters(
            job_title=job_title,
            company_name=company_name,
            location=location,
            remote_type=remote_type,
            min_salary=min_salary,
        )

        if not passed:
            return MatchResult(
                passed_hard_filters=False,
                filter_reasons=filter_reasons,
                score=0.0,
                matched_skills=[],
                missing_skills=[],
                pros=[],
                cons=filter_reasons,
            )

        # Run Stage 2 Skills Analysis
        job_skills = self.extract_job_skills(job_title, description)
        candidate_skills = self._candidate_skills

        matched_skills: List[str] = []
        missing_skills: List[str] = []

        for skill in job_skills:
            if skill in candidate_skills:
                matched_skills.append(skill)
            else:
                missing_skills.append(skill)

        # -------------------------------------------------------------
        # Compute Weighted Score Breakdown
        # 1. Title Fit (up to 30 pts)
        # 2. Skill Overlap (up to 50 pts)
        # 3. Location / Remote Fit (up to 10 pts)
        # 4. Description Depth & Experience Alignment (up to 10 pts)
        # -------------------------------------------------------------
        pros: List[str] = []
        cons: List[str] = []

        # 1. Title Fit (30 points max)
        title_score = 0.0
        normalized_title = job_title.lower()
        target_titles = [t.lower() for t in self.profile.preferences.target_titles]
        
        # Exact title match
        if any(t in normalized_title or normalized_title in t for t in target_titles):
            title_score = 30.0
            pros.append(f"Title '{job_title}' strongly aligns with target career titles.")
        else:
            # Partial keyword match (e.g. "Engineer", "Developer", "Backend")
            words_in_title = set(re.findall(r"\b\w+\b", normalized_title))
            target_words: Set[str] = set()
            for t in target_titles:
                target_words.update(re.findall(r"\b\w+\b", t))
            overlap_words = words_in_title.intersection(target_words)
            if overlap_words:
                title_score = min(20.0, len(overlap_words) * 7.0)
                pros.append(f"Title contains relevant target keywords: {', '.join(sorted(overlap_words))}.")
            else:
                title_score = 5.0
                cons.append(f"Title '{job_title}' does not closely match preferred target titles.")

        # 2. Skill Overlap (50 points max)
        skill_score = 0.0
        if job_skills:
            overlap_ratio = len(matched_skills) / len(job_skills)
            skill_score = overlap_ratio * 50.0
            if overlap_ratio >= 0.7:
                pros.append(f"High technical skill alignment ({len(matched_skills)}/{len(job_skills)} required skills matched).")
            elif overlap_ratio >= 0.4:
                pros.append(f"Moderate technical overlap ({len(matched_skills)}/{len(job_skills)} skills matched).")
            else:
                cons.append(f"Low skill match ({len(matched_skills)}/{len(job_skills)} skills matched). Missing: {', '.join(missing_skills[:5])}.")
        else:
            # No specific technical skills found in posting, award median default
            skill_score = 30.0
            pros.append("Broad or general technical requirements.")

        # 3. Location / Remote Fit (10 points max)
        loc_score = 0.0
        combined_loc = f"{location} {remote_type}".lower()
        if "remote" in combined_loc or "anywhere" in combined_loc:
            loc_score = 10.0
            pros.append("Fully remote position matching candidate preference.")
        else:
            # Check target locations
            target_locs = [l.lower() for l in self.profile.preferences.target_locations]
            if any(l in combined_loc for l in target_locs if l != "remote"):
                loc_score = 8.0
                pros.append(f"Location '{location}' is in target location list.")
            else:
                loc_score = 4.0
                cons.append(f"Position is located in '{location}'.")

        # 4. Experience & Bonus Alignment (10 points max)
        desc_score = 5.0  # Base score
        # Check years of experience alignment if mentioned in description
        yoe_pattern = r"(\d+)[\+]?\s*(?:to\s*(\d+))?\s*years?(?:\s*of)?\s*experience"
        yoe_match = re.search(yoe_pattern, description, re.IGNORECASE)
        if yoe_match:
            min_yoe_req = int(yoe_match.group(1))
            candidate_max_yoe = max(self.profile.screening_answers.years_of_experience.values(), default=3.0)
            if candidate_max_yoe >= min_yoe_req:
                desc_score = 10.0
                pros.append(f"Candidate meets experience requirement (~{min_yoe_req}+ years).")
            else:
                desc_score = 3.0
                cons.append(f"Role asks for {min_yoe_req}+ years experience (candidate profile shows ~{candidate_max_yoe:.0f} yrs).")
        else:
            desc_score = 8.0

        # Total Composite Score (0 - 100)
        total_score = min(100.0, max(0.0, title_score + skill_score + loc_score + desc_score))

        return MatchResult(
            passed_hard_filters=True,
            filter_reasons=[],
            score=total_score,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            pros=pros,
            cons=cons,
        )


def score_job(job: Any, profile: CandidateProfile) -> MatchResult:
    """
    Convenience function that takes a Job database model (or duck-typed object)
    and candidate profile, runs matcher, and updates the job instance fields.
    """
    matcher = MatchEngine(profile)
    res = matcher.match(
        job_title=job.title,
        company_name=job.company,
        description=job.description or "",
        location=job.location or "Remote",
        remote_type=job.remote_type or "Remote",
    )
    job.match_score = round(res.score, 1)
    job.matched_skills = json.dumps(res.matched_skills)
    job.missing_skills = json.dumps(res.missing_skills)
    job.pros_cons = json.dumps({"pros": res.pros, "cons": res.cons, "filter_reasons": res.filter_reasons})
    job.status = "scored" if res.passed_hard_filters else "rejected"
    return res
