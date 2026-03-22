from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup
from flask import render_template

from app.orchestrator import run_full_comp_pipeline
from app.payload_contract import apply_payload_contract

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "review_bundles" / "report_acceptance"
DEFAULT_PROPERTY_FILE = BASE_DIR / "validation" / "report_acceptance_property_pack.json"
STATIC_DIR = BASE_DIR / "static"
STATIC_CSS_PATH = STATIC_DIR / "css" / "comp.css"
STATIC_LOGO_PATH = STATIC_DIR / "LG.png"
STATIC_FALLBACK_ASSET_NAMES = ("LG.png",)
BUNDLE_ASSETS_DIRNAME = "_assets"
EXPECTED_SECTION_ORDER = [
    "Developer Snapshot",
    "Timeline Summary",
    "Construction Summary",
    "Cost Model",
    "Permit Overview",
    "ZIMAS Parcel Profile",
    "LADBS Records",
    "Team",
    "Strategy Notes",
    "Review Flags",
    "Data Notes",
    "Links",
]
MOJIBAKE_TOKENS = ("Â·", "â€”", "â€¦", "Ã", "Â ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate tracked report-acceptance bundles for a small real-property review set."
    )
    parser.add_argument(
        "--property-file",
        default=str(DEFAULT_PROPERTY_FILE),
        help="JSON file containing the report-acceptance property pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where per-property review bundles should be written.",
    )
    parser.add_argument("--json", action="store_true", help="Print the acceptance summary payload as JSON.")
    parser.add_argument(
        "--offline-existing",
        action="store_true",
        help="Reuse existing payload.normalized.json files from the output directory instead of running live providers.",
    )
    return parser


def _load_property_file(path_text: str) -> List[Dict[str, Any]]:
    path = Path(path_text)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("properties") or []

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not item.get("redfin_url"):
            continue
        case = dict(item)
        case["name"] = item.get("name") or f"property-{index + 1}"
        case["expectations"] = item.get("expectations") or {}
        case["known_truths"] = item.get("known_truths") or {}
        case["acceptable_uncertainty_notes"] = item.get("acceptable_uncertainty_notes") or []
        case["review_checks"] = item.get("review_checks") or {}
        results.append(case)
    return results


def _render_template_html(template_name: str, **context: Any) -> str:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_TESTING", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "report-acceptance-secret")
    os.environ.setdefault("APP_ACCESS_PASSWORD", "report-acceptance-password")
    from app.ui_server import app as ui_app

    with ui_app.test_request_context("/report"):
        return render_template(template_name, **context)


def _render_report_html(payload: Dict[str, Any]) -> str:
    return _render_template_html("report.html", r=payload)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_compare_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normalize_text(value).lower()).strip()


def _pin_permit_results_url(pin: Optional[str]) -> Optional[str]:
    normalized_pin = _normalize_text(pin)
    if not normalized_pin:
        return None
    return "https://www.ladbsservices2.lacity.org/OnlineServices/?service=plr&view=permit&pin=" + quote(
        normalized_pin
    )


def _slug_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def _extract_css_asset_paths(css_text: str) -> List[str]:
    asset_paths: List[str] = []
    for match in re.findall(r"url\(([^)]+)\)", css_text):
        candidate = match.strip().strip("'\"")
        if not candidate or candidate.startswith(("data:", "http:", "https:", "//")):
            continue
        candidate = candidate.split("?", 1)[0].split("#", 1)[0]
        asset_paths.append(candidate)
    return list(dict.fromkeys(asset_paths))


def _copy_bundle_assets(bundle_root: Path) -> None:
    assets_root = bundle_root / BUNDLE_ASSETS_DIRNAME
    css_dir = assets_root / "css"
    css_dir.mkdir(parents=True, exist_ok=True)
    css_text = STATIC_CSS_PATH.read_text(encoding="utf-8")
    (css_dir / STATIC_CSS_PATH.name).write_text(css_text, encoding="utf-8")

    assets_root_resolved = assets_root.resolve()
    for relative_asset_path in _extract_css_asset_paths(css_text):
        source_path = (STATIC_CSS_PATH.parent / relative_asset_path).resolve()
        destination_path = (css_dir / relative_asset_path).resolve()
        try:
            destination_path.relative_to(assets_root_resolved)
        except ValueError as exc:
            raise ValueError(f"CSS asset path escapes bundle assets root: {relative_asset_path!r}") from exc
        if not source_path.exists():
            raise FileNotFoundError(f"Missing CSS asset referenced by comp.css: {source_path}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)

    for asset_name in STATIC_FALLBACK_ASSET_NAMES:
        source_path = STATIC_DIR / asset_name
        if source_path.exists():
            shutil.copy2(source_path, assets_root / asset_name)


def _bundle_asset_prefix(page_kind: str) -> str:
    return BUNDLE_ASSETS_DIRNAME if page_kind == "index" else f"../{BUNDLE_ASSETS_DIRNAME}"


def _build_link_item(
    key: str,
    label: str,
    url: Optional[str],
    *,
    unavailable_reason: str,
    external: bool,
) -> Dict[str, Any]:
    normalized_url = _normalize_text(url)
    item: Dict[str, Any] = {
        "key": key,
        "label": label,
        "external": external,
    }
    if normalized_url:
        item["status"] = "available"
        item["url"] = normalized_url
    else:
        item["status"] = "unavailable"
        item["reason"] = unavailable_reason
    return item


def _first_document_with_url(documents: List[Dict[str, Any]], field_name: str) -> Optional[Dict[str, Any]]:
    for document in documents:
        if isinstance(document, dict) and _normalize_text(document.get(field_name)):
            return document
    return None


def _build_review_bundle_context(
    payload: Dict[str, Any],
    *,
    property_name: str,
    page_kind: str,
) -> Dict[str, Any]:
    links = payload.get("links") or {}
    zimas = payload.get("zimas_profile") or {}
    ladbs = payload.get("ladbs") or {}
    records = payload.get("ladbs_records") or {}
    documents = records.get("documents") or []
    first_doc_with_summary = _first_document_with_url(documents, "summary_url")
    first_doc_with_pdf = _first_document_with_url(documents, "pdf_url")
    pin = zimas.get("pin") or ladbs.get("pin")
    zimas_page = links.get("zimas_url") or ((zimas.get("links") or {}).get("profile_url"))
    docs_page = links.get("ladbs_records_url") or ((records.get("links") or {}).get("search_url"))
    asset_prefix = _bundle_asset_prefix(page_kind)

    if page_kind == "report":
        local_actions = [
            _build_link_item(
                "back_to_bundles",
                "Back to review bundles",
                "../index.html",
                unavailable_reason="Bundle index is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_summary",
                "Open summary",
                "summary.html",
                unavailable_reason="Summary page is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_payload",
                "Open payload",
                "payload.normalized.json",
                unavailable_reason="Normalized payload is unavailable.",
                external=False,
            ),
        ]
    elif page_kind == "summary":
        local_actions = [
            _build_link_item(
                "back_to_bundles",
                "Back to review bundles",
                "../index.html",
                unavailable_reason="Bundle index is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_report",
                "Open report",
                "report.html",
                unavailable_reason="Report page is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_payload",
                "Open payload",
                "payload.normalized.json",
                unavailable_reason="Normalized payload is unavailable.",
                external=False,
            ),
        ]
    elif page_kind == "index":
        local_prefix = f"{property_name}/"
        local_actions = [
            _build_link_item(
                "open_report",
                "Open report",
                f"{local_prefix}report.html",
                unavailable_reason="Report page is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_summary",
                "Open summary",
                f"{local_prefix}summary.html",
                unavailable_reason="Summary page is unavailable.",
                external=False,
            ),
            _build_link_item(
                "open_payload",
                "Open payload",
                f"{local_prefix}payload.normalized.json",
                unavailable_reason="Normalized payload is unavailable.",
                external=False,
            ),
        ]
    else:
        raise ValueError(f"Unsupported page kind: {page_kind!r}")

    source_links = [
        _build_link_item(
            "zimas_parcel_page",
            "ZIMAS parcel page",
            zimas_page,
            unavailable_reason="No canonical ZIMAS parcel page was available in the payload.",
            external=True,
        ),
        _build_link_item(
            "pin_permit_results",
            "PIN permit results",
            _pin_permit_results_url(pin),
            unavailable_reason="No normalized PIN was available for a property-specific permit results link.",
            external=True,
        ),
        _build_link_item(
            "first_ladbs_record",
            "First LADBS record",
            first_doc_with_summary.get("summary_url") if first_doc_with_summary else None,
            unavailable_reason="No LADBS record summary URL was available in the payload documents.",
            external=True,
        ),
        _build_link_item(
            "first_ladbs_pdf",
            "First LADBS PDF",
            first_doc_with_pdf.get("pdf_url") if first_doc_with_pdf else None,
            unavailable_reason="No LADBS PDF URL was available in the payload documents.",
            external=True,
        ),
    ]

    generic_links = [
        _build_link_item(
            "permit_search_home",
            "Permit search home",
            links.get("ladbs_url"),
            unavailable_reason="No generic LADBS permit search home URL was available in the payload.",
            external=True,
        ),
        _build_link_item(
            "docs_search_home",
            "Docs search home",
            docs_page,
            unavailable_reason="No generic LADBS docs search home URL was available in the payload.",
            external=True,
        ),
    ]

    link_groups = [
        {"key": "local", "title": "Local review actions", "links": local_actions},
        {"key": "source", "title": "Property-specific source links", "links": source_links},
        {"key": "generic", "title": "Generic search/home pages", "links": generic_links},
    ]

    return {
        "offline_bundle": True,
        "include_remote_fonts": False,
        "page_kind": page_kind,
        "property_name": property_name,
        "stylesheet_href": f"{asset_prefix}/css/{STATIC_CSS_PATH.name}",
        "logo_href": f"{asset_prefix}/{STATIC_LOGO_PATH.name}",
        "link_groups": link_groups,
        "local_actions": local_actions,
        "source_links": source_links,
        "generic_links": generic_links,
    }


def _attach_review_bundle(
    payload: Dict[str, Any],
    *,
    property_name: str,
    page_kind: str = "report",
) -> Dict[str, Any]:
    enriched = dict(payload)
    enriched["review_bundle"] = _build_review_bundle_context(
        payload,
        property_name=property_name,
        page_kind=page_kind,
    )
    return enriched


def _load_existing_payload(bundle_root: Path, case: Dict[str, Any]) -> Dict[str, Any]:
    payload_path = bundle_root / case["name"] / "payload.normalized.json"
    return apply_payload_contract(json.loads(payload_path.read_text(encoding="utf-8")))


def _load_payload(case: Dict[str, Any], bundle_root: Path, offline_existing: bool) -> Dict[str, Any]:
    if offline_existing:
        return _load_existing_payload(bundle_root, case)
    return apply_payload_contract(run_full_comp_pipeline(case["redfin_url"]))


def _extract_section_map(report_html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(report_html, "lxml")
    section_map: Dict[str, Any] = {}
    for section in soup.select(".report-section"):
        header = section.select_one(".report-section-header")
        if header:
            section_map[_normalize_text(header.get_text(" ", strip=True))] = section
    return section_map


def _extract_report_checks(payload: Dict[str, Any], report_html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(report_html, "lxml")
    section_map = _extract_section_map(report_html)
    actual_headers = list(section_map.keys())
    strategy_notes_present = bool((payload.get("strategy_notes") or {}).get("tactics") or (payload.get("strategy_notes") or {}).get("risks") or (payload.get("strategy_notes") or {}).get("insights"))
    expected_headers = [header for header in EXPECTED_SECTION_ORDER if header != "Strategy Notes" or strategy_notes_present]

    permit_section = section_map.get("Permit Overview")
    record_section = section_map.get("LADBS Records")
    zimas_section = section_map.get("ZIMAS Parcel Profile")
    review_flag_messages = [
        _normalize_text(node.get_text(" ", strip=True))
        for node in soup.select(".review-flag-message")
        if _normalize_text(node.get_text(" ", strip=True))
    ]
    data_note_messages = [
        _normalize_text(node.get_text(" ", strip=True))
        for node in soup.select(".data-notes-list li")
        if _normalize_text(node.get_text(" ", strip=True))
    ]
    normalized_data_notes = {_normalize_compare_text(note) for note in data_note_messages}
    duplicate_note_overlap = [
        message for message in review_flag_messages if _normalize_compare_text(message) in normalized_data_notes
    ]

    zimas_rows: Dict[str, str] = {}
    if zimas_section:
        for row in zimas_section.select("table.audit-list tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                zimas_rows[_normalize_text(cells[0].get_text(" ", strip=True))] = _normalize_text(cells[1].get_text(" ", strip=True))

    key_field_mismatches: List[str] = []
    rendered_address = _normalize_text((soup.select_one(".property-address") or {}).get_text(" ", strip=True) if soup.select_one(".property-address") else "")
    payload_address = _normalize_text(payload.get("address"))
    if payload_address and rendered_address and payload_address != rendered_address:
        key_field_mismatches.append(f"Report address {rendered_address!r} does not match payload address {payload_address!r}.")

    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    expected_render_pairs = {
        "PIN": zimas.get("pin"),
        "APN": zimas.get("apn"),
        "Zoning": zoning_profile.get("zoning"),
        "General Plan": zoning_profile.get("general_plan_land_use"),
        "Community Plan": planning_context.get("community_plan_area"),
    }
    for label, payload_value in expected_render_pairs.items():
        rendered_value = zimas_rows.get(label)
        if payload_value and rendered_value and _normalize_compare_text(rendered_value) == "unknown":
            key_field_mismatches.append(f"{label} rendered as Unknown despite payload value {payload_value!r}.")

    report_pdf_links = 0
    if record_section:
        for link in record_section.select(".doc-links a"):
            if _normalize_compare_text(link.get_text(" ", strip=True)) == "pdf":
                report_pdf_links += 1

    return {
        "property_header_present": bool(soup.select_one(".property-header")),
        "section_headers": actual_headers,
        "expected_section_headers": expected_headers,
        "section_order_matches": actual_headers == expected_headers,
        "missing_sections": [header for header in expected_headers if header not in actual_headers],
        "contains_none": ">None<" in report_html or " None " in report_html,
        "contains_null": "null" in report_html,
        "contains_mojibake": any(token in report_html for token in MOJIBAKE_TOKENS),
        "permit_items_rendered": len(permit_section.select(".permit-item")) if permit_section else 0,
        "record_items_rendered": len(record_section.select(".permit-item")) if record_section else 0,
        "pdf_links_rendered": report_pdf_links,
        "duplicate_note_overlap": duplicate_note_overlap,
        "zimas_rows": zimas_rows,
        "key_field_render_mismatches": key_field_mismatches,
    }


def _build_representative_permit_details(
    payload: Dict[str, Any],
    *,
    limit: int = 4,
) -> List[Dict[str, str]]:
    permits = (payload.get("ladbs") or {}).get("permits") or []
    details: List[Dict[str, str]] = []
    for permit in permits[:limit]:
        if not isinstance(permit, dict):
            continue
        details.append(
            {
                "permit_number": _normalize_text(permit.get("permit_number")) or "Unknown permit number",
                "permit_type": _normalize_text(permit.get("permit_type") or permit.get("Type"))
                or "Unknown permit type",
                "status": _normalize_text(permit.get("Status")) or "Status unavailable",
                "description": _normalize_text(permit.get("Work_Description")) or "Description unavailable",
            }
        )
    return details


def _build_representative_document_details(
    payload: Dict[str, Any],
    *,
    limit: int = 4,
) -> List[Dict[str, str]]:
    documents = (payload.get("ladbs_records") or {}).get("documents") or []
    details: List[Dict[str, str]] = []
    for document in documents[:limit]:
        if not isinstance(document, dict):
            continue
        details.append(
            {
                "doc_number": _normalize_text(document.get("doc_number")) or "Unknown document number",
                "doc_type": _normalize_text(document.get("doc_type")) or "Unknown document type",
                "doc_date": _normalize_text(document.get("doc_date")) or "Date unavailable",
                "description": _normalize_text(document.get("description")) or "Description unavailable",
            }
        )
    return details


def _evaluate_property(case: Dict[str, Any], payload: Dict[str, Any], report_checks: Dict[str, Any]) -> Dict[str, Any]:
    expectations = case.get("expectations") or {}
    known_truths = case.get("known_truths") or {}
    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    permits = (payload.get("ladbs") or {}).get("permits") or []
    documents = (payload.get("ladbs_records") or {}).get("documents") or []
    pdf_count = sum(1 for doc in documents if isinstance(doc, dict) and doc.get("pdf_url"))
    source_states = (payload.get("source_diagnostics") or {}).get("source_states") or {}

    fact_mismatches: List[str] = []
    report_issues: List[str] = []
    questionable_items: List[str] = []

    expected_pairs = {
        "address": payload.get("address"),
        "apn": zimas.get("apn"),
        "pin": zimas.get("pin"),
        "zoning": zoning_profile.get("zoning"),
        "general_plan_land_use": zoning_profile.get("general_plan_land_use"),
        "community_plan_area": planning_context.get("community_plan_area"),
    }
    for key, expected_value in known_truths.items():
        actual_value = expected_pairs.get(key)
        if expected_value and actual_value != expected_value:
            fact_mismatches.append(f"{key} expected {expected_value!r} but got {actual_value!r}.")

    min_permit_count = expectations.get("min_permit_count")
    if isinstance(min_permit_count, int) and len(permits) < min_permit_count:
        fact_mismatches.append(f"Permit count {len(permits)} is below expected minimum {min_permit_count}.")

    min_record_count = expectations.get("min_record_count")
    if isinstance(min_record_count, int) and len(documents) < min_record_count:
        fact_mismatches.append(f"Record count {len(documents)} is below expected minimum {min_record_count}.")

    min_pdf_count = expectations.get("min_pdf_count")
    if isinstance(min_pdf_count, int) and pdf_count < min_pdf_count:
        fact_mismatches.append(f"PDF-link count {pdf_count} is below expected minimum {min_pdf_count}.")

    permit_numbers = {str(permit.get("permit_number")) for permit in permits if isinstance(permit, dict)}
    for permit_number in expectations.get("required_permit_numbers") or []:
        if permit_number not in permit_numbers:
            fact_mismatches.append(f"Representative permit {permit_number} is missing from the payload.")

    document_numbers = {str(document.get("doc_number")) for document in documents if isinstance(document, dict)}
    for document_number in expectations.get("required_document_numbers") or []:
        if document_number not in document_numbers:
            fact_mismatches.append(f"Representative document {document_number} is missing from the payload.")

    if not report_checks["property_header_present"]:
        report_issues.append("Property header is missing from the rendered report.")
    if not report_checks["section_order_matches"]:
        report_issues.append(
            "Section order mismatch: "
            f"expected {report_checks['expected_section_headers']!r}, got {report_checks['section_headers']!r}."
        )
    if report_checks["missing_sections"]:
        report_issues.append(f"Missing report sections: {report_checks['missing_sections']!r}.")
    if report_checks["contains_none"]:
        report_issues.append("Rendered report still contains raw None-style placeholder text.")
    if report_checks["contains_null"]:
        report_issues.append("Rendered report still contains raw null text.")
    if report_checks["contains_mojibake"]:
        report_issues.append("Rendered report contains mojibake or encoding garbage.")
    if report_checks["duplicate_note_overlap"]:
        report_issues.append(
            "Review Flags and Data Notes repeat the same message(s): "
            f"{report_checks['duplicate_note_overlap']!r}."
        )
    if report_checks["key_field_render_mismatches"]:
        report_issues.extend(report_checks["key_field_render_mismatches"])

    if report_checks["permit_items_rendered"] != len(permits):
        report_issues.append(
            "Permit item count in the report "
            f"({report_checks['permit_items_rendered']}) does not match payload permit count ({len(permits)})."
        )
    if report_checks["record_items_rendered"] != len(documents):
        report_issues.append(
            "Record item count in the report "
            f"({report_checks['record_items_rendered']}) does not match payload record count ({len(documents)})."
        )
    if report_checks["pdf_links_rendered"] != pdf_count:
        report_issues.append(
            "PDF-link count in the report "
            f"({report_checks['pdf_links_rendered']}) does not match payload PDF-link count ({pdf_count})."
        )

    for flag in payload.get("anomalies") or []:
        message = _normalize_text(flag.get("message"))
        if message:
            questionable_items.append(message)
    for note in payload.get("data_notes") or []:
        normalized_note = _normalize_text(note)
        if normalized_note:
            questionable_items.append(normalized_note)
    for note in case.get("acceptable_uncertainty_notes") or []:
        normalized_note = _normalize_text(note)
        if normalized_note and normalized_note not in questionable_items:
            questionable_items.append(normalized_note)

    questionable_items = list(dict.fromkeys(questionable_items))

    if fact_mismatches or report_issues:
        verdict = "needs-fix"
    elif (payload.get("anomalies") or []) or (payload.get("data_notes") or []):
        verdict = "accepted-with-review"
    else:
        verdict = "accepted"

    representative_permits = [
        permit.get("permit_number")
        for permit in permits[:3]
        if isinstance(permit, dict) and permit.get("permit_number")
    ]
    representative_documents = [
        document.get("doc_number")
        for document in documents[:3]
        if isinstance(document, dict) and document.get("doc_number")
    ]

    return {
        "name": case.get("name"),
        "role": case.get("role"),
        "redfin_url": case.get("redfin_url"),
        "address": payload.get("address"),
        "verdict": verdict,
        "acceptable_uncertainty_notes": case.get("acceptable_uncertainty_notes") or [],
        "known_truths": known_truths,
        "actual_facts": {
            "apn": zimas.get("apn"),
            "pin": zimas.get("pin"),
            "zoning": zoning_profile.get("zoning"),
            "general_plan_land_use": zoning_profile.get("general_plan_land_use"),
            "community_plan_area": planning_context.get("community_plan_area"),
            "permit_count": len(permits),
            "record_count": len(documents),
            "pdf_link_count": pdf_count,
        },
        "representative_permits": representative_permits,
        "representative_documents": representative_documents,
        "representative_permit_details": _build_representative_permit_details(payload),
        "representative_document_details": _build_representative_document_details(payload),
        "source_states": source_states,
        "fact_mismatches": fact_mismatches,
        "report_issues": report_issues,
        "questionable_items": questionable_items,
        "review_context_items": questionable_items[:4],
        "review_flags": payload.get("anomalies") or [],
        "data_notes": payload.get("data_notes") or [],
        "report_checks": report_checks,
    }


def _build_property_page_context(summary: Dict[str, Any], *, page_kind: str) -> Dict[str, Any]:
    payload = summary["payload"]
    review_bundle = _build_review_bundle_context(
        payload,
        property_name=summary["name"],
        page_kind=page_kind,
    )
    facts = summary["actual_facts"]
    return {
        "slug": summary["name"],
        "display_name": _slug_title(summary["name"]),
        "address": summary["address"],
        "role": summary.get("role") or "review",
        "verdict": summary["verdict"],
        "redfin_url": summary.get("redfin_url"),
        "facts": facts,
        "review_flags": summary.get("review_flags") or [],
        "data_notes": summary.get("data_notes") or [],
        "acceptable_uncertainty_notes": summary.get("acceptable_uncertainty_notes") or [],
        "questionable_items": summary.get("questionable_items") or [],
        "review_context_items": summary.get("review_context_items") or [],
        "representative_permits": summary.get("representative_permit_details") or [],
        "representative_documents": summary.get("representative_document_details") or [],
        "review_bundle": review_bundle,
        "review_link_groups": review_bundle["link_groups"],
        "local_actions": review_bundle["local_actions"],
        "source_links": review_bundle["source_links"],
        "generic_links": review_bundle["generic_links"],
    }


def _render_summary_html(summary: Dict[str, Any]) -> str:
    return _render_template_html(
        "report_acceptance_summary.html",
        page=_build_property_page_context(summary, page_kind="summary"),
    )


def _render_landing_page_html(summaries: List[Dict[str, Any]]) -> str:
    cards = [_build_property_page_context(summary, page_kind="index") for summary in summaries]
    return _render_template_html(
        "report_acceptance_index.html",
        bundle={
            "title": "Report Acceptance Review Bundles",
            "property_count": len(cards),
            "stylesheet_href": f"{BUNDLE_ASSETS_DIRNAME}/css/{STATIC_CSS_PATH.name}",
            "logo_href": f"{BUNDLE_ASSETS_DIRNAME}/{STATIC_LOGO_PATH.name}",
            "cards": cards,
        },
    )


def _build_property_summary_markdown(summary: Dict[str, Any], bundle_dir: Path) -> str:
    actual = summary["actual_facts"]
    source_states = summary["source_states"]
    review_flags = summary["review_flags"]
    report_checks = summary["report_checks"]
    review_bundle = _build_review_bundle_context(
        summary.get("payload") or {},
        property_name=summary["name"],
        page_kind="summary",
    )
    lines = [
        f"# {summary['name'].replace('-', ' ').title()} Review Summary",
        "",
        f"- Verdict: `{summary['verdict']}`",
        f"- Role: `{summary.get('role') or 'review'}`",
        f"- Address: `{summary['address']}`",
        f"- URL: {summary['redfin_url']}",
        f"- Browser summary: [summary.html](summary.html)",
        f"- Payload: [payload.normalized.json](payload.normalized.json)",
        f"- Rendered report: [report.html](report.html)",
        "",
        "## Key Facts",
        "",
        f"- APN: `{actual['apn']}`",
        f"- PIN: `{actual['pin']}`",
        f"- Zoning: `{actual['zoning']}`",
        f"- General Plan: `{actual['general_plan_land_use']}`",
        f"- Community Plan: `{actual['community_plan_area']}`",
        f"- Permit count: `{actual['permit_count']}`",
        f"- Record count: `{actual['record_count']}`",
        f"- PDF-link count: `{actual['pdf_link_count']}`",
        "",
        "## Representative IDs",
        "",
        f"- Permits: {', '.join(summary['representative_permits']) if summary['representative_permits'] else 'None'}",
        f"- Documents: {', '.join(summary['representative_documents']) if summary['representative_documents'] else 'None'}",
        "",
        "## Sources",
        "",
    ]
    for name, state in source_states.items():
        lines.append(f"- {name}: `{state.get('source')}`")

    lines.extend(
        [
            "",
            "## Report Checks",
            "",
            f"- Section order matches: `{report_checks['section_order_matches']}`",
            f"- Property header present: `{report_checks['property_header_present']}`",
            f"- Rendered permit items: `{report_checks['permit_items_rendered']}`",
            f"- Rendered record items: `{report_checks['record_items_rendered']}`",
            f"- Rendered PDF links: `{report_checks['pdf_links_rendered']}`",
            f"- Raw None text present: `{report_checks['contains_none']}`",
            f"- Raw null text present: `{report_checks['contains_null']}`",
            f"- Mojibake present: `{report_checks['contains_mojibake']}`",
            "",
            "## Review Flags",
            "",
        ]
    )
    if review_flags:
        for flag in review_flags:
            lines.append(f"- `{flag.get('code')}`: {flag.get('message')}")
    else:
        lines.append("- None")

    lines.extend(["", "## Data Notes", ""])
    if summary["data_notes"]:
        for note in summary["data_notes"]:
            lines.append(f"- {note}")
    else:
        lines.append("- None")

    lines.extend(["", "## Questionable Items", ""])
    if summary["questionable_items"]:
        for item in summary["questionable_items"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(["", "## Browser Review Links", ""])
    for group in review_bundle["link_groups"]:
        lines.append(f"### {group['title']}")
        for link in group["links"]:
            if link["status"] == "available":
                lines.append(f"- {link['label']}: [{link['url']}]({link['url']})")
            else:
                lines.append(f"- {link['label']}: {link['reason']}")
        lines.append("")

    lines.extend(["", "## Mismatches / Issues", ""])
    if summary["fact_mismatches"] or summary["report_issues"]:
        for item in summary["fact_mismatches"]:
            lines.append(f"- Fact mismatch: {item}")
        for item in summary["report_issues"]:
            lines.append(f"- Report issue: {item}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def _write_bundle(bundle_root: Path, payload: Dict[str, Any], report_html: str, summary: Dict[str, Any]) -> None:
    bundle_dir = bundle_root / summary["name"]
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "payload.normalized.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (bundle_dir / "report.html").write_text(report_html, encoding="utf-8")
    summary_with_payload = dict(summary)
    summary_with_payload["payload"] = payload
    (bundle_dir / "summary.html").write_text(
        _render_summary_html(summary_with_payload),
        encoding="utf-8",
    )
    (bundle_dir / "summary.md").write_text(
        _build_property_summary_markdown(summary_with_payload, bundle_dir),
        encoding="utf-8",
    )


def _build_landing_page(bundle_root: Path, summaries: List[Dict[str, Any]]) -> str:
    return _render_landing_page_html(summaries)


def _build_index_markdown(bundle_root: Path, summaries: List[Dict[str, Any]]) -> str:
    lines = [
        "# Report Review Index",
        "",
        "- Static landing page: [review_bundles/report_acceptance/index.html](./review_bundles/report_acceptance/index.html)",
        "",
        "| Property | Role | Verdict | Address | Key Facts | Review Context | Local Review | Source Links | Generic Search |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for summary in summaries:
        facts = summary["actual_facts"]
        review_bundle = _build_review_bundle_context(
            summary.get("payload") or {},
            property_name=summary["name"],
            page_kind="index",
        )
        review_context = " / ".join(summary.get("review_context_items") or []) or "none"
        local_review_links = ", ".join(
            f"[{link['label']}]({link['url']})" for link in review_bundle["local_actions"] if link["status"] == "available"
        )
        property_source_links = ", ".join(
            f"[{link['label']}]({link['url']})" for link in review_bundle["source_links"] if link["status"] == "available"
        )
        generic_search_links = ", ".join(
            f"[{link['label']}]({link['url']})" for link in review_bundle["generic_links"] if link["status"] == "available"
        )
        unavailable_source_links = ", ".join(
            link["label"] for link in review_bundle["source_links"] if link["status"] != "available"
        )
        unavailable_generic_links = ", ".join(
            link["label"] for link in review_bundle["generic_links"] if link["status"] != "available"
        )
        if unavailable_source_links:
            property_source_links = (
                f"{property_source_links} ; unavailable: {unavailable_source_links}"
                if property_source_links
                else f"unavailable: {unavailable_source_links}"
            )
        if unavailable_generic_links:
            generic_search_links = (
                f"{generic_search_links} ; unavailable: {unavailable_generic_links}"
                if generic_search_links
                else f"unavailable: {unavailable_generic_links}"
            )
        lines.append(
            "| "
            + f"{summary['name']} | "
            + f"{summary.get('role') or 'review'} | "
            + f"`{summary['verdict']}` | "
            + f"{summary['address']} | "
            + f"PIN `{facts['pin']}` / APN `{facts['apn']}` / permits `{facts['permit_count']}` / records `{facts['record_count']}` | "
            + f"{review_context} | "
            + f"{local_review_links or 'none'} | "
            + f"{property_source_links or 'none'} | "
            + f"{generic_search_links or 'none'} |"
        )

    lines.extend(["", "## Questionable Items", ""])
    for summary in summaries:
        if not summary["questionable_items"]:
            continue
        lines.append(f"### {summary['name']}")
        for item in summary["questionable_items"]:
            lines.append(f"- {item}")
        lines.append("")

    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def generate_review_bundle_outputs(
    *,
    cases: List[Dict[str, Any]],
    bundle_root: Path,
    offline_existing: bool,
    review_index_path: Path,
) -> List[Dict[str, Any]]:
    bundle_root.mkdir(parents=True, exist_ok=True)
    _copy_bundle_assets(bundle_root)

    summaries: List[Dict[str, Any]] = []
    for case in cases:
        payload = _load_payload(case, bundle_root, offline_existing)
        report_payload = _attach_review_bundle(
            payload,
            property_name=case["name"],
            page_kind="report",
        )
        report_html = _render_report_html(report_payload)
        report_checks = _extract_report_checks(payload, report_html)
        summary = _evaluate_property(case, payload, report_checks)
        summary["payload"] = payload
        summaries.append(summary)
        _write_bundle(bundle_root, payload, report_html, summary)

    review_index = _build_index_markdown(bundle_root, summaries)
    review_index_path.write_text(review_index, encoding="utf-8")
    (bundle_root / "index.html").write_text(_build_landing_page(bundle_root, summaries), encoding="utf-8")
    return summaries


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    bundle_root = Path(args.output_dir)
    cases = _load_property_file(args.property_file)
    summaries = generate_review_bundle_outputs(
        cases=cases,
        bundle_root=bundle_root,
        offline_existing=args.offline_existing,
        review_index_path=BASE_DIR / "REVIEW_INDEX.md",
    )

    if args.json:
        print(json.dumps({"properties": summaries}, indent=2, sort_keys=True))
    else:
        for summary in summaries:
            print(f"[REVIEW] name={summary['name']!r}")
            print(f"[REVIEW] verdict={summary['verdict']!r}")
            print(f"[REVIEW] address={summary['address']!r}")
            print("[REVIEW] facts=" + json.dumps(summary["actual_facts"], sort_keys=True))
            print("[REVIEW] report_checks=" + json.dumps(summary["report_checks"], sort_keys=True))
            if summary["fact_mismatches"]:
                print(f"[REVIEW] fact_mismatches={summary['fact_mismatches']}")
            if summary["report_issues"]:
                print(f"[REVIEW] report_issues={summary['report_issues']}")
            if summary["questionable_items"]:
                print(f"[REVIEW] questionable_items={summary['questionable_items']}")

    return 0 if all(summary["verdict"] != "needs-fix" for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
