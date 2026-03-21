from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
import os
import re
import time

import requests
from bs4 import BeautifulSoup

from app.zimas_pin_client import DEFAULT_HEADERS, REQUEST_TIMEOUT_SECONDS, ZIMAS_SEARCH_URL, resolve_pin

ZIMAS_PROFILE_URL = "https://zimas.lacity.org/map.aspx"
SECTION_KEY_PATTERN = re.compile(r"(divTab\d+):\s*\"((?:\\.|[^\"\\])*)\"", re.S)
DOUBLE_QUOTED_VALUE_TEMPLATE = r"{key}:\s*\"((?:\\.|[^\"\\])*)\""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default


def _request_with_retries(
    session: requests.Session,
    *,
    url: str,
    params: Dict[str, Any],
    timeout: int,
) -> Tuple[Optional[requests.Response], List[Dict[str, Any]], Optional[str]]:
    attempts = max(1, _env_int("ZIMAS_HTTP_ATTEMPTS", 3))
    retry_delay_seconds = max(0.0, _env_float("ZIMAS_HTTP_RETRY_DELAY_SECONDS", 1.5))
    attempt_diagnostics: List[Dict[str, Any]] = []
    last_error: Optional[str] = None

    for attempt in range(1, attempts + 1):
        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            attempt_diagnostics.append(
                {
                    "attempt": attempt,
                    "status_code": getattr(response, "status_code", None),
                }
            )
            return response, attempt_diagnostics, None
        except requests.RequestException as exc:
            last_error = str(exc)
            attempt_diagnostics.append({"attempt": attempt, "error": last_error})
            if attempt < attempts:
                time.sleep(retry_delay_seconds * attempt)

    return None, attempt_diagnostics, last_error


def _collapse_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _strip_preserve_internal_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_apn(apn: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in (apn or "") if ch.isdigit())
    return digits or None


def _decode_js_string(value: str) -> str:
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return value.replace('\\"', '"').replace("\\'", "'")


def _extract_js_string(payload: str, key: str) -> Optional[str]:
    match = re.search(DOUBLE_QUOTED_VALUE_TEMPLATE.format(key=re.escape(key)), payload or "", re.S)
    if not match:
        return None
    return _decode_js_string(match.group(1))


def _extract_pin_from_apn_response(payload: str) -> Tuple[Optional[str], Optional[str]]:
    pin_match = re.search(r'pin:\s*"([^"]+)"', payload or "")
    address_match = re.search(r'Address:\s*"([^"]+)"', payload or "")
    return (
        _strip_preserve_internal_whitespace(pin_match.group(1)) if pin_match else None,
        _collapse_whitespace(address_match.group(1)) if address_match else None,
    )


def _first_present(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _parse_section_rows(section_html: str) -> List[Dict[str, Optional[str]]]:
    soup = BeautifulSoup(section_html or "", "lxml")
    rows: List[Dict[str, Optional[str]]] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = _collapse_whitespace(cells[0].get_text(" ", strip=True))
        value_cell = cells[1]
        value = _collapse_whitespace(value_cell.get_text(" ", strip=True))
        link = value_cell.find("a")
        rows.append(
            {
                "label": label,
                "value": value,
                "href": link.get("href") if link else None,
                "onclick": link.get("onclick") if link else None,
            }
        )
    return rows


def _rows_to_map(rows: List[Dict[str, Optional[str]]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for row in rows:
        label = row.get("label")
        value = row.get("value")
        if label and value:
            result[label] = value
    return result


def _parse_float_from_text(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"(-?\d[\d,]*(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_profile_payload(payload: str) -> Dict[str, Any]:
    section_rows: Dict[str, List[Dict[str, Optional[str]]]] = {}
    for key, raw_value in SECTION_KEY_PATTERN.findall(payload or ""):
        section_rows[key] = _parse_section_rows(_decode_js_string(raw_value))

    section_maps = {key: _rows_to_map(rows) for key, rows in section_rows.items()}
    tab1 = section_maps.get("divTab1", {})
    tab2 = section_maps.get("divTab2", {})
    tab3 = section_maps.get("divTab3", {})
    tab5 = section_maps.get("divTab5", {})
    tab7 = section_maps.get("divTab7", {})
    tab8 = section_maps.get("divTab8", {})
    tab1200 = section_maps.get("divTab1200", {})

    profile_address = _collapse_whitespace(_extract_js_string(payload, "Address"))
    selected_apn = _normalize_apn(_extract_js_string(payload, "selectedAPN"))

    return {
        "address": profile_address or tab1.get("Site Address"),
        "apn": selected_apn or _normalize_apn(tab1.get("Assessor Parcel No. (APN)")),
        "section_rows": section_rows,
        "section_maps": section_maps,
        "parcel_identity": {
            "site_address": tab1.get("Site Address") or profile_address,
            "zip_code": tab1.get("ZIP Code"),
            "pin": tab1.get("PIN Number"),
            "apn": selected_apn or _normalize_apn(tab1.get("Assessor Parcel No. (APN)")),
            "lot_area_sqft": _parse_float_from_text(tab1.get("Lot/Parcel Area (Calculated)")),
            "tract": tab1.get("Tract"),
            "map_reference": tab1.get("Map Reference"),
            "lot": tab1.get("Lot"),
            "map_sheet": tab1.get("Map Sheet"),
            "thomas_brothers_grid": tab1.get("Thomas Brothers Grid"),
        },
        "planning_context": {
            "community_plan_area": tab2.get("Community Plan Area"),
            "area_planning_commission": tab2.get("Area Planning Commission"),
            "neighborhood_council": tab2.get("Neighborhood Council"),
            "council_district": tab2.get("Council District"),
            "census_tract": tab2.get("Census Tract #"),
            "ladbs_district_office": tab2.get("LADBS District Office"),
            "recent_activity": tab5.get("Recent Activity"),
            "city_planning_commission": tab5.get("City Planning Commission"),
            "ordinance": tab5.get("Ordinance"),
        },
        "zoning_profile": {
            "zoning": tab3.get("Zoning"),
            "zoning_information": tab3.get("Zoning Information (ZI)"),
            "general_plan_land_use": tab3.get("General Plan Land Use"),
            "general_plan_notes": tab3.get("General Plan Note(s)"),
            "special_notes": tab3.get("Special Notes"),
            "historic_preservation_review": tab3.get("Historic Preservation Review"),
            "special_land_use_zoning": tab3.get("Special Land Use / Zoning"),
            "hpoz": tab3.get("Historic Preservation Overlay Zone"),
            "baseline_hillside_ordinance": tab3.get("Baseline Hillside Ordinance"),
            "specific_plan_area": tab3.get("Specific Plan Area"),
            "residential_market_area": tab3.get("Residential Market Area"),
        },
        "environmental_profile": {
            "urban_agriculture_incentive_zone": tab7.get("Urban Agriculture Incentive Zone"),
            "flood_zone": tab7.get("Flood Zone"),
            "methane_hazard_site": tab7.get("Methane Hazard Site"),
            "upRS_applicability": tab7.get("Universal Planning Review Service Applicability"),
            "hillside_area": tab3.get("Hillside Area (Zoning Code)") or tab7.get("Hillside Area (Zoning Code)"),
        },
        "hazard_profile": {
            "nearest_fault": _first_present(tab8.get("Nearest Fault (Name)"), tab8.get("Nearest Fault")),
            "nearest_fault_distance_km": _parse_float_from_text(tab8.get("Nearest Fault (Distance in km)")),
            "alquist_priolo_fault_zone": tab8.get("Alquist-Priolo Fault Zone"),
            "liquefaction": tab8.get("Liquefaction"),
            "landslide": tab8.get("Landslide"),
            "tsunami_hazard_area": _first_present(tab8.get("Tsunami Hazard Area"), tab8.get("Tsunami Inundation Zone")),
        },
        "permit_references": {
            "building_permit_info": tab1200.get("Building Permit Info"),
            "administrative_review": tab1200.get("Administrative Review"),
            "home_sharing": tab1200.get("Home Sharing"),
        },
    }


def _resolve_pin_from_apn(apn: str, session: requests.Session) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "request_url": ZIMAS_SEARCH_URL,
        "request_params": {"search": "apn", "apn": apn},
        "response_preview": None,
        "request_attempts": [],
    }

    response, attempt_diagnostics, error_message = _request_with_retries(
        session,
        url=ZIMAS_SEARCH_URL,
        params=diagnostics["request_params"],
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    diagnostics["request_attempts"] = attempt_diagnostics
    if response is None:
        return {
            "pin": None,
            "matched_address": None,
            "source": "zimas_apn_error",
            "note": f"ZIMAS APN lookup failed: {error_message}",
            "diagnostics": diagnostics,
        }

    diagnostics["response_preview"] = (response.text or "")[:500]
    pin, matched_address = _extract_pin_from_apn_response(response.text or "")
    if not pin:
        return {
            "pin": None,
            "matched_address": None,
            "source": "zimas_apn_no_match",
            "note": f"ZIMAS APN lookup did not return a parcel PIN for APN {apn}.",
            "diagnostics": diagnostics,
        }

    return {
        "pin": pin,
        "matched_address": matched_address,
        "source": "zimas_apn_v1",
        "note": f"Resolved ZIMAS PIN via APN lookup for APN {apn}.",
        "diagnostics": diagnostics,
    }


def get_zimas_profile(
    *,
    pin: Optional[str] = None,
    apn: Optional[str] = None,
    address: Optional[str] = None,
    redfin_url: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_apn = _normalize_apn(apn)
    session_to_use = session or requests.Session()
    session_to_use.headers.update(DEFAULT_HEADERS)

    pin_resolution: Optional[Dict[str, Any]] = None
    resolved_pin = _strip_preserve_internal_whitespace(pin)

    if not resolved_pin and normalized_apn:
        pin_resolution = _resolve_pin_from_apn(normalized_apn, session_to_use)
        resolved_pin = pin_resolution.get("pin")

    if not resolved_pin:
        pin_resolution = resolve_pin(
            redfin_url=redfin_url,
            address=address,
            session=session_to_use,
        )
        resolved_pin = pin_resolution.get("pin")

    if not resolved_pin:
        return {
            "source": "zimas_profile_bad_input",
            "transport": "http",
            "fetched_at": fetched_at,
            "pin": None,
            "apn": normalized_apn,
            "address": address,
            "note": (
                "Could not resolve a ZIMAS parcel PIN from the provided inputs. "
                f"{(pin_resolution or {}).get('note') or 'No usable pin, APN, or address was provided.'}"
            ),
            "diagnostics": {
                "pin_resolution": pin_resolution,
                "profile_url": None,
            },
            "section_rows": {},
        }

    profile_url = f"{ZIMAS_PROFILE_URL}?pin={quote(resolved_pin)}&ajax=yes"
    profile_params = {"pin": resolved_pin, "ajax": "yes"}
    response, profile_attempts, error_message = _request_with_retries(
        session_to_use,
        url=ZIMAS_PROFILE_URL,
        params=profile_params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response is None:
        return {
            "source": "zimas_profile_error",
            "transport": "http",
            "fetched_at": fetched_at,
            "pin": resolved_pin,
            "apn": normalized_apn,
            "address": address,
            "note": f"ZIMAS parcel-profile request failed: {error_message}",
            "diagnostics": {
                "pin_resolution": pin_resolution,
                "profile_url": profile_url,
                "request_attempts": profile_attempts,
            },
            "section_rows": {},
        }

    parsed = _parse_profile_payload(response.text or "")
    parsed_apn = _normalize_apn(parsed.get("apn")) or normalized_apn
    address_value = _collapse_whitespace(parsed.get("address")) or _collapse_whitespace(address)
    parcel_identity = dict(parsed["parcel_identity"])
    if resolved_pin:
        parcel_identity["pin"] = resolved_pin

    return {
        "source": "zimas_profile_v1",
        "transport": "http",
        "fetched_at": fetched_at,
        "pin": resolved_pin,
        "apn": parsed_apn,
        "address": address_value,
        "note": f"Resolved ZIMAS parcel profile for PIN {resolved_pin}.",
        "pin_resolution_source": (pin_resolution or {}).get("source") or ("direct_pin" if pin else None),
        "pin_resolution": pin_resolution,
        "parcel_identity": parcel_identity,
        "planning_context": parsed["planning_context"],
        "zoning_profile": parsed["zoning_profile"],
        "environmental_profile": parsed["environmental_profile"],
        "hazard_profile": parsed["hazard_profile"],
        "permit_references": parsed["permit_references"],
        "section_rows": parsed["section_rows"],
        "links": {
            "profile_url": profile_url,
            "root_url": "https://zimas.lacity.org/",
        },
        "diagnostics": {
            "pin_resolution": pin_resolution,
            "profile_url": profile_url,
            "request_attempts": profile_attempts,
            "tab_keys": sorted(parsed["section_rows"].keys()),
        },
    }
