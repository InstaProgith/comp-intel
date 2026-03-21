from __future__ import annotations

from unittest import TestCase

from app import zimas_pin_client


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, text: str) -> None:
        self._text = text
        self.headers = {}
        self.calls = []

    def get(self, url: str, params=None, timeout=None):  # type: ignore[override]
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(self._text)


class ZimasPinClientTests(TestCase):
    def test_parse_search_response_extracts_pin_and_matched_address(self) -> None:
        parsed = zimas_pin_client.parse_search_response(
            "{action: \"ZimasData.navigateDataToPin('129B185   131', '1120 S LUCERNE BLVD');\"}"
        )

        self.assertEqual(parsed["pin"], "129B185   131")
        self.assertEqual(parsed["matched_address"], "1120 S LUCERNE BLVD")
        self.assertIsNone(parsed["error_message"])

    def test_resolve_pin_uses_ajax_search_response(self) -> None:
        session = _FakeSession(
            "{action: \"ZimasData.setWaitingDataTabs; "
            "ZimasData.navigateDataToPin('129B185   131', '1120 S LUCERNE BLVD');\"}"
        )

        result = zimas_pin_client.resolve_pin(
            address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
            session=session,
        )

        self.assertEqual(result["source"], "zimas_ajax_v1")
        self.assertEqual(result["pin"], "129B185   131")
        self.assertEqual(result["street_number"], "1120")
        self.assertEqual(result["street_name"], "Lucerne")
        self.assertEqual(session.calls[0]["params"]["HouseNumber"], "1120")
        self.assertEqual(session.calls[0]["params"]["StreetName"], "Lucerne")

    def test_resolve_pin_returns_no_match_for_error_response(self) -> None:
        session = _FakeSession(
            "{type: 'error', message: 'There was no address found for the house number and street you entered, please try your search again.'}"
        )

        result = zimas_pin_client.resolve_pin(
            address="99999 Fake St, Los Angeles, CA 90019",
            session=session,
        )

        self.assertEqual(result["source"], "zimas_no_match")
        self.assertIsNone(result["pin"])
        self.assertIn("There was no address found", result["note"])
