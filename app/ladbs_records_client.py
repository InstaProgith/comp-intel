from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin
import os
import re

import requests
from bs4 import BeautifulSoup

from app.zimas_client import get_zimas_profile

LADBS_RECORDS_BASE_URL = "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/"
LADBS_RECORDS_BOOTSTRAP_URL = urljoin(LADBS_RECORDS_BASE_URL, "DefaultCustom.aspx")
LADBS_RECORDS_SEARCH_URL = urljoin(LADBS_RECORDS_BASE_URL, "DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW")
LADBS_RECORDS_SELECTION_URL = "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearchSelection.aspx"
LADBS_IMAGE_MAIN_URL = urljoin(LADBS_RECORDS_BASE_URL, "ImageMain.aspx")
LADBS_IMAGE_LIST_URL = urljoin(LADBS_RECORDS_BASE_URL, "ImageList.aspx")
LADBS_PDF_VIEWER_URL = urljoin(LADBS_RECORDS_BASE_URL, "StPdfViewer.aspx")
REQUEST_TIMEOUT_SECONDS = 45
DOC_LINK_LIMIT = max(1, int(os.environ.get("LADBS_RECORDS_MAX_PDF_RESOLUTIONS", "20")))
DOC_REPORT_CALL_PATTERN = re.compile(r"OpenWindow\('([^']*)','([^']*)','([^']*)'\)")
DOC_IMAGE_CALL_PATTERN = re.compile(r"OpenDocument\('([^']*)'\)")
IMAGE_LIST_CALL_PATTERN = re.compile(r"JavaViewDocument\('([^']*)','([^']*)',")
CHECKBOX_NAME_PATTERN = re.compile(r"^chkAddress\d+$")


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "HeadlessChrome/146.0.0.0 Safari/537.36"
            ),
            "Referer": LADBS_RECORDS_SEARCH_URL,
            "Origin": "https://ladbsdoc.lacity.org",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def _collapse_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _normalize_apn(apn: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in (apn or "") if ch.isdigit())
    return digits if len(digits) == 10 else None


def split_apn(apn: Optional[str]) -> Optional[Dict[str, str]]:
    normalized = _normalize_apn(apn)
    if not normalized:
        return None
    return {
        "book": normalized[:4],
        "page": normalized[4:7],
        "parcel": normalized[7:10],
    }


def _normalize_address_for_match(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9 ]+", " ", value.upper()).strip()


def _collect_form_payload(
    form: Any,
    *,
    clicked_button_name: Optional[str] = None,
    clicked_button_value: Optional[str] = None,
    extra_fields: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    for tag in form.find_all(["input", "select"]):
        name = tag.get("name")
        if not name:
            continue

        if tag.name == "input":
            input_type = (tag.get("type") or "").lower()
            if input_type in {"submit", "button", "image", "reset"}:
                continue
            if input_type in {"checkbox", "radio"}:
                if tag.has_attr("checked"):
                    payload[name] = tag.get("value", "on")
                continue
            payload[name] = tag.get("value", "")
            continue

        first_option = tag.find("option", selected=True) or tag.find("option")
        payload[name] = first_option.get("value", "") if first_option else ""

    if extra_fields:
        payload.update(extra_fields)
    if clicked_button_name:
        payload[clicked_button_name] = clicked_button_value or ""
    return payload


def _parse_address_candidates(html_text: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html_text or "", "lxml")
    candidates: List[Dict[str, str]] = []
    for checkbox in soup.find_all("input", attrs={"name": CHECKBOX_NAME_PATTERN}):
        row = checkbox.find_parent("tr")
        if not row:
            continue
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        label_parts = [
            _collapse_whitespace(cells[1].get_text(" ", strip=True)),
            _collapse_whitespace(cells[3].get_text(" ", strip=True)),
            _collapse_whitespace(cells[4].get_text(" ", strip=True)),
            _collapse_whitespace(cells[5].get_text(" ", strip=True)),
        ]
        label = _collapse_whitespace(" ".join(part for part in label_parts if part))
        candidates.append(
            {
                "checkbox_name": checkbox.get("name"),
                "value": checkbox.get("value", ""),
                "label": label or "",
            }
        )
    return candidates


def _select_address_candidates(
    candidates: List[Dict[str, str]],
    requested_address: Optional[str],
) -> List[Dict[str, str]]:
    if not candidates:
        return []
    if len(candidates) == 1:
        return candidates

    target = _normalize_address_for_match((requested_address or "").split(",", 1)[0])
    if not target:
        return candidates[:1]

    exact_matches = [
        candidate
        for candidate in candidates
        if _normalize_address_for_match(candidate.get("label")) == target
    ]
    if exact_matches:
        return exact_matches

    partial_matches = [
        candidate
        for candidate in candidates
        if target in _normalize_address_for_match(candidate.get("label"))
        or _normalize_address_for_match(candidate.get("label")) in target
    ]
    if partial_matches:
        return partial_matches

    return candidates[:1]


def _build_records_report_url(record_id: str, image_flag: str, image_to_open: str) -> str:
    return f"{urljoin(LADBS_RECORDS_BASE_URL, 'Report.aspx')}?{urlencode({'Record_Id': record_id, 'Image': image_flag, 'ImageToOpen': image_to_open})}"


def _build_records_image_main_url(doc_ids: str) -> str:
    return f"{LADBS_IMAGE_MAIN_URL}?{urlencode({'DocIds': doc_ids})}"


def _build_records_pdf_url(doc_id: str, library_name: str) -> str:
    return f"{LADBS_PDF_VIEWER_URL}?{urlencode({'Library': library_name, 'Id': doc_id, 'ObjType': '2', 'Op': 'View'})}"


def _parse_records_results(html_text: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text or "", "lxml")
    grid = soup.find("table", id="grdIdisResult")
    if not grid:
        return {
            "documents": [],
            "preselected_addresses": [],
            "search_criteria": None,
            "page_summary": None,
        }

    documents: List[Dict[str, Any]] = []
    rows = grid.find_all("tr")
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        report_anchor = cells[1].find("a", href=True)
        if not report_anchor:
            continue

        report_match = DOC_REPORT_CALL_PATTERN.search(report_anchor.get("href", ""))
        image_anchor = cells[5].find("a", href=True)
        image_match = DOC_IMAGE_CALL_PATTERN.search(image_anchor.get("href", "")) if image_anchor else None
        comments_input = row.find("input", attrs={"type": "hidden", "name": re.compile(r"hidComments")})

        record_id = report_match.group(1) if report_match else None
        image_flag = report_match.group(2) if report_match else None
        image_to_open = report_match.group(3) if report_match else None
        doc_ids = image_match.group(1) if image_match else None

        documents.append(
            {
                "doc_type": _collapse_whitespace(cells[1].get_text(" ", strip=True)),
                "sub_type": _collapse_whitespace(cells[2].get_text(" ", strip=True)),
                "doc_date": _collapse_whitespace(cells[3].get_text(" ", strip=True)),
                "doc_number": _collapse_whitespace(cells[4].get_text(" ", strip=True)),
                "description": _collapse_whitespace(comments_input.get("value")) if comments_input else None,
                "record_id": record_id,
                "image_visibility": image_flag,
                "image_to_open": image_to_open,
                "doc_ids": doc_ids,
                "has_digital_image": bool(image_match),
                "summary_url": (
                    _build_records_report_url(record_id, image_flag or "", image_to_open or "")
                    if record_id and image_flag is not None and image_to_open is not None
                    else None
                ),
                "image_main_url": _build_records_image_main_url(doc_ids) if doc_ids else None,
            }
        )

    search_criteria = soup.find("span", id="lblSearchCriteria")
    preselected_addresses = [
        _collapse_whitespace(option.get_text(" ", strip=True))
        for option in soup.find_all("option")
        if option.get_text(" ", strip=True) and option.get_text(" ", strip=True) != "All"
    ]
    page_summary_match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", soup.get_text(" ", strip=True))

    return {
        "documents": documents,
        "preselected_addresses": [value for value in preselected_addresses if value],
        "search_criteria": _collapse_whitespace(search_criteria.get_text(" ", strip=True)) if search_criteria else None,
        "page_summary": (
            {
                "page_number": int(page_summary_match.group(1)),
                "total_pages": int(page_summary_match.group(2)),
            }
            if page_summary_match
            else None
        ),
    }


def _resolve_document_artifact_refs(session: requests.Session, document: Dict[str, Any]) -> Dict[str, Any]:
    doc_ids = document.get("doc_ids")
    if not doc_ids or doc_ids == "ShowMessage":
        return {}

    image_main_url = document.get("image_main_url")
    if not image_main_url:
        return {}

    try:
        session.get(image_main_url, timeout=REQUEST_TIMEOUT_SECONDS)
        image_list_response = session.get(LADBS_IMAGE_LIST_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        image_list_response.raise_for_status()
    except requests.RequestException:
        return {}

    match = IMAGE_LIST_CALL_PATTERN.search(image_list_response.text or "")
    if not match:
        return {
            "image_list_url": LADBS_IMAGE_LIST_URL,
        }

    doc_id = match.group(1)
    library_name = match.group(2)
    return {
        "image_list_url": LADBS_IMAGE_LIST_URL,
        "pdf_library": library_name,
        "pdf_doc_id": doc_id,
        "pdf_url": _build_records_pdf_url(doc_id, library_name),
    }


def get_ladbs_records(
    *,
    apn: Optional[str] = None,
    pin: Optional[str] = None,
    address: Optional[str] = None,
    redfin_url: Optional[str] = None,
    zimas_profile: Optional[Dict[str, Any]] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_apn = _normalize_apn(apn) or _normalize_apn((zimas_profile or {}).get("apn"))
    resolved_pin = (zimas_profile or {}).get("pin") or pin

    if not normalized_apn:
        zimas_lookup = zimas_profile or get_zimas_profile(pin=pin, address=address, redfin_url=redfin_url)
        normalized_apn = _normalize_apn(zimas_lookup.get("apn"))
        resolved_pin = resolved_pin or zimas_lookup.get("pin")
        zimas_profile = zimas_lookup

    apn_parts = split_apn(normalized_apn)
    if not apn_parts:
        return {
            "source": "ladbs_records_bad_apn",
            "transport": "http",
            "fetched_at": fetched_at,
            "apn": normalized_apn,
            "pin": resolved_pin,
            "documents": [],
            "note": "Could not derive a valid 10-digit APN for LADBS records search.",
            "diagnostics": {
                "zimas_profile_source": (zimas_profile or {}).get("source"),
                "search_url": LADBS_RECORDS_SEARCH_URL,
            },
        }

    session_to_use = session or _build_session()
    diagnostics: Dict[str, Any] = {
        "search_url": LADBS_RECORDS_SEARCH_URL,
        "bootstrap_url": LADBS_RECORDS_BOOTSTRAP_URL,
        "selection_candidates": [],
        "selected_addresses": [],
        "document_link_resolutions": [],
    }

    try:
        session_to_use.get(LADBS_RECORDS_BOOTSTRAP_URL, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
        search_page = session_to_use.get(LADBS_RECORDS_SEARCH_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        search_page.raise_for_status()
    except requests.RequestException as exc:
        return {
            "source": "ladbs_records_error",
            "transport": "http",
            "fetched_at": fetched_at,
            "apn": normalized_apn,
            "pin": resolved_pin,
            "documents": [],
            "note": f"LADBS records bootstrap failed: {exc}",
            "diagnostics": diagnostics,
        }

    search_form = BeautifulSoup(search_page.text or "", "lxml").find("form")
    if not search_form:
        return {
            "source": "ladbs_records_error",
            "transport": "http",
            "fetched_at": fetched_at,
            "apn": normalized_apn,
            "pin": resolved_pin,
            "documents": [],
            "note": "LADBS records search page did not contain a search form.",
            "diagnostics": diagnostics,
        }

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

    try:
        selection_response = session_to_use.post(
            LADBS_RECORDS_SEARCH_URL,
            data=search_payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        selection_response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "source": "ladbs_records_error",
            "transport": "http",
            "fetched_at": fetched_at,
            "apn": normalized_apn,
            "pin": resolved_pin,
            "documents": [],
            "note": f"LADBS records assessor search failed: {exc}",
            "diagnostics": diagnostics,
        }

    selection_html = selection_response.text or ""
    selection_candidates = _parse_address_candidates(selection_html)
    diagnostics["selection_candidates"] = [candidate["label"] for candidate in selection_candidates]

    if selection_candidates:
        chosen_candidates = _select_address_candidates(selection_candidates, address)
        diagnostics["selected_addresses"] = [candidate["label"] for candidate in chosen_candidates]
        selection_form = BeautifulSoup(selection_html, "lxml").find("form")
        if not selection_form:
            return {
                "source": "ladbs_records_error",
                "transport": "http",
                "fetched_at": fetched_at,
                "apn": normalized_apn,
                "pin": resolved_pin,
                "documents": [],
                "note": "LADBS records address-selection page did not contain a form.",
                "diagnostics": diagnostics,
            }

        continue_payload = _collect_form_payload(selection_form, clicked_button_name="btnNext2", clicked_button_value="Continue")
        for candidate in chosen_candidates:
            continue_payload[candidate["checkbox_name"]] = candidate["value"]

        try:
            results_response = session_to_use.post(
                LADBS_RECORDS_SEARCH_URL,
                data=continue_payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            results_response.raise_for_status()
        except requests.RequestException as exc:
            return {
                "source": "ladbs_records_error",
                "transport": "http",
                "fetched_at": fetched_at,
                "apn": normalized_apn,
                "pin": resolved_pin,
                "documents": [],
                "note": f"LADBS records address-selection submit failed: {exc}",
                "diagnostics": diagnostics,
            }
        results_html = results_response.text or ""
    else:
        results_html = selection_html

    parsed_results = _parse_records_results(results_html)
    documents = parsed_results["documents"]
    if not documents:
        return {
            "source": "ladbs_records_no_results",
            "transport": "http",
            "fetched_at": fetched_at,
            "apn": normalized_apn,
            "pin": resolved_pin,
            "documents": [],
            "note": f"No LADBS records documents were returned for APN {normalized_apn}.",
            "diagnostics": diagnostics,
            "search_criteria": parsed_results.get("search_criteria"),
            "preselected_addresses": parsed_results.get("preselected_addresses"),
        }

    resolved_document_count = 0
    for document in documents:
        if document.get("has_digital_image") and resolved_document_count < DOC_LINK_LIMIT:
            artifact_refs = _resolve_document_artifact_refs(session_to_use, document)
            if artifact_refs:
                document.update(artifact_refs)
                diagnostics["document_link_resolutions"].append(document.get("doc_number"))
            resolved_document_count += 1

    return {
        "source": "ladbs_records_v1",
        "transport": "http",
        "fetched_at": fetched_at,
        "apn": normalized_apn,
        "pin": resolved_pin,
        "documents": documents,
        "note": f"Fetched {len(documents)} LADBS records document(s) for APN {normalized_apn}.",
        "links": {
            "search_url": LADBS_RECORDS_SEARCH_URL,
            "selection_url": LADBS_RECORDS_SELECTION_URL,
        },
        "search_criteria": parsed_results.get("search_criteria"),
        "preselected_addresses": parsed_results.get("preselected_addresses"),
        "page_summary": parsed_results.get("page_summary"),
        "diagnostics": diagnostics,
    }
