"""
Guffy Configuration Loader and Settings Model
"""

from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = "Guffy"
    version: str = "0.1.0"
    database_url: str = "sqlite:///./data/Guffy.db"
    screenshots_dir: str = "./data/screenshots"
    resumes_dir: str = "./data/resumes"


class SearchConfig(BaseModel):
    keywords: List[str] = Field(default_factory=lambda: ["Software Engineer"])
    locations: List[str] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = True
    min_match_score: int = 75
    max_jobs_per_source: int = 30


class BrowserConfig(BaseModel):
    headless: bool = False
    user_data_dir: str = "./.browser_profile"
    implicit_wait_seconds: int = 5
    page_load_timeout_seconds: int = 30


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)

    @classmethod
    def load_from_yaml(cls, path: str = "config.yaml") -> "Settings":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            
        return cls(**data)


_settings: Optional[Settings] = None


def get_settings(config_path: str = "config.yaml") -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load_from_yaml(config_path)
    return _settings
