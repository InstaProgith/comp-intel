from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from bs4 import BeautifulSoup

from app import report_acceptance
from app.payload_contract import apply_payload_contract

ACCEPTED_PROPERTIES = ("lucerne", "malcolm", "rosewood", "kelton")


class ReportAcceptanceTests(TestCase):
    def _build_payload(self) -> dict:
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
                    "planning_context": {
                        "community_plan_area": "Wilshire",
                        "council_district": "CD 10 - Heather Hutt",
                    },
                    "zoning_profile": {
                        "zoning": "R1-1-O",
                        "general_plan_land_use": "Low II Residential",
                    },
                    "environmental_profile": {
                        "flood_zone": "500 Yr",
                        "methane_hazard_site": "Methane Zone",
                    },
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
                            "image_main_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/ImageMain.aspx?one",
                            "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?one",
                        },
                        {
                            "doc_number": "CERT 40332",
                            "doc_type": "CERTIFICATE OF OCCUPANCY",
                            "doc_date": "2/16/2016",
                            "record_id": "56658479",
                            "has_digital_image": True,
                            "summary_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/Report.aspx?two",
                            "pdf_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?two",
                        },
                    ],
                    "diagnostics": {
                        "bootstrap_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DefaultCustom.aspx",
                    },
                },
                "links": {
                    "redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003",
                    "zimas_url": "https://zimas.lacity.org/map.aspx?pin=129B185%20%20%20131&ajax=yes",
                    "ladbs_url": "https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr",
                    "ladbs_records_url": "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW",
                },
                "data_notes": [
                    "Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed."
                ],
            }
        )

    def _build_case(self) -> dict:
        return {
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

    def _build_summary(self, payload: dict | None = None) -> dict:
        payload = payload or self._build_payload()
        report_html = report_acceptance._render_report_html(
            report_acceptance._attach_review_bundle(payload, property_name="lucerne", page_kind="report")
        )
        report_checks = report_acceptance._extract_report_checks(payload, report_html)
        summary = report_acceptance._evaluate_property(self._build_case(), payload, report_checks)
        summary["payload"] = payload
        return summary

    def _soup(self, path: Path) -> BeautifulSoup:
        return BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

    def _assert_local_href_resolves(self, base_file: Path, href: str, bundle_root: Path) -> None:
        self.assertFalse(href.startswith("/"), f"{base_file} uses absolute local href {href!r}")
        self.assertNotIn("://", href, f"{base_file} should not use remote href {href!r} for local actions")
        target = (base_file.parent / href).resolve()
        self.assertTrue(target.exists(), f"{base_file} -> {href} does not resolve to a real file")
        target.relative_to(bundle_root.resolve())

    @contextmanager
    def _generated_bundle(self):
        with TemporaryDirectory(dir=report_acceptance.BASE_DIR) as temp_dir:
            temp_root = Path(temp_dir)
            bundle_root = temp_root / "review_bundles" / "report_acceptance"
            review_index_path = temp_root / "REVIEW_INDEX.md"
            bundle_root.mkdir(parents=True, exist_ok=True)

            for slug in ACCEPTED_PROPERTIES:
                source_payload = report_acceptance.DEFAULT_OUTPUT_DIR / slug / "payload.normalized.json"
                destination_dir = bundle_root / slug
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_payload, destination_dir / "payload.normalized.json")

            cases = report_acceptance._load_property_file(str(report_acceptance.DEFAULT_PROPERTY_FILE))
            summaries = report_acceptance.generate_review_bundle_outputs(
                cases=cases,
                bundle_root=bundle_root,
                offline_existing=True,
                review_index_path=review_index_path,
            )
            yield temp_root, bundle_root, review_index_path, summaries

    def test_extract_report_checks_keeps_expected_section_order(self) -> None:
        payload = self._build_payload()
        report_html = report_acceptance._render_report_html(
            report_acceptance._attach_review_bundle(payload, property_name="lucerne", page_kind="report")
        )

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
        null Ã‚Â· >None<
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

    def test_build_review_bundle_context_groups_links_and_uses_first_available_urls(self) -> None:
        payload = self._build_payload()

        context = report_acceptance._build_review_bundle_context(
            payload,
            property_name="lucerne",
            page_kind="report",
        )

        local_links = {item["key"]: item for item in context["local_actions"]}
        source_links = {item["key"]: item for item in context["source_links"]}
        generic_links = {item["key"]: item for item in context["generic_links"]}
        fallback_links = {item["key"]: item for item in context["fallback_links"]}
        first_image_doc = next(
            document for document in payload["ladbs_records"]["documents"] if document.get("image_main_url")
        )
        first_pdf_doc = next(
            document for document in payload["ladbs_records"]["documents"] if document.get("pdf_url")
        )

        self.assertEqual(context["stylesheet_href"], "../_assets/css/comp.css")
        self.assertEqual(local_links["back_to_bundles"]["url"], "../index.html")
        self.assertEqual(local_links["open_summary"]["url"], "summary.html")
        self.assertEqual(local_links["open_payload"]["url"], "payload.normalized.json")
        self.assertEqual(source_links["first_ladbs_record"]["url"], first_image_doc["image_main_url"])
        self.assertEqual(source_links["first_ladbs_pdf"]["url"], first_pdf_doc["pdf_url"])
        self.assertEqual(source_links["first_ladbs_record"]["label"], "First LADBS document images")
        self.assertEqual(source_links["zimas_parcel_page"]["classification"], "canonical")
        self.assertEqual(source_links["zimas_parcel_page"]["source_basis"], "payload_field")
        self.assertTrue(source_links["zimas_parcel_page"]["primary"])
        self.assertEqual(source_links["first_ladbs_record"]["classification"], "canonical")
        self.assertEqual(source_links["first_ladbs_pdf"]["classification"], "canonical")
        self.assertEqual(generic_links["permit_search_home"]["label"], "Permit search home")
        self.assertEqual(generic_links["docs_search_home"]["label"], "Docs search home")
        self.assertEqual(
            generic_links["docs_search_home"]["url"],
            payload["ladbs_records"]["diagnostics"]["bootstrap_url"],
        )
        self.assertEqual(generic_links["permit_search_home"]["classification"], "generic")
        self.assertEqual(generic_links["permit_search_home"]["source_basis"], "generic_home")
        self.assertFalse(generic_links["permit_search_home"]["primary"])
        self.assertEqual(fallback_links["pin_permit_results"]["label"], "PIN permit search fallback")
        self.assertEqual(fallback_links["pin_permit_results"]["classification"], "synthetic")
        self.assertEqual(fallback_links["pin_permit_results"]["source_basis"], "pin_derived")
        self.assertFalse(fallback_links["pin_permit_results"]["primary"])

    def test_build_review_bundle_context_marks_missing_values_unavailable(self) -> None:
        payload = self._build_payload()
        payload["zimas_profile"]["pin"] = None
        payload["links"]["zimas_url"] = None
        payload["links"]["ladbs_url"] = None
        payload["links"]["ladbs_records_url"] = None
        payload["ladbs_records"]["diagnostics"]["bootstrap_url"] = None
        payload["ladbs_records"]["documents"] = [{}]

        context = report_acceptance._build_review_bundle_context(
            payload,
            property_name="lucerne",
            page_kind="summary",
        )

        source_links = {item["key"]: item for item in context["source_links"]}
        generic_links = {item["key"]: item for item in context["generic_links"]}
        fallback_links = {item["key"]: item for item in context["fallback_links"]}
        self.assertEqual(source_links["zimas_parcel_page"]["status"], "unavailable")
        self.assertEqual(source_links["first_ladbs_record"]["status"], "unavailable")
        self.assertEqual(source_links["first_ladbs_pdf"]["status"], "unavailable")
        self.assertEqual(generic_links["permit_search_home"]["status"], "unavailable")
        self.assertEqual(generic_links["docs_search_home"]["status"], "unavailable")
        self.assertEqual(fallback_links["pin_permit_results"]["status"], "unavailable")

    def test_render_report_html_renders_grouped_toolbar_and_explicit_unavailable_states(self) -> None:
        payload = self._build_payload()
        payload["zimas_profile"]["pin"] = None
        payload["links"]["zimas_url"] = None
        payload["ladbs_records"]["documents"] = [{}]

        report_html = report_acceptance._render_report_html(
            report_acceptance._attach_review_bundle(payload, property_name="lucerne", page_kind="report")
        )

        soup = BeautifulSoup(report_html, "lxml")
        toolbar_groups = [node["data-group"] for node in soup.select(".review-toolbar [data-group]")]
        self.assertEqual(toolbar_groups, ["local", "verified_source", "generic", "fallback"])
        self.assertIn("Back to review bundles", soup.get_text(" ", strip=True))
        self.assertIn(
            "ZIMAS parcel page unavailable: No canonical ZIMAS parcel page was available in the payload.",
            soup.get_text(" ", strip=True),
        )
        self.assertIn("Permit search home", soup.get_text(" ", strip=True))
        self.assertIn("PIN permit search fallback", soup.get_text(" ", strip=True))
        self.assertEqual(
            soup.select_one('.review-toolbar [data-link-key="open_summary"]')["href"],
            "summary.html",
        )

    def test_generate_offline_bundle_outputs_are_self_contained_and_resolvable(self) -> None:
        with self._generated_bundle() as (_, bundle_root, review_index_path, _summaries):
            index_path = bundle_root / "index.html"
            self.assertTrue(index_path.exists())
            self.assertTrue(review_index_path.exists())
            self.assertTrue((bundle_root / "_assets" / "css" / "comp.css").exists())
            self.assertTrue((bundle_root / "_assets" / "BK.webp").exists())
            self.assertTrue((bundle_root / "_assets" / "LG.png").exists())
            self.assertIn("summary.html", review_index_path.read_text(encoding="utf-8"))

            index_html = index_path.read_text(encoding="utf-8")
            self.assertNotIn("/static/", index_html)
            self.assertNotIn("url_for(", index_html)
            self.assertEqual(self._soup(index_path).select_one('link[rel="stylesheet"]')["href"], "_assets/css/comp.css")

            for slug in ACCEPTED_PROPERTIES:
                report_path = bundle_root / slug / "report.html"
                summary_path = bundle_root / slug / "summary.html"
                payload_path = bundle_root / slug / "payload.normalized.json"
                self.assertTrue(report_path.exists())
                self.assertTrue(summary_path.exists())
                self.assertTrue(payload_path.exists())

                for html_path in (report_path, summary_path):
                    html = html_path.read_text(encoding="utf-8")
                    self.assertNotIn("/static/", html)
                    self.assertNotIn("url_for(", html)
                    self.assertNotIn("localhost", html)

                report_soup = self._soup(report_path)
                summary_soup = self._soup(summary_path)
                self.assertEqual(
                    report_soup.select_one('link[rel="stylesheet"]')["href"],
                    "../_assets/css/comp.css",
                )
                self.assertEqual(
                    summary_soup.select_one('link[rel="stylesheet"]')["href"],
                    "../_assets/css/comp.css",
                )
                self.assertEqual(
                    [node["data-group"] for node in report_soup.select(".review-toolbar [data-group]")],
                    ["local", "verified_source", "generic", "fallback"],
                )
                self.assertEqual(
                    [node["data-group"] for node in summary_soup.select(".bundle-toolbar-panel [data-group]")],
                    ["local", "verified_source", "generic", "fallback"],
                )

                self._assert_local_href_resolves(
                    report_path,
                    report_soup.select_one('.review-toolbar [data-link-key="back_to_bundles"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    report_path,
                    report_soup.select_one('.review-toolbar [data-link-key="open_summary"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    report_path,
                    report_soup.select_one('.review-toolbar [data-link-key="open_payload"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    summary_path,
                    summary_soup.select_one('[data-group="local"] [data-link-key="back_to_bundles"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    summary_path,
                    summary_soup.select_one('[data-group="local"] [data-link-key="open_report"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    summary_path,
                    summary_soup.select_one('[data-group="local"] [data-link-key="open_payload"]')["href"],
                    bundle_root,
                )

                card = self._soup(index_path).select_one(f'[data-property="{slug}"]')
                self.assertIsNotNone(card)
                self._assert_local_href_resolves(
                    index_path,
                    card.select_one('[data-group="local"] [data-link-key="open_report"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    index_path,
                    card.select_one('[data-group="local"] [data-link-key="open_summary"]')["href"],
                    bundle_root,
                )
                self._assert_local_href_resolves(
                    index_path,
                    card.select_one('[data-group="local"] [data-link-key="open_payload"]')["href"],
                    bundle_root,
                )

                generic_group_text = report_soup.select_one('[data-group="generic"]').get_text(" ", strip=True)
                self.assertIn("Permit search home", generic_group_text)
                self.assertIn("Docs search home", generic_group_text)
                fallback_group_text = report_soup.select_one('[data-group="fallback"]').get_text(" ", strip=True)
                self.assertIn("PIN permit search fallback", fallback_group_text)

    def test_generated_bundle_links_and_displayed_facts_match_payloads(self) -> None:
        with self._generated_bundle() as (_, bundle_root, _review_index_path, summaries):
            summary_by_slug = {summary["name"]: summary for summary in summaries}
            index_soup = self._soup(bundle_root / "index.html")

            for slug in ACCEPTED_PROPERTIES:
                payload = json.loads((bundle_root / slug / "payload.normalized.json").read_text(encoding="utf-8"))
                summary_path = bundle_root / slug / "summary.html"
                report_path = bundle_root / slug / "report.html"
                summary_soup = self._soup(summary_path)
                report_soup = self._soup(report_path)
                landing_card = index_soup.select_one(f'[data-property="{slug}"]')
                self.assertIsNotNone(landing_card)

                expected_address = payload["address"]
                expected_apn = payload["zimas_profile"]["apn"]
                expected_pin = payload["zimas_profile"]["pin"]
                expected_permit_count = str(len(payload["ladbs"]["permits"]))
                expected_record_count = str(len(payload["ladbs_records"]["documents"]))

                summary_text = summary_soup.get_text(" ", strip=True)
                report_text = report_soup.get_text(" ", strip=True)
                card_text = landing_card.get_text(" ", strip=True)

                for expected_text in (
                    expected_address,
                    expected_apn,
                    expected_pin,
                    expected_permit_count,
                    expected_record_count,
                ):
                    self.assertIn(expected_text, summary_text)
                    self.assertIn(expected_text, card_text)

                for permit in report_acceptance._build_representative_permit_details(payload)[:3]:
                    self.assertIn(permit["permit_number"], summary_text)
                    self.assertIn(permit["permit_number"], card_text)

                for document in report_acceptance._build_representative_document_details(payload)[:3]:
                    self.assertIn(document["doc_number"], summary_text)
                    self.assertIn(document["doc_number"], card_text)

                for item in summary_by_slug[slug]["review_context_items"]:
                    self.assertIn(item, card_text)

                expected_summary_context = report_acceptance._build_review_bundle_context(
                    payload,
                    property_name=slug,
                    page_kind="summary",
                )
                for link in expected_summary_context["source_links"]:
                    rendered = summary_soup.select_one(
                        f'[data-group="verified_source"] [data-link-key="{link["key"]}"]'
                    )
                    self.assertIsNotNone(rendered)
                    if link["status"] == "available":
                        self.assertEqual(rendered["href"], link["url"])
                    else:
                        self.assertIn(link["reason"], rendered.get_text(" ", strip=True))
                    self.assertIn(link["classification"], {"canonical", "verified_derived"})
                    self.assertTrue(link["primary"])

                for link in expected_summary_context["generic_links"]:
                    rendered = summary_soup.select_one(f'[data-group="generic"] [data-link-key="{link["key"]}"]')
                    self.assertIsNotNone(rendered)
                    self.assertEqual(link["classification"], "generic")
                    self.assertFalse(link["primary"])

                for link in expected_summary_context["fallback_links"]:
                    rendered = summary_soup.select_one(f'[data-group="fallback"] [data-link-key="{link["key"]}"]')
                    self.assertIsNotNone(rendered)
                    self.assertEqual(link["classification"], "synthetic")
                    self.assertFalse(link["primary"])

                expected_report_context = report_acceptance._build_review_bundle_context(
                    payload,
                    property_name=slug,
                    page_kind="report",
                )
                for link in expected_report_context["source_links"]:
                    rendered = report_soup.select_one(
                        f'.review-toolbar [data-group="verified_source"] [data-link-key="{link["key"]}"]'
                    )
                    self.assertIsNotNone(rendered)
                    if link["status"] == "available":
                        self.assertEqual(rendered["href"], link["url"])
                    else:
                        self.assertIn(link["reason"], rendered.get_text(" ", strip=True))
