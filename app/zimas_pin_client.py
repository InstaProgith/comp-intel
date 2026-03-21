from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse
import re

import requests

ZIMAS_SEARCH_URL = "https://zimas.lacity.org/ajaxSearchResults.aspx"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Referer": "https://zimas.lacity.org/",
}
STREET_NOISE_TOKENS = {
    "N",
    "S",
    "E",
    "W",
    "NE",
    "NW",
    "SE",
    "SW",
    "BLVD",
    "ST",
    "AVE",
    "RD",
    "PL",
    "DR",
    "CT",
    "LN",
    "WAY",
    "PKWY",
    "TER",
    "HWY",
}


def _normalize_street_name_parts(parts: List[str]) -> Optional[str]:
    clean_parts: List[str] = []
    for part in parts:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", part).strip()
        if not cleaned:
            continue
        if cleaned.upper() in STREET_NOISE_TOKENS:
            continue
        clean_parts.append(cleaned)
    if not clean_parts:
        return None
    return " ".join(clean_parts)


def extract_address_from_redfin_url(redfin_url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        path = urlparse(redfin_url).path
        parts = path.split("/")
        if len(parts) < 4:
            return None, None
        address_part = parts[3]

        address_components = address_part.split("-")[:-1]
        if not address_components:
            return None, None

        street_number = address_components[0]
        street_name = _normalize_street_name_parts(address_components[1:])
        return street_number, street_name
    except Exception:
        return None, None


def extract_address_from_text(address: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        street_line = (address or "").split(",", 1)[0].strip()
        match = re.match(r"^(\d+[A-Za-z]?)\s+(.+)$", street_line)
        if not match:
            return None, None
        street_number = match.group(1)
        street_name = _normalize_street_name_parts(match.group(2).split())
        return street_number, street_name
    except Exception:
        return None, None


def parse_search_response(response_text: str) -> Dict[str, Optional[str]]:
    pin_match = re.search(r"navigateDataToPin\('([^']+)'\s*,\s*'([^']*)'\)", response_text or "")
    if pin_match:
        return {
            "pin": unquote(pin_match.group(1)),
            "matched_address": unquote(pin_match.group(2)) or None,
            "error_message": None,
        }

    error_match = re.search(r"message:\s*'([^']+)'", response_text or "")
    return {
        "pin": None,
        "matched_address": None,
        "error_message": error_match.group(1) if error_match else None,
    }


def resolve_pin(
    *,
    redfin_url: Optional[str] = None,
    address: Optional[str] = None,
    street_number: Optional[str] = None,
    street_name: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "request_url": ZIMAS_SEARCH_URL,
        "request_params": None,
        "response_preview": None,
        "browser_fallback_attempted": False,
    }

    if not street_number or not street_name:
        if redfin_url:
            street_number, street_name = extract_address_from_redfin_url(redfin_url)
        if (not street_number or not street_name) and address:
            street_number, street_name = extract_address_from_text(address)

    if not street_number or not street_name:
        return {
            "pin": None,
            "matched_address": None,
            "source": "zimas_bad_address",
            "note": (
                "Could not derive a ZIMAS street number/name from the provided inputs. "
                f"redfin_url={redfin_url!r} address={address!r}"
            ),
            "street_number": street_number,
            "street_name": street_name,
            "diagnostics": diagnostics,
        }

    params = {
        "search": "address",
        "HouseNumber": street_number,
        "StreetName": street_name,
    }
    diagnostics["request_params"] = params

    session_to_use = session or requests.Session()
    session_to_use.headers.update(DEFAULT_HEADERS)

    try:
        response = session_to_use.get(
            ZIMAS_SEARCH_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "pin": None,
            "matched_address": None,
            "source": "zimas_error",
            "note": f"ZIMAS PIN lookup failed: {exc}",
            "street_number": street_number,
            "street_name": street_name,
            "diagnostics": diagnostics,
        }

    response_text = response.text or ""
    diagnostics["response_preview"] = response_text[:500]
    parsed = parse_search_response(response_text)
    if parsed["pin"]:
        return {
            "pin": parsed["pin"],
            "matched_address": parsed["matched_address"],
            "source": "zimas_ajax_v1",
            "note": "Resolved ZIMAS PIN via ajaxSearchResults address lookup.",
            "street_number": street_number,
            "street_name": street_name,
            "diagnostics": diagnostics,
        }

    error_message = parsed["error_message"] or "ZIMAS search did not return a parcel PIN."
    return {
        "pin": None,
        "matched_address": None,
        "source": "zimas_no_match",
        "note": error_message,
        "street_number": street_number,
        "street_name": street_name,
        "diagnostics": diagnostics,
    }
