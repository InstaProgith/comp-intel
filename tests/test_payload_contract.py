from __future__ import annotations

from unittest import TestCase

from app.payload_contract import apply_payload_contract, detect_payload_anomalies


class PayloadContractTests(TestCase):
    def test_apply_payload_contract_fills_expected_sections(self) -> None:
        payload = apply_payload_contract(
            {
                "url": "https://example.com/property",
                "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                "redfin": {"source": "redfin_parsed_v3", "timeline": []},
                "ladbs": {"source": "ladbs_pin_v1", "permits": []},
            }
        )

        self.assertEqual(payload["payload_contract_version"], "qa-v1")
        self.assertIsInstance(payload["metrics"], dict)
        self.assertIsInstance(payload["headline_metrics"], dict)
        self.assertIsInstance(payload["zimas_profile"], dict)
        self.assertIsInstance(payload["ladbs_records"], dict)
        self.assertIsInstance(payload["anomalies"], list)
        self.assertIsInstance(payload["source_diagnostics"], dict)
        self.assertEqual(payload["ladbs_records"]["documents"], [])
        self.assertEqual(payload["zimas_profile"]["parcel_identity"]["pin"], None)
        self.assertEqual(payload["source_diagnostics"]["schema_warnings"], [])
        self.assertEqual(payload["source_diagnostics"]["anomaly_codes"], [])

    def test_detect_payload_anomalies_flags_review_cases(self) -> None:
        payload = apply_payload_contract(
            {
                "metrics": {"land_sf": 8379.0},
                "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                "zimas_profile": {
                    "source": "zimas_profile_v1",
                    "parcel_identity": {"lot_area_sqft": 7196.1},
                    "planning_context": {"community_plan_area": "Wilshire"},
                    "zoning_profile": {"zoning": "R1-1-O"},
                },
                "zimas_ok": True,
                "ladbs": {
                    "source": "ladbs_pin_v1",
                    "permits": [
                        {"address_label": "1120 S LUCERNE BLVD 90019"},
                        {"address_label": "1122 S LUCERNE BLVD 90019"},
                    ],
                },
                "ladbs_records": {
                    "source": "ladbs_records_v1",
                    "documents": [
                        {"record_id": "56658478", "doc_number": "06014-70000-09673", "doc_date": "10/27/2006"},
                        {"record_id": "56658478", "doc_number": "CERT 40332", "doc_date": "2/16/2016"},
                        {"record_id": "130956780", "doc_number": "25041-90000-59794", "doc_date": "12/22/2025"},
                    ],
                },
            }
        )

        anomaly_codes = {anomaly["code"] for anomaly in detect_payload_anomalies(payload)}

        self.assertIn("lot_size_mismatch", anomaly_codes)
        self.assertIn("permit_address_variants", anomaly_codes)
        self.assertIn("shared_record_ids", anomaly_codes)

    def test_detect_payload_anomalies_ignores_temp_and_range_labels_that_include_subject(self) -> None:
        payload = apply_payload_contract(
            {
                "address": "3629 Rosewood Ave, Los Angeles, CA 90066",
                "ladbs": {
                    "source": "ladbs_pin_v1",
                    "permits": [
                        {"address_label": "3629 S ROSEWOOD AVE 90066"},
                        {"address_label": "3629 S ROSEWOOD AVE TEMP 90066"},
                        {"address_label": "3627-3629 S ROSEWOOD AVE 90066"},
                    ],
                },
            }
        )

        anomaly_codes = {anomaly["code"] for anomaly in payload["anomalies"]}

        self.assertNotIn("permit_address_variants", anomaly_codes)

    def test_detect_payload_anomalies_ignores_same_day_certificate_bundles(self) -> None:
        payload = apply_payload_contract(
            {
                "ladbs_records": {
                    "source": "ladbs_records_v1",
                    "documents": [
                        {"record_id": "130935075", "doc_number": "CERT 275679", "doc_type": "CERTIFICATE OF OCCUPANCY", "doc_date": "11/29/2025"},
                        {"record_id": "130935075", "doc_number": "24014-30001-03980", "doc_type": "CERTIFICATE OF OCCUPANCY", "doc_date": "11/29/2025"},
                        {"record_id": "130935075", "doc_number": "24014-30000-03980", "doc_type": "CERTIFICATE OF OCCUPANCY", "doc_date": "11/29/2025"},
                    ],
                },
            }
        )

        anomaly_codes = {anomaly["code"] for anomaly in payload["anomalies"]}

        self.assertNotIn("shared_record_ids", anomaly_codes)

    def test_apply_payload_contract_sorts_permits_and_documents_newest_first(self) -> None:
        payload = apply_payload_contract(
            {
                "ladbs": {
                    "permits": [
                        {"permit_number": "older", "status_date": "11/17/2025", "Issued_Date": "Issued on 11/17/2025"},
                        {"permit_number": "newer", "status_date": "2/28/2026", "Issued_Date": "Issued on 2/28/2026"},
                    ]
                },
                "ladbs_records": {
                    "documents": [
                        {"doc_number": "older-doc", "doc_date": "10/27/2006"},
                        {"doc_number": "newer-doc", "doc_date": "2/16/2016"},
                    ]
                },
            }
        )

        self.assertEqual(payload["ladbs"]["permits"][0]["permit_number"], "newer")
        self.assertEqual(payload["ladbs_records"]["documents"][0]["doc_number"], "newer-doc")
        anomaly_codes = {anomaly["code"] for anomaly in payload["anomalies"]}
        self.assertNotIn("records_not_date_sorted", anomaly_codes)
