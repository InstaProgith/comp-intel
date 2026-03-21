from __future__ import annotations

from unittest import TestCase

from app.payload_contract import apply_payload_contract
from app.qa_harness import _evaluate_expectations


class QAHarnessTests(TestCase):
    def test_evaluate_expectations_accepts_matching_payload_and_report(self) -> None:
        payload = apply_payload_contract(
            {
                "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                "zimas_profile": {
                    "source": "zimas_profile_v1",
                    "pin": "129B185   131",
                    "apn": "5082004025",
                    "zoning_profile": {"zoning": "R1-1-O", "general_plan_land_use": "Low II Residential"},
                    "planning_context": {"community_plan_area": "Wilshire"},
                },
                "ladbs": {
                    "source": "ladbs_pin_v1",
                    "permits": [
                        {"permit_number": "25041-90000-59794"},
                        {"permit_number": "25042-90000-22280"},
                        {"permit_number": "25014-10000-03595"},
                        {"permit_number": "extra-permit"},
                    ]
                },
                "ladbs_records": {
                    "source": "ladbs_records_v1",
                    "documents": [
                        {"doc_number": "06014-70000-09673", "doc_date": "10/27/2006", "pdf_url": "one"},
                        {"doc_number": "06016-70000-21824", "doc_date": "10/30/2006", "pdf_url": "two"},
                        {"doc_number": "06014-70001-09673", "doc_date": "11/14/2006", "pdf_url": "three"},
                        {"doc_number": "extra-doc", "doc_date": "01/01/2010", "pdf_url": "four"},
                    ]
                },
            }
        )
        case = {
            "expectations": {
                "address_contains": "Lucerne",
                "pin": "129B185   131",
                "apn": "5082004025",
                "zoning": "R1-1-O",
                "general_plan_land_use": "Low II Residential",
                "community_plan_area": "Wilshire",
                "allowed_zimas_sources": ["zimas_profile_v1"],
                "allowed_permit_sources": ["ladbs_pin_v1"],
                "allowed_records_sources": ["ladbs_records_v1"],
                "min_permit_count": 3,
                "min_record_count": 3,
                "min_pdf_count": 3,
                "required_permit_numbers": [
                    "25041-90000-59794",
                    "25042-90000-22280",
                    "25014-10000-03595",
                ],
                "required_document_numbers": [
                    "06014-70000-09673",
                    "06016-70000-21824",
                    "06014-70001-09673",
                ],
                "required_report_sections": ["ZIMAS Parcel Profile", "LADBS Records"],
                "forbidden_report_strings": ["null"],
                "required_data_note_substrings": [],
            }
        }
        html = "<html><body>ZIMAS Parcel Profile LADBS Records Review Flags</body></html>"

        failures = _evaluate_expectations(case, payload, html)

        self.assertEqual(failures, [])

    def test_evaluate_expectations_reports_missing_values(self) -> None:
        payload = apply_payload_contract(
            {
                "address": "Other address",
                "zimas_profile": {
                    "pin": "wrong",
                    "apn": "wrong",
                    "zoning_profile": {"zoning": "C2", "general_plan_land_use": "Commercial"},
                    "planning_context": {"community_plan_area": "Downtown"},
                },
                "ladbs": {"source": "ladbs_pin_error", "permits": []},
                "ladbs_records": {"source": "ladbs_records_error", "documents": []},
            }
        )
        case = {
            "expectations": {
                "address_contains": "Lucerne",
                "pin": "129B185   131",
                "apn": "5082004025",
                "zoning": "R1-1-O",
                "general_plan_land_use": "Low II Residential",
                "community_plan_area": "Wilshire",
                "allowed_zimas_sources": ["zimas_profile_v1"],
                "allowed_permit_sources": ["ladbs_pin_v1"],
                "allowed_records_sources": ["ladbs_records_v1"],
                "min_permit_count": 1,
                "min_record_count": 1,
                "min_pdf_count": 1,
                "required_permit_numbers": ["25041-90000-59794"],
                "required_document_numbers": ["06014-70000-09673"],
                "required_report_sections": ["ZIMAS Parcel Profile"],
                "forbidden_report_strings": ["null"],
                "required_data_note_substrings": ["Purchase price unknown"],
            }
        }
        html = "<html><body>null</body></html>"

        failures = _evaluate_expectations(case, payload, html)

        self.assertGreaterEqual(len(failures), 9)
        self.assertTrue(any("address should contain" in failure for failure in failures))
        self.assertTrue(any("required permit number missing" in failure for failure in failures))
        self.assertTrue(any("forbidden report text present" in failure for failure in failures))
