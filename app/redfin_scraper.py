from __future__ import annotations
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup


# Base directories (project root is one level up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent
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


def fetch_redfin_html(url: str) -> Optional[Path]:
    """
    Fetch the raw HTML for the given Redfin URL and save it under data/raw/.
    Returns the path of the saved HTML file, or None if fetch fails.
    """
    _ensure_dirs()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = _guess_address_from_url(url).replace(" ", "_")
        filename = f"{timestamp}_redfin_{safe_name}.html"
        out_path = RAW_DIR / filename
        out_path.write_text(resp.text, encoding="utf-8", errors="ignore")
        return out_path
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Redfin fetch failed: {e}")
        return None


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
      - baths (including half baths)
      - building_sf
      - lot_sf (from listing banner or property details)
      - current list_price (ONLY from active listing banner)
      - listing_year_built
      - property_type
      - price_per_sf
      - sold_status (SOLD banner detection)
    
    CRITICAL RULE: list_price comes ONLY from [data-rf-test-id="abp-price"].
    NEVER use tax amounts, assessed values, or tax table numbers as list_price.
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
    
    # Enhanced bath parsing to handle "4 Full, 2 Half" format
    if not baths_val:
        full_half_match = re.search(r'(\d+)\s*Full,\s*(\d+)\s*Half', html_text, re.I)
        if full_half_match:
            full = int(full_half_match.group(1))
            half = int(full_half_match.group(2))
            baths_val = full + (half * 0.5)
    
    if sqft_el:
        building_sf_val = _extract_first_number(sqft_el.get_text(strip=True))

    # Lot size from listing banner (e.g., "6,494 Sq. Ft. Lot")
    lot_sf_val: Optional[float] = None
    lot_patterns = [
        r'([\d,]+)\s*Sq\.\s*Ft\.\s*Lot',
        r'([\d,]+)\s*sq\s*ft\s*lot',
        r'Lot[:\s]+([\d,]+)\s*Sq\.\s*Ft\.',
    ]
    for pattern in lot_patterns:
        lot_match = re.search(pattern, html_text, re.I)
        if lot_match:
            try:
                lot_sf_val = float(lot_match.group(1).replace(",", ""))
                break
            except (ValueError, IndexError):
                continue

    # Current list price from price banner ONLY
    # RULE: ONLY from data-rf-test-id="abp-price" - NEVER from tax table
    list_price_val: Optional[float] = None
    price_el = soup.select_one('[data-rf-test-id="abp-price"]')
    if price_el:
        price_text = price_el.get_text(strip=True)
        # Extract numeric value from "$3,849,000" format
        price_match = re.search(r'\$?([\d,]+)', price_text)
        if price_match:
            try:
                list_price_val = float(price_match.group(1).replace(",", ""))
            except ValueError:
                pass

    # Listing year built (e.g. "2025 Year Built" or "Year Built: 2022")
    listing_year_built: Optional[int] = None
    year_patterns = [
        r'(\d{4})\s+Year Built',
        r'Year Built[:\s]+(\d{4})',
        r'Built in (\d{4})',
    ]
    for pattern in year_patterns:
        year_str = _regex_first_group(pattern, html_text)
        if year_str:
            try:
                listing_year_built = int(year_str)
                break
            except ValueError:
                continue
    
    # Property type
    property_type: Optional[str] = None
    prop_type_match = re.search(r'Property Type[:\s]+([^<\n]+)', html_text)
    if prop_type_match:
        property_type = prop_type_match.group(1).strip()
        # Normalize common types
        if 'single' in property_type.lower() and 'family' in property_type.lower():
            property_type = "Single-family"
        elif 'condo' in property_type.lower():
            property_type = "Condo"
        elif 'townhouse' in property_type.lower():
            property_type = "Townhouse"
    
    # Price per SF
    price_per_sf: Optional[float] = None
    price_sf_match = re.search(r'\$([\d,]+)\s*/\s*Sq\.\s*Ft\.', html_text)
    if price_sf_match:
        try:
            price_per_sf = float(price_sf_match.group(1).replace(",", ""))
        except ValueError:
            pass
    
    # SOLD status detection (e.g., "SOLD NOV 21, 2025")
    sold_banner: Optional[str] = None
    sold_match = re.search(r'SOLD\s+([A-Z]{3}\s+\d{1,2},\s+\d{4})', html_text, re.I)
    if sold_match:
        sold_banner = sold_match.group(1)

    return {
        "address": address_text,
        "beds": beds_val,
        "baths": baths_val,
        "building_sf": building_sf_val,
        "lot_sf": lot_sf_val,
        "list_price": list_price_val,  # PRICE: from active listing banner ONLY
        "listing_year_built": listing_year_built,
        "property_type": property_type,
        "price_per_sf": price_per_sf,
        "sold_banner": sold_banner,
    }


def parse_public_facts_and_apn(html_text: str) -> Dict[str, Any]:
    """
    Parse public records stats and APN from the raw HTML text:
      - public_beds
      - public_baths
      - public_building_sf
      - public_lot_sf  (from Property Details section ONLY, NOT from tax table)
      - public_year_built
      - apn
    
    CRITICAL RULE: Lot size MUST come from Property Details section ONLY.
    NEVER use tax table values.
    """
    result: Dict[str, Any] = {}

    beds_str = _regex_first_group(r"Beds:\s*([0-9\.]+)", html_text)
    baths_str = _regex_first_group(r"Baths:\s*([0-9\.]+)", html_text)
    sf_str = _regex_first_group(r"Finished Sq\. Ft\.\s*:\s*([\d,]+)", html_text)
    
    # Try multiple patterns for lot size to be more robust
    # Pattern 1: "Lot Size (Sq. Ft.): 6,001"
    lot_str = _regex_first_group(r"Lot Size \(Sq\. Ft\.\):\s*([\d,]+)", html_text)
    if not lot_str:
        # Pattern 2: "Lot Size: 6,001 square feet"
        lot_str = _regex_first_group(r"Lot Size:\s*([\d,]+)\s+square feet", html_text)
    if not lot_str:
        # Pattern 3: "Lot Size: 6,001 Sq. Ft."
        lot_str = _regex_first_group(r"Lot Size:\s*([\d,]+)\s+Sq\. Ft\.", html_text)
    if not lot_str:
        # Pattern 4: Just "Lot Size: 6,001"
        lot_str = _regex_first_group(r"Lot Size:\s*([\d,]+)", html_text)
    
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


def parse_sale_history(html_text: str, soup: Optional[BeautifulSoup] = None, sold_banner: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parse the 'Sale and tax history' section into a list of REAL sale/list events ONLY.
    Returns: List of { date: 'YYYY-MM-DD', event: 'listed'|'sold'|'price_changed', price: int, raw_status: str }
    
    CRITICAL ANTI-HALLUCINATION RULES:
    - ONLY parse events labeled "Sold", "Listed", or "Price changed" from the sale history timeline.
    - NEVER use property tax amounts (e.g. $15,403 annual tax) as prices.
    - NEVER use assessed values from the tax table as sale prices.
    - If a listing event shows "*" or no price, skip it (do NOT invent a price).
    - Validate that prices are realistic (>= $100,000) to avoid capturing tax/HOA amounts.
    - NEVER fabricate a sold event.
    - Skip rows containing keywords: "tax", "assessment", "assessed", "property tax"
    
    FALLBACK: 
    - If no PropertyHistoryEventRow found, extract from meta tags (for sold properties).
    - Use sold_banner parameter (e.g., "NOV 21, 2025") to create sold event if needed.
    """

    events: List[Dict[str, Any]] = []

    # Strategy 1: Look for PropertyHistoryEventRow divs
    for match_obj in re.finditer(
        r'<div[^>]*class="[^"]*PropertyHistoryEventRow[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html_text,
        re.DOTALL
    ):
        row_html = match_obj.group(1)
        
        # FILTER OUT TAX ROWS - skip if row contains tax-related keywords
        row_lower = row_html.lower()
        if any(keyword in row_lower for keyword in ["tax", "assessment", "assessed", "property tax"]):
            continue
        
        # Extract date
        date_match = re.search(r'<p>([A-Z][a-z]{2} \d{1,2}, \d{4})</p>', row_html)
        if not date_match:
            continue
        date_str = date_match.group(1)
        
        # Extract event type and status
        event_match = re.search(r'<div>(Sold|Listed|Price\s+changed)\s*\(([^)]+)\)</div>', row_html, re.IGNORECASE)
        if not event_match:
            continue
        event_type_raw = event_match.group(1)
        status = event_match.group(2)
        
        # Normalize event type
        event_type = event_type_raw.lower().replace(" ", "_")
        
        # Extract price
        price_match = re.search(r'<div[^>]*class="[^"]*price-col[^"]*"[^>]*>\$?([\d,]+|\*)', row_html)
        if not price_match:
            continue
        price_str = price_match.group(1)
        
        # Skip if price is "*" (no price listed)
        if price_str == "*":
            continue
            
        try:
            dt = datetime.strptime(date_str, "%b %d, %Y")
            price = int(price_str.replace(",", ""))
            
            # STRICT validation: real estate prices should be >= $100,000
            # This filters out tax amounts (typically $5k-$20k)
            if price < 100000:
                continue
                
        except (ValueError, AttributeError):
            continue
        
        events.append({
            "date": dt.date().isoformat(),
            "event": event_type,
            "price": price,
            "raw_status": status,
        })
    
    # Strategy 2: Fallback to meta tags (for sold properties without timeline)
    if not events:
        # Check for sold price in meta description
        meta_match = re.search(
            r'sold for \$?([\d,]+) on ([A-Z][a-z]{2} \d{1,2}, \d{4})',
            html_text,
            re.IGNORECASE
        )
        if meta_match:
            try:
                price_str = meta_match.group(1)
                date_str = meta_match.group(2)
                price = int(price_str.replace(",", ""))
                dt = datetime.strptime(date_str, "%b %d, %Y")
                if price >= 100000:  # Validate realistic price
                    events.append({
                        "date": dt.date().isoformat(),
                        "event": "sold",
                        "price": price,
                        "raw_status": "Sold (from meta)",
                    })
            except (ValueError, AttributeError):
                pass
    
    # Strategy 3: Use sold_banner if provided and no sold event found
    if sold_banner and not any(e.get("event") == "sold" for e in events):
        try:
            # Parse sold_banner like "NOV 21, 2025"
            dt = datetime.strptime(sold_banner, "%b %d, %Y")
            # Try to extract price from somewhere in the HTML
            # Look for price near SOLD banner
            sold_price_match = re.search(r'SOLD[^$]*\$?([\d,]+)', html_text, re.I | re.DOTALL)
            if sold_price_match:
                price = int(sold_price_match.group(1).replace(",", ""))
                if price >= 100000:
                    events.append({
                        "date": dt.date().isoformat(),
                        "event": "sold",
                        "price": price,
                        "raw_status": "Sold (from banner)",
                    })
        except (ValueError, AttributeError):
            pass

    # Sort by date ascending
    events.sort(key=lambda e: e["date"])
    return events


def get_redfin_data(url: str) -> Dict[str, Any]:
    """
    Fetch and parse Redfin property data.
    
    CRITICAL RULES FOR PRICE DATA:
    1. list_price comes ONLY from [data-rf-test-id="abp-price"] 
    2. timeline[].price comes ONLY from PropertyHistoryEventRow divs with Sold/Listed events
    3. NEVER use:
       - Property tax amounts
       - Assessed values
       - Tax table numbers
       - HOA fees
       - Any non-sale/list numeric value
    
    Returns a dict with:
      - listing stats (beds, baths, SF, list_price, year built)
      - public records (beds, baths, SF, lot_sf, year built, APN)
      - timeline: list of real sale/list events ONLY
      - tax: separate tax/assessment data (never used as prices)
    """
    _ensure_dirs()

    html_path: Optional[Path] = None
    html_text: Optional[str] = None
    soup: Optional[BeautifulSoup] = None

    html_path = fetch_redfin_html(url)
    
    # If fetch failed, return minimal error structure
    if html_path is None:
        return {
            "source": "redfin_fetch_error",
            "url": url,
            "address": "Unknown (Redfin fetch failed)",
            "timeline": [],
            "tax": {},
            "current_summary": "—",
            "public_record_summary": "—",
            "lot_summary": "—",
        }
    
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as e:
        print(f"[WARN] Failed to read Redfin HTML: {e}")

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
            sale_events = parse_sale_history(html_text, soup, sold_banner)
        except Exception as e:
            print(f"[WARN] Failed to parse sale history: {e}")
            sale_events = []

    now = datetime.now().strftime("%Y-%m-%d")
    address_label = listing_parsed.get("address") or _guess_address_from_url(url)

    # Listing stats - NO FAKE DATA, use None if missing
    beds = listing_parsed.get("beds")
    baths = listing_parsed.get("baths")
    building_sf = listing_parsed.get("building_sf")
    lot_sf_listing = listing_parsed.get("lot_sf")  # From listing banner
    list_price = listing_parsed.get("list_price")  # PRICE: from active listing banner ONLY
    listing_year_built = listing_parsed.get("listing_year_built")
    property_type = listing_parsed.get("property_type")
    price_per_sf = listing_parsed.get("price_per_sf")
    sold_banner = listing_parsed.get("sold_banner")  # e.g., "NOV 21, 2025"

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
    
    # Merge lot size: prefer listing banner, fallback to public records
    lot_sf = lot_sf_listing if lot_sf_listing else public_parsed.get("public_lot_sf")

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
    if lot_sf:
        # Format lot size nicely with acres if available
        lot_summary = f"Lot: {int(lot_sf):,} SF"
        # Optionally add acres (1 acre = 43,560 sq ft)
        acres = lot_sf / 43560.0
        if acres >= 0.1:
            lot_summary += f" ({acres:.2f} acres)"
    else:
        lot_summary = "Lot: Data not available"

    redfin_struct: Dict[str, Any] = {
        "source": "redfin_parsed_v3",
        "url": url,
        "address": address_label,
        # listing (current configuration)
        "listing_beds": beds,
        "listing_baths": baths,
        "listing_building_sf": building_sf,
        "listing_year_built": listing_year_built,
        "list_price": list_price,  # PRICE: from active listing banner ONLY
        "property_type": property_type,
        "price_per_sf": price_per_sf,
        "sold_banner": sold_banner,  # SOLD detection
        # backward compatible top-level
        "beds": beds,
        "baths": baths,
        "building_sf": building_sf,
        "lot_sf": lot_sf,
        "year_built": listing_year_built or public_records.get("year_built"),  # Prefer listing, fallback to public
        # timeline: real sale/list history ONLY - NO tax amounts, NO assessed values
        "timeline": sale_events,
        # tax + APN: Keep tax/assessed values separate from prices (NEVER used as prices)
        "tax": {
            "apn": public_parsed.get("apn"),
            "year": 2023,
            "assessed_value": None,  # Could parse from tax table if needed (but NOT as a price)
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
    test_url = "https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580"
    print(f"[TEST] Fetching + parsing Redfin HTML for: {test_url}")
    data = get_redfin_data(test_url)
    print("Structured Redfin data (listing + public records + real sale history):")
    for k, v in data.items():
        print(f"{k}: {v}")
