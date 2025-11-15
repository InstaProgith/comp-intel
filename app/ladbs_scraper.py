"""
LADBS PLR automation for comp-intel.

Flow:
1) Open PLR URL and run Single Address Search (Street Number + Street Name).
2) On results page:
   - Try to directly locate the permit table(s) by header "Application/Permit #".
   - If not found, click h3#pcis ("Permit Information found") and h3.accordianAddress,
     then locate table(s).
   - For each permit row, capture permit number, detail URL, status text/date.
   - Keep only permits with status date year >= CUTOFF_YEAR.
3) For each kept permit:
   - Open detail page.
   - Extract general info (from <dt>/<dd>), Contact Information, Status History.
   - Summarize into a compact record with:
       - permit_number, job_number
       - permit_type
       - current_status
       - work_description
       - issued_date
       - status_date (from list page)
       - contractor / architect / engineer names
       - optional contractor/engineer/architect license numbers (if visible)
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import re

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

LADBS_PLR_URL = (
    "https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr"
)
CUTOFF_YEAR = 2020
FIVE_YEARS_AGO = datetime.now() - timedelta(days=5 * 365)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------------
# Helpers: address from Redfin URL
# -------------------------------------------------------------------


def extract_address_from_redfin_url(redfin_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract street number + street name from a Redfin URL.
    Example:
      https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003
    -> ('1120', 'Lucerne')
    """
    try:
        path = urlparse(redfin_url).path
        parts = path.split("/")
        # ['', 'CA', 'Los-Angeles', '1120-S-Lucerne-Blvd-90019', 'home', '6911003']
        if len(parts) < 4:
            return None, None
        address_part = parts[3]

        address_components = address_part.split("-")[:-1]  # drop ZIP
        if not address_components:
            return None, None

        street_number = address_components[0]
        street_name_parts = address_components[1:]

        clean_parts: List[str] = []
        for part in street_name_parts:
            if part.upper() not in [
                "N",
                "S",
                "E",
                "W",
                "BLVD",
                "ST",
                "AVE",
                "RD",
                "PL",
                "DR",
                "CT",
                "LN",
                "WAY",
            ]:
                clean_parts.append(part)

        street_name = " ".join(clean_parts) if clean_parts else ""
        return street_number, street_name
    except Exception as e:
        print(f"[LADBS] Error extracting address from URL: {e}")
        return None, None


# -------------------------------------------------------------------
# Selenium setup
# -------------------------------------------------------------------


def setup_driver() -> Optional[webdriver.Chrome]:
    if not SELENIUM_AVAILABLE:
        print("[LADBS] Selenium not installed. Run: pip install selenium")
        return None

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    # For debugging you usually want to SEE Chrome; for headless, uncomment:
    # chrome_options.add_argument("--headless=new")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"[LADBS] Error setting up Chrome driver: {e}")
        print("Make sure Chrome + ChromeDriver are installed and on PATH.")
        return None


# -------------------------------------------------------------------
# Step 1–2: PLR search
# -------------------------------------------------------------------


def search_plr(driver, street_number: str, street_name: str) -> Optional[str]:
    """
    Run Single Address Search and save the results HTML.
    """
    print(f"[LADBS] Opening PLR page: {LADBS_PLR_URL}")
    driver.get(LADBS_PLR_URL)

    wait = WebDriverWait(driver, 20)

    # Wait for "Street Number" label
    wait.until(
        EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Street Number')]"))
    )

    # Street Number input = first input after label "Street Number"
    try:
        street_no_label = driver.find_element(By.XPATH, "//label[contains(., 'Street Number')]")
        street_no_input = street_no_label.find_element(By.XPATH, ".//following::input[1]")
    except Exception as e:
        print(f"[LADBS] Could not locate Street Number input: {e}")
        return None

    # Street Name input = first input after label "Street Name"
    try:
        street_name_label = driver.find_element(By.XPATH, "//label[contains(., 'Street Name')]")
        street_name_input = street_name_label.find_element(By.XPATH, ".//following::input[1]")
    except Exception as e:
        print(f"[LADBS] Could not locate Street Name input: {e}")
        return None

    print(f"[LADBS] Filling Single Address Search with: {street_number} {street_name}")
    street_no_input.clear()
    street_no_input.send_keys(street_number)

    street_name_input.clear()
    street_name_input.send_keys(street_name)

    # Search button
    try:
        search_button = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Search')] | "
            "//input[@type='submit' and contains(@value, 'Search')]",
        )
        search_button.click()
    except Exception as e:
        print(f"[LADBS] Could not click Search button: {e}")
        return None

    # Wait for results page
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    current_url = driver.current_url
    print(f"[LADBS] Results page URL: {current_url}")

    # Save raw HTML for debugging/reference
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_street = street_name.replace(" ", "_")
    out_path = RAW_DIR / f"{timestamp}_ladbs_{street_number}_{safe_street}.html"
    html = driver.page_source
    out_path.write_text(html, encoding="utf-8", errors="ignore")
    print(f"[LADBS] Saved PLR results HTML to {out_path}")

    return current_url


# -------------------------------------------------------------------
# Step 3: permit table listing
# -------------------------------------------------------------------


def get_permit_list(driver) -> List[Dict[str, Any]]:
    """
    From the results page:
      - Prefer: directly locate the permit table(s) by header "Application/Permit #".
      - Fallback: expand Permit Information section (h3#pcis) and address rows (h3.accordianAddress),
        then locate permit table(s).
      - Return permits where status date year >= CUTOFF_YEAR.
    """
    print("[LADBS] Extracting permit list ...")
    wait = WebDriverWait(driver, 10)

    tables: List[Any] = []
    # Direct approach
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
            )
        )
        tables = driver.find_elements(
            By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]"
        )
        if tables:
            print(f"[LADBS] Found {len(tables)} permit table(s) without extra clicks.")
    except Exception:
        print("[LADBS] Direct table lookup failed; will try expanding accordions.")

    # Fallback: expand accordions then search tables again
    if not tables:
        # Expand "Permit Information found"
        print("[LADBS] Expanding 'Permit Information found' section via h3#pcis...")
        try:
            permit_header = wait.until(EC.presence_of_element_located((By.ID, "pcis")))
            header_class = permit_header.get_attribute("class") or ""
            if "ui-state-active" not in header_class:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", permit_header
                )
                permit_header.click()
                print("[LADBS] Clicked 'Permit Information found' (h3#pcis).")
            else:
                print("[LADBS] 'Permit Information found' already active; no click needed.")
        except Exception as e:
            print(f"[LADBS] Failed to find or handle 'Permit Information found': {e}")

        # Expand address rows
        print("[LADBS] Expanding address rows (h3.accordianAddress)...")
        try:
            address_row_xpath = "//h3[contains(@class, 'accordianAddress')]"
            wait.until(EC.presence_of_element_located((By.XPATH, address_row_xpath)))
            address_rows = driver.find_elements(By.XPATH, address_row_xpath)
            print(f"[LADBS] Found {len(address_rows)} address row(s).")
            for i, row in enumerate(address_rows):
                try:
                    addr_text = row.text.strip().split("\n")[0]
                    print(f"[LADBS] Clicking address row {i+1}: {addr_text!r}")
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", row
                    )
                    row.click()
                except Exception as e:
                    print(f"[LADBS] Could not click address row: {e}")
        except Exception as e:
            print(f"[LADBS] Error finding or expanding address rows: {e}")

        # Find tables after expansion
        print("[LADBS] Locating permit table(s) after expanding sections...")
        try:
            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
                )
            )
            tables = driver.find_elements(
                By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]"
            )
            print(f"[LADBS] Found {len(tables)} permit table(s) after expansion.")
        except Exception as e:
            print(f"[LADBS] Could not find permit table after expanding sections: {e}")
            driver.save_screenshot(str(RAW_DIR / "debug_table_not_found.png"))
            print(f"[LADBS] Saved debug screenshot to {RAW_DIR}")
            return []

    permits: List[Dict[str, Any]] = []

    for table in tables:
        rows = table.find_elements(By.XPATH, ".//tr[position() > 1]")  # Skip header
        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 4:
                    continue

                link = cols[0].find_element(By.TAG_NAME, "a")
                permit_number = link.text.strip()
                permit_url = link.get_attribute("href")

                status_text = cols[3].text.strip()
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", status_text)
                permit_date_str = date_match.group(1) if date_match else None

                permit_dt: Optional[datetime] = None
                if permit_date_str:
                    try:
                        permit_dt = datetime.strptime(permit_date_str, "%m/%d/%Y")
                    except Exception:
                        permit_dt = None

                # Filter by cutoff year
                if permit_dt is not None and permit_dt.year < CUTOFF_YEAR:
                    continue

                permits.append(
                    {
                        "permit_number": permit_number,
                        "url": permit_url,
                        "status_text": status_text,
                        "status_date": permit_date_str,  # mm/dd/yyyy string
                    }
                )
            except Exception as e:
                print(f"[LADBS] Error parsing permit row: {e}")
                continue

    print(f"[LADBS] Found {len(permits)} permits with status date >= {CUTOFF_YEAR}.")
    return permits


# -------------------------------------------------------------------
# Step 4: permit detail pages
# -------------------------------------------------------------------


def _get_detail_value(driver, label_text: str) -> Optional[str]:
    """
    Helper to find a <dt> by its text and return the text of the
    immediately following <dd>.
    """
    try:
        dt = driver.find_element(
            By.XPATH, f"//dt[contains(normalize-space(), '{label_text}')]"
        )
        dd = dt.find_element(By.XPATH, "./following-sibling::dd[1]")
        return dd.text.strip()
    except Exception:
        return None


def get_permit_details(driver, permit_url: str) -> Dict[str, Any]:
    print(f"[LADBS] -> Details from {permit_url}")
    details: Dict[str, Any] = {}

    try:
        driver.get(permit_url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        print(f"[LADBS] Error loading permit page: {e}")
        return details

    general_info_map = {
        "Application / Permit": "permit_number",
        "Plan Check / Job No.": "job_number",
        "Group": "group",
        "Type": "type",
        "Sub-Type": "sub_type",
        "Primary Use": "primary_use",
        "Work Description": "work_description",
        "Permit Issued": "permit_issued",
        "Current Status": "current_status",
        "Issuing Office": "issuing_office",
        "Certificate of Occupancy": "certificate_of_occupancy",
    }

    for label_text, key in general_info_map.items():
        value = _get_detail_value(driver, label_text)
        if value:
            details[key] = value

    # Contact Information
    contact_info: Dict[str, str] = {}
    try:
        header = driver.find_element(By.XPATH, "//h3[contains(., 'Contact Information')]")
        table = header.find_element(By.XPATH, "following-sibling::table[1]")
        for row in table.find_elements(By.TAG_NAME, "tr"):
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 2:
                role = cols[0].text.strip().replace(":", "")
                info = cols[1].text.strip()
                if len(cols) > 2:
                    info += " " + cols[2].text.strip()
                contact_info[role] = info
    except Exception:
        pass
    details["contact_information"] = contact_info

    # Status history
    status_history: List[Dict[str, str]] = []
    try:
        header = driver.find_element(
            By.XPATH, "//h3[contains(., 'Permit Application Status History')]"
        )
        table = header.find_element(By.XPATH, "following-sibling::table[1]")
        for row in table.find_elements(By.TAG_NAME, "tr"):
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 3:
                status_history.append(
                    {
                        "event": cols[0].text.strip(),
                        "date": cols[1].text.strip(),
                        "person": cols[2].text.strip(),
                    }
                )
    except Exception:
        pass
    details["status_history"] = status_history

    return details


def _extract_name_and_license(info: str) -> Tuple[str, Optional[str]]:
    """
    Given a contact info string from LADBS (e.g. "ABC CONST INC LIC 123456"),
    return (full_string_as_name, license_number_if_any).
    We do NOT fabricate; license is only taken if digits are present.
    """
    if not info:
        return "", None
    # Very simple: first 6+ digit run is treated as license number if present.
    m = re.search(r"(\d{6,})", info)
    lic = m.group(1) if m else None
    return info, lic


def _summarize_permit(details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact summary for each permit with explicit fields used downstream.
    """
    permit_number = details.get("permit_number", "N/A")
    job_number = details.get("job_number", "N/A")
    typ = details.get("type", "N/A")
    sub_type = details.get("sub_type", "")
    full_type = typ if not sub_type else f"{typ} - {sub_type}"
    status = details.get("current_status", "N/A")
    work_desc = details.get("work_description", "N/A")
    issued = details.get("permit_issued", "N/A")

    contact_info = details.get("contact_information") or {}

    contractor_raw = None
    architect_raw = None
    engineer_raw = None

    # Normalize role keys lightly (LADBS uses "Contractor", "Engineer", "Architect").
    for role_key, value in contact_info.items():
        role_upper = role_key.upper()
        if "CONTRACTOR" in role_upper and not contractor_raw:
            contractor_raw = value
        elif "ARCHITECT" in role_upper and not architect_raw:
            architect_raw = value
        elif "ENGINEER" in role_upper and not engineer_raw:
            engineer_raw = value

    contractor_name, contractor_license = (
        _extract_name_and_license(contractor_raw) if contractor_raw else ("", None)
    )
    architect_name, architect_license = (
        _extract_name_and_license(architect_raw) if architect_raw else ("", None)
    )
    engineer_name, engineer_license = (
        _extract_name_and_license(engineer_raw) if engineer_raw else ("", None)
    )

    # Status date from list page, if we carried it through
    status_date = details.get("status_date")  # expected "mm/dd/yyyy" string

    return {
        "permit_number": permit_number,
        "job_number": job_number,
        "permit_type": full_type,  # used for UI ribbon and metrics
        "Type": full_type,  # backward compatible label
        "Status": status,
        "status_date": status_date,
        "Work_Description": work_desc,
        "Issued_Date": issued,
        "contractor": contractor_name or None,
        "contractor_license": contractor_license,
        "architect": architect_name or None,
        "architect_license": architect_license,
        "engineer": engineer_name or None,
        "engineer_license": engineer_license,
        "raw_details": details,
    }


# -------------------------------------------------------------------
# Public entry point
# -------------------------------------------------------------------


def get_ladbs_data(
    apn: Optional[str],
    address: Optional[str],
    redfin_url: Optional[str],
) -> Dict[str, Any]:
    """
    Main entry used by orchestrator.py.
    Uses Redfin URL to derive street number/name → searches PLR → gets permit list → gets detail pages.
    """
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not SELENIUM_AVAILABLE:
        return {
            "source": "ladbs_stub_no_selenium",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": "Selenium not installed; LADBS not queried.",
        }

    if not redfin_url:
        return {
            "source": "ladbs_stub_no_url",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": "No Redfin URL provided; cannot derive LADBS address.",
        }

    street_number, street_name = extract_address_from_redfin_url(redfin_url)
    if not street_number or not street_name:
        return {
            "source": "ladbs_stub_bad_address",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": f"Could not extract street number/name from Redfin URL: {redfin_url}",
        }

    driver = setup_driver()
    if not driver:
        return {
            "source": "ladbs_stub_driver_error",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": "Failed to start Chrome driver.",
        }

    permits_slim: List[Dict[str, Any]] = []

    try:
        results_url = search_plr(driver, street_number, street_name)
        if not results_url:
            return {
                "source": "ladbs_no_results_page",
                "apn": apn,
                "address": address,
                "fetched_at": fetched_at,
                "permits": [],
                "note": f"PLR search did not return a results page for {street_number} {street_name}.",
            }

        permits_basic = get_permit_list(driver)
        if not permits_basic:
            return {
                "source": "ladbs_no_permits_found",
                "apn": apn,
                "address": address,
                "fetched_at": fetched_at,
                "permits": [],
                "note": f"No permits with status date >= {CUTOFF_YEAR} found for this address.",
            }

        for idx, pb in enumerate(permits_basic, start=1):
            print(f"[LADBS] Processing permit {idx}/{len(permits_basic)}: {pb['permit_number']}")
            details = get_permit_details(driver, pb["url"])
            if details:
                # Carry status_date from list page into details so summary can keep it
                if pb.get("status_date"):
                    details.setdefault("status_date", pb["status_date"])
                permits_slim.append(_summarize_permit(details))

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return {
        "source": "ladbs_plr_v5",
        "apn": apn,
        "address": address,
        "fetched_at": fetched_at,
        "permits": permits_slim,
        "note": f"Found {len(permits_slim)} permits with status date >= {CUTOFF_YEAR} via PLR.",
    }


if __name__ == "__main__":
    test_redfin_url = (
        "https://www.redfin.com/CA/Sherman-Oaks/13157-Otsego-St-91423/home/5216364"
    )
    print(f"[TEST] LADBS PLR data for {test_redfin_url}")
    data = get_ladbs_data(apn=None, address=None, redfin_url=test_redfin_url)
    for k, v in data.items():
        if k == "permits":
            print(f"{k}: {len(v)} permits")
        else:
            print(f"{k}: {v}")
