from __future__ import annotations

from pathlib import Path
import shutil
from unittest import TestCase, mock

from app import ladbs_scraper

TEST_TMP_ROOT = Path(__file__).resolve().parent.parent / "data" / "test-temp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class LadbsScraperTests(TestCase):
    def test_fetch_pin_route_data_retries_service_unavailable_results_page(self) -> None:
        class _FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        class _FakeSession:
            def __init__(self) -> None:
                self.calls = []

            def get(self, url: str, params=None, timeout=None):  # type: ignore[override]
                self.calls.append({"url": url, "params": params, "timeout": timeout})
                if url == ladbs_scraper.LADBS_PERMIT_RESULTS_BY_PIN_URL:
                    return _FakeResponse("permit-results")
                if url == ladbs_scraper.LADBS_PIN_ADDRESS_PARTIAL_URL:
                    return _FakeResponse("address-partial")
                if "lucerne" in url:
                    return _FakeResponse("lucerne-section")
                return _FakeResponse("permit-detail")

        fake_session = _FakeSession()

        with (
            mock.patch.object(ladbs_scraper, "_build_http_session", return_value=fake_session),
            mock.patch.object(
                ladbs_scraper,
                "_parse_pin_results_summary",
                side_effect=[
                    {"text": "busy", "count_text": None, "permit_count": None, "service_unavailable": True},
                    {"text": "ok", "count_text": "1", "permit_count": 1, "service_unavailable": False},
                ],
            ),
            mock.patch.object(
                ladbs_scraper,
                "_parse_pin_address_sections",
                return_value=[{"label": "1120 S LUCERNE BLVD 90019", "query_suffix": "lucerne"}],
            ),
            mock.patch.object(
                ladbs_scraper,
                "_parse_pin_permit_rows",
                return_value=[
                    {
                        "permit_number": "25014-10000-03595",
                        "url": "https://example.com/detail/lucerne",
                        "job_number": "B25LA33094",
                        "type": "Bldg-Addition",
                        "status_text": "Issued on 11/17/2025",
                        "status_date": "11/17/2025",
                        "work_description": "Major remodel",
                        "address_label": "1120 S LUCERNE BLVD 90019",
                    }
                ],
            ),
            mock.patch.object(
                ladbs_scraper,
                "parse_pcis_detail_html",
                return_value={"permit_number": "25014-10000-03595", "contact_information": {}, "status_history": []},
            ),
            mock.patch.object(ladbs_scraper.time, "sleep"),
        ):
            result = ladbs_scraper._fetch_pin_route_data(
                pin="129B185   131",
                apn="5082004025",
                address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
                fetched_at="2026-03-21 02:00:00",
                pin_resolution={"source": "zimas_ajax_v1", "matched_address": "1120 S LUCERNE BLVD"},
            )

        self.assertEqual(result["source"], "ladbs_pin_v1")
        self.assertEqual(len(result["permits"]), 1)
        self.assertEqual(len(result["pin_route"]["request_attempts"]), 2)
        self.assertTrue(result["pin_route"]["request_attempts"][0]["page_summary"]["service_unavailable"])
        self.assertFalse(result["pin_route"]["request_attempts"][1]["page_summary"]["service_unavailable"])

    def test_fetch_pin_route_data_filters_unrelated_address_sections(self) -> None:
        class _FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        class _FakeSession:
            def __init__(self) -> None:
                self.calls = []

            def get(self, url: str, params=None, timeout=None):  # type: ignore[override]
                self.calls.append({"url": url, "params": params, "timeout": timeout})
                if url == ladbs_scraper.LADBS_PERMIT_RESULTS_BY_PIN_URL:
                    return _FakeResponse("permit-results")
                if url == ladbs_scraper.LADBS_PIN_ADDRESS_PARTIAL_URL:
                    return _FakeResponse("address-partial")
                if "malcolm" in url:
                    return _FakeResponse("malcolm-section")
                if "albers" in url:
                    return _FakeResponse("albers-section")
                return _FakeResponse("permit-detail")

        fake_session = _FakeSession()
        section_rows = {
            "malcolm-section": [
                {
                    "permit_number": "23010-20000-03343",
                    "url": "https://example.com/detail/malcolm",
                    "job_number": "B23VN11182",
                    "type": "Bldg-New",
                    "status_text": "Issued on 4/1/2024",
                    "status_date": "4/1/2024",
                    "work_description": "ADU",
                    "address_label": "2831-2831 1/2 S MALCOLM AVE 90064",
                }
            ],
            "albers-section": [
                {
                    "permit_number": "99999-99999-99999",
                    "url": "https://example.com/detail/albers",
                    "job_number": "X",
                    "type": "Bldg-New",
                    "status_text": "Issued on 1/1/2024",
                    "status_date": "1/1/2024",
                    "work_description": "Wrong parcel",
                    "address_label": "24137 W ALBERS ST 91367",
                }
            ],
        }

        def _parse_rows(html_text: str, address_label: str):
            return list(section_rows[html_text])

        with (
            mock.patch.object(ladbs_scraper, "_build_http_session", return_value=fake_session),
            mock.patch.object(
                ladbs_scraper,
                "_parse_pin_results_summary",
                return_value={"text": "ok", "count_text": "2", "permit_count": 2, "service_unavailable": False},
            ),
            mock.patch.object(
                ladbs_scraper,
                "_parse_pin_address_sections",
                return_value=[
                    {"label": "24137 W ALBERS ST 91367", "query_suffix": "albers"},
                    {"label": "2831-2831 1/2 S MALCOLM AVE 90064", "query_suffix": "malcolm"},
                ],
            ),
            mock.patch.object(ladbs_scraper, "_parse_pin_permit_rows", side_effect=_parse_rows),
            mock.patch.object(
                ladbs_scraper,
                "parse_pcis_detail_html",
                return_value={"permit_number": "23010-20000-03343", "contact_information": {}, "status_history": []},
            ),
        ):
            result = ladbs_scraper._fetch_pin_route_data(
                pin="123B157   607",
                apn="4255013007",
                address="2831 Malcolm Ave, Los Angeles, CA 90064",
                fetched_at="2026-03-21 02:00:00",
                pin_resolution={"source": "zimas_ajax_v1", "matched_address": "2831 1/2 S MALCOLM AVE"},
            )

        self.assertEqual(result["source"], "ladbs_pin_v1")
        self.assertEqual([permit["permit_number"] for permit in result["permits"]], ["23010-20000-03343"])
        self.assertEqual(result["pin_route"]["address_sections"], ["2831-2831 1/2 S MALCOLM AVE 90064"])
        self.assertEqual(result["pin_route"]["ignored_address_sections"], ["24137 W ALBERS ST 91367"])

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
                    strategy="plr",
                )
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

        self.assertEqual(result["source"], "ladbs_stub_driver_error")
        self.assertIn("driver startup failed for test", result["note"])
        self.assertEqual(result["retrieval_strategy"], "plr-address")

    def test_driver_settings_recovers_when_cache_path_is_a_file(self) -> None:
        test_dir = TEST_TMP_ROOT / "ladbs-cache-file"
        shutil.rmtree(test_dir, ignore_errors=True)
        test_dir.mkdir(parents=True, exist_ok=True)
        cache_file = test_dir / "selenium-cache"
        cache_file.write_text("not a directory", encoding="utf-8")

        try:
            with mock.patch.dict(
                "os.environ",
                {
                    "SE_CACHE_PATH": str(cache_file),
                },
                clear=False,
            ):
                settings = ladbs_scraper.get_driver_settings()
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

        self.assertTrue(settings["cache_dir"].endswith("selenium-cache-dir"))

    def test_parse_pin_permit_rows_skips_old_permits(self) -> None:
        html = """
        <table>
          <tr>
            <th>Application/Permit #</th>
            <th>PC/Job #</th>
            <th>Type</th>
            <th>Status</th>
            <th>Work Description</th>
          </tr>
          <tr>
            <td><a href="/OnlineServices/PermitReport/PcisPermitDetail?id1=25014&id2=10000&id3=03595">25014-10000-03595</a></td>
            <td>B25LA33094</td>
            <td>Bldg-Addition</td>
            <td>Issued 11/17/2025</td>
            <td>Major remodel</td>
          </tr>
          <tr>
            <td><a href="/OnlineServices/PermitReport/PcisPermitDetail?id1=06014&id2=70000&id3=09673">06014-70000-09673</a></td>
            <td>06014-70000-09673</td>
            <td>Bldg-Addition</td>
            <td>CofO Issued 2/16/2016</td>
            <td>Old permit</td>
          </tr>
        </table>
        """

        permits = ladbs_scraper._parse_pin_permit_rows(html, "1120 S LUCERNE BLVD 90019")

        self.assertEqual(len(permits), 1)
        self.assertEqual(permits[0]["permit_number"], "25014-10000-03595")
        self.assertEqual(permits[0]["address_label"], "1120 S LUCERNE BLVD 90019")

    def test_parse_pcis_detail_html_extracts_key_fields(self) -> None:
        html = """
        <html>
          <body>
            <dl>
              <dt>Application / Permit</dt><dd>25014-10000-03595</dd>
              <dt>Plan Check / Job No.</dt><dd>B25LA33094</dd>
              <dt>Type</dt><dd>Bldg-Addition</dd>
              <dt>Sub-Type</dt><dd>1 or 2 Family Dwelling</dd>
              <dt>Work Description</dt><dd>Major remodel</dd>
              <dt>Permit Issued</dt><dd>Issued on 11/17/2025</dd>
              <dt>Current Status</dt><dd>Issued on 11/17/2025</dd>
            </dl>
            <h3>Contact Information</h3>
            <table>
              <tr><td>Contractor:</td><td>Stay Forever Construction Corporation; Lic. No.: 986055-B</td><td>Valencia, CA</td></tr>
            </table>
            <h3>Permit Application Status History</h3>
            <table>
              <tr><td>Submitted</td><td>8/8/2025</td><td>APPLICANT</td></tr>
            </table>
          </body>
        </html>
        """

        details = ladbs_scraper.parse_pcis_detail_html(html)

        self.assertEqual(details["permit_number"], "25014-10000-03595")
        self.assertEqual(details["job_number"], "B25LA33094")
        self.assertEqual(details["type"], "Bldg-Addition")
        self.assertEqual(details["sub_type"], "1 or 2 Family Dwelling")
        self.assertEqual(details["contact_information"]["Contractor"], "Stay Forever Construction Corporation; Lic. No.: 986055-B Valencia, CA")
        self.assertEqual(details["status_history"][0]["event"], "Submitted")

    def test_get_ladbs_data_pin_first_success_without_fallback(self) -> None:
        pin_resolution = {
            "pin": "129B185   131",
            "source": "zimas_ajax_v1",
            "note": "Resolved via ZIMAS.",
            "matched_address": "1120 S LUCERNE BLVD",
        }
        pin_result = {
            "source": "ladbs_pin_v1",
            "apn": None,
            "address": None,
            "fetched_at": "2026-03-20 12:00:00",
            "permits": [{"permit_number": "25014-10000-03595"}],
            "pin": "129B185   131",
            "pin_source": "zimas_ajax_v1",
            "note": "Fetched permits by PIN.",
            "pin_route": {"page_summary": {"permit_count": 3}},
        }

        with (
            mock.patch.object(ladbs_scraper, "resolve_pin", return_value=pin_resolution),
            mock.patch.object(ladbs_scraper, "_fetch_pin_route_data", return_value=pin_result),
            mock.patch.object(ladbs_scraper, "_get_ladbs_data_via_plr") as plr_mock,
        ):
            result = ladbs_scraper.get_ladbs_data(
                apn=None,
                address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
                redfin_url=None,
            )

        plr_mock.assert_not_called()
        self.assertEqual(result["source"], "ladbs_pin_v1")
        self.assertEqual(result["retrieval_strategy"], "pin-first")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["pin"], "129B185   131")
        self.assertEqual(result["pin_source"], "zimas_ajax_v1")
        self.assertEqual(result["address"], "1120 S LUCERNE BLVD")

    def test_get_ladbs_data_pin_first_falls_back_to_plr(self) -> None:
        pin_resolution = {
            "pin": None,
            "source": "zimas_no_match",
            "note": "No PIN match.",
        }
        plr_result = {
            "source": "ladbs_plr_v6",
            "apn": None,
            "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
            "fetched_at": "2026-03-20 12:00:00",
            "permits": [{"permit_number": "25014-10000-03595"}],
            "note": "Found via PLR.",
            "retrieval_strategy": "plr-address-fallback",
            "fallback_used": True,
            "pin": None,
            "pin_source": "zimas_no_match",
        }

        with (
            mock.patch.object(ladbs_scraper, "resolve_pin", return_value=pin_resolution),
            mock.patch.object(ladbs_scraper, "_get_ladbs_data_via_plr", return_value=plr_result) as plr_mock,
        ):
            result = ladbs_scraper.get_ladbs_data(
                apn=None,
                address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
                redfin_url=None,
            )

        plr_mock.assert_called_once()
        self.assertEqual(result["source"], "ladbs_plr_v6")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["retrieval_strategy"], "plr-address-fallback")
