from __future__ import annotations

from unittest import TestCase, mock

from app import orchestrator


class OrchestratorContractTests(TestCase):
    def test_run_full_comp_pipeline_applies_payload_contract_and_review_flags(self) -> None:
        redfin_data = {
            "source": "redfin_parsed_v3",
            "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
            "tax": {"apn": "5082004025"},
            "timeline": [{"event": "sold", "date": "2025-09-05", "price": 800000}],
            "current_summary": "Sold for $800,000",
            "public_record_summary": "Built 1922",
            "lot_summary": "Lot: 8,379 SF",
            "list_price": None,
            "lot_sf": 8379.0,
            "public_records": {"lot_sf": None, "building_sf": 1008.0},
            "building_sf": 1008.0,
        }
        zimas_data = {
            "source": "zimas_profile_v1",
            "transport": "http",
            "pin": "129B185   131",
            "apn": "5082004025",
            "parcel_identity": {"lot_area_sqft": 7196.1},
            "planning_context": {"community_plan_area": "Wilshire", "council_district": "CD 10 - Heather Hutt"},
            "zoning_profile": {"zoning": "R1-1-O", "general_plan_land_use": "Low II Residential"},
            "environmental_profile": {"flood_zone": "500 Yr", "methane_hazard_site": "Methane Zone"},
            "hazard_profile": {"nearest_fault": "Puente Hills Blind Thrust"},
            "links": {"profile_url": "https://zimas.lacity.org/map.aspx?pin=129B185%20%20%20131&ajax=yes"},
        }
        ladbs_data = {
            "source": "ladbs_pin_v1",
            "permits": [
                {
                    "permit_number": "25014-10000-03595",
                    "permit_type": "Bldg-Addition - 1 or 2 Family Dwelling",
                    "Type": "Bldg-Addition - 1 or 2 Family Dwelling",
                    "Status": "Issued on 11/17/2025",
                    "status_date": "11/17/2025",
                    "Work_Description": "Major remodel",
                    "address_label": "1120 S LUCERNE BLVD 90019",
                    "raw_details": {"status_history": [{"event": "Submitted", "date": "8/8/2025", "person": "APPLICANT"}]},
                },
                {
                    "permit_number": "25016-10000-27059",
                    "permit_type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                    "Type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                    "Status": "Issued on 11/19/2025",
                    "status_date": "11/19/2025",
                    "Work_Description": "Garage conversion",
                    "address_label": "1122 S LUCERNE BLVD 90019",
                    "raw_details": {
                        "status_history": [{"event": "Issued", "date": "11/19/2025", "person": "APPLICANT"}],
                        "contact_information": {
                            "Contractor": "Stay Forever Construction Corporation; Lic. No.: 986055-B",
                            "Engineer": "Charles Norman Mccormick; Lic. No.: C32534",
                        },
                    },
                    "contractor": "Stay Forever Construction Corporation",
                    "contractor_license": "986055",
                    "engineer": "Charles Norman Mccormick",
                },
            ],
            "note": "Fetched permits by PIN.",
            "retrieval_strategy": "pin-first",
            "fallback_used": False,
            "pin": "129B185   131",
            "pin_source": "zimas_ajax_v1",
            "address": "1120 S LUCERNE BLVD",
        }
        ladbs_records_data = {
            "source": "ladbs_records_v1",
            "transport": "http",
            "documents": [
                {
                    "doc_number": "06014-70000-09673",
                    "doc_type": "BUILDING PERMIT",
                    "doc_date": "10/27/2006",
                    "record_id": "56658478",
                    "has_digital_image": True,
                    "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?one",
                },
                {
                    "doc_number": "CERT 40332",
                    "doc_type": "CERTIFICATE OF OCCUPANCY",
                    "doc_date": "2/16/2016",
                    "record_id": "56658478",
                    "has_digital_image": True,
                    "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?two",
                },
            ],
            "links": {"search_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW"},
        }

        with (
            mock.patch.object(orchestrator, "get_redfin_data", return_value=redfin_data),
            mock.patch.object(orchestrator, "get_zimas_profile", return_value=zimas_data),
            mock.patch.object(orchestrator, "get_ladbs_data", return_value=ladbs_data),
            mock.patch.object(orchestrator, "get_ladbs_records", return_value=ladbs_records_data),
            mock.patch.object(orchestrator, "lookup_cslb_license", return_value=None),
            mock.patch.object(orchestrator, "summarize_comp", return_value={"tactics": ["Validate costs"], "risks": [], "insights": []}),
            mock.patch.object(orchestrator, "append_to_search_log"),
            mock.patch("pathlib.Path.write_text", return_value=0),
        ):
            result = orchestrator.run_full_comp_pipeline(
                "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
            )

        self.assertEqual(result["payload_contract_version"], "qa-v1")
        self.assertEqual(result["zimas_profile"]["source"], "zimas_profile_v1")
        self.assertEqual(result["ladbs_records"]["source"], "ladbs_records_v1")
        self.assertIn("source_states", result["source_diagnostics"])
        self.assertEqual(result["source_diagnostics"]["source_states"]["ladbs_permits"]["permit_count"], 2)
        self.assertTrue(result["anomalies"])
        self.assertIn("lot_size_mismatch", {flag["code"] for flag in result["anomalies"]})

    def test_run_multiple_fallback_keeps_stable_shape(self) -> None:
        with mock.patch.object(orchestrator, "run_full_comp_pipeline", side_effect=RuntimeError("boom")):
            results = orchestrator.run_multiple(["https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"])

        self.assertEqual(len(results), 1)
        payload = results[0]
        self.assertEqual(payload["payload_contract_version"], "qa-v1")
        self.assertIsInstance(payload["zimas_profile"], dict)
        self.assertIsInstance(payload["ladbs_records"], dict)
        self.assertIsInstance(payload["source_diagnostics"], dict)
        self.assertEqual(payload["data_notes"], ["Pipeline error while processing this property."])
        self.assertEqual(payload["current_summary"], "N/A")
        self.assertEqual(payload["public_record_summary"], "N/A")
        self.assertEqual(payload["lot_summary"], "N/A")
        self.assertEqual(payload["permit_summary"], "N/A")
        self.assertIsNone(payload["summary_markdown"])

    def test_run_full_comp_pipeline_marks_ladbs_pin_error_as_not_ok(self) -> None:
        redfin_data = {
            "source": "redfin_parsed_v3",
            "address": "2831 Malcolm Ave, Los Angeles, CA 90064",
            "tax": {"apn": "4255013007"},
            "timeline": [{"event": "sold", "date": "2026-02-10", "price": 3700000}],
            "current_summary": "Sold for $3,700,000",
            "public_record_summary": "Built 1945",
            "lot_summary": "Lot: 6,800 SF",
            "public_records": {"lot_sf": 6800.0, "building_sf": 1946.0},
            "building_sf": 1946.0,
        }
        zimas_data = {
            "source": "zimas_profile_v1",
            "transport": "http",
            "pin": "123B157   607",
            "apn": "4255013007",
            "parcel_identity": {"lot_area_sqft": 6800.0},
            "planning_context": {"community_plan_area": "West Los Angeles"},
            "zoning_profile": {"zoning": "R1-1", "general_plan_land_use": "Low Residential"},
        }
        ladbs_data = {
            "source": "ladbs_pin_error",
            "pin": "123B157   607",
            "permits": [],
            "note": "LADBS PermitResultsbyPin loaded, but the site reported service-unavailable content for this PIN request.",
        }
        ladbs_records_data = {
            "source": "ladbs_records_v1",
            "transport": "http",
            "documents": [{"doc_number": "23010-20000-03343", "doc_date": "8/9/2023"}],
        }

        with (
            mock.patch.object(orchestrator, "get_redfin_data", return_value=redfin_data),
            mock.patch.object(orchestrator, "get_zimas_profile", return_value=zimas_data),
            mock.patch.object(orchestrator, "get_ladbs_data", return_value=ladbs_data),
            mock.patch.object(orchestrator, "get_ladbs_records", return_value=ladbs_records_data),
            mock.patch.object(orchestrator, "lookup_cslb_license", return_value=None),
            mock.patch.object(orchestrator, "append_to_search_log"),
            mock.patch("pathlib.Path.write_text", return_value=0),
        ):
            result = orchestrator.run_full_comp_pipeline(
                "https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382"
            )

        self.assertFalse(result["ladbs_ok"])
        self.assertEqual(result["ladbs"]["source"], "ladbs_pin_error")
        self.assertEqual(
            result["ladbs_error"],
            "LADBS PermitResultsbyPin loaded, but the site reported service-unavailable content for this PIN request.",
        )
        self.assertFalse(result["source_diagnostics"]["source_states"]["ladbs_permits"]["ok"])
