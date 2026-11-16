# HuntFlow: Modular Ticketed Implementation Plan

## Goal Description
Break down the complete **HuntFlow** architecture into 12 self-contained, sequentially executable, and independently testable tickets. Each ticket delivers a complete functional component with automated unit tests and verification steps before moving to the next.

---

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

## User Review Required

> [!IMPORTANT]
> **Sequential Execution**:
> Each ticket will be executed in order. After each ticket is coded, automated tests will run to verify its functionality before we move to the next ticket.
> You will be able to test each milestone incrementally (e.g. testing resume parsing in Ticket 2, live job scraping in Ticket 5 & 6, scoring in Ticket 3, etc.).

---

## Breakdown of Tickets

---

### [Ticket 1] Project Foundation, Database Models & Configuration Setup
**Goal**: Establish project directory structure, dependencies, configuration files, and SQLite database models.
- **Components & Files**:
  - `[NEW] pyproject.toml` & `requirements.txt` (FastAPI, Uvicorn, SQLAlchemy, Pydantic, Selenium, PyYAML, pypdf, python-docx, requests, beautifulsoup4).
  - `[NEW] config.yaml` (Search defaults, match score thresholds, browser settings).
  - `[NEW] profile.example.yaml` (Template for personal info, target titles, salary, screening Q&A).
  - `[NEW] companies.yaml` (Template for target companies and custom career URLs).
  - `[NEW] huntflow/config.py` (Pydantic settings and YAML configuration loader).
  - `[NEW] huntflow/core/database.py` (SQLAlchemy models: `Job`, `Company`, `Application`, `ProfileSetting`, and SQLite session manager).
  - `[NEW] tests/test_database.py` (Unit tests for DB initialization, CRUD operations, state transitions).
- **Verification**: Run `pytest tests/test_database.py`.

---

### [Ticket 2] Candidate Profile & Resume Ingestion Engine
**Goal**: Parse and extract structured data from user resumes (PDF and DOCX) and validate `profile.yaml`.
- **Components & Files**:
  - `[NEW] huntflow/core/profile_manager.py`:
    - Resume text extractor using `pypdf` and `python-docx`.
    - Skill catalog matcher (extracts programming languages, frameworks, cloud platforms, databases, tools).
    - Profile validator loading personal contact info, target titles, blacklist employers, and screening Q&A dictionary.
  - `[NEW] tests/test_profile_manager.py`:
    - Unit tests validating parsing of sample PDF and DOCX files.
    - Test validation of required vs optional profile fields.
- **Verification**: Run `pytest tests/test_profile_manager.py`.

---

### [Ticket 3] Semantic Fit Scoring & Match Engine (0–100%)
**Goal**: Implement the multi-stage matching engine that evaluates candidate fit against job requirements.
- **Components & Files**:
  - `[NEW] huntflow/core/matcher.py`:
    - **Stage 1 (Hard Rule Filters)**: Excludes blacklisted companies, disfavored locations/employment types, and title negative keywords.
    - **Stage 2 (Keyword & Skill Overlap)**: Calculates weighted required vs preferred skill overlap.
    - **Stage 3 (Seniority & Fit Scoring)**: Produces an overall **Fit Score (0–100%)**, list of **Matched Skills**, **Missing Skills**, and **Pros/Cons Rationale**.
  - `[NEW] tests/test_matcher.py`:
    - Test scoring with high-fit (e.g. 90%+), medium-fit (60–75%), and low-fit (<50%) mock job postings.
    - Test company blacklist and title exclusion rules.
- **Verification**: Run `pytest tests/test_matcher.py`.

---

### [Ticket 4] Tailored Content & Screening Q&A Synthesizer
**Goal**: Generate tailored application materials (cover letters, Wellfound startup pitch notes, and automated screening answers).
- **Components & Files**:
  - `[NEW] huntflow/core/generator.py`:
    - Tailored Cover Letter Generator (aligns candidate's specific background with job requirements).
    - Wellfound Startup Pitch Note Synthesizer (concise 3–4 sentence pitch highlighting high-impact accomplishments).
    - Screening Q&A Resolver (maps answers for work authorization, visa sponsorship, years of experience, notice period, compensation).
  - `[NEW] tests/test_generator.py`:
    - Test generation of tailored cover letters and pitch notes.
    - Test exact and fuzzy Q&A matching for common HR screening prompts.
- **Verification**: Run `pytest tests/test_generator.py`.

---

### [Ticket 5] Job Discovery Engine: Remote Tech Portals (RemoteOK, WWR, YC Startup)
**Goal**: Build the normalized `JobPosting` data model, base searcher interface, and collectors for remote tech portals.
- **Components & Files**:
  - `[NEW] huntflow/searchers/base.py` (`JobPosting` model and `BaseSearcher` abstract class).
  - `[NEW] huntflow/searchers/remote_portals.py`:
    - `RemoteOKSearcher`: Consumes RemoteOK API for verified remote software and tech jobs.
    - `WeWorkRemotelySearcher`: Parses WWR RSS feeds across Programming, DevOps, and Product.
    - `YCStartupSearcher`: Scrapes Y Combinator Work at a Startup job listings.
  - `[NEW] tests/test_remote_portals.py`:
    - Unit tests with mock responses to verify parsing, deduplication, and DB persistence.
- **Verification**: Run `pytest tests/test_remote_portals.py`.

---

### [Ticket 6] Official Company Career Page & Direct ATS Crawler
**Goal**: Build the target company manager and ATS crawler for direct career page scraping.
- **Components & Files**:
  - `[NEW] huntflow/searchers/company_crawler.py`:
    - Target Company Manager (loads and syncs `companies.yaml` with DB).
    - Career Page URL Discovery (locates `/careers`, `/jobs`, `careers.domain.com`).
    - ATS Signature Detector (identifies Greenhouse, Lever, Ashby, Workday, SmartRecruiters).
    - Direct Job Parsers for detected ATS platforms (extracts job title, location, description, direct apply URL).
  - `[NEW] tests/test_company_crawler.py`:
    - Test ATS detection on mock HTML and career URLs.
    - Test job listing extraction from sample Greenhouse/Lever boards.
- **Verification**: Run `pytest tests/test_company_crawler.py`.

---

### [Ticket 7] Aggregator & Board Searchers (LinkedIn, Wellfound, Indeed, Dice)
**Goal**: Implement searchers for major portals.
- **Components & Files**:
  - `[NEW] huntflow/searchers/linkedin.py`: LinkedIn search queries with Easy Apply detection.
  - `[NEW] huntflow/searchers/wellfound.py`: Wellfound startup role discovery.
  - `[NEW] huntflow/searchers/indeed.py`: Indeed search with quick apply detection.
  - `[NEW] huntflow/searchers/glassdoor_dice.py`: Dice & Glassdoor search queries.
  - `[NEW] tests/test_searchers.py`:
    - Unit tests for query formatting, HTML response parsing, and error handling.
- **Verification**: Run `pytest tests/test_searchers.py`.

---

### [Ticket 8] Browser Controller & Universal Form Filler
**Goal**: Build safe, anti-detection Chrome automation with persistent sessions and intelligent form field detection.
- **Components & Files**:
  - `[NEW] huntflow/automation/browser.py`:
    - Selenium Chrome controller with `--user-data-dir=.browser_profile`.
    - Anti-detection flags (removes `navigator.webdriver`, randomizes delays, natural typing speed).
  - `[NEW] huntflow/automation/form_filler.py`:
    - Heuristic field detector matching labels, placeholders, and IDs (First Name, Last Name, Email, Phone, LinkedIn, Resume file input).
    - Dropdown and radio button selector matching user profile values.
  - `[NEW] tests/test_form_filler.py`:
    - Test field detection on mock HTML application forms.
- **Verification**: Run `pytest tests/test_form_filler.py`.

---

### [Ticket 9] Portal-Specific Appliers & Staging Engine
**Goal**: Implement application workflows with Human-in-the-Loop staging.
- **Components & Files**:
  - `[NEW] huntflow/automation/linkedin_applier.py` (LinkedIn Easy Apply multi-step modal handler).
  - `[NEW] huntflow/automation/wellfound_applier.py` (Wellfound apply drawer + custom pitch insertion).
  - `[NEW] huntflow/automation/indeed_applier.py` (Indeed Quick Apply handler).
  - `[NEW] huntflow/automation/ats_applier.py` (Greenhouse, Lever, Ashby standard form submission).
  - Staging Engine: Fills fields, stops before final submit, captures snapshot for user review.
  - `[NEW] tests/test_appliers.py`:
    - Test state machines and step progression logic.
- **Verification**: Run `pytest tests/test_appliers.py`.

---

### [Ticket 10] FastAPI Backend & REST API
**Goal**: Create high-performance REST API endpoints for job management, search, matching, and application execution.
- **Components & Files**:
  - `[NEW] huntflow/web/app.py`:
    - `GET /api/jobs`: List and filter jobs (status, score threshold, portal, company).
    - `POST /api/search`: Trigger multi-portal discovery.
    - `POST /api/crawl-companies`: Trigger target company career crawl.
    - `POST /api/match`: Run matcher on unreviewed jobs.
    - `POST /api/stage/{job_id}`: Trigger auto-fill and staging.
    - `POST /api/approve/{job_id}`: Confirm and execute 1-click submission.
    - `GET /api/profile` & `PUT /api/profile`: Read/update candidate profile and upload resume.
    - `GET /api/companies` & `POST /api/companies`: Manage target companies.
    - `GET /api/analytics`: Application statistics and conversion pipeline.
  - `[NEW] tests/test_api.py`:
    - Test endpoints with `starlette.testclient.TestClient`.
- **Verification**: Run `pytest tests/test_api.py`.

---

### [Ticket 11] Modern Web Dashboard UI (Tailwind SPA)
**Goal**: Build a responsive, single-page web dashboard served directly by FastAPI.
- **Components & Files**:
  - `[NEW] huntflow/web/static/index.html`: Clean, responsive UI with navigation tabs:
    - **Tab 1: Jobs Discovery**: Search controls, portal filters, match score slider, job cards.
    - **Tab 2: Company Career Monitor**: Manage target dream companies, live status, one-click crawl.
    - **Tab 3: Review & Staging Queue (HITL)**: Side-by-side job description, match breakdown, tailored cover letter/pitch note, pre-filled form preview, and `[Approve & Submit]` button.
    - **Tab 4: Application Tracker**: Applied jobs table, submission timestamps, status badges, confirmation screenshots.
    - **Tab 5: Profile & Settings**: In-browser profile editor, target criteria, screening Q&A.
  - `[NEW] huntflow/web/static/app.js`: Reactive frontend controller (API calls, state updates, toast alerts, modals).
- **Verification**: Start server (`uvicorn huntflow.web.app:app`) and verify UI interactions in browser.

---

### [Ticket 12] Unified CLI Suite & End-to-End Verification
**Goal**: Provide full CLI commands and verify complete end-to-end user workflows.
- **Components & Files**:
  - `[NEW] huntflow/cli.py`: Commands:
    - `huntflow init`: Setup configuration files and SQLite DB.
    - `huntflow search [--portals ...] [--keywords ...]`: CLI job search.
    - `huntflow crawl-companies`: CLI career page crawl.
    - `huntflow match`: Score newly discovered jobs.
    - `huntflow review`: Interactive CLI review prompt with rich formatting.
    - `huntflow serve`: Start Web Dashboard server.
  - `[NEW] tests/test_e2e.py`:
    - End-to-end workflow test: init -> profile load -> search/crawl -> match score -> stage application -> review.
  - `[NEW] README.md`: Complete setup and user guide.
- **Verification**: Run `pytest tests/test_e2e.py` and execute CLI commands.

---

## Execution Strategy

We will proceed **one ticket at a time**:
1. Execute the ticket's code changes.
2. Run its automated test suite to ensure green passing tests.
3. Provide a clear status summary before proceeding to the next ticket.
