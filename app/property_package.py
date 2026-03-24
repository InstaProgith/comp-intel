from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import render_template

from app.ladbs_records_client import (
    LADBS_IMAGE_LIST_URL,
    LADBS_RECORDS_BOOTSTRAP_URL,
    LADBS_RECORDS_SEARCH_URL,
    _build_session as _build_records_session,
    _collect_form_payload,
    _parse_address_candidates,
    _parse_records_results,
    _resolve_document_artifact_refs,
    _select_address_candidates,
    split_apn,
)
from app.ladbs_scraper import (
    LADBS_PERMIT_REPORT_BASE_URL,
    LADBS_PERMIT_RESULTS_BY_PIN_URL,
    LADBS_PIN_ADDRESS_PARTIAL_URL,
    _build_http_session,
    _normalize_address_signature,
    _parse_pin_address_sections,
    _parse_pin_permit_rows,
    _parse_pin_results_summary,
    parse_pcis_detail_html,
)
from app.orchestrator import run_full_comp_pipeline
from app.report_acceptance import _copy_bundle_assets

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "property_runs" / "midvale_live"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live single-property package with durable local LADBS document capture."
    )
    parser.add_argument("--redfin-url", required=True, help="Redfin property URL to process live.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where the single-property package should be written.",
    )
    parser.add_argument("--json", action="store_true", help="Print the package summary as JSON.")
    return parser


def _render_template_html(template_name: str, **context: Any) -> str:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_TESTING", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "property-package-secret")
    os.environ.setdefault("APP_ACCESS_PASSWORD", "property-package-password")
    from app.ui_server import app as ui_app

    with ui_app.test_request_context("/property-package"):
        return render_template(template_name, **context)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_text(value).lower())
    return slug.strip("-") or "property"


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative_href(from_path: Path, target_path: Path) -> str:
    return Path(os.path.relpath(target_path, from_path.parent)).as_posix()


def _path_from_root(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _record_local_file(root: Path, path: Path, label: str, kind: str) -> Dict[str, Any]:
    content = path.read_bytes()
    return {
        "label": label,
        "path": _path_from_root(root, path),
        "kind": kind,
        "size_bytes": len(content),
        "sha256": _sha256_hex(content),
    }


def _extract_html_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n", strip=True).splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_pdf_text(pdf_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    if not pdf_bytes.startswith(b"%PDF"):
        return None, "PDF bytes were not returned."
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None, "pypdf is not installed; PDF preserved locally without text extraction."

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:  # pragma: no cover - depends on live PDF parser behavior
        return None, f"PDF text extraction failed: {exc}"

    text = "\n\n".join(part for part in text_parts if part)
    return (text or None), None


def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_us_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _format_date(value: Optional[str]) -> str:
    iso_dt = _parse_iso_date(value)
    if iso_dt:
        return iso_dt.strftime("%b %d, %Y")
    us_dt = _parse_us_date(value)
    if us_dt:
        return us_dt.strftime("%b %d, %Y")
    return _normalize_text(value) or "Unknown"


def _format_bath_value(value: Optional[Any]) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    return f"{number:g}"


def _format_money(value: Optional[Any]) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    return f"${amount:,.0f}"


def _format_int(value: Optional[Any]) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"


def _clean_scope_text(value: Optional[str]) -> str:
    text = _normalize_text(value)
    return text.rstrip(" .;,:")


def _build_redfin_truth(payload: Dict[str, Any]) -> Dict[str, Any]:
    redfin = payload.get("redfin") or {}
    timeline = sorted(redfin.get("timeline") or [], key=lambda event: event.get("date") or "")
    sold_events = [event for event in timeline if event.get("event") == "sold"]
    latest_sale = sold_events[-1] if sold_events else None
    prior_sale = sold_events[-2] if len(sold_events) > 1 else None
    listing_baths = redfin.get("baths") or redfin.get("listing_baths")
    public_record_baths = ((redfin.get("public_records") or {}).get("baths"))

    cautions: List[str] = []
    if listing_baths is not None and public_record_baths is not None and listing_baths != public_record_baths:
        cautions.append(
            "Redfin is internally inconsistent on baths: the live listing header shows "
            f"{_format_bath_value(listing_baths)} bath(s), while Redfin public records show "
            f"{_format_bath_value(public_record_baths)} bath(s)."
        )

    if prior_sale and prior_sale.get("price") and latest_sale and latest_sale.get("price"):
        spread = int(latest_sale["price"]) - int(prior_sale["price"])
        sold_flip_summary = (
            f"Latest Redfin sale: {_format_date(latest_sale.get('date'))} for {_format_money(latest_sale.get('price'))}. "
            f"Prior Redfin sale: {_format_date(prior_sale.get('date'))} for {_format_money(prior_sale.get('price'))}. "
            f"Observed spread: {_format_money(spread)}."
        )
    elif latest_sale:
        sold_flip_summary = (
            f"Latest Redfin sale: {_format_date(latest_sale.get('date'))} for "
            f"{_format_money(latest_sale.get('price'))}. "
            "No prior Redfin sale event is exposed in the current live timeline, so prior buy/flip logic is not discoverable."
        )
    else:
        sold_flip_summary = "No live Redfin sale event was available in the current timeline."
        cautions.append("Redfin did not expose a sale event for this subject during the live run.")

    return {
        "address": redfin.get("address"),
        "status": "Sold" if latest_sale else _normalize_text(redfin.get("status")) or "Unknown",
        "last_sold_date": latest_sale.get("date") if latest_sale else None,
        "last_sold_price": latest_sale.get("price") if latest_sale else None,
        "last_sold_date_display": _format_date(latest_sale.get("date")) if latest_sale else "Unknown",
        "last_sold_price_display": _format_money(latest_sale.get("price")) if latest_sale else "Unknown",
        "list_price": redfin.get("list_price"),
        "beds": redfin.get("beds") or redfin.get("listing_beds"),
        "beds_display": _format_int(redfin.get("beds") or redfin.get("listing_beds")),
        "baths": listing_baths,
        "baths_display": _format_bath_value(listing_baths),
        "living_area_sf": redfin.get("building_sf") or redfin.get("listing_building_sf"),
        "living_area_sf_display": _format_int(redfin.get("building_sf") or redfin.get("listing_building_sf")),
        "lot_size_sf": redfin.get("lot_sf"),
        "lot_size_sf_display": _format_int(redfin.get("lot_sf")),
        "year_built": redfin.get("year_built") or redfin.get("listing_year_built"),
        "property_type": redfin.get("property_type"),
        "prior_sale": prior_sale,
        "latest_sale": latest_sale,
        "sold_flip_summary": sold_flip_summary,
        "cautions": cautions,
    }


def _build_identity(payload: Dict[str, Any]) -> Dict[str, Any]:
    redfin = payload.get("redfin") or {}
    zimas = payload.get("zimas_profile") or {}
    parcel = zimas.get("parcel_identity") or {}
    redfin_apn = ((redfin.get("tax") or {}).get("apn"))
    apn = zimas.get("apn") or redfin_apn
    pin = zimas.get("pin") or ((payload.get("ladbs") or {}).get("pin"))
    municipal_address = (
        parcel.get("site_address")
        or zimas.get("address")
        or ((zimas.get("pin_resolution") or {}).get("matched_address"))
    )
    evidence = [
        f"Redfin address: {_normalize_text(redfin.get('address')) or 'Unknown'}",
        f"ZIMAS municipal address: {_normalize_text(municipal_address) or 'Unknown'}",
        f"APN: {_normalize_text(apn) or 'Unknown'}",
        f"PIN: {_normalize_text(pin) or 'Unknown'}",
    ]
    return {
        "subject_address": redfin.get("address"),
        "municipal_address": municipal_address,
        "apn": apn,
        "pin": pin,
        "lot_area_sqft": parcel.get("lot_area_sqft"),
        "zoning": ((zimas.get("zoning_profile") or {}).get("zoning")),
        "general_plan_land_use": ((zimas.get("zoning_profile") or {}).get("general_plan_land_use")),
        "community_plan_area": ((zimas.get("planning_context") or {}).get("community_plan_area")),
        "evidence": evidence,
    }


def _match_subject_address(candidate: Optional[str], identity: Dict[str, Any]) -> bool:
    normalized_candidate = _normalize_address_signature(candidate)
    if not normalized_candidate:
        return False
    for value in (
        identity.get("municipal_address"),
        identity.get("subject_address"),
    ):
        normalized_value = _normalize_address_signature(value)
        if not normalized_value:
            continue
        if (
            normalized_candidate == normalized_value
            or normalized_value in normalized_candidate
            or normalized_candidate in normalized_value
        ):
            return True
    return False


def _build_doc_file_entry(root: Path, path: Path, label: str, kind: str) -> Dict[str, Any]:
    metadata = _record_local_file(root, path, label, kind)
    metadata["href"] = metadata["path"]
    return metadata


def _build_named_party(
    role: str,
    name: str,
    *,
    license_number: Optional[str] = None,
    source: str,
    party_type: str,
) -> Dict[str, Any]:
    item = {
        "role": role,
        "name": _normalize_text(name),
        "source": source,
        "party_type": party_type,
    }
    if _normalize_text(license_number):
        item["license_number"] = _normalize_text(license_number)
    return item


def _collect_contact_team_mentions(details: Dict[str, Any], permit_number: str) -> List[Dict[str, Any]]:
    mentions: List[Dict[str, Any]] = []
    contractor = _normalize_text(details.get("contractor"))
    if contractor:
        mentions.append(
            _build_named_party(
                "Contractor",
                contractor,
                license_number=details.get("contractor_license"),
                source=f"Permit {permit_number} contact information",
                party_type="project_side",
            )
        )

    architect = _normalize_text(details.get("architect"))
    if architect:
        mentions.append(
            _build_named_party(
                "Architect",
                architect,
                license_number=details.get("architect_license"),
                source=f"Permit {permit_number} contact information",
                party_type="project_side",
            )
        )

    engineer = _normalize_text(details.get("engineer"))
    if engineer:
        mentions.append(
            _build_named_party(
                "Engineer",
                engineer,
                license_number=details.get("engineer_license"),
                source=f"Permit {permit_number} contact information",
                party_type="project_side",
            )
        )

    status_history = (details.get("raw_details") or {}).get("status_history") or []
    for row in status_history:
        person = _normalize_text((row or {}).get("person"))
        if not person or person.upper() in {"LADBS", "APPLICANT"}:
            continue
        mentions.append(
            _build_named_party(
                row.get("event") or "Status history",
                person,
                source=f"Permit {permit_number} status history",
                party_type="city_side",
            )
        )

    return mentions


def _extract_record_team_mentions(summary_text: Optional[str], doc_number: str) -> List[Dict[str, Any]]:
    if not summary_text:
        return []
    lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    mentions: List[Dict[str, Any]] = []
    for index, line in enumerate(lines):
        if line.lower() == "contact":
            for offset in range(index + 1, min(index + 5, len(lines) - 1)):
                if lines[offset].lower().startswith("name"):
                    candidate = lines[offset + 1].strip()
                    if candidate and not candidate.endswith(":"):
                        mentions.append(
                            _build_named_party(
                                "Record contact",
                                candidate,
                                source=f"Record {doc_number} summary page",
                                party_type="project_side",
                            )
                        )
                        return mentions
    return mentions


def _capture_permit_documents(
    payload: Dict[str, Any],
    root_dir: Path,
    identity: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    pin = _normalize_text(identity.get("pin"))
    subject_address = identity.get("municipal_address") or identity.get("subject_address")
    session = _build_http_session()
    captures: List[Dict[str, Any]] = []
    notes: List[str] = []
    diagnostics: Dict[str, Any] = {}

    pin_results_response = session.get(LADBS_PERMIT_RESULTS_BY_PIN_URL, params={"pin": pin}, timeout=30)
    pin_results_response.raise_for_status()
    page_summary = _parse_pin_results_summary(pin_results_response.text or "")
    diagnostics["pin_results_url"] = pin_results_response.url
    diagnostics["page_summary"] = page_summary

    address_partial_response = session.get(LADBS_PIN_ADDRESS_PARTIAL_URL, params={"pin": pin}, timeout=30)
    address_partial_response.raise_for_status()
    address_sections = _parse_pin_address_sections(address_partial_response.text or "")
    subject_signature = _normalize_address_signature(subject_address)
    if subject_signature:
        matching_sections = [
            section
            for section in address_sections
            if _normalize_address_signature(section.get("label")) == subject_signature
        ]
        if matching_sections:
            address_sections = matching_sections
    diagnostics["address_sections"] = [section.get("label") for section in address_sections]

    permits_by_number = {
        _normalize_text(permit.get("permit_number")): permit
        for permit in (payload.get("ladbs") or {}).get("permits") or []
        if _normalize_text(permit.get("permit_number"))
    }

    if page_summary.get("permit_count") is not None:
        extracted_count = len(permits_by_number)
        if page_summary.get("permit_count") != extracted_count:
            notes.append(
                f"LADBS PermitResultsbyPin page summary reported {page_summary.get('permit_count')} permit(s), "
                f"but the subject-address drilldown yielded {extracted_count} permit detail page(s)."
            )

    for section in address_sections:
        query_suffix = section.get("query_suffix")
        if not query_suffix:
            continue
        section_url = f"{LADBS_PERMIT_REPORT_BASE_URL}_IparPcisAddressDrillDownPartial{query_suffix}"
        section_response = session.get(section_url, timeout=30)
        section_response.raise_for_status()
        permit_rows = _parse_pin_permit_rows(section_response.text or "", section.get("label"))

        for permit_basic in permit_rows:
            permit_number = _normalize_text(permit_basic.get("permit_number"))
            if not permit_number:
                continue

            detail_response = session.get(permit_basic["url"], timeout=30)
            detail_response.raise_for_status()
            detail_html = detail_response.text or ""
            detail_text = _extract_html_text(detail_html)
            detail_path = root_dir / "docs" / "permits" / permit_number / "permit_detail.source.html"
            text_path = root_dir / "docs" / "permits" / permit_number / "permit_detail.txt"
            _write_text(detail_path, detail_html)
            _write_text(text_path, detail_text)

            payload_permit = permits_by_number.get(permit_number) or {}
            parsed_details = parse_pcis_detail_html(detail_html) or {}
            parsed_details.setdefault("permit_number", permit_number)
            parsed_details.setdefault("status_date", payload_permit.get("status_date"))
            parsed_details.setdefault("address_label", permit_basic.get("address_label"))
            parsed_details.setdefault("work_description", payload_permit.get("Work_Description"))
            parsed_details.setdefault("current_status", payload_permit.get("Status"))
            parsed_details.setdefault("permit_issued", payload_permit.get("Issued_Date"))
            parsed_details.setdefault("job_number", payload_permit.get("job_number"))

            validation_evidence: List[str] = []
            if _match_subject_address(permit_basic.get("address_label"), identity):
                validation_evidence.append(
                    f"LADBS permit drilldown was filtered to {permit_basic.get('address_label')}."
                )
            if _match_subject_address(detail_text, identity):
                validation_evidence.append("Permit detail page text repeats the subject address.")
            validation_status = "valid_for_subject" if validation_evidence else "reachable_but_unverifiable"

            team_mentions = _collect_contact_team_mentions(payload_permit, permit_number)
            scope_signals = [
                _normalize_text(parsed_details.get("work_description")),
                _normalize_text((payload_permit.get("raw_details") or {}).get("certificate_of_occupancy")),
            ]
            scope_signals = [signal for signal in scope_signals if signal]

            metadata = {
                "permit_number": permit_number,
                "job_number": _normalize_text(parsed_details.get("job_number")) or None,
                "permit_type": _normalize_text(payload_permit.get("permit_type") or payload_permit.get("Type")) or None,
                "status_text": _normalize_text(payload_permit.get("Status") or parsed_details.get("current_status")) or None,
                "status_date": payload_permit.get("status_date") or parsed_details.get("status_date"),
                "issued_text": _normalize_text(payload_permit.get("Issued_Date") or parsed_details.get("permit_issued")) or None,
                "address_label": permit_basic.get("address_label"),
                "source_url": permit_basic.get("url"),
                "capture_type": "permit_detail_html",
                "validation_status": validation_status,
                "validation_evidence": validation_evidence,
                "work_description": _normalize_text(parsed_details.get("work_description")) or None,
                "certificate_of_occupancy": _normalize_text(parsed_details.get("certificate_of_occupancy")) or None,
                "team_mentions": team_mentions,
                "scope_signals": scope_signals,
            }
            metadata_path = detail_path.parent / "metadata.json"
            _write_json(metadata_path, metadata)

            captures.append(
                {
                    "id": f"permit-{permit_number}",
                    "category": "permit",
                    "title": f"Permit {permit_number}",
                    "doc_number": permit_number,
                    "doc_type": "Permit detail",
                    "sub_type": _normalize_text(payload_permit.get("permit_type") or payload_permit.get("Type")) or "Unknown",
                    "doc_date": payload_permit.get("status_date") or parsed_details.get("status_date"),
                    "address_label": permit_basic.get("address_label"),
                    "capture_status": "captured",
                    "validation_status": validation_status,
                    "validation_evidence": validation_evidence,
                    "source_links": [
                        {
                            "label": "Permit detail source",
                            "url": permit_basic.get("url"),
                            "stable": True,
                        }
                    ],
                    "scope_signals": scope_signals,
                    "team_mentions": team_mentions,
                    "capture_notes": [],
                    "local_files": [
                        _build_doc_file_entry(root_dir, detail_path, "Permit detail snapshot", "html"),
                        _build_doc_file_entry(root_dir, text_path, "Extracted text", "text"),
                        _build_doc_file_entry(root_dir, metadata_path, "Metadata", "json"),
                    ],
                }
            )

    return captures, notes, diagnostics


def _capture_record_documents(
    payload: Dict[str, Any],
    root_dir: Path,
    identity: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    apn = _normalize_text(identity.get("apn"))
    subject_address = identity.get("subject_address") or identity.get("municipal_address")
    records_notes: List[str] = []
    diagnostics: Dict[str, Any] = {}
    captures: List[Dict[str, Any]] = []

    apn_parts = split_apn(apn)
    if not apn_parts:
        return [], [f"Could not derive a valid LADBS records APN from {apn!r}."], diagnostics

    session = _build_records_session()
    session.get(LADBS_RECORDS_BOOTSTRAP_URL, timeout=45, allow_redirects=True)
    search_page = session.get(LADBS_RECORDS_SEARCH_URL, timeout=45)
    search_page.raise_for_status()
    search_form = BeautifulSoup(search_page.text or "", "lxml").find("form")
    if not search_form:
        raise RuntimeError("LADBS records search page did not contain a form during local capture.")

    search_payload = _collect_form_payload(
        search_form,
        clicked_button_name="btnSearchAssessor",
        clicked_button_value="Search",
        extra_fields={
            "Assessor$txtAssessorNoBook": apn_parts["book"],
            "Assessor$txtAssessorNoPage": apn_parts["page"],
            "Assessor$txtAssessorNoParcel": apn_parts["parcel"],
        },
    )
    selection_response = session.post(LADBS_RECORDS_SEARCH_URL, data=search_payload, timeout=45)
    selection_response.raise_for_status()
    selection_html = selection_response.text or ""
    selection_candidates = _parse_address_candidates(selection_html)
    chosen_candidates = _select_address_candidates(selection_candidates, subject_address)
    diagnostics["selection_candidates"] = [candidate.get("label") for candidate in selection_candidates]
    diagnostics["selected_addresses"] = [candidate.get("label") for candidate in chosen_candidates]

    results_html = selection_html
    if chosen_candidates:
        selection_form = BeautifulSoup(selection_html, "lxml").find("form")
        if not selection_form:
            raise RuntimeError("LADBS records address-selection page did not contain a form during local capture.")
        continue_payload = _collect_form_payload(
            selection_form,
            clicked_button_name="btnNext2",
            clicked_button_value="Continue",
        )
        for candidate in chosen_candidates:
            continue_payload[candidate["checkbox_name"]] = candidate["value"]
        results_response = session.post(LADBS_RECORDS_SEARCH_URL, data=continue_payload, timeout=45)
        results_response.raise_for_status()
        results_html = results_response.text or ""

    parsed_results = _parse_records_results(results_html)
    diagnostics["search_criteria"] = parsed_results.get("search_criteria")
    diagnostics["page_summary"] = parsed_results.get("page_summary")

    for document in parsed_results.get("documents") or []:
        if document.get("has_digital_image"):
            document.update(_resolve_document_artifact_refs(session, document))

        doc_number = _normalize_text(document.get("doc_number")) or "record"
        doc_dir = root_dir / "docs" / "records" / _slugify(doc_number)
        doc_dir.mkdir(parents=True, exist_ok=True)
        local_files: List[Dict[str, Any]] = []
        capture_notes: List[str] = []

        summary_text = None
        summary_url = document.get("summary_url")
        if summary_url:
            summary_response = session.get(summary_url, timeout=45, allow_redirects=True)
            summary_response.raise_for_status()
            summary_html = summary_response.text or ""
            summary_path = doc_dir / "record_summary.source.html"
            summary_text_path = doc_dir / "record_summary.txt"
            summary_text = _extract_html_text(summary_html)
            _write_text(summary_path, summary_html)
            _write_text(summary_text_path, summary_text)
            local_files.append(_build_doc_file_entry(root_dir, summary_path, "Record summary snapshot", "html"))
            local_files.append(_build_doc_file_entry(root_dir, summary_text_path, "Record summary text", "text"))
        team_mentions = _extract_record_team_mentions(summary_text, doc_number)

        image_main_url = document.get("image_main_url")
        if image_main_url:
            image_main_response = session.get(image_main_url, timeout=45, allow_redirects=True)
            image_main_response.raise_for_status()
            image_main_html = image_main_response.text or ""
            image_main_path = doc_dir / "image_main.source.html"
            _write_text(image_main_path, image_main_html)
            local_files.append(_build_doc_file_entry(root_dir, image_main_path, "Image viewer snapshot", "html"))

            image_list_response = session.get(LADBS_IMAGE_LIST_URL, timeout=45, allow_redirects=True)
            image_list_response.raise_for_status()
            image_list_html = image_list_response.text or ""
            image_list_path = doc_dir / "image_list.source.html"
            image_list_text_path = doc_dir / "image_list.txt"
            _write_text(image_list_path, image_list_html)
            _write_text(image_list_text_path, _extract_html_text(image_list_html))
            local_files.append(_build_doc_file_entry(root_dir, image_list_path, "Image list snapshot", "html"))
            local_files.append(_build_doc_file_entry(root_dir, image_list_text_path, "Image list text", "text"))

        pdf_url = document.get("pdf_url")
        if pdf_url:
            pdf_response = session.get(pdf_url, timeout=45, allow_redirects=True)
            pdf_response.raise_for_status()
            content_type = _normalize_text(pdf_response.headers.get("content-type")).lower()
            if "application/pdf" in content_type or pdf_response.content.startswith(b"%PDF"):
                pdf_path = doc_dir / "document.pdf"
                _write_bytes(pdf_path, pdf_response.content)
                local_files.append(_build_doc_file_entry(root_dir, pdf_path, "Captured PDF", "pdf"))
                pdf_text, pdf_text_note = _extract_pdf_text(pdf_response.content)
                if pdf_text:
                    pdf_text_path = doc_dir / "document.txt"
                    _write_text(pdf_text_path, pdf_text)
                    local_files.append(_build_doc_file_entry(root_dir, pdf_text_path, "PDF text", "text"))
                elif pdf_text_note:
                    capture_notes.append(pdf_text_note)
            else:
                failed_pdf_path = doc_dir / "pdf_viewer_response.txt"
                _write_text(failed_pdf_path, pdf_response.content.decode("utf-16-le", errors="ignore"))
                local_files.append(_build_doc_file_entry(root_dir, failed_pdf_path, "PDF viewer response", "text"))
                capture_notes.append("LADBS PDF viewer did not return a real PDF inside the live session.")

        validation_evidence: List[str] = []
        if any(_match_subject_address(label, identity) for label in diagnostics.get("selected_addresses") or []):
            validation_evidence.append(
                f"LADBS records assessor search selected {', '.join(diagnostics.get('selected_addresses') or [])}."
            )
        if summary_text and _match_subject_address(summary_text, identity):
            validation_evidence.append("Record summary page text repeats the subject address.")
        if _normalize_text(document.get("doc_number")):
            validation_evidence.append(f"Live records result returned document {document.get('doc_number')}.")
        validation_status = "valid_for_subject" if validation_evidence else "reachable_but_unverifiable"

        if summary_url:
            capture_notes.append("LADBS record summary URL was usable only inside the live search session and is not treated as a durable public link.")
        if pdf_url:
            capture_notes.append("The LADBS PDF URL yielded a real PDF only inside the live records session, so the local PDF is the durable artifact.")

        metadata = {
            "doc_number": document.get("doc_number"),
            "doc_type": document.get("doc_type"),
            "sub_type": document.get("sub_type"),
            "doc_date": document.get("doc_date"),
            "description": document.get("description"),
            "record_id": document.get("record_id"),
            "doc_ids": document.get("doc_ids"),
            "image_main_url": image_main_url,
            "summary_url": summary_url,
            "pdf_url": pdf_url,
            "capture_type": "ladbs_record_pdf" if any(item["kind"] == "pdf" for item in local_files) else "ladbs_record_html",
            "validation_status": validation_status,
            "validation_evidence": validation_evidence,
            "capture_notes": capture_notes,
        }
        metadata_path = doc_dir / "metadata.json"
        _write_json(metadata_path, metadata)
        local_files.append(_build_doc_file_entry(root_dir, metadata_path, "Metadata", "json"))

        stable_source_links = []
        if image_main_url:
            stable_source_links.append(
                {
                    "label": "LADBS document viewer source",
                    "url": image_main_url,
                    "stable": True,
                }
            )

        captures.append(
            {
                "id": f"record-{_slugify(doc_number)}",
                "category": "record",
                "title": f"Record {doc_number}",
                "doc_number": document.get("doc_number"),
                "doc_type": document.get("doc_type"),
                "sub_type": document.get("sub_type"),
                "doc_date": document.get("doc_date"),
                "address_label": ", ".join(diagnostics.get("selected_addresses") or []),
                "capture_status": "captured",
                "validation_status": validation_status,
                "validation_evidence": validation_evidence,
                "source_links": stable_source_links,
                "scope_signals": [
                    _normalize_text(document.get("description")),
                    _normalize_text(document.get("doc_type")),
                ],
                "team_mentions": team_mentions,
                "capture_notes": list(dict.fromkeys(capture_notes)),
                "local_files": local_files,
            }
        )

    if not captures:
        records_notes.append("No LADBS record documents were returned during the live assessor search.")

    return captures, records_notes, diagnostics


def _summarize_scope(
    permit_captures: List[Dict[str, Any]],
    record_captures: List[Dict[str, Any]],
    truth: Dict[str, Any],
) -> Dict[str, Any]:
    current_items: List[str] = []
    older_items: List[str] = []
    latest_sold_date = truth.get("last_sold_date")
    sold_dt = _parse_iso_date(latest_sold_date)

    for capture in permit_captures:
        description = next((_clean_scope_text(item) for item in capture.get("scope_signals") or [] if _clean_scope_text(item)), None)
        if not description:
            continue
        doc_dt = _parse_us_date(capture.get("doc_date"))
        item = f"{capture.get('doc_number')}: {description}"
        if sold_dt and doc_dt and doc_dt > sold_dt:
            current_items.append(item)
        else:
            older_items.append(item)

    for capture in record_captures:
        description = next((_clean_scope_text(item) for item in capture.get("scope_signals") or [] if _clean_scope_text(item)), None)
        if description:
            older_items.append(f"{capture.get('doc_number')}: {description}")

    if current_items:
        current_summary = "Current LADBS activity centers on " + "; ".join(current_items[:2]) + "."
    else:
        current_summary = "No active post-sale construction scope was exposed in the live permit detail pages."

    if older_items:
        historical_summary = "Older captured permit/doc history includes " + "; ".join(older_items[:3]) + "."
    else:
        historical_summary = "No older captured permit or record documents were available."

    return {
        "summary": f"{current_summary} {historical_summary}",
        "current_items": current_items,
        "historical_items": older_items,
    }


def _summarize_team(captures: List[Dict[str, Any]]) -> Dict[str, Any]:
    project_side: List[Dict[str, Any]] = []
    city_side: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()

    for capture in captures:
        for mention in capture.get("team_mentions") or []:
            key = (
                _normalize_text(mention.get("role")),
                _normalize_text(mention.get("name")),
                _normalize_text(mention.get("license_number")),
            )
            if key in seen:
                continue
            seen.add(key)
            if mention.get("party_type") == "project_side":
                project_side.append(mention)
            else:
                city_side.append(mention)

    if project_side:
        summary = "Project-side names found in live LADBS permit detail pages: " + "; ".join(
            (
                f"{item['role']}: {item['name']}"
                + (f" (Lic. {item['license_number']})" if item.get("license_number") else "")
            )
            for item in project_side
        ) + "."
    else:
        summary = (
            "No architect, engineer, owner, or applicant names were exposed in the captured LADBS permit or record docs. "
            "The only project-side name found was the contractor if listed below."
        )
    return {
        "summary": summary,
        "project_side": project_side,
        "city_side": city_side,
    }


def _build_cautions(
    truth: Dict[str, Any],
    permit_notes: Iterable[str],
    record_notes: Iterable[str],
    record_captures: List[Dict[str, Any]],
    permit_captures: List[Dict[str, Any]],
) -> List[str]:
    cautions = list(truth.get("cautions") or [])
    cautions.extend(_normalize_text(note) for note in permit_notes if _normalize_text(note))
    cautions.extend(_normalize_text(note) for note in record_notes if _normalize_text(note))

    if not record_captures:
        cautions.append("No LADBS record documents were captured locally for this property.")
    elif len(record_captures) < len(permit_captures):
        cautions.append(
            f"LADBS records coverage is sparse relative to the permit set: {len(record_captures)} record doc(s) versus {len(permit_captures)} permit detail page(s)."
        )

    if not truth.get("prior_sale"):
        cautions.append("Prior developer buy price is not discoverable from the current live Redfin timeline.")

    if not any(
        "certificate of occupancy" in _normalize_text(doc.get("sub_type")).lower()
        or any("certificate of occupancy" in _normalize_text(signal).lower() for signal in doc.get("scope_signals") or [])
        for doc in permit_captures + record_captures
    ):
        cautions.append("No certificate-of-occupancy document or permit field was accessible in this live run.")

    return list(dict.fromkeys(cautions))


def _finalize_doc_pages(root_dir: Path, docs_manifest: List[Dict[str, Any]], package_title: str) -> None:
    for doc in docs_manifest:
        doc_path = root_dir / doc["local_doc_path"]
        local_files = []
        for item in doc.get("local_files") or []:
            path = root_dir / item["path"]
            local_files.append(
                {
                    **item,
                    "href": _relative_href(doc_path, path),
                }
            )

        source_links = [link for link in doc.get("source_links") or [] if link.get("stable")]
        html = _render_template_html(
            "property_package_doc.html",
            package={
                "title": package_title,
                "report_href": _relative_href(doc_path, root_dir / "report.html"),
                "summary_href": _relative_href(doc_path, root_dir / "summary.html"),
                "stylesheet_href": _relative_href(doc_path, root_dir / "_assets" / "css" / "comp.css"),
                "logo_href": _relative_href(doc_path, root_dir / "_assets" / "LG.png"),
            },
            doc={
                **doc,
                "local_files": local_files,
                "source_links": source_links,
            },
        )
        _write_text(doc_path, html)
        doc["local_files"][0] = _build_doc_file_entry(root_dir, doc_path, "Local doc package", "html")


def _build_report_context(
    *,
    output_dir: Path,
    redfin_url: str,
    payload: Dict[str, Any],
    truth: Dict[str, Any],
    identity: Dict[str, Any],
    docs_manifest: List[Dict[str, Any]],
    team_summary: Dict[str, Any],
    scope_summary: Dict[str, Any],
    cautions: List[str],
    permit_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    zimas_url = ((payload.get("zimas_profile") or {}).get("links") or {}).get("profile_url")
    pin = _normalize_text(identity.get("pin"))
    permit_results_url = f"{LADBS_PERMIT_RESULTS_BY_PIN_URL}?pin={requests.utils.quote(pin)}" if pin else None
    top_source_links = [
        {"label": "Redfin source", "url": redfin_url},
        {"label": "ZIMAS parcel page", "url": zimas_url},
        {"label": "LADBS permit results", "url": permit_results_url},
    ]
    top_source_links = [link for link in top_source_links if _normalize_text(link.get("url"))]

    local_actions = [
        {"label": "Open payload", "href": "payload.normalized.json"},
        {"label": "Open live truth JSON", "href": "live_truth.json"},
        {"label": "Open docs manifest", "href": "docs_manifest.json"},
    ]

    return {
        "package_title": "BLDGBIT - Midvale Live Package",
        "stylesheet_href": "_assets/css/comp.css",
        "logo_href": "_assets/LG.png",
        "redfin_url": redfin_url,
        "truth": truth,
        "identity": identity,
        "docs_manifest": docs_manifest,
        "team_summary": team_summary,
        "scope_summary": scope_summary,
        "cautions": cautions,
        "local_actions": local_actions,
        "top_source_links": top_source_links,
        "permit_page_summary": permit_diagnostics.get("page_summary"),
        "permit_count": len([doc for doc in docs_manifest if doc.get("category") == "permit"]),
        "record_count": len([doc for doc in docs_manifest if doc.get("category") == "record"]),
        "doc_capture_count": len(docs_manifest),
        "output_dir": str(output_dir),
    }


def generate_property_package(redfin_url: str, output_dir: Path) -> Dict[str, Any]:
    output_dir = output_dir.resolve()
    _ensure_directory(output_dir)
    _copy_bundle_assets(output_dir)

    payload = run_full_comp_pipeline(redfin_url)
    payload_path = output_dir / "payload.normalized.json"
    _write_json(payload_path, payload)

    truth = _build_redfin_truth(payload)
    identity = _build_identity(payload)
    permit_captures, permit_notes, permit_diagnostics = _capture_permit_documents(payload, output_dir, identity)
    record_captures, record_notes, record_diagnostics = _capture_record_documents(payload, output_dir, identity)

    docs_manifest = permit_captures + record_captures
    for doc in docs_manifest:
        doc_dir = output_dir / "docs" / ("permits" if doc["category"] == "permit" else "records") / _slugify(
            _normalize_text(doc.get("doc_number"))
        )
        doc["local_doc_path"] = _path_from_root(output_dir, doc_dir / "index.html")
        doc["local_files"] = doc.get("local_files") or []
        doc["local_files"].insert(
            0,
            {
                "label": "Local doc package",
                "path": doc["local_doc_path"],
                "kind": "html",
            },
        )

    scope_summary = _summarize_scope(permit_captures, record_captures, truth)
    team_summary = _summarize_team(docs_manifest)
    cautions = _build_cautions(truth, permit_notes, record_notes, record_captures, permit_captures)

    live_truth = {
        "address": truth.get("address"),
        "status": truth.get("status"),
        "last_sold_date": truth.get("last_sold_date"),
        "last_sold_price": truth.get("last_sold_price"),
        "beds": truth.get("beds"),
        "baths": truth.get("baths"),
        "living_area_sf": truth.get("living_area_sf"),
        "lot_size_sf": truth.get("lot_size_sf"),
        "year_built": truth.get("year_built"),
        "property_type": truth.get("property_type"),
        "prior_sale": truth.get("prior_sale"),
        "apn": identity.get("apn"),
        "pin": identity.get("pin"),
        "municipal_address": identity.get("municipal_address"),
        "cautions": cautions,
        "permit_diagnostics": permit_diagnostics,
        "record_diagnostics": record_diagnostics,
    }
    _write_json(output_dir / "live_truth.json", live_truth)
    _write_json(output_dir / "docs_manifest.json", docs_manifest)

    context = _build_report_context(
        output_dir=output_dir,
        redfin_url=redfin_url,
        payload=payload,
        truth=truth,
        identity=identity,
        docs_manifest=docs_manifest,
        team_summary=team_summary,
        scope_summary=scope_summary,
        cautions=cautions,
        permit_diagnostics=permit_diagnostics,
    )
    context["record_diagnostics"] = record_diagnostics

    report_html = _render_template_html("property_package_report.html", page=context)
    summary_html = _render_template_html("property_package_summary.html", page=dict(context))
    _write_text(output_dir / "report.html", report_html)
    _write_text(output_dir / "summary.html", summary_html)

    _finalize_doc_pages(output_dir, docs_manifest, context["package_title"])
    _write_json(output_dir / "docs_manifest.json", docs_manifest)

    old_permit_docs_captured = any(
        (_parse_us_date(doc.get("doc_date")) or datetime.max).year <= 2018 for doc in docs_manifest
    )
    cofo_docs_captured = any(
        "certificate of occupancy" in _normalize_text(doc.get("sub_type")).lower()
        or any("certificate of occupancy" in _normalize_text(signal).lower() for signal in doc.get("scope_signals") or [])
        for doc in docs_manifest
    )

    return {
        "output_dir": str(output_dir),
        "payload_path": _path_from_root(output_dir, payload_path),
        "summary_path": "summary.html",
        "report_path": "report.html",
        "docs_manifest_path": "docs_manifest.json",
        "permit_count": len(permit_captures),
        "record_count": len(record_captures),
        "captured_doc_count": len(docs_manifest),
        "old_permit_docs_captured": old_permit_docs_captured,
        "cofo_docs_captured": cofo_docs_captured,
        "truth": truth,
        "identity": identity,
        "team_summary": team_summary,
        "scope_summary": scope_summary,
        "cautions": cautions,
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    result = generate_property_package(args.redfin_url, Path(args.output_dir))
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Wrote property package to {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
