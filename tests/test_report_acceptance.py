from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from bs4 import BeautifulSoup

from app.payload_contract import apply_payload_contract
from app import report_acceptance


class ReportAcceptanceTests(TestCase):
    def _build_payload(self):
        return apply_payload_contract(
            {
                "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                "url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003",
                "metrics": {
                    "purchase_price": None,
                    "exit_price": 800000,
                    "list_price": None,
                    "hold_days": None,
                    "spread": None,
                    "roi_pct": None,
                    "spread_per_day": None,
                    "land_sf": 8379,
                    "far_before": 0.12,
                    "far_after": 0.26,
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
                    "existing_sf": 1008,
                    "added_sf": 1600,
                    "final_sf": 2608,
                    "lot_sf": 8379,
                    "scope_level": "MEDIUM",
                    "is_new_construction": False,
                },
                "permit_categories": {
                    "building_count": 2,
                    "demo_count": 0,
                    "mep_count": 0,
                    "other_count": 0,
                    "scope_level": "MEDIUM",
                    "permit_complexity_score": "MEDIUM",
                    "building_permits": [
                        {
                            "permit_number": "25014-10000-03595",
                            "permit_type": "Bldg-Addition - 1 or 2 Family Dwelling",
                            "Type": "Bldg-Addition - 1 or 2 Family Dwelling",
                            "Status": "Issued on 11/17/2025",
                            "Work_Description": "Major remodel",
                            "address_label": "1120 S LUCERNE BLVD 90019",
                        },
                        {
                            "permit_number": "25041-90000-59794",
                            "permit_type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                            "Type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                            "Status": "Issued on 11/19/2025",
                            "Work_Description": "Scope revision",
                            "address_label": "1120 S LUCERNE BLVD 90019",
                        },
                    ],
                    "mep_permits": [],
                    "supplement_permits": [],
                    "other_permits": [],
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
                        },
                        {
                            "permit_number": "25041-90000-59794",
                            "permit_type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                            "Type": "Bldg-Alter/Repair - 1 or 2 Family Dwelling",
                            "Status": "Issued on 11/19/2025",
                            "Work_Description": "Scope revision",
                            "address_label": "1120 S LUCERNE BLVD 90019",
                        },
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
                            "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?one",
                        },
                        {
                            "doc_number": "CERT 40332",
                            "doc_type": "CERTIFICATE OF OCCUPANCY",
                            "doc_date": "2/16/2016",
                            "record_id": "56658479",
                            "has_digital_image": True,
                            "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?two",
                        },
                    ],
                },
                "links": {
                    "redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003",
                    "zimas_url": "https://zimas.lacity.org/map.aspx?pin=129B185%20%20%20131&ajax=yes",
                    "ladbs_url": "https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr",
                    "ladbs_records_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW",
                },
                "data_notes": ["Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed."],
            }
        )

    def test_extract_report_checks_keeps_expected_section_order(self) -> None:
        payload = self._build_payload()
        report_html = report_acceptance._render_report_html(payload)

        checks = report_acceptance._extract_report_checks(payload, report_html)

        self.assertTrue(checks["property_header_present"])
        self.assertTrue(checks["section_order_matches"])
        self.assertFalse(checks["contains_none"])
        self.assertFalse(checks["contains_null"])
        self.assertFalse(checks["contains_mojibake"])
        self.assertEqual(checks["permit_items_rendered"], 2)
        self.assertEqual(checks["record_items_rendered"], 2)
        self.assertEqual(checks["pdf_links_rendered"], 2)

    def test_extract_report_checks_flags_placeholder_garbage(self) -> None:
        html = """
        <div class="property-header"></div>
        <div class="report-section"><div class="report-section-header">Developer Snapshot</div></div>
        <div class="report-section"><div class="report-section-header">Timeline Summary</div></div>
        null Â· >None<
        """

        checks = report_acceptance._extract_report_checks({}, html)

        self.assertTrue(checks["contains_none"])
        self.assertTrue(checks["contains_null"])
        self.assertTrue(checks["contains_mojibake"])

    def test_evaluate_property_marks_needs_fix_when_truths_or_report_fail(self) -> None:
        payload = self._build_payload()
        report_checks = {
            "property_header_present": True,
            "section_headers": ["Developer Snapshot"],
            "expected_section_headers": report_acceptance.EXPECTED_SECTION_ORDER,
            "section_order_matches": False,
            "missing_sections": ["Timeline Summary"],
            "contains_none": False,
            "contains_null": False,
            "contains_mojibake": False,
            "permit_items_rendered": 2,
            "record_items_rendered": 2,
            "pdf_links_rendered": 2,
            "duplicate_note_overlap": [],
            "zimas_rows": {},
            "key_field_render_mismatches": [],
        }
        case = {
            "name": "lucerne",
            "role": "flagship-baseline",
            "redfin_url": "https://example.com",
            "known_truths": {"zoning": "R2-1"},
            "expectations": {"min_permit_count": 3},
            "acceptable_uncertainty_notes": [],
        }

        summary = report_acceptance._evaluate_property(case, payload, report_checks)

        self.assertEqual(summary["verdict"], "needs-fix")
        self.assertTrue(summary["fact_mismatches"])
        self.assertTrue(summary["report_issues"])

    def test_evaluate_property_marks_accepted_with_review_for_clean_report_with_notes(self) -> None:
        payload = self._build_payload()
        report_html = report_acceptance._render_report_html(payload)
        report_checks = report_acceptance._extract_report_checks(payload, report_html)
        case = {
            "name": "lucerne",
            "role": "flagship-baseline",
            "redfin_url": "https://example.com",
            "known_truths": {
                "address": "1120 S Lucerne Blvd, Los Angeles, CA 90019",
                "apn": "5082004025",
                "pin": "129B185   131",
                "zoning": "R1-1-O",
                "general_plan_land_use": "Low II Residential",
                "community_plan_area": "Wilshire",
            },
            "expectations": {
                "min_permit_count": 2,
                "min_record_count": 2,
                "min_pdf_count": 2,
                "required_permit_numbers": ["25014-10000-03595"],
                "required_document_numbers": ["06014-70000-09673"],
            },
            "acceptable_uncertainty_notes": [],
        }

        summary = report_acceptance._evaluate_property(case, payload, report_checks)

        self.assertEqual(summary["verdict"], "accepted-with-review")
        self.assertEqual(summary["fact_mismatches"], [])
        self.assertEqual(summary["report_issues"], [])

    def test_extract_report_checks_does_not_double_render_demolition_permits(self) -> None:
        payload = apply_payload_contract(
            {
                "address": "2831 Malcolm Ave, Los Angeles, CA 90064",
                "url": "https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382",
                "property_snapshot": {
                    "address_full": "2831 Malcolm Ave, Los Angeles, CA 90064",
                    "status": "Sold",
                    "status_date": "2026-02-10",
                    "status_price": 3700000,
                },
                "permit_categories": {
                    "building_count": 1,
                    "demo_count": 1,
                    "mep_count": 0,
                    "other_count": 0,
                    "supplement_count": 0,
                    "scope_level": "MEDIUM",
                    "permit_complexity_score": "MEDIUM",
                    "building_permits": [
                        {
                            "permit_number": "23010-10000-05197",
                            "permit_type": "Bldg-New - 1 or 2 Family Dwelling",
                            "Type": "Bldg-New - 1 or 2 Family Dwelling",
                            "Status": "Issued on 8/9/2023",
                            "Work_Description": "New single-family dwelling",
                            "address_label": "2831 S MALCOLM AVE 90064",
                        }
                    ],
                    "mep_permits": [],
                    "supplement_permits": [],
                    "other_permits": [
                        {
                            "permit_number": "23019-10000-04893",
                            "permit_type": "Bldg-Demolition - 1 or 2 Family Dwelling",
                            "Type": "Bldg-Demolition - 1 or 2 Family Dwelling",
                            "Status": "Issued on 8/9/2023",
                            "Work_Description": "Demolish existing structure",
                            "address_label": "2831 S MALCOLM AVE 90064",
                        }
                    ],
                },
                "ladbs": {
                    "source": "ladbs_pin_v1",
                    "permits": [
                        {
                            "permit_number": "23010-10000-05197",
                            "permit_type": "Bldg-New - 1 or 2 Family Dwelling",
                            "Type": "Bldg-New - 1 or 2 Family Dwelling",
                            "Status": "Issued on 8/9/2023",
                            "Work_Description": "New single-family dwelling",
                            "address_label": "2831 S MALCOLM AVE 90064",
                        },
                        {
                            "permit_number": "23019-10000-04893",
                            "permit_type": "Bldg-Demolition - 1 or 2 Family Dwelling",
                            "Type": "Bldg-Demolition - 1 or 2 Family Dwelling",
                            "Status": "Issued on 8/9/2023",
                            "Work_Description": "Demolish existing structure",
                            "address_label": "2831 S MALCOLM AVE 90064",
                        },
                    ],
                },
                "zimas_profile": {
                    "source": "zimas_profile_v1",
                    "transport": "http",
                    "pin": "123B157   607",
                    "apn": "4255013007",
                    "planning_context": {"community_plan_area": "West Los Angeles"},
                    "zoning_profile": {"zoning": "R1-1", "general_plan_land_use": "Low Residential"},
                },
                "ladbs_records": {
                    "source": "ladbs_records_v1",
                    "transport": "http",
                    "documents": [
                        {
                            "doc_number": "23010-20000-03343",
                            "doc_type": "BUILDING PERMIT",
                            "doc_date": "8/9/2023",
                            "pdf_url": "https://example.com/doc.pdf",
                        }
                    ],
                },
            }
        )

        report_html = report_acceptance._render_report_html(payload)
        checks = report_acceptance._extract_report_checks(payload, report_html)

        self.assertEqual(checks["permit_items_rendered"], 2)

    def test_build_review_links_includes_expected_destinations(self) -> None:
        payload = self._build_payload()

        links = report_acceptance._build_review_links(payload, bundle_dir=Path("review_bundles/report_acceptance/lucerne"))

        labels = {item["label"]: item for item in links}
        self.assertEqual(labels["Local report"]["url"], "report.html")
        self.assertTrue(labels["ZIMAS page"]["url"].startswith("https://"))
        self.assertIn("pin=", labels["PIN-based LADBS permit-results link"]["url"])
        self.assertEqual(labels["First record summary link"]["status"], "unavailable")
        self.assertTrue(labels["First available PDF link"]["url"].startswith("https://"))

    def test_build_review_links_marks_missing_values_unavailable(self) -> None:
        payload = self._build_payload()
        payload["zimas_profile"]["pin"] = None
        payload["links"]["zimas_url"] = None
        payload["ladbs_records"]["documents"] = [{}]

        links = report_acceptance._build_review_links(payload, bundle_dir=Path("review_bundles/report_acceptance/lucerne"))

        labels = {item["label"]: item for item in links}
        self.assertEqual(labels["ZIMAS page"]["status"], "unavailable")
        self.assertEqual(labels["First available PDF link"]["status"], "unavailable")
        self.assertEqual(labels["PIN-based LADBS permit-results link"]["status"], "unavailable")

    def test_render_report_html_renders_review_toolbar_and_unavailable_labels(self) -> None:
        payload = self._build_payload()
        payload["zimas_profile"]["pin"] = None
        payload["links"]["zimas_url"] = None
        payload["ladbs_records"]["documents"] = [{}]

        report_html = report_acceptance._render_report_html(
            report_acceptance._attach_review_bundle(
                payload,
                bundle_dir=Path("review_bundles/report_acceptance/lucerne"),
            )
        )

        soup = BeautifulSoup(report_html, "lxml")
        toolbar = soup.select_one(".review-toolbar")
        self.assertIsNotNone(toolbar)
        self.assertIn("Local report", toolbar.get_text(" ", strip=True))
        self.assertIn("ZIMAS page: Unavailable offline", toolbar.get_text(" ", strip=True))

    def test_build_landing_page_renders_property_cards(self) -> None:
        payload = self._build_payload()
        summary = report_acceptance._evaluate_property(
            {
                "name": "lucerne",
                "role": "flagship-baseline",
                "redfin_url": "https://example.com",
                "known_truths": {},
                "expectations": {},
                "acceptable_uncertainty_notes": [],
            },
            payload,
            report_acceptance._extract_report_checks(
                payload,
                report_acceptance._render_report_html(
                    report_acceptance._attach_review_bundle(
                        payload, bundle_dir=Path("review_bundles/report_acceptance/lucerne")
                    )
                ),
            ),
        )
        summary["payload"] = payload

        html = report_acceptance._build_landing_page(Path("review_bundles/report_acceptance"), [summary])

        self.assertIn("Report Acceptance Review Bundles", html)
        self.assertIn("lucerne", html)
        self.assertIn("report.html", html)
