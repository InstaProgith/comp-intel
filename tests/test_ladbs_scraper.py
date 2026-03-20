from __future__ import annotations

from pathlib import Path
import shutil
from unittest import TestCase, mock

from app import ladbs_scraper

TEST_TMP_ROOT = Path(__file__).resolve().parent.parent / "data" / "test-temp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class LadbsScraperTests(TestCase):
    def test_driver_settings_use_writable_workspace_dirs(self) -> None:
        test_dir = TEST_TMP_ROOT / "ladbs-scraper-test"
        shutil.rmtree(test_dir, ignore_errors=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        cache_dir = test_dir / "cache"
        profile_dir = test_dir / "profiles"
        custom_driver = test_dir / "chromedriver"
        custom_browser = test_dir / "chrome.exe"

        try:
            custom_driver.write_text("", encoding="utf-8")
            custom_browser.write_text("", encoding="utf-8")
            with mock.patch.dict(
                "os.environ",
                {
                    "SE_CACHE_PATH": str(cache_dir),
                    "LADBS_SELENIUM_PROFILE_DIR": str(profile_dir),
                    "LADBS_CHROME_BINARY": str(custom_browser),
                    "LADBS_CHROMEDRIVER_PATH": str(custom_driver),
                    "LADBS_DRIVER_START_RETRIES": "3",
                    "LADBS_HEADLESS": "0",
                },
                clear=False,
            ):
                settings = ladbs_scraper.get_driver_settings()

            self.assertEqual(settings["cache_dir"], str(cache_dir))
            self.assertEqual(settings["profile_root"], str(profile_dir))
            self.assertEqual(settings["chrome_binary"], str(custom_browser))
            self.assertEqual(settings["chrome_binary_source"], "env:LADBS_CHROME_BINARY")
            self.assertEqual(settings["chromedriver_path"], str(custom_driver))
            self.assertEqual(settings["chromedriver_source"], "env:LADBS_CHROMEDRIVER_PATH")
            self.assertEqual(settings["start_retries"], 3)
            self.assertFalse(settings["headless"])
            self.assertTrue(cache_dir.exists())
            self.assertTrue(profile_dir.exists())
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_extract_address_from_text_supports_direct_address_input(self) -> None:
        street_number, street_name = ladbs_scraper.extract_address_from_text(
            "1120 S Lucerne Blvd, Los Angeles, CA 90019"
        )

        self.assertEqual(street_number, "1120")
        self.assertEqual(street_name, "Lucerne")

    def test_get_ladbs_data_accepts_direct_address_without_redfin_url(self) -> None:
        test_dir = TEST_TMP_ROOT / "ladbs-direct-address"
        shutil.rmtree(test_dir, ignore_errors=True)
        test_dir.mkdir(parents=True, exist_ok=True)
        settings = ladbs_scraper.DriverSettings(
            chrome_binary=str(test_dir / "chrome.exe"),
            chrome_binary_source="env:LADBS_CHROME_BINARY",
            chromedriver_path=str(test_dir / "chromedriver.exe"),
            chromedriver_source="env:LADBS_CHROMEDRIVER_PATH",
            cache_dir=test_dir / "cache",
            profile_root=test_dir / "profiles",
            browser_env_root=test_dir / "browser-env",
            logs_dir=test_dir / "logs",
            start_retries=1,
            retry_delay_seconds=0.0,
            page_load_timeout_seconds=15,
            implicit_wait_seconds=0,
            headless=True,
            allow_headed_fallback=True,
            use_remote_debugging_pipe=False,
            browser_probe_timeout_seconds=3,
        )

        try:
            with (
                mock.patch.object(ladbs_scraper, "setup_driver", return_value=None),
                mock.patch.object(ladbs_scraper, "_resolve_driver_settings", return_value=settings),
                mock.patch.object(
                    ladbs_scraper,
                    "LAST_DRIVER_ERROR_SUMMARY",
                    "driver startup failed for test",
                ),
            ):
                result = ladbs_scraper.get_ladbs_data(
                    apn=None,
                    address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
                    redfin_url=None,
                )
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

        self.assertEqual(result["source"], "ladbs_stub_driver_error")
        self.assertIn("driver startup failed for test", result["note"])
