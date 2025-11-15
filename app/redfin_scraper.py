from __future__ import annotations
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup


# Base directories (project root is one level up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent  # C:\Users\navid\comp-intel
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"


def _ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def _guess_address_from_url(url: str) -> str:
    """
    Fallback: extract something readable from a Redfin URL path.
    """
    try:
        path = urlparse(url).path
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3:
            address_segment = parts[2]
            return address_segment.replace("-", " ")
    except Exception:
        pass
    return "Unknown address from URL"


def fetch_redfin_html(url: str) -> Path:
    """
    Fetch the raw HTML for the given Redfin URL and save it under data/raw/.
    Returns the path of the saved HTML file.
    """
    _ensure_dirs()

    headers = {
        # Pretend to be Chrome on Windows
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = _guess_address_from_url(url).replace(" ", "_")
    filename = f"{timestamp}_redfin_{safe_name}.html"
    out_path = RAW_DIR / filename
    out_path.write_text(resp.text, encoding="utf-8", errors="ignore")
    return out_path


def _extract_first_number(text: str) -> Optional[float]:
    """
    Grab the first integer/float number from a string like "3 Beds", "1,662 sq ft".
    Returns float or None.
    """
    if not text:
        return None
    cleaned = text.replace(",", "")
    m = re.search(r"(\d+(\.\d+)?)", cleaned)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _regex_first_group(pattern: str, text: str) -> Optional[str]:
    """
    Simple helper: return first capture group for a regex pattern, or None.
    DOTALL so it can cross line breaks.
    """
    if not text:
        return None
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def parse_redfin_html_listing(soup: BeautifulSoup, html_text: str) -> Dict[str, Any]:
    """
    Parse the listing (top-of-page) stats:
      - address
      - beds
      - baths
      - building_sf
      - current list_price
      - listing_year_built
    """
    # Address
    address_text: Optional[str] = None
    addr_el = soup.select_one('[data-rf-test-id="abp-streetLine"]')
    if not addr_el:
        addr_el = soup.select_one('[data-rf-test-id="abp-street-line"]')
    if not addr_el:
        addr_el = soup.find("h1")
    if addr_el:
        address_text = addr_el.get_text(strip=True) or None

    # Beds / baths / SF
    beds_val: Optional[float] = None
    baths_val: Optional[float] = None
    building_sf_val: Optional[float] = None

    beds_el = soup.select_one('[data-rf-test-id="abp-beds"]')
    baths_el = soup.select_one('[data-rf-test-id="abp-baths"]')
    sqft_el = soup.select_one('[data-rf-test-id="abp-sqFt"]')

    if beds_el:
        beds_val = _extract_first_number(beds_el.get_text(strip=True))
    if baths_el:
        baths_val = _extract_first_number(baths_el.get_text(strip=True))
    if sqft_el:
        building_sf_val = _extract_first_number(sqft_el.get_text(strip=True))

    # For sale price (block usually shows "For sale" then "$X,XXX,XXX")
    list_price_val: Optional[float] = None
    m_price = re.search(r"For sale\s*[\r\n]+\s*\$([\d,]+)", html_text, re.DOTALL)
    if m_price:
        try:
            list_price_val = float(m_price.group(1).replace(",", ""))
        except ValueError:
            list_price_val = None

    # Listing year built (e.g. "2025 Year Built" in property details)
    listing_year_built: Optional[int] = None
    year_str = _regex_first_group(r"(\d{4})\s+Year Built", html_text)
    if year_str:
        try:
            listing_year_built = int(year_str)
        except ValueError:
            listing_year_built = None

    return {
        "address": address_text,
        "beds": beds_val,
        "baths": baths_val,
        "building_sf": building_sf_val,
        "list_price": list_price_val,
        "listing_year_built": listing_year_built,
    }


def parse_public_facts_and_apn(html_text: str) -> Dict[str, Any]:
    """
    Parse public records stats and APN from the raw HTML text:
      - public_beds
      - public_baths
      - public_building_sf
      - public_lot_sf
      - public_year_built
      - apn
    """
    result: Dict[str, Any] = {}

    beds_str = _regex_first_group(r"Beds:\s*([0-9\.]+)", html_text)
    baths_str = _regex_first_group(r"Baths:\s*([0-9\.]+)", html_text)
    sf_str = _regex_first_group(r"Finished Sq\. Ft\.\s*:\s*([\d,]+)", html_text)
    lot_str = _regex_first_group(r"Lot Size:\s*([\d,]+)\s+square feet", html_text)
    year_str = _regex_first_group(r"Year Built:\s*([0-9]{4})", html_text)
    apn_str = _regex_first_group(r"APN:\s*([0-9\-]+)", html_text)

    def _to_float(s: Optional[str]) -> Optional[float]:
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None

    if beds_str:
        result["public_beds"] = _to_float(beds_str)
    if baths_str:
        result["public_baths"] = _to_float(baths_str)
    if sf_str:
        result["public_building_sf"] = _to_float(sf_str)
    if lot_str:
        result["public_lot_sf"] = _to_float(lot_str)
    if year_str:
        try:
            result["public_year_built"] = int(year_str)
        except ValueError:
            pass
    if apn_str:
        result["apn"] = apn_str

    return result


def parse_sale_history(html_text: str) -> List[Dict[str, Any]]:
    """
    Parse the 'Sale and tax history' section into a list of events:
      { date: 'YYYY-MM-DD', event: 'listed'|'sold', price: int, raw_status: str }
    """

    events: List[Dict[str, Any]] = []

    # Pattern for listed events (e.g. Nov 4, 2025 ... Listed (Active) ... $3,795,000)
    pattern_listed = re.compile(
        r"([A-Z][a-z]{2} \d{1,2}, \d{4}).{0,200}?Listed\s*\(([^)]+)\).*?\$([\d,]+)",
        re.DOTALL,
    )

    # Pattern for sold events (e.g. May 31, 2024 ... Sold (MLS) (Closed Sale) ... $1,460,000)
    pattern_sold = re.compile(
        r"([A-Z][a-z]{2} \d{1,2}, \d{4}).{0,200}?Sold\s*\(([^)]+)\).*?\$([\d,]+)",
        re.DOTALL,
    )

    for m in pattern_listed.finditer(html_text):
        date_str = m.group(1)
        status_desc = f"Listed ({m.group(2)})"
        price_str = m.group(3)
        try:
            dt = datetime.strptime(date_str, "%b %d, %Y")
            price = int(price_str.replace(",", ""))
        except ValueError:
            continue
        events.append(
            {
                "date": dt.date().isoformat(),
                "event": "listed",
                "price": price,
                "raw_status": status_desc,
            }
        )

    for m in pattern_sold.finditer(html_text):
        date_str = m.group(1)
        status_desc = f"Sold ({m.group(2)})"
        price_str = m.group(3)
        try:
            dt = datetime.strptime(date_str, "%b %d, %Y")
            price = int(price_str.replace(",", ""))
        except ValueError:
            continue
        events.append(
            {
                "date": dt.date().isoformat(),
                "event": "sold",
                "price": price,
                "raw_status": status_desc,
            }
        )

    # Sort by date ascending so metrics logic can use first sold + first listed cleanly
    events.sort(key=lambda e: e["date"])
    return events


def get_redfin_data(url: str) -> Dict[str, Any]:
    """
    1) Fetch & save the real Redfin HTML.
    2) Parse listing stats (address + beds + baths + SF + list_price + listing_year_built).
    3) Parse public records stats (beds/baths/SF/lot/year built) and APN.
    4) Parse sale history into a real timeline.
    """
    _ensure_dirs()

    html_path: Optional[Path] = None
    html_text: Optional[str] = None
    soup: Optional[BeautifulSoup] = None

    try:
        html_path = fetch_redfin_html(url)
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as e:
        print(f"[WARN] Failed to fetch or read Redfin HTML: {e}")

    listing_parsed: Dict[str, Any] = {}
    if soup is not None and html_text:
        try:
            listing_parsed = parse_redfin_html_listing(soup, html_text)
        except Exception as e:
            print(f"[WARN] Failed to parse listing stats: {e}")
            listing_parsed = {}

    public_parsed: Dict[str, Any] = {}
    if html_text:
        try:
            public_parsed = parse_public_facts_and_apn(html_text)
        except Exception as e:
            print(f"[WARN] Failed to parse public facts: {e}")
            public_parsed = {}

    sale_events: List[Dict[str, Any]] = []
    if html_text:
        try:
            sale_events = parse_sale_history(html_text)
        except Exception as e:
            print(f"[WARN] Failed to parse sale history: {e}")
            sale_events = []

    now = datetime.now().strftime("%Y-%m-%d")
    address_label = listing_parsed.get("address") or _guess_address_from_url(url)

    # Listing stats - NO FAKE DATA, use None if missing
    beds = listing_parsed.get("beds")
    baths = listing_parsed.get("baths")
    building_sf = listing_parsed.get("building_sf")
    list_price = listing_parsed.get("list_price")
    listing_year_built = listing_parsed.get("listing_year_built")

    # Public records / APN
    public_records: Dict[str, Any] = {}
    if public_parsed.get("public_beds") is not None:
        public_records["beds"] = public_parsed["public_beds"]
    if public_parsed.get("public_baths") is not None:
        public_records["baths"] = public_parsed["public_baths"]
    if public_parsed.get("public_building_sf") is not None:
        public_records["building_sf"] = public_parsed["public_building_sf"]
    if public_parsed.get("public_lot_sf") is not None:
        public_records["lot_sf"] = public_parsed["public_lot_sf"]
    if public_parsed.get("public_year_built") is not None:
        public_records["year_built"] = public_parsed["public_year_built"]

    # Build summary strings
    def _format_summary(beds, baths, sf, label=""):
        parts = []
        if beds is not None:
            parts.append(f"{int(beds)} bed")
        if baths is not None:
            parts.append(f"{baths} bath")
        if sf is not None:
            parts.append(f"{int(sf):,} SF")
        return ", ".join(parts) if parts else f"{label}Data not available"

    current_summary = _format_summary(beds, baths, building_sf, "Current: ")
    public_record_summary = _format_summary(
        public_records.get("beds"),
        public_records.get("baths"),
        public_records.get("building_sf"),
        "Public Record: "
    )
    
    lot_sf = public_parsed.get("public_lot_sf")
    lot_summary = f"{int(lot_sf):,} SF" if lot_sf else "Lot: Data not available"

    redfin_struct: Dict[str, Any] = {
        "source": "redfin_parsed_v2",
        "url": url,
        "address": address_label,
        # listing (current configuration)
        "listing_beds": beds,
        "listing_baths": baths,
        "listing_building_sf": building_sf,
        "listing_year_built": listing_year_built,
        "list_price": list_price,
        # backward compatible top-level
        "beds": beds,
        "baths": baths,
        "building_sf": building_sf,
        "lot_sf": lot_sf,
        # timeline: real sale/list history ONLY, no fake data
        "timeline": sale_events,
        # tax + APN
        "tax": {
            "apn": public_parsed.get("apn"),
            "year": 2023,
            "assessed_value": None,  # Could parse from tax table later
        },
        "public_records": public_records,
        "generated_at": now,
        # Summary strings for template
        "current_summary": current_summary,
        "public_record_summary": public_record_summary,
        "lot_summary": lot_summary,
    }

    if html_path is not None:
        redfin_struct["raw_html_path"] = str(html_path)

    return redfin_struct


if __name__ == "__main__":
    test_url = "https://www.redfin.com/CA/Sherman-Oaks/13157-Otsego-St-91423/home/5216364"
    print(f"[TEST] Fetching + parsing Redfin HTML for: {test_url}")
    data = get_redfin_data(test_url)
    print("Structured Redfin data (listing + public records + real sale history):")
    for k, v in data.items():
        print(f"{k}: {v}")
