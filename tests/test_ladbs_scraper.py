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

        try:
            with mock.patch.dict(
                "os.environ",
                {
                    "SE_CACHE_PATH": str(cache_dir),
                    "LADBS_SELENIUM_PROFILE_DIR": str(profile_dir),
                    "LADBS_CHROMEDRIVER_PATH": str(custom_driver),
                    "LADBS_DRIVER_START_RETRIES": "3",
                    "LADBS_HEADLESS": "0",
                },
                clear=False,
            ):
                settings = ladbs_scraper.get_driver_settings()

            self.assertEqual(settings["cache_dir"], str(cache_dir))
            self.assertEqual(settings["profile_root"], str(profile_dir))
            self.assertEqual(settings["chromedriver_path"], str(custom_driver))
            self.assertEqual(settings["start_retries"], 3)
            self.assertFalse(settings["headless"])
            self.assertTrue(cache_dir.exists())
            self.assertTrue(profile_dir.exists())
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
