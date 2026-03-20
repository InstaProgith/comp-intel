from __future__ import annotations

from unittest import TestCase, mock

from app import runtime_config


class RuntimeConfigTests(TestCase):
    def test_resolve_flask_secret_key_requires_value_in_production(self) -> None:
        with mock.patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                runtime_config.resolve_flask_secret_key()

    def test_resolve_access_password_uses_dev_placeholder_outside_production(self) -> None:
        with mock.patch.dict("os.environ", {"APP_ENV": "development"}, clear=True):
            with self.assertWarns(RuntimeWarning):
                self.assertEqual(runtime_config.resolve_access_password(), "CHANGE_ME_DEV")
