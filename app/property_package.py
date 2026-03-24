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
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import render_template

from app.ladbs_records_client import (
    LADBS_IMAGE_LIST_URL,
    LADBS_RECORDS_BASE_URL,
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
NAVIGATELA_REPORTS_URL = "https://navigatela.lacity.org/navigatela/reports/dc_parcel_reports.cfm"
ZIMAS_DISPLAY_REPORT_URL = "https://zimas.lacity.org/displayreport.aspx"
ZIMAS_RUN_REPORT_URL = "https://zimas.lacity.org/RunReport.aspx"
LADBS_PARCEL_PROFILE_BAS_URL = urljoin(LADBS_PERMIT_REPORT_BASE_URL, "ParcelProfileDetail2")
HISTORIC_TEAM_YEARS = 5


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


def _extract_zip_code(address: Optional[str]) -> Optional[str]:
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", str(address or ""))
    return match.group(1) if match else None


def _normalize_pin_parts(pin: Optional[str], separator: str) -> Optional[str]:
    tokens = re.findall(r"[A-Z0-9]+", str(pin or "").upper())
    if len(tokens) >= 2:
        return f"{tokens[0]}{separator}{tokens[1]}"
    return _normalize_text(pin) or None


def _historic_cutoff_date() -> datetime:
    now = datetime.now()
    try:
        return now.replace(year=now.year - HISTORIC_TEAM_YEARS)
    except ValueError:
        return now.replace(month=2, day=28, year=now.year - HISTORIC_TEAM_YEARS)


def _parse_doc_capture_date(value: Optional[str]) -> Optional[datetime]:
    return _parse_iso_date(value) or _parse_us_date(value)


def _is_historic_capture(capture: Dict[str, Any]) -> bool:
    doc_dt = _parse_doc_capture_date(capture.get("doc_date"))
    return bool(doc_dt and doc_dt <= _historic_cutoff_date())


def _is_certificate_doc(capture: Dict[str, Any]) -> bool:
    text = " ".join(
        _normalize_text(value)
        for value in [
            capture.get("doc_type"),
            capture.get("sub_type"),
            capture.get("title"),
            *(capture.get("scope_signals") or []),
        ]
        if _normalize_text(value)
    ).lower()
    return "certificate of occupancy" in text or "occupancy" in text


def _doc_group_key(capture: Dict[str, Any]) -> str:
    if capture.get("category") == "parcel":
        return "parcel_zoning"
    if _is_certificate_doc(capture):
        return "certificate_of_occupancy"
    if capture.get("category") == "permit" and _is_historic_capture(capture):
        return "historic_permits"
    if capture.get("category") == "permit":
        return "current_permits"
    return "other_records"


def _doc_group_label(group_key: str) -> str:
    labels = {
        "parcel_zoning": "Parcel / zoning",
        "current_permits": "Current permits",
        "historic_permits": "Historic permits",
        "certificate_of_occupancy": "Certificates of Occupancy",
        "other_records": "Other LADBS records",
    }
    return labels.get(group_key, group_key.replace("_", " ").title())


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
    cleaned_name = _normalize_text(name)
    cleaned_name = re.split(r"\s*;\s*Lic\.?\s*No\.?:", cleaned_name, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ;,")
    if not cleaned_name:
        cleaned_name = _normalize_text(name)
    item = {
        "role": role,
        "name": cleaned_name,
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


def _run_records_search_attempt(
    *,
    search_type: str,
    button_name: str,
    extra_fields: Dict[str, str],
    subject_address: Optional[str],
    attempt_label: str,
) -> Dict[str, Any]:
    session = _build_records_session()
    search_url = urljoin(LADBS_RECORDS_BASE_URL, f"DocumentSearch.aspx?SearchType={search_type}")
    session.get(LADBS_RECORDS_BOOTSTRAP_URL, timeout=45, allow_redirects=True)
    search_page = session.get(search_url, timeout=45)
    search_page.raise_for_status()
    form = BeautifulSoup(search_page.text or "", "lxml").find("form")
    if not form:
        raise RuntimeError(f"LADBS records {attempt_label} page did not contain a form.")

    search_payload = _collect_form_payload(
        form,
        clicked_button_name=button_name,
        clicked_button_value="Search",
        extra_fields=extra_fields,
    )
    results_response = session.post(search_url, data=search_payload, timeout=45)
    results_response.raise_for_status()
    results_html = results_response.text or ""
    candidate_labels: List[str] = []
    selected_labels: List[str] = []

    candidates = _parse_address_candidates(results_html)
    if candidates:
        candidate_labels = [candidate.get("label") or "" for candidate in candidates]
        selected_candidates = _select_address_candidates(candidates, subject_address)
        selected_labels = [candidate.get("label") or "" for candidate in selected_candidates]
        continue_form = BeautifulSoup(results_html, "lxml").find("form")
        if continue_form and selected_candidates:
            continue_payload = list(
                _collect_form_payload(
                    continue_form,
                    clicked_button_name="btnNext2",
                    clicked_button_value="Continue",
                ).items()
            )
            for candidate in selected_candidates:
                continue_payload.append((candidate["checkbox_name"], candidate["value"]))
            continued_response = session.post(search_url, data=continue_payload, timeout=45)
            continued_response.raise_for_status()
            results_html = continued_response.text or ""

    parsed = _parse_records_results(results_html)
    if not selected_labels:
        selected_labels = [
            label
            for label in parsed.get("preselected_addresses") or []
            if label and re.search(r"\d", label)
        ]
    if not selected_labels and (parsed.get("documents") or []):
        selected_labels = [
            _normalize_text(extra_fields.get("Address$txtAddress") or subject_address)
        ]
        selected_labels = [label for label in selected_labels if label]

    return {
        "attempt": attempt_label,
        "search_type": search_type,
        "search_url": search_url,
        "criteria": parsed.get("search_criteria"),
        "page_summary": parsed.get("page_summary"),
        "candidate_labels": candidate_labels,
        "selected_addresses": selected_labels,
        "documents": parsed.get("documents") or [],
        "session": session,
        "extra_fields": dict(extra_fields),
    }


def _capture_parcel_documents(
    payload: Dict[str, Any],
    root_dir: Path,
    identity: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    pin_double = _normalize_pin_parts(identity.get("pin"), "  ")
    pin_hyphen = _normalize_pin_parts(identity.get("pin"), "-")
    zip_code = _extract_zip_code(identity.get("subject_address"))
    municipal_address = _normalize_text(identity.get("municipal_address"))
    zimas_url = ((payload.get("zimas_profile") or {}).get("links") or {}).get("profile_url")
    if not pin_double or not pin_hyphen:
        return [], ["Could not derive a valid PIN for parcel-profile capture."], {}

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            )
        }
    )

    available_url = f"{NAVIGATELA_REPORTS_URL}?PK={requests.utils.quote(pin_hyphen)}"
    available_response = session.get(available_url, timeout=60, allow_redirects=True)
    available_response.raise_for_status()
    available_html = available_response.text or ""
    available_text = _extract_html_text(available_html)
    available_soup = BeautifulSoup(available_html, "lxml")
    available_links = {
        _normalize_text(anchor.get_text(" ", strip=True)): anchor.get("href")
        for anchor in available_soup.find_all("a", href=True)
    }

    parcel_dir = _ensure_directory(root_dir / "docs" / "parcel")
    diagnostics: Dict[str, Any] = {
        "available_reports_url": available_response.url,
        "available_links": available_links,
    }
    notes: List[str] = []
    captures: List[Dict[str, Any]] = []

    available_html_path = parcel_dir / "navigatela_available_reports.source.html"
    available_text_path = parcel_dir / "navigatela_available_reports.txt"
    _write_text(available_html_path, available_html)
    _write_text(available_text_path, available_text)

    now = datetime.now()
    display_url = (
        f"{ZIMAS_DISPLAY_REPORT_URL}?pin={requests.utils.quote(pin_double)}"
    )
    session.get(display_url, timeout=60, allow_redirects=True).raise_for_status()
    report_address = f"{municipal_address} {zip_code}".strip() if zip_code else municipal_address
    run_report_url = (
        f"{ZIMAS_RUN_REPORT_URL}?type=ParcelOfficial"
        f"&pin={requests.utils.quote(pin_double)}"
        f"&apn=all"
        f"&cases=true"
        f"&address={requests.utils.quote(report_address)}"
        f"&timestamp={requests.utils.quote(now.isoformat())}"
    )
    report_response = session.post(run_report_url, data={}, timeout=120, allow_redirects=True)
    report_response.raise_for_status()
    report_target = _normalize_text(report_response.text)
    report_generation_path = parcel_dir / "navigatela_report_generation.txt"
    _write_text(report_generation_path, report_target or "")
    diagnostics["report_flow_url"] = display_url
    diagnostics["run_report_url"] = run_report_url
    diagnostics["run_report_response"] = report_target

    parcel_profile_local_files = [
        _build_doc_file_entry(root_dir, available_html_path, "Available reports snapshot", "html"),
        _build_doc_file_entry(root_dir, available_text_path, "Available reports text", "text"),
        _build_doc_file_entry(root_dir, report_generation_path, "Report generation response", "text"),
    ]
    parcel_profile_notes: List[str] = []
    parcel_profile_source_links = [
        {"label": "NavigateLA reports page", "url": available_response.url, "stable": True},
    ]
    validation_evidence = []
    if municipal_address and municipal_address in available_text:
        validation_evidence.append(f"NavigateLA reports page lists {municipal_address}.")
    if _normalize_text(identity.get("apn")) and _normalize_text(identity.get("apn")) in available_text:
        validation_evidence.append(f"NavigateLA reports page lists APN {_normalize_text(identity.get('apn'))}.")
    if pin_hyphen and pin_hyphen in available_text:
        validation_evidence.append(f"NavigateLA reports page lists PIN {pin_hyphen}.")

    navigate_pdf_captured = False
    if report_target.lower().endswith(".pdf"):
        pdf_url = urljoin("https://zimas.lacity.org/", report_target.lstrip("/"))
        pdf_response = session.get(pdf_url, timeout=120, allow_redirects=True)
        pdf_response.raise_for_status()
        if pdf_response.content.startswith(b"%PDF"):
            pdf_path = parcel_dir / "navigatela_parcel_profile.pdf"
            _write_bytes(pdf_path, pdf_response.content)
            parcel_profile_local_files.insert(
                0,
                _build_doc_file_entry(root_dir, pdf_path, "Captured parcel profile PDF", "pdf"),
            )
            pdf_text, pdf_text_note = _extract_pdf_text(pdf_response.content)
            if pdf_text:
                pdf_text_path = parcel_dir / "navigatela_parcel_profile.txt"
                _write_text(pdf_text_path, pdf_text)
                parcel_profile_local_files.append(
                    _build_doc_file_entry(root_dir, pdf_text_path, "Parcel profile text", "text")
                )
            elif pdf_text_note:
                parcel_profile_notes.append(pdf_text_note)
            diagnostics["navigatela_pdf_url"] = pdf_response.url
            parcel_profile_source_links.append(
                {"label": "Generated parcel profile source", "url": pdf_response.url, "stable": False}
            )
            navigate_pdf_captured = True
        else:
            parcel_profile_notes.append("NavigateLA parcel report flow returned a path, but the fetched artifact was not a PDF.")
    else:
        parcel_profile_notes.append("NavigateLA parcel profile PDF capture did not return a direct PDF path.")

    if not navigate_pdf_captured and zimas_url:
        parcel_profile_notes.append("Fell back to the ZIMAS parcel page because the NavigateLA parcel PDF was unavailable.")
        parcel_profile_source_links.append({"label": "ZIMAS parcel page fallback", "url": zimas_url, "stable": True})

    parcel_metadata_path = parcel_dir / "navigatela_parcel_profile.metadata.json"
    _write_json(
        parcel_metadata_path,
        {
            "pin": pin_double,
            "pin_hyphen": pin_hyphen,
            "apn": identity.get("apn"),
            "municipal_address": municipal_address,
            "available_reports_url": available_response.url,
            "run_report_url": run_report_url,
            "run_report_response": report_target,
            "navigate_pdf_captured": navigate_pdf_captured,
            "diagnostics": diagnostics,
            "capture_notes": parcel_profile_notes,
        },
    )
    parcel_profile_local_files.append(
        _build_doc_file_entry(root_dir, parcel_metadata_path, "Metadata", "json")
    )
    captures.append(
        {
            "id": "parcel-navigatela-profile",
            "category": "parcel",
            "title": "NavigateLA parcel profile",
            "doc_number": pin_hyphen,
            "doc_type": "Parcel profile report",
            "sub_type": "NavigateLA / ZIMAS DCP",
            "doc_date": f"{now.month}/{now.day}/{now.year}",
            "address_label": municipal_address,
            "capture_status": "captured" if navigate_pdf_captured else "partial",
            "validation_status": "valid_for_subject" if validation_evidence else "reachable_but_unverifiable",
            "validation_evidence": validation_evidence,
            "source_links": parcel_profile_source_links,
            "scope_signals": [
                "Parcel profile report flow",
                _normalize_text(identity.get("zoning")),
                _normalize_text(identity.get("general_plan_land_use")),
            ],
            "team_mentions": [],
            "capture_notes": list(dict.fromkeys(parcel_profile_notes)),
            "local_files": parcel_profile_local_files,
            "primary_local_file": "Captured parcel profile PDF" if navigate_pdf_captured else None,
            "navigate_pdf_captured": navigate_pdf_captured,
        }
    )

    bas_url = f"{LADBS_PARCEL_PROFILE_BAS_URL}?pin={requests.utils.quote(pin_hyphen)}"
    bas_response = session.get(bas_url, timeout=60, allow_redirects=True)
    bas_response.raise_for_status()
    bas_html = bas_response.text or ""
    bas_text = _extract_html_text(bas_html)
    bas_html_path = parcel_dir / "ladbs_parcel_profile.source.html"
    bas_text_path = parcel_dir / "ladbs_parcel_profile.txt"
    _write_text(bas_html_path, bas_html)
    _write_text(bas_text_path, bas_text)
    bas_notes: List[str] = []
    bas_validation = []
    if municipal_address and municipal_address in bas_text:
        bas_validation.append(f"BAS parcel profile repeats {municipal_address}.")
    if pin_double and pin_double in bas_text:
        bas_validation.append(f"BAS parcel profile repeats PIN {pin_double}.")
    if _normalize_text(identity.get("zoning")) and _normalize_text(identity.get("zoning")) in bas_text:
        bas_validation.append(f"BAS parcel profile repeats zoning {_normalize_text(identity.get('zoning'))}.")
    bas_metadata_path = parcel_dir / "ladbs_parcel_profile.metadata.json"
    _write_json(
        bas_metadata_path,
        {
            "pin_hyphen": pin_hyphen,
            "source_url": bas_response.url,
            "capture_notes": bas_notes,
        },
    )
    captures.append(
        {
            "id": "parcel-bas-profile",
            "category": "parcel",
            "title": "LADBS parcel profile",
            "doc_number": pin_hyphen,
            "doc_type": "Parcel profile detail",
            "sub_type": "BAS",
            "doc_date": f"{now.month}/{now.day}/{now.year}",
            "address_label": municipal_address,
            "capture_status": "captured",
            "validation_status": "valid_for_subject" if bas_validation else "reachable_but_unverifiable",
            "validation_evidence": bas_validation,
            "source_links": [{"label": "BAS parcel profile source", "url": bas_response.url, "stable": True}],
            "scope_signals": [
                _normalize_text(identity.get("zoning")),
                _normalize_text(identity.get("general_plan_land_use")),
                _normalize_text(identity.get("community_plan_area")),
            ],
            "team_mentions": [],
            "capture_notes": bas_notes,
            "local_files": [
                _build_doc_file_entry(root_dir, bas_html_path, "Parcel profile snapshot", "html"),
                _build_doc_file_entry(root_dir, bas_text_path, "Parcel profile text", "text"),
                _build_doc_file_entry(root_dir, bas_metadata_path, "Metadata", "json"),
            ],
        }
    )

    cadastral_href = available_links.get("Cadastral Map")
    if cadastral_href:
        cadastral_response = session.get(cadastral_href, timeout=120, allow_redirects=True)
        cadastral_response.raise_for_status()
        cadastral_pdf_path = parcel_dir / "cadastral_map.pdf"
        _write_bytes(cadastral_pdf_path, cadastral_response.content)
        cadastral_notes: List[str] = []
        _, cadastral_pdf_note = _extract_pdf_text(cadastral_response.content)
        if cadastral_pdf_note:
            cadastral_notes.append(cadastral_pdf_note)
        cadastral_metadata_path = parcel_dir / "cadastral_map.metadata.json"
        _write_json(
            cadastral_metadata_path,
            {
                "source_url": cadastral_response.url,
                "pin_hyphen": pin_hyphen,
            },
        )
        captures.append(
            {
                "id": "parcel-cadastral-map",
                "category": "parcel",
                "title": "NavigateLA cadastral map",
                "doc_number": pin_hyphen,
                "doc_type": "Cadastral map",
                "sub_type": "NavigateLA",
                "doc_date": f"{now.month}/{now.day}/{now.year}",
                "address_label": municipal_address,
                "capture_status": "captured",
                "validation_status": "valid_for_subject" if validation_evidence else "reachable_but_unverifiable",
                "validation_evidence": list(validation_evidence),
                "source_links": [{"label": "Cadastral map source", "url": cadastral_response.url, "stable": True}],
                "scope_signals": ["Parcel map"],
                "team_mentions": [],
                "capture_notes": cadastral_notes,
                "local_files": [
                    _build_doc_file_entry(root_dir, cadastral_pdf_path, "Captured cadastral map PDF", "pdf"),
                    _build_doc_file_entry(root_dir, cadastral_metadata_path, "Metadata", "json"),
                ],
            }
        )

    diagnostics["navigate_pdf_captured"] = navigate_pdf_captured
    return captures, notes, diagnostics


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


def _capture_single_record_document(
    *,
    session: requests.Session,
    document: Dict[str, Any],
    root_dir: Path,
    identity: Dict[str, Any],
    selected_addresses: List[str],
    discovery_paths: List[str],
) -> Dict[str, Any]:
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
    if any(_match_subject_address(label, identity) for label in selected_addresses):
        validation_evidence.append(
            f"LADBS records search selected {', '.join(selected_addresses)}."
        )
    if summary_text and _match_subject_address(summary_text, identity):
        validation_evidence.append("Record summary page text repeats the subject address.")
    if _normalize_text(document.get("doc_number")):
        validation_evidence.append(f"Live records result returned document {document.get('doc_number')}.")
    validation_status = "valid_for_subject" if validation_evidence else "reachable_but_unverifiable"

    if summary_url:
        capture_notes.append(
            "LADBS record summary URL was usable only inside the live search session and is not treated as a durable public link."
        )
    if pdf_url:
        capture_notes.append(
            "The LADBS PDF URL yielded a real PDF only inside the live records session, so the local PDF is the durable artifact."
        )
    if not document.get("has_digital_image"):
        capture_notes.append("LADBS listed the document, but no digital image link was exposed in IDIS.")

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
        "discovery_paths": discovery_paths,
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

    return {
        "id": f"record-{_slugify(doc_number)}",
        "category": "record",
        "title": f"Record {doc_number}",
        "doc_number": document.get("doc_number"),
        "doc_type": document.get("doc_type"),
        "sub_type": document.get("sub_type"),
        "doc_date": document.get("doc_date"),
        "address_label": ", ".join(selected_addresses),
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
        "discovery_paths": discovery_paths,
    }


def _capture_record_documents(
    payload: Dict[str, Any],
    root_dir: Path,
    identity: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    apn = _normalize_text(identity.get("apn"))
    subject_address = identity.get("subject_address") or identity.get("municipal_address")
    municipal_address = _normalize_text(identity.get("municipal_address"))
    records_notes: List[str] = []
    diagnostics: Dict[str, Any] = {"search_attempts": []}

    apn_parts = split_apn(apn)
    if not apn_parts:
        return [], [f"Could not derive a valid LADBS records APN from {apn!r}."], diagnostics

    attempts: List[Dict[str, Any]] = []
    assessor_attempt = _run_records_search_attempt(
        search_type="DCMT_ASSR",
        button_name="btnSearchAssessor",
        extra_fields={
            "Assessor$txtAssessorNoBook": apn_parts["book"],
            "Assessor$txtAssessorNoPage": apn_parts["page"],
            "Assessor$txtAssessorNoParcel": apn_parts["parcel"],
        },
        subject_address=subject_address,
        attempt_label="assessor_apn",
    )
    attempts.append(assessor_attempt)

    if municipal_address:
        attempts.append(
            _run_records_search_attempt(
                search_type="DCMT_ADDR",
                button_name="btnSearchAddress",
                extra_fields={"Address$txtAddress": municipal_address},
                subject_address=subject_address,
                attempt_label="address_exact",
            )
        )

        tokens = municipal_address.split()
        broad_tokens: List[str] = []
        if tokens:
            broad_tokens.append(tokens[0])
            for token in tokens[1:]:
                if token in {"N", "S", "E", "W"}:
                    continue
                if token in {"AVE", "AVENUE", "ST", "STREET", "BLVD", "ROAD", "RD", "DR", "DRIVE", "LN", "LANE", "PL", "PLACE", "CT", "COURT"}:
                    continue
                if re.fullmatch(r"\d{5}", token):
                    continue
                broad_tokens.append(token)
                break
        broad_query = " ".join(broad_tokens)
        if broad_query and broad_query != municipal_address:
            attempts.append(
                _run_records_search_attempt(
                    search_type="DCMT_ADDR",
                    button_name="btnSearchAddress",
                    extra_fields={"Address$txtAddress": broad_query, "HistAddr": "True"},
                    subject_address=subject_address,
                    attempt_label="address_history",
                )
            )

    permit_numbers = [
        _normalize_text(permit.get("permit_number"))
        for permit in (payload.get("ladbs") or {}).get("permits") or []
        if _normalize_text(permit.get("permit_number"))
    ]
    for permit_number in permit_numbers:
        attempts.append(
            _run_records_search_attempt(
                search_type="DCMT_DOCNO",
                button_name="btnSearchDocNumber",
                extra_fields={"DocumentNumber$txtDocNumber": permit_number},
                subject_address=subject_address,
                attempt_label=f"doc_number:{permit_number}",
            )
        )

    chosen_documents: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    discovery_paths: Dict[str, List[str]] = {}
    for attempt in attempts:
        documents = attempt.get("documents") or []
        diagnostics["search_attempts"].append(
            {
                "attempt": attempt["attempt"],
                "criteria": attempt.get("criteria"),
                "result_count": len(documents),
                "selected_addresses": attempt.get("selected_addresses") or [],
                "candidate_labels": attempt.get("candidate_labels") or [],
                "search_type": attempt.get("search_type"),
                "query": attempt.get("extra_fields"),
            }
        )
        for document in documents:
            doc_number = _normalize_text(document.get("doc_number")) or "record"
            discovery_paths.setdefault(doc_number, [])
            discovery_paths[doc_number].append(attempt["attempt"])
            if doc_number not in chosen_documents:
                chosen_documents[doc_number] = (attempt, document)

    diagnostics["selection_candidates"] = assessor_attempt.get("candidate_labels") or []
    diagnostics["selected_addresses"] = assessor_attempt.get("selected_addresses") or []
    diagnostics["search_criteria"] = assessor_attempt.get("criteria")
    diagnostics["page_summary"] = assessor_attempt.get("page_summary")

    captures: List[Dict[str, Any]] = []
    for doc_number, (attempt, document) in chosen_documents.items():
        captures.append(
            _capture_single_record_document(
                session=attempt["session"],
                document=document,
                root_dir=root_dir,
                identity=identity,
                selected_addresses=attempt.get("selected_addresses") or [],
                discovery_paths=sorted(set(discovery_paths.get(doc_number) or [])),
            )
        )

    if not captures:
        records_notes.append("No LADBS record documents were returned across the live assessor, address, and document-number searches.")

    missed_docno = [
        attempt["attempt"].split(":", 1)[1]
        for attempt in attempts
        if str(attempt.get("attempt", "")).startswith("doc_number:") and not (attempt.get("documents") or [])
    ]
    if missed_docno:
        records_notes.append(
            "Document-number searches for permit(s) "
            + ", ".join(missed_docno)
            + " returned no additional IDIS record docs."
        )

    if not any(_is_certificate_doc(capture) for capture in captures):
        records_notes.append(
            "Expanded LADBS assessor, address, and document-number searches did not surface any certificate-of-occupancy record."
        )

    unique_doc_numbers = sorted(chosen_documents.keys())
    if unique_doc_numbers:
        records_notes.append(
            "Expanded LADBS searches converged on the following record doc(s): " + ", ".join(unique_doc_numbers) + "."
        )

    return captures, list(dict.fromkeys(records_notes)), diagnostics


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
    buckets = {
        "current": {"project_side": [], "city_side": []},
        "historic": {"project_side": [], "city_side": []},
    }
    seen: set[Tuple[str, str, str, str]] = set()

    for capture in captures:
        bucket_key = "historic" if _is_historic_capture(capture) else "current"
        for mention in capture.get("team_mentions") or []:
            key = (
                bucket_key,
                _normalize_text(mention.get("role")),
                _normalize_text(mention.get("name")),
                _normalize_text(mention.get("license_number")),
            )
            if key in seen:
                continue
            seen.add(key)
            enriched = {
                **mention,
                "source_doc": capture.get("doc_number"),
                "source_title": capture.get("title"),
            }
            if mention.get("party_type") == "project_side":
                buckets[bucket_key]["project_side"].append(enriched)
            else:
                buckets[bucket_key]["city_side"].append(enriched)

    current_project = buckets["current"]["project_side"]
    historic_project = buckets["historic"]["project_side"]

    if current_project:
        current_summary = "Recent/current team names found in non-historic docs: " + "; ".join(
            (
                f"{item['role']}: {item['name']}"
                + (f" (Lic. {item['license_number']})" if item.get("license_number") else "")
            )
            for item in current_project
        ) + "."
    elif buckets["current"]["city_side"]:
        current_summary = "No recent/current project-side names were exposed. The only current named parties are LADBS reviewers/approvers shown below."
    else:
        current_summary = (
            "No recent/current project-side architect, engineer, owner, applicant, or contractor names were exposed in the captured non-historic docs."
        )

    if historic_project:
        historic_summary = "Historic team names from 5+ year-old docs: " + "; ".join(
            (
                f"{item['role']}: {item['name']}"
                + (f" (Lic. {item['license_number']})" if item.get("license_number") else "")
            )
            for item in historic_project
        ) + "."
        if buckets["historic"]["city_side"]:
            historic_summary += " Historic city-side names are listed separately below."
    else:
        historic_summary = "No project-side names were exposed in the captured 5+ year-old docs."

    return {
        "summary": current_summary,
        "current_summary": current_summary,
        "historic_summary": historic_summary,
        "current": buckets["current"],
        "historic": buckets["historic"],
    }


def _build_chronology(truth: Dict[str, Any], docs_manifest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    latest_sale = truth.get("latest_sale") or {}
    if latest_sale.get("date") or latest_sale.get("price"):
        items.append(
            {
                "sort_date": _parse_iso_date(latest_sale.get("date")) or datetime.min,
                "date_display": _format_date(latest_sale.get("date")),
                "label": "Redfin sale",
                "detail": f"Sold for {_format_money(latest_sale.get('price'))}.",
                "kind": "transaction",
            }
        )

    sorted_docs = sorted(
        [doc for doc in docs_manifest if doc.get("category") in {"permit", "record"}],
        key=lambda doc: _parse_doc_capture_date(doc.get("doc_date")) or datetime.min,
        reverse=True,
    )
    for doc in sorted_docs:
        description = next(
            (
                _clean_scope_text(value)
                for value in doc.get("scope_signals") or []
                if _clean_scope_text(value)
            ),
            None,
        ) or _normalize_text(doc.get("doc_type"))
        label = doc.get("title") or _normalize_text(doc.get("doc_number")) or "Document"
        items.append(
            {
                "sort_date": _parse_doc_capture_date(doc.get("doc_date")) or datetime.min,
                "date_display": _format_date(doc.get("doc_date")),
                "label": label,
                "detail": description,
                "kind": doc.get("category") or "document",
            }
        )

    items.sort(key=lambda item: item.get("sort_date") or datetime.min, reverse=True)
    deduped: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for item in items:
        key = (item["date_display"], item["label"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "date_display": item["date_display"],
                "label": item["label"],
                "detail": item["detail"],
                "kind": item["kind"],
            }
        )
    return deduped[:8]


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
                "property_href": _relative_href(doc_path, root_dir / "property.html"),
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


def _build_property_context(
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
    record_diagnostics: Dict[str, Any],
    parcel_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    zimas_url = ((payload.get("zimas_profile") or {}).get("links") or {}).get("profile_url")
    pin = _normalize_pin_parts(identity.get("pin"), " ")
    permit_results_url = f"{LADBS_PERMIT_RESULTS_BY_PIN_URL}?pin={requests.utils.quote(pin)}" if pin else None
    parcel_doc = next((doc for doc in docs_manifest if doc.get("id") == "parcel-navigatela-profile"), None)
    bas_doc = next((doc for doc in docs_manifest if doc.get("id") == "parcel-bas-profile"), None)

    source_links = [{"label": "Redfin live listing", "url": redfin_url}]
    if parcel_doc:
        navigate_source = next(
            (
                link
                for link in parcel_doc.get("source_links") or []
                if _normalize_text(link.get("label")) == "NavigateLA reports page"
            ),
            None,
        )
        if navigate_source:
            source_links.append({"label": "NavigateLA reports page", "url": navigate_source.get("url")})
    if bas_doc:
        bas_source = next(
            (
                link
                for link in bas_doc.get("source_links") or []
                if _normalize_text(link.get("url"))
            ),
            None,
        )
        if bas_source:
            source_links.append({"label": "BAS parcel profile", "url": bas_source.get("url")})
    if permit_results_url:
        source_links.append({"label": "LADBS permit results by PIN", "url": permit_results_url})
    if not parcel_diagnostics.get("navigate_pdf_captured") and _normalize_text(zimas_url):
        source_links.append({"label": "ZIMAS parcel page fallback", "url": zimas_url})
    source_links = [link for link in source_links if _normalize_text(link.get("url"))]

    audit_links = [
        {"label": "Open payload", "href": "payload.normalized.json"},
        {"label": "Open live truth JSON", "href": "live_truth.json"},
        {"label": "Open docs manifest", "href": "docs_manifest.json"},
    ]

    grouped_docs: List[Dict[str, Any]] = []
    for group_key in [
        "parcel_zoning",
        "current_permits",
        "historic_permits",
        "certificate_of_occupancy",
        "other_records",
    ]:
        group_docs = [doc for doc in docs_manifest if _doc_group_key(doc) == group_key]
        grouped_docs.append(
            {
                "key": group_key,
                "label": _doc_group_label(group_key),
                "docs": group_docs,
                "count": len(group_docs),
            }
        )

    primary_parcel_local = None
    if parcel_doc:
        primary_parcel_local = next(
            (
                file
                for file in parcel_doc.get("local_files") or []
                if file.get("label") == "Captured parcel profile PDF"
            ),
            None,
            )

    chronology = _build_chronology(truth, docs_manifest)

    historical_attempts = record_diagnostics.get("search_attempts") or []
    search_summary = []
    for attempt in historical_attempts:
        attempt_name = str(attempt.get("attempt") or "").replace("_", " ")
        result_count = attempt.get("result_count")
        if result_count:
            search_summary.append(
                f"{attempt_name}: {result_count} result(s)"
                + (
                    f" for {', '.join(attempt.get('selected_addresses') or [])}."
                    if attempt.get("selected_addresses")
                    else "."
                )
            )
        else:
            query = attempt.get("query") or {}
            query_value = next((value for value in query.values() if _normalize_text(value)), None)
            search_summary.append(
                f"{attempt_name}: no record docs surfaced"
                + (f" for {query_value}." if query_value else ".")
            )

    return {
        "package_title": f"BLDGBIT | ParcelIQ - {_normalize_text(truth.get('address')) or 'Property Package'}",
        "stylesheet_href": "_assets/css/comp.css",
        "logo_href": "_assets/LG.png",
        "brand_name": "BLDGBIT | ParcelIQ",
        "brand_tagline": "Evidence-backed property intelligence",
        "hero_summary": (
            "One compact ParcelIQ property package with live truth locking, durable local parcel/doc capture, "
            "and explicit cautions wherever Redfin or LADBS stayed incomplete or inconsistent."
        ),
        "redfin_url": redfin_url,
        "truth": truth,
        "identity": identity,
        "docs_manifest": docs_manifest,
        "grouped_docs": grouped_docs,
        "team_summary": team_summary,
        "scope_summary": scope_summary,
        "chronology": chronology,
        "cautions": cautions,
        "audit_links": audit_links,
        "source_links": source_links,
        "primary_parcel_local": primary_parcel_local,
        "navigate_pdf_captured": bool(parcel_diagnostics.get("navigate_pdf_captured")),
        "search_summary": search_summary,
        "parcel_diagnostics": parcel_diagnostics,
        "permit_page_summary": permit_diagnostics.get("page_summary"),
        "record_diagnostics": record_diagnostics,
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
    parcel_captures, parcel_notes, parcel_diagnostics = _capture_parcel_documents(payload, output_dir, identity)
    permit_captures, permit_notes, permit_diagnostics = _capture_permit_documents(payload, output_dir, identity)
    record_captures, record_notes, record_diagnostics = _capture_record_documents(payload, output_dir, identity)

    docs_manifest = parcel_captures + permit_captures + record_captures
    for doc in docs_manifest:
        if doc["category"] == "permit":
            doc_dir = output_dir / "docs" / "permits" / _slugify(_normalize_text(doc.get("doc_number")))
        elif doc["category"] == "record":
            doc_dir = output_dir / "docs" / "records" / _slugify(_normalize_text(doc.get("doc_number")))
        else:
            doc_dir = output_dir / "docs" / "parcel" / _slugify(
                _normalize_text(doc.get("id") or doc.get("doc_number") or doc.get("title"))
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
    cautions = _build_cautions(
        truth,
        parcel_notes + permit_notes,
        record_notes,
        record_captures,
        permit_captures,
    )

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
        "parcel_diagnostics": parcel_diagnostics,
        "permit_diagnostics": permit_diagnostics,
        "record_diagnostics": record_diagnostics,
    }
    _write_json(output_dir / "live_truth.json", live_truth)
    _write_json(output_dir / "docs_manifest.json", docs_manifest)

    context = _build_property_context(
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
        record_diagnostics=record_diagnostics,
        parcel_diagnostics=parcel_diagnostics,
    )
    property_html = _render_template_html("property_package_primary.html", page=context)
    compat_context = {
        "package_title": context["package_title"],
        "stylesheet_href": context["stylesheet_href"],
        "logo_href": context["logo_href"],
        "truth": truth,
        "primary_href": "property.html",
    }
    report_html = _render_template_html("property_package_compat.html", page={**compat_context, "page_kind": "Report"})
    summary_html = _render_template_html("property_package_compat.html", page={**compat_context, "page_kind": "Summary"})
    _write_text(output_dir / "property.html", property_html)
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
        "property_path": "property.html",
        "summary_path": "summary.html",
        "report_path": "report.html",
        "docs_manifest_path": "docs_manifest.json",
        "permit_count": len(permit_captures),
        "record_count": len(record_captures),
        "captured_doc_count": len(docs_manifest),
        "navigate_pdf_captured": bool(parcel_diagnostics.get("navigate_pdf_captured")),
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
