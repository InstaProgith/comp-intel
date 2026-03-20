from __future__ import annotations

import importlib
import os
import sys
from unittest import TestCase, mock


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
