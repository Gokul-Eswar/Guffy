"""
Unit Tests for Web Dashboard SPA (Ticket 11)
"""

from pathlib import Path
import pytest
from guffy.web.app import static_dir


def test_static_directory_and_assets_exist():
    """Verify that static UI assets for the Tailwind SPA exist on disk."""
    assert static_dir.exists(), "Static directory should exist"
    
    index_html = static_dir / "index.html"
    assert index_html.exists(), "index.html must exist"
    
    app_js = static_dir / "app.js"
    assert app_js.exists(), "app.js must exist"


def test_index_html_structure():
    """Verify index.html contains essential layout elements and components."""
    index_html = static_dir / "index.html"
    content = index_html.read_text(encoding="utf-8")
    
    # Check framework and dependencies
    assert "cdn.tailwindcss.com" in content
    assert "font-awesome" in content
    assert "/static/app.js" in content
    
    # Check main tabs and sections
    assert 'id="tab-jobs"' in content
    assert 'id="tab-review"' in content
    assert 'id="tab-companies"' in content
    assert 'id="tab-profile"' in content
    assert 'id="tab-analytics"' in content
    
    # Check modals
    assert 'id="job-detail-modal"' in content
    assert 'id="search-modal"' in content
    assert 'id="crawl-modal"' in content
    assert 'id="add-company-modal"' in content


def test_app_js_functionality():
    """Verify app.js defines essential interactive handlers."""
    app_js = static_dir / "app.js"
    content = app_js.read_text(encoding="utf-8")
    
    # Core state & tab routing
    assert "switchTab" in content
    assert "loadJobs" in content
    assert "renderJobsTable" in content
    assert "loadStagedJobs" in content
    assert "loadCompanies" in content
    assert "loadProfile" in content
    assert "loadAnalytics" in content
    
    # HITL actions & endpoints
    assert "stageSingleJob" in content
    assert "approveSingleJob" in content
    assert "executeSearchPortals" in content
    assert "executeCrawlCompanies" in content
    assert "triggerRunMatch" in content
