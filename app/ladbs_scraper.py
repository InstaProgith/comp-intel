# BEGIN FULL FILE REPLACEMENT (overwrite ENTIRE file)
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
        street_name_parts = address_components[1:]

        clean_parts: List[str] = []
        for part in street_name_parts:
            if part.upper() not in [
                "N","S","E","W","BLVD","ST","AVE","RD","PL","DR","CT","LN","WAY"
            ]:
                clean_parts.append(part)

        street_name = " ".join(clean_parts) if clean_parts else ""
        return street_number, street_name
    except Exception as e:
        print(f"[LADBS] Error extracting address from URL: {e}")
        return None, None


def setup_driver() -> Optional[webdriver.Chrome]:
    if not SELENIUM_AVAILABLE:
        print("[LADBS] Selenium not installed. Run: pip install selenium")
        return None

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--remote-debugging-port=9222")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"[LADBS] Error setting up Chrome driver: {e}")
        print("Make sure Chrome + ChromeDriver are installed and on PATH.")
        return None


def search_plr(driver, street_number: str, street_name: str) -> Optional[str]:
    print(f"[LADBS] Opening PLR page: {LADBS_PLR_URL}")
    driver.get(LADBS_PLR_URL)

    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Street Number')]")))

    try:
        street_no_label = driver.find_element(By.XPATH, "//label[contains(., 'Street Number')]")
        street_no_input = street_no_label.find_element(By.XPATH, ".//following::input[1]")
    except Exception as e:
        print(f"[LADBS] Could not locate Street Number input: {e}")
        return None

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

    try:
        search_button = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Search')] | //input[@type='submit' and contains(@value, 'Search')]"
        )
        search_button.click()
    except Exception as e:
        print(f"[LADBS] Could not click Search button: {e}")
        return None

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    current_url = driver.current_url

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_street = street_name.replace(" ", "_")
    out_path = RAW_DIR / f"{timestamp}_ladbs_{street_number}_{safe_street}.html"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(driver.page_source, encoding="utf-8", errors="ignore")

    return current_url


def get_permit_list(driver) -> List[Dict[str, Any]]:
    print("[LADBS] Extracting permit list ...")
    wait = WebDriverWait(driver, 15)

    tables: List[Any] = []
    try:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
        ))
        tables = driver.find_elements(
            By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]"
        )
        print(f"[LADBS] Found {len(tables)} permit tables directly")
    except Exception:
        print("[LADBS] Direct table lookup failed; trying to expand accordions")

    if not tables:
        # Step 1: Expand main "Permit Information" accordion
        try:
            permit_header = wait.until(EC.element_to_be_clickable((By.ID, "pcis")))
            header_class = permit_header.get_attribute("class") or ""
            if "ui-state-active" not in header_class:
                print("[LADBS] Clicking main permit accordion...")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", permit_header)
                import time
                time.sleep(0.5)
                permit_header.click()
                time.sleep(1.5)  # Wait for accordion animation
        except Exception as e:
            print(f"[LADBS] Could not expand main accordion: {e}")

        # Step 2: Expand address-specific accordions
        try:
            wait_short = WebDriverWait(driver, 5)
            wait_short.until(EC.presence_of_element_located(
                (By.XPATH, "//h3[contains(@class, 'accordianAddress')]")
            ))
            address_rows = driver.find_elements(By.XPATH, "//h3[contains(@class, 'accordianAddress')]")
            print(f"[LADBS] Found {len(address_rows)} address accordions to expand")
            for idx, r in enumerate(address_rows):
                try:
                    row_class = r.get_attribute("class") or ""
                    if "ui-state-active" not in row_class:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
                        import time
                        time.sleep(0.3)
                        r.click()
                        time.sleep(1.0)  # Wait for animation
                        print(f"[LADBS] Expanded address accordion {idx+1}")
                except Exception as e:
                    print(f"[LADBS] Could not expand address accordion {idx+1}: {e}")
        except Exception as e:
            print(f"[LADBS] No address accordions found: {e}")

        # Step 3: Now try to find tables again
        try:
            import time
            time.sleep(1)  # Final wait for DOM to settle
            tables = driver.find_elements(
                By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]"
            )
            print(f"[LADBS] After expansion, found {len(tables)} permit tables")
        except Exception as e:
            print(f"[LADBS] Still no tables after expansion: {e}")
            return []

    if not tables:
        print("[LADBS] No permit tables found after all attempts")
        return []

    permits: List[Dict[str, Any]] = []

    for table_idx, table in enumerate(tables):
        print(f"[LADBS] Processing table {table_idx+1}/{len(tables)}")
        rows = table.find_elements(By.XPATH, ".//tr[position()>1]")
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

                permit_dt = None
                if permit_date_str:
                    try:
                        permit_dt = datetime.strptime(permit_date_str, "%m/%d/%Y")
                    except:
                        pass

                if permit_dt and permit_dt.year < CUTOFF_YEAR:
                    print(f"[LADBS] Skipping old permit {permit_number} from {permit_dt.year}")
                    continue

                print(f"[LADBS] Found permit: {permit_number}")
                permits.append(
                    {
                        "permit_number": permit_number,
                        "url": permit_url,
                        "status_text": status_text,
                        "status_date": permit_date_str,
                    }
                )
            except Exception as e:
                print(f"[LADBS] Error parsing row: {e}")
                continue

    return permits


def _get_detail_value(driver, label_text: str) -> Optional[str]:
    try:
        dt = driver.find_element(
            By.XPATH, f"//dt[contains(normalize-space(), '{label_text}')]"
        )
        dd = dt.find_element(By.XPATH, "./following-sibling::dd[1]")
        return dd.text.strip()
    except:
        return None


def get_permit_details(driver, permit_url: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    try:
        driver.get(permit_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except:
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

    for lt, key in general_info_map.items():
        v = _get_detail_value(driver, lt)
        if v:
            details[key] = v

    contact_info = {}
    try:
        header = driver.find_element(By.XPATH, "//h3[contains(., 'Contact Information')]")
        table = header.find_element(By.XPATH, "following-sibling::table[1]")
        for row in table.find_elements(By.TAG_NAME, "tr"):
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 2:
                role = cols[0].text.strip().replace(":", "")
                value = cols[1].text.strip()
                if len(cols) > 2:
                    value += " " + cols[2].text.strip()
                contact_info[role] = value
    except:
        pass
    details["contact_information"] = contact_info

    status_history = []
    try:
        header = driver.find_element(By.XPATH, "//h3[contains(., 'Permit Application Status History')]")
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
    except:
        pass
    details["status_history"] = status_history

    return details


def _extract_name_and_license(info: str) -> Tuple[str, Optional[str]]:
    if not info:
        return "", None
    m = re.search(r"(\d{6,})", info)
    lic = m.group(1) if m else None
    return info, lic


def _summarize_permit(details: Dict[str, Any]) -> Dict[str, Any]:
    permit_number = details.get("permit_number", "N/A")
    job_number = details.get("job_number", "N/A")
    typ = details.get("type", "N/A")
    sub_type = details.get("sub_type", "")
    full_type = typ if not sub_type else f"{typ} - {sub_type}"
    status = details.get("current_status", "N/A")
    work_desc = details.get("work_description", "N/A")
    issued = details.get("permit_issued", "N/A")

    contact = details.get("contact_information", {})
    contractor_raw = None
    architect_raw = None
    engineer_raw = None

    for role_key, value in contact.items():
        u = role_key.upper()
        if "CONTRACTOR" in u and not contractor_raw:
            contractor_raw = value
        elif "ARCHITECT" in u and not architect_raw:
            architect_raw = value
        elif "ENGINEER" in u and not engineer_raw:
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

    status_date = details.get("status_date")

    return {
        "permit_number": permit_number,
        "job_number": job_number,
        "permit_type": full_type,
        "Type": full_type,
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


def get_ladbs_data(
    apn: Optional[str],
    address: Optional[str],
    redfin_url: Optional[str],
) -> Dict[str, Any]:

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
            details = get_permit_details(driver, pb["url"])
            if details:
                if pb.get("status_date"):
                    details.setdefault("status_date", pb["status_date"])
                permits_slim.append(_summarize_permit(details))

    finally:
        try:
            driver.quit()
        except:
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
# END FULL FILE REPLACEMENT
