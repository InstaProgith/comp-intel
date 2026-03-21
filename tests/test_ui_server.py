from __future__ import annotations

import importlib
import os
import sys
from unittest import TestCase, mock

from app.payload_contract import apply_payload_contract


def _load_ui_server():
    sys.modules.pop("app.ui_server", None)
    import app.ui_server as ui_server

    return importlib.reload(ui_server)


class UIServerTests(TestCase):
    def test_login_flow_and_history_api_smoke(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "APP_TESTING": "1",
                "FLASK_SECRET_KEY": "test-secret-key",
                "APP_ACCESS_PASSWORD": "test-password",
            },
            clear=False,
        ):
            os.environ.pop("PORT", None)
            os.environ.pop("GUNICORN_CMD_ARGS", None)
            os.environ.pop("SERVER_SOFTWARE", None)
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("FLASK_DEBUG", None)

            ui_server = _load_ui_server()
            client = ui_server.app.test_client()

            login_page = client.get("/")
            self.assertEqual(login_page.status_code, 200)
            self.assertIn(b"Access password", login_page.data)

            logged_in = client.post("/", data={"password": "test-password"}, follow_redirects=True)
            self.assertEqual(logged_in.status_code, 200)
            self.assertIn(b"Paste Redfin URLs", logged_in.data)

            history_payload = client.get("/api/history")
            self.assertEqual(history_payload.status_code, 200)
            self.assertTrue(history_payload.is_json)

    def test_single_report_accepts_redfin_url_field(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "APP_TESTING": "1",
                "FLASK_SECRET_KEY": "test-secret-key",
                "APP_ACCESS_PASSWORD": "test-password",
            },
            clear=False,
        ):
            os.environ.pop("PORT", None)
            os.environ.pop("GUNICORN_CMD_ARGS", None)
            os.environ.pop("SERVER_SOFTWARE", None)
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("FLASK_DEBUG", None)

            ui_server = _load_ui_server()
            client = ui_server.app.test_client()

            client.post("/", data={"password": "test-password"}, follow_redirects=True)

            fake_result = {"address": "1120 S Lucerne Blvd, Los Angeles, CA 90019"}

            with (
                mock.patch.object(ui_server, "run_full_comp_pipeline", return_value=fake_result) as pipeline_mock,
                mock.patch.object(ui_server, "render_template", return_value="rendered-report") as render_mock,
            ):
                report = client.post(
                    "/report",
                    data={
                        "redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
                    },
                )

            self.assertEqual(report.status_code, 200)
            self.assertIn(b"rendered-report", report.data)
            pipeline_mock.assert_called_once_with(
                "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
            )
            render_mock.assert_called_once()
            self.assertEqual(render_mock.call_args.kwargs["r"], fake_result)

    def test_single_report_render_shows_review_flags_and_hides_none_null(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "APP_TESTING": "1",
                "FLASK_SECRET_KEY": "test-secret-key",
                "APP_ACCESS_PASSWORD": "test-password",
            },
            clear=False,
        ):
            os.environ.pop("PORT", None)
            os.environ.pop("GUNICORN_CMD_ARGS", None)
            os.environ.pop("SERVER_SOFTWARE", None)
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("FLASK_DEBUG", None)

            ui_server = _load_ui_server()
            client = ui_server.app.test_client()

            client.post("/", data={"password": "test-password"}, follow_redirects=True)

            fake_result = apply_payload_contract(
                {
                    "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                    "url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003",
                    "metrics": {
                        "purchase_price": 0,
                        "exit_price": 0,
                        "hold_days": 0,
                        "spread": 0,
                        "roi_pct": 0,
                        "spread_per_day": 0,
                        "land_sf": 0,
                        "far_before": 0,
                        "far_after": 0,
                    },
                    "property_snapshot": {
                        "address_full": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                        "beds": 2,
                        "baths": 1,
                        "building_sf": 1008,
                        "lot_sf": 8379,
                        "property_type": "Single Family Residential",
                        "year_built": 1922,
                        "status": "Sold",
                        "status_date": "2025-09-05",
                        "status_price": 800000,
                    },
                    "construction_summary": {
                        "existing_sf": 0,
                        "added_sf": 0,
                        "final_sf": 0,
                        "lot_sf": 0,
                        "scope_level": "LIGHT",
                        "is_new_construction": False,
                    },
                    "permit_categories": {
                        "building_count": 1,
                        "demo_count": 0,
                        "mep_count": 0,
                        "other_count": 0,
                        "scope_level": "LIGHT",
                        "permit_complexity_score": "LOW",
                    },
                    "ladbs": {
                        "source": "ladbs_pin_v1",
                        "permits": [
                            {
                                "permit_number": "25014-10000-03595",
                                "permit_type": "Bldg-Addition - 1 or 2 Family Dwelling",
                                "Type": "Bldg-Addition - 1 or 2 Family Dwelling",
                                "Status": "Issued on 11/17/2025",
                                "Work_Description": "Major remodel",
                                "address_label": "1120 S LUCERNE BLVD 90019",
                            }
                        ],
                    },
                    "zimas_profile": {
                        "source": "zimas_profile_v1",
                        "transport": "http",
                        "pin": "129B185   131",
                        "apn": "5082004025",
                        "parcel_identity": {"lot_area_sqft": 7196.1},
                        "planning_context": {"community_plan_area": "Wilshire", "council_district": "CD 10 - Heather Hutt"},
                        "zoning_profile": {"zoning": "R1-1-O", "general_plan_land_use": "Low II Residential"},
                        "environmental_profile": {"flood_zone": "500 Yr", "methane_hazard_site": "Methane Zone"},
                        "hazard_profile": {"nearest_fault": "Puente Hills Blind Thrust"},
                    },
                    "ladbs_records": {
                        "source": "ladbs_records_v1",
                        "transport": "http",
                        "documents": [
                            {
                                "doc_number": "06014-70000-09673",
                                "doc_type": "BUILDING PERMIT",
                                "doc_date": "10/27/2006",
                                "record_id": "56658478",
                                "has_digital_image": True,
                            },
                            {
                                "doc_number": "CERT 40332",
                                "doc_type": "CERTIFICATE OF OCCUPANCY",
                                "doc_date": "2/16/2016",
                                "record_id": "56658478",
                                "has_digital_image": True,
                            },
                        ],
                    },
                    "links": {"redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"},
                }
            )

            with mock.patch.object(ui_server, "run_full_comp_pipeline", return_value=fake_result):
                report = client.post(
                    "/report",
                    data={
                        "redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
                    },
                )

            self.assertEqual(report.status_code, 200)
            html = report.get_data(as_text=True)
            self.assertIn("Review Flags", html)
            self.assertIn("LADBS Records", html)
            self.assertIn("ZIMAS Parcel Profile", html)
            self.assertIn("BLDGBIT - Property Report", html)
            self.assertIn("$0", html)
            self.assertIn("0 days", html)
            self.assertNotIn(">None<", html)
            self.assertNotIn("null", html)
