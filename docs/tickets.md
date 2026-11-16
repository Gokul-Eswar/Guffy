# Guffy: Roadmap & Ticket Tracking

## Overall Architecture Flow

```mermaid
flowchart TD
    subgraph Foundation
        T1["Ticket 1: Core DB & Config Setup"] --> T2["Ticket 2: Resume & Profile Engine"]
        T2 --> T3["Ticket 3: Fit Scoring Engine (0-100%)"]
        T3 --> T4["Ticket 4: Tailored Content & Q&A Synthesizer"]
    end

    subgraph Discovery
        T1 --> T5["Ticket 5: Remote Tech Portals (RemoteOK, WWR, YC)"]
        T5 --> T6["Ticket 6: Company Career & ATS Crawler (Greenhouse, Lever, Ashby)"]
        T6 --> T7["Ticket 7: Aggregators & Boards (LinkedIn, Wellfound, Indeed, Dice)"]
    end

    subgraph Automation
        T4 --> T8["Ticket 8: Browser Controller & Universal Form Filler"]
        T7 --> T8
        T8 --> T9["Ticket 9: Portal-Specific Appliers & Staging Engine"]
    end

    subgraph Interface & Review
        T1 --> T10["Ticket 10: FastAPI Backend & REST API"]
        T9 --> T10
        T10 --> T11["Ticket 11: Web Dashboard (Tailwind SPA)"]
        T11 --> T12["Ticket 12: CLI Suite & End-to-End Verification"]
    end
```

---

## Ticket Progress Board

| Ticket | Description | Status | Verification Tests |
| :--- | :--- | :---: | :--- |
| **Ticket 1** | Project Foundation, Database Models & Configuration Setup | ✅ Completed | `tests/test_database.py` (4 passed) |
| **Ticket 2** | Candidate Profile & Resume Ingestion Engine (PDF/DOCX) | ✅ Completed | `tests/test_profile_manager.py` (7 passed) |
| **Ticket 3** | Semantic Fit Scoring & Match Engine (0–100%) | ✅ Completed | `tests/test_matcher.py` (9 passed) |
| **Ticket 4** | Tailored Content & Screening Q&A Synthesizer | ✅ Completed | `tests/test_generator.py` (9 passed) |
| **Ticket 5** | Job Discovery Engine: Remote Tech Portals (RemoteOK, WWR, YC Startup) | ✅ Completed | `tests/test_remote_portals.py` (6 passed) |
| **Ticket 6** | Official Company Career Page & Direct ATS Crawler (Greenhouse, Lever, Ashby) | ✅ Completed | `tests/test_company_crawler.py` (7 passed) |
| **Ticket 7** | Aggregator & Board Searchers (LinkedIn, Wellfound, Indeed, Dice) | ✅ Completed | `tests/test_searchers.py` (9 passed) |
| **Ticket 8** | Browser Controller & Universal Form Filler | ✅ Completed | `tests/test_form_filler.py` (4 passed) |
| **Ticket 9** | Portal-Specific Appliers & Staging Engine (HITL) | ✅ Completed | `tests/test_appliers.py` (9 passed) |
| **Ticket 10** | FastAPI Backend & REST API | ⏳ **Next Up** | `tests/test_api.py` |
| **Ticket 11** | Modern Web Dashboard UI (Tailwind SPA) | 📋 Pending | Manual / Browser |
| **Ticket 12** | Unified CLI Suite & End-to-End Verification | 📋 Pending | `tests/test_e2e.py` |

---

## Detailed Ticket Breakdown

### ✅ [Ticket 1] Project Foundation, Database Models & Configuration Setup
- **Deliverables**:
  - `pyproject.toml`, `requirements.txt`
  - `config.yaml`, `profile.example.yaml`, `companies.yaml`
  - `guffy/config.py` (Pydantic Settings loader)
  - `guffy/core/database.py` (SQLAlchemy models: `Job`, `Company`, `Application`, `ProfileSetting`, SQLite SessionManager)
  - `tests/test_database.py`

---

### ✅ [Ticket 2] Candidate Profile & Resume Ingestion Engine
- **Deliverables**:
  - `guffy/core/profile_manager.py`:
    - `ResumeParser`: PDF (`pypdf`), DOCX (`python-docx`), text parsing.
    - `COMMON_SKILLS_CATALOG`: Regex boundary catalog matching.
    - `CandidateProfile`: Pydantic schema validation for contact info, preferences, skills, and Q&A.
  - `tests/test_profile_manager.py`

---

### ✅ [Ticket 3] Semantic Fit Scoring & Match Engine (0–100%)
- **Deliverables**:
  - `guffy/core/matcher.py`:
    - Stage 1: Hard rule filters (company blacklist, title negative keywords, remote-only, salary floor).
    - Stage 2: Skill overlap detection (`matched_skills`, `missing_skills`).
    - Stage 3: Multi-factor composite fit scoring (0–100%) and pros/cons rationale generator.
    - Database updater `score_job(job, profile)`.
  - `tests/test_matcher.py`

---

### ✅ [Ticket 4] Tailored Content & Screening Q&A Synthesizer
- **Deliverables**:
  - `guffy/core/generator.py`:
    - `CoverLetterGenerator`: Tailored 3-4 paragraph cover letter aligning candidate background, top matched skills, and past projects with job specs.
    - `PitchSynthesizer`: Concise, high-conversion 3-4 sentence pitch note (100-150 words) optimized for Wellfound / AngelList and direct startup outreach.
    - `QASynthesizer`: Screening Q&A resolver with exact & fuzzy string matching, rule-based heuristics for sponsorship, legal work authorization, notice period, salary, and skill-specific years of experience.
    - `stage_application_content`: Helper function connecting Job and Application database records with generated copy.
  - `tests/test_generator.py`: 9 comprehensive test cases verifying content tailoring and screening Q&A resolution.

---

### ✅ [Ticket 5] Job Discovery Engine: Remote Tech Portals
- **Deliverables**:
  - `guffy/searchers/base.py`:
    - `JobPosting` schema with automatic SHA-256 ID generation and `.to_job_model()` conversion to SQLAlchemy `Job`.
    - `BaseSearcher` abstract base interface with robust HTML tag stripping and formatting utilities.
  - `guffy/searchers/remote_portals.py`:
    - `RemoteOKSearcher`: Consumes RemoteOK's public JSON API with salary range and keyword matching.
    - `WeWorkRemotelySearcher`: Parses WWR XML/RSS feeds (`remote-programming-jobs.rss`) with title/company separation and category tagging.
    - `YCStartupSearcher`: Scrapes and standardizes Y Combinator and Hacker News "Who Is Hiring" startup job listings.
  - `guffy/searchers/__init__.py`: Package entrypoint exporting all searchers.
  - `tests/test_remote_portals.py`: 6 unit tests with full network mocking and edge case coverage.

---

### ✅ [Ticket 6] Official Company Career Page & Direct ATS Crawler
- **Deliverables**:
  - `guffy/searchers/company_crawler.py`:
    - `TargetCompanyManager`: Loads and syncs target companies from `companies.yaml` into SQLite.
    - `ATSSignatureDetector`: Regex and signature detection across Greenhouse, Lever, Ashby, Workday, SmartRecruiters.
    - `GreenhouseParser`: Direct Greenhouse boards API (`boards-api.greenhouse.io`) and HTML fallback scraper.
    - `LeverParser`: Lever postings JSON API (`api.lever.co/v0/postings`) and HTML fallback scraper.
    - `AshbyParser`: Ashby job board API (`api.ashbyhq.com/posting-api`) and HTML scraper.
    - `GenericCareerParser`: Pattern-matching fallback for bespoke company career sites.
    - `CompanyCrawler`: Batch crawl orchestration with keyword filtering, database deduplication, and active job counters.
  - `guffy/searchers/__init__.py`: Package export updates.
  - `tests/test_company_crawler.py`: 7 comprehensive unit and integration tests.

---

### ✅ [Ticket 7] Aggregator & Board Searchers (LinkedIn, Wellfound, Indeed, Dice)
- **Deliverables**:
  - `guffy/searchers/linkedin.py`: LinkedIn guest search endpoint client with Easy Apply tag detection, location/remote query filters, and salary parsing.
  - `guffy/searchers/wellfound.py`: Next.js hydration parser and HTML scraper for high-growth startups, equity/salary compensation, and quick pitch links.
  - `guffy/searchers/indeed.py`: Indeed search engine querying date-sorted listings, parsing mosaic data and `job_seen_beacon` cards, detecting 'Easily apply'.
  - `guffy/searchers/glassdoor_dice.py`:
    - `DiceSearcher`: Tech-specific searcher with API payload querying and HTML fallback.
    - `GlassdoorSearcher`: Glassdoor job listing extraction with Apollo cache parsing.
  - `guffy/searchers/__init__.py`: Package export updates.
  - `tests/test_searchers.py`: 9 comprehensive test cases verifying card extraction, JSON hydration, and network mocking across all searchers.

---

### ✅ [Ticket 8] Browser Controller & Universal Form Filler
- **Deliverables**:
  - `guffy/automation/browser.py`:
    - `BrowserController`: Selenium Chrome lifecycle management with persistent session profile (`--user-data-dir`).
    - Anti-detection flags (`--disable-blink-features=AutomationControlled`, removal of `navigator.webdriver` via CDP scripts, realistic user agent, window size).
    - `human_type`: Character-by-character typing with micro-randomized delays, smooth scrolling, and viewport screenshot capture.
  - `guffy/automation/form_filler.py`:
    - `FormFieldDetector`: Regex classification for 18+ field categories (contact info, profile URLs, file/resume, work authorization, sponsorship, notice period, compensation).
    - `UniversalFormFiller`: Bridges `CandidateProfile` and `QASynthesizer` into DOM form inputs, textareas, file upload controls, and dropdown options.
  - `guffy/automation/__init__.py`: Package export updates.
  - `tests/test_form_filler.py`: 4 unit tests verifying field classification, Chrome options, candidate value resolution, and DOM form filling.

---

### ✅ [Ticket 9] Portal-Specific Appliers & Staging Engine
- **Deliverables**:
  - `guffy/automation/ats_applier.py`: Direct ATS applier (Greenhouse, Lever, Ashby, Workday).
  - `guffy/automation/linkedin_applier.py`: LinkedIn Easy Apply multi-step modal applier with step progression and safety review halts.
  - `guffy/automation/wellfound_applier.py`: Wellfound apply drawer with custom startup pitch note insertion.
  - `guffy/automation/indeed_applier.py`: Indeed Quick Apply wizard handler.
  - `guffy/automation/staging_engine.py`: `ApplicationStagingEngine` orchestrating form filling, screenshot review snapshots, database staging, and 1-click human-in-the-loop submission approval.
  - `guffy/automation/__init__.py`: Package export updates.
  - `tests/test_appliers.py`: 9 comprehensive unit tests verifying staging, submit triggers, and state transitions.

---

### 📋 [Ticket 10] FastAPI Backend & REST API
- **Deliverables**:
  - `guffy/web/app.py`: `/api/jobs`, `/api/search`, `/api/match`, `/api/stage/{id}`, `/api/approve/{id}`, `/api/profile`, `/api/companies`, `/api/analytics`.
  - `tests/test_api.py`

---

### 📋 [Ticket 11] Modern Web Dashboard UI (Tailwind SPA)
- **Deliverables**:
  - `guffy/web/static/index.html` & `app.js`: Interactive UI for discovery, staging review queue, application tracker, company monitor.

---

### 📋 [Ticket 12] Unified CLI Suite & End-to-End Verification
- **Deliverables**:
  - `guffy/cli.py` (Commands: `init`, `search`, `crawl-companies`, `match`, `review`, `serve`).
  - `tests/test_e2e.py`
  - Complete `README.md`.
