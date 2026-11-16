"""
Browser Controller for Safe, Anti-Detection Chrome Automation (Ticket 8)

Features:
- Chrome WebDriver initialization with persistent session profile (`--user-data-dir`).
- Anti-detection flags:
  - `--disable-blink-features=AutomationControlled`
  - Removes `navigator.webdriver` via Chrome DevTools Protocol / script evaluation.
  - Realistic user agent and window dimensions.
- Human-like typing simulation (`human_type`) with randomized micro-delays.
- Safe element interactions, scroll into view, and screenshot capture.
"""

from contextlib import contextmanager
import logging
import os
from pathlib import Path
import random
import time
from typing import Generator, Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from guffy.config import BrowserConfig, Settings

logger = logging.getLogger(__name__)


class BrowserController:
    """
    Manages Selenium Chrome lifecycle, anti-detection flags, and human-like interactions.
    """

    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        headless: Optional[bool] = None,
        user_data_dir: Optional[str] = None,
    ):
        if config is None:
            settings = Settings.load_from_yaml()
            self.config = settings.browser
        else:
            self.config = config

        self.headless = headless if headless is not None else self.config.headless
        self.user_data_dir = user_data_dir or self.config.user_data_dir
        self.driver: Optional[webdriver.Chrome] = None

    def build_chrome_options(self) -> Options:
        """Configures Chrome options with anti-detection and persistent session flags."""
        options = Options()

        # Persistent user data directory
        profile_path = Path(self.user_data_dir).resolve()
        profile_path.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={str(profile_path)}")

        # Anti-detection flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Standard stability flags
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--window-size=1440,900")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        if self.headless:
            # Modern headless flag
            options.add_argument("--headless=new")

        return options

    def start(self) -> webdriver.Chrome:
        """Starts Chrome browser with CDP anti-detection injections."""
        if self.driver is not None:
            return self.driver

        options = self.build_chrome_options()
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(self.config.implicit_wait_seconds)
            self.driver.set_page_load_timeout(self.config.page_load_timeout_seconds)

            # Mask navigator.webdriver via CDP script
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        window.chrome = {
                            runtime: {}
                        };
                    """
                },
            )
            return self.driver
        except Exception as e:
            logger.error(f"Failed to start Chrome browser: {e}")
            raise

    def stop(self) -> None:
        """Closes the browser session."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.driver = None

    def navigate(self, url: str) -> bool:
        """Navigates to URL safely."""
        if not self.driver:
            self.start()
        try:
            self.driver.get(url)
            self.random_delay(0.5, 1.2)
            return True
        except Exception as e:
            logger.error(f"Failed navigating to {url}: {e}")
            return False

    @staticmethod
    def random_delay(min_s: float = 0.2, max_s: float = 0.6) -> None:
        """Pause execution for a random human-like interval."""
        time.sleep(random.uniform(min_s, max_s))

    def human_type(self, element: WebElement, text: str, clear_first: bool = True) -> None:
        """
        Types text character by character with randomized realistic micro-intervals.
        """
        if clear_first:
            try:
                element.clear()
            except Exception:
                pass
            self.random_delay(0.05, 0.15)

        for char in text:
            element.send_keys(char)
            # Randomized delay between keystrokes (20ms to 70ms)
            time.sleep(random.uniform(0.02, 0.07))

        self.random_delay(0.1, 0.25)

    def scroll_into_view(self, element: WebElement) -> None:
        """Smoothly scrolls element into view."""
        if self.driver:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            self.random_delay(0.15, 0.3)

    def take_screenshot(self, output_path: str) -> Optional[str]:
        """Saves current viewport screenshot to file."""
        if not self.driver:
            return None
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(path))
            return str(path)
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None


@contextmanager
def get_browser(headless: bool = False, user_data_dir: Optional[str] = None) -> Generator[BrowserController, None, None]:
    """Context manager for safe browser session lifecycle."""
    controller = BrowserController(headless=headless, user_data_dir=user_data_dir)
    try:
        controller.start()
        yield controller
    finally:
        controller.stop()
