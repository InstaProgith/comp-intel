from __future__ import annotations

from unittest import TestCase

from app import zimas_client


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, response_map):
        self.response_map = response_map
        self.headers = {}
        self.calls = []

    def get(self, url: str, params=None, timeout=None):  # type: ignore[override]
        key = (url, tuple(sorted((params or {}).items())))
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(self.response_map[key])


class ZimasClientTests(TestCase):
    def test_extract_pin_from_apn_response(self) -> None:
        pin, address = zimas_client._extract_pin_from_apn_response(
            '{type: "APN", pin: "129B185   131", Address: "1120 S LUCERNE BLVD"}'
        )

        self.assertEqual(pin, "129B185   131")
        self.assertEqual(address, "1120 S LUCERNE BLVD")

    def test_parse_profile_payload_extracts_core_fields(self) -> None:
        payload = (
            '{Address: "1120 S LUCERNE BLVD", selectedAPN: "5082004025", '
            'divTab1: "<table><tr><td>Site Address</td><td>1120 S LUCERNE BLVD</td></tr>'
            '<tr><td>ZIP Code</td><td>90019</td></tr>'
            '<tr><td>PIN Number</td><td>129B185   131</td></tr>'
            '<tr><td>Lot/Parcel Area (Calculated)</td><td>7,196.1 (sq ft)</td></tr>'
            '<tr><td>Assessor Parcel No. (APN)</td><td>5082004025</td></tr></table>", '
            'divTab2: "<table><tr><td>Community Plan Area</td><td>Wilshire</td></tr>'
            '<tr><td>Council District</td><td>CD 10 - Heather Hutt</td></tr></table>", '
            'divTab3: "<table><tr><td>Zoning</td><td>R1-1-O</td></tr>'
            '<tr><td>General Plan Land Use</td><td>Low II Residential</td></tr>'
            '<tr><td>General Plan Note(s)</td><td>Yes</td></tr>'
            '<tr><td>Hillside Area (Zoning Code)</td><td>No</td></tr>'
            '<tr><td>Residential Market Area</td><td>Medium-High</td></tr></table>", '
            'divTab7: "<table><tr><td>Flood Zone</td><td>500 Yr</td></tr>'
            '<tr><td>Methane Hazard Site</td><td>Methane Zone</td></tr></table>", '
            'divTab8: "<table><tr><td>Nearest Fault (Name)</td><td>Puente Hills Blind Thrust</td></tr>'
            '<tr><td>Nearest Fault (Distance in km)</td><td>2.5415748</td></tr>'
            '<tr><td>Tsunami Hazard Area</td><td>No</td></tr></table>", '
            'divTab1200: "<table><tr><td>Building Permit Info</td><td>View</td></tr></table>"}'
        )

        parsed = zimas_client._parse_profile_payload(payload)

        self.assertEqual(parsed["parcel_identity"]["site_address"], "1120 S LUCERNE BLVD")
        self.assertEqual(parsed["parcel_identity"]["apn"], "5082004025")
        self.assertEqual(parsed["planning_context"]["community_plan_area"], "Wilshire")
        self.assertEqual(parsed["zoning_profile"]["zoning"], "R1-1-O")
        self.assertEqual(parsed["zoning_profile"]["general_plan_notes"], "Yes")
        self.assertEqual(parsed["zoning_profile"]["residential_market_area"], "Medium-High")
        self.assertEqual(parsed["environmental_profile"]["hillside_area"], "No")
        self.assertEqual(parsed["environmental_profile"]["flood_zone"], "500 Yr")
        self.assertEqual(parsed["hazard_profile"]["nearest_fault"], "Puente Hills Blind Thrust")
        self.assertEqual(parsed["hazard_profile"]["nearest_fault_distance_km"], 2.5415748)
        self.assertEqual(parsed["hazard_profile"]["tsunami_hazard_area"], "No")
        self.assertEqual(parsed["permit_references"]["building_permit_info"], "View")

    def test_get_zimas_profile_uses_direct_pin(self) -> None:
        profile_response = (
            '{Address: "1120 S LUCERNE BLVD", selectedAPN: "5082004025", '
            'divTab1: "<table><tr><td>Site Address</td><td>1120 S LUCERNE BLVD</td></tr>'
            '<tr><td>PIN Number</td><td>129B185   131</td></tr>'
            '<tr><td>Assessor Parcel No. (APN)</td><td>5082004025</td></tr></table>", '
            'divTab3: "<table><tr><td>Zoning</td><td>R1-1-O</td></tr></table>"}'
        )
        session = _FakeSession(
            {
                (
                    zimas_client.ZIMAS_PROFILE_URL,
                    (("ajax", "yes"), ("pin", "129B185   131")),
                ): profile_response
            }
        )

        result = zimas_client.get_zimas_profile(pin="129B185   131", session=session)

        self.assertEqual(result["source"], "zimas_profile_v1")
        self.assertEqual(result["pin"], "129B185   131")
        self.assertEqual(result["apn"], "5082004025")
        self.assertEqual(result["zoning_profile"]["zoning"], "R1-1-O")

    def test_get_zimas_profile_preserves_apn_lookup_pin_spacing(self) -> None:
        apn_response = '{type: "APN", pin: "129B185   131", Address: "1120 S LUCERNE BLVD"}'
        profile_response = (
            '{Address: "1120 S LUCERNE BLVD", selectedAPN: "5082004025", '
            'divTab1: "<table><tr><td>Site Address</td><td>1120 S LUCERNE BLVD</td></tr>'
            '<tr><td>PIN Number</td><td>129B185   131</td></tr>'
            '<tr><td>Assessor Parcel No. (APN)</td><td>5082004025</td></tr></table>", '
            'divTab2: "<table><tr><td>Community Plan Area</td><td>Wilshire</td></tr></table>", '
            'divTab3: "<table><tr><td>Zoning</td><td>R1-1-O</td></tr></table>"}'
        )
        session = _FakeSession(
            {
                (
                    zimas_client.ZIMAS_SEARCH_URL,
                    (("apn", "5082004025"), ("search", "apn")),
                ): apn_response,
                (
                    zimas_client.ZIMAS_PROFILE_URL,
                    (("ajax", "yes"), ("pin", "129B185   131")),
                ): profile_response,
            }
        )

        result = zimas_client.get_zimas_profile(apn="5082004025", session=session)

        self.assertEqual(result["source"], "zimas_profile_v1")
        self.assertEqual(result["pin"], "129B185   131")
        self.assertEqual(result["planning_context"]["community_plan_area"], "Wilshire")
        self.assertEqual(result["zoning_profile"]["zoning"], "R1-1-O")
