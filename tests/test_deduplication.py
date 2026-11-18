import pytest
from guffy.core.database import DatabaseManager, Job, JobOutlet, get_db_manager
from guffy.searchers.base import (
    JobPosting,
    compute_canonical_id,
    get_outlet_directness_score,
    get_outlet_badge_and_label,
    normalize_company,
    normalize_title,
)


def test_normalization_and_canonical_id():
    # Test company name variations
    c1 = "Stripe, Inc."
    c2 = "Stripe LLC"
    c3 = "Stripe"
    assert normalize_company(c1) == normalize_company(c2) == normalize_company(c3) == "stripe"

    # Test title variations
    t1 = "Senior Backend Engineer [Remote]"
    t2 = "Senior Backend Engineer (US Only)"
    t3 = "Senior Backend Engineer - Remote"
    assert normalize_title(t1) == normalize_title(t2) == normalize_title(t3) == "senior backend engineer"

    # Canonical IDs should match across variations
    id1 = compute_canonical_id("Stripe, Inc.", "Senior Backend Engineer [Remote]")
    id2 = compute_canonical_id("Stripe", "Senior Backend Engineer")
    assert id1 == id2


def test_directness_scores_and_badges():
    assert get_outlet_directness_score("company_ats") == 100
    assert get_outlet_directness_score("greenhouse") == 100
    assert get_outlet_directness_score("linkedin", easy_apply=True) == 80
    assert get_outlet_directness_score("wellfound") == 80
    assert get_outlet_directness_score("indeed", easy_apply=False) == 60
    assert get_outlet_directness_score("remoteok") == 40

    badge_ats = get_outlet_badge_and_label("greenhouse", 100)
    assert badge_ats["tier"] == "direct_ats"
    assert "Direct to Recruiter" in badge_ats["label"]


def test_db_job_outlet_relationship(tmp_path):
    db_file = tmp_path / "test_dedup.db"
    manager = DatabaseManager(f"sqlite:///{db_file}")
    manager.init_db()

    session = manager.SessionLocal()
    try:
        # Create canonical primary job
        posting = JobPosting(
            title="Full Stack Engineer",
            company="Acme Corp",
            job_url="https://jobs.lever.co/acme/123",
            portal="lever",
        )
        job = posting.to_job_model()
        session.add(job)
        session.commit()

        # Add an alternate outlet
        outlet = JobOutlet(
            job_id=job.id,
            portal="linkedin",
            job_url="https://linkedin.com/jobs/view/456",
            easy_apply=True,
            directness_score=80,
        )
        session.add(outlet)
        session.commit()

        # Query and verify relationship
        loaded_job = session.query(Job).filter_by(id=job.id).first()
        assert loaded_job is not None
        assert len(loaded_job.outlets) == 1
        assert loaded_job.outlets[0].portal == "linkedin"
        assert loaded_job.outlets[0].directness_score == 80
    finally:
        session.close()
