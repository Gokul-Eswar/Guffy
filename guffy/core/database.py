"""
Guffy Database Models and SQLite Session Manager
"""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), default="Remote")
    remote_type = Column(String(64), default="Remote")  # Remote, Hybrid, Onsite
    portal = Column(String(64), nullable=False, index=True)  # linkedin, indeed, wellfound, remoteok, company_ats, etc.
    job_url = Column(Text, nullable=False, unique=True)
    description = Column(Text, default="")
    salary_range = Column(String(128), nullable=True)
    easy_apply = Column(Boolean, default=False)
    
    # Fit & Match fields
    match_score = Column(Float, default=0.0, index=True)  # 0.0 - 100.0
    matched_skills = Column(Text, default="")  # JSON or comma-separated list
    missing_skills = Column(Text, default="")
    pros_cons = Column(Text, default="")
    
    # Deduplication & Canonical grouping (Ticket 13)
    canonical_id = Column(String(64), nullable=True, index=True)
    is_canonical_primary = Column(Boolean, default=True)

    # Lifecycle Status: discovered, scored, staged, applied, rejected, interviewing
    status = Column(String(32), default="discovered", index=True)
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship to application log
    application = relationship("Application", back_populates="job", uselist=False, cascade="all, delete-orphan")
    # Outlets representing other sources for this job
    outlets = relationship("JobOutlet", back_populates="job", cascade="all, delete-orphan")


class JobOutlet(Base):
    """Represents an outlet/source where a job posting is listed."""
    __tablename__ = "job_outlets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    portal = Column(String(64), nullable=False)
    job_url = Column(Text, nullable=False)
    easy_apply = Column(Boolean, default=False)
    directness_score = Column(Integer, default=50)  # 100 = Direct ATS, 80 = Direct Easy Apply, 60 = Board, 40 = Aggregator
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="outlets")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True)
    careers_url = Column(Text, nullable=True)
    ats = Column(String(64), default="unknown")  # greenhouse, lever, ashby, workday, smartrecruiters, custom
    priority = Column(String(32), default="medium")  # high, medium, low
    active_jobs_count = Column(Integer, default=0)
    last_crawled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    portal = Column(String(64), nullable=False)
    status = Column(String(32), default="staged", index=True)  # staged, submitted, failed
    tailored_cover_letter = Column(Text, nullable=True)
    tailored_pitch = Column(Text, nullable=True)
    submitted_qa = Column(Text, nullable=True)  # JSON string of answers
    screenshot_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    staged_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime, nullable=True)

    job = relationship("Job", back_populates="application")


class ProfileSetting(Base):
    __tablename__ = "profile_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DatabaseManager:
    def __init__(self, db_url: str = "sqlite:///./data/Guffy.db"):
        self.db_url = db_url
        if db_url.startswith("sqlite:///./"):
            rel_path = db_url.replace("sqlite:///./", "")
            Path(rel_path).parent.mkdir(parents=True, exist_ok=True)
        elif db_url.startswith("sqlite:///"):
            rel_path = db_url.replace("sqlite:///", "")
            Path(rel_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=self.engine)

    def init_db(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()


_db_manager: Optional[DatabaseManager] = None


def get_db_manager(db_url: str = "sqlite:///./data/Guffy.db") -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_url)
        _db_manager.init_db()
    return _db_manager
