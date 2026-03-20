from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import os
import re
import shutil
import tempfile
import time
import traceback

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

LADBS_PLR_URL = (
    "https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr"
)
CUTOFF_YEAR = 2018

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
LAST_DRIVER_ERROR_SUMMARY = "ChromeDriver startup failed for an unknown reason."


@dataclass
class DriverSettings:
    chrome_binary: Optional[str]
    chromedriver_path: Optional[str]
    cache_dir: Path
    profile_root: Path
    browser_env_root: Path
    logs_dir: Path
    start_retries: int
    retry_delay_seconds: float
    page_load_timeout_seconds: int
    implicit_wait_seconds: int
    headless: bool


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _resolve_driver_settings() -> DriverSettings:
    cache_dir = Path(os.environ.get("SE_CACHE_PATH") or (DATA_DIR / "selenium-cache"))
    profile_root = Path(
        os.environ.get("LADBS_SELENIUM_PROFILE_DIR") or (DATA_DIR / "browser" / "chrome")
    )
    browser_env_root = Path(os.environ.get("LADBS_BROWSER_ENV_DIR") or (DATA_DIR / "browser-env"))
    logs_dir = DATA_DIR / "logs" / "ladbs"

    for path in (cache_dir, profile_root, browser_env_root, logs_dir):
        path.mkdir(parents=True, exist_ok=True)

    return DriverSettings(
        chrome_binary=os.environ.get("LADBS_CHROME_BINARY") or os.environ.get("CHROME_BINARY"),
        chromedriver_path=os.environ.get("LADBS_CHROMEDRIVER_PATH")
        or os.environ.get("CHROMEDRIVER_PATH"),
        cache_dir=cache_dir,
        profile_root=profile_root,
        browser_env_root=browser_env_root,
        logs_dir=logs_dir,
        start_retries=max(1, _env_int("LADBS_DRIVER_START_RETRIES", 2)),
        retry_delay_seconds=max(0.0, _env_float("LADBS_DRIVER_START_RETRY_DELAY_SECONDS", 2.0)),
        page_load_timeout_seconds=max(10, _env_int("LADBS_PAGE_LOAD_TIMEOUT", 45)),
        implicit_wait_seconds=max(0, _env_int("LADBS_IMPLICIT_WAIT", 1)),
        headless=_env_flag("LADBS_HEADLESS", True),
    )


def get_driver_settings() -> Dict[str, Any]:
    settings = _resolve_driver_settings()
    data = asdict(settings)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data


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
    except Exception as exc:
        print(f"[LADBS] Error extracting address from URL: {exc}")
        return None, None


def _build_chrome_options(settings: DriverSettings, profile_dir: Path) -> "Options":
    chrome_options = Options()
    if settings.headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-breakpad")
    chrome_options.add_argument("--disable-crash-reporter")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-features=Translate,OptimizationGuideModelDownloading")
    chrome_options.add_argument("--hide-crash-restore-bubble")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--password-store=basic")
    chrome_options.add_argument("--remote-debugging-pipe")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")
    chrome_options.page_load_strategy = "eager"

    if settings.chrome_binary:
        chrome_options.binary_location = settings.chrome_binary

    return chrome_options


def _build_chrome_service(settings: DriverSettings, log_path: Path) -> "Service":
    kwargs: Dict[str, Any] = {
        "log_output": str(log_path),
        "env": _build_browser_env(settings),
    }
    if settings.chromedriver_path:
        kwargs["executable_path"] = settings.chromedriver_path
    return Service(**kwargs)


def _build_browser_env(settings: DriverSettings) -> Dict[str, str]:
    env = os.environ.copy()

    local_app_data = settings.browser_env_root / "localapp"
    app_data = settings.browser_env_root / "appdata"
    temp_dir = settings.browser_env_root / "temp"
    for path in (local_app_data, app_data, temp_dir):
        path.mkdir(parents=True, exist_ok=True)

    env["LOCALAPPDATA"] = str(local_app_data)
    env["APPDATA"] = str(app_data)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["SE_CACHE_PATH"] = str(settings.cache_dir)
    return env


def _cleanup_profile_dir(profile_dir: Path | None) -> None:
    if profile_dir:
        shutil.rmtree(profile_dir, ignore_errors=True)


def _log_driver_failure(
    settings: DriverSettings,
    attempt: int,
    error: Exception,
    profile_dir: Path,
    service_log_path: Path,
) -> None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = settings.logs_dir / f"driver_bootstrap_{timestamp}_attempt{attempt}.log"
    log_path.write_text(
        "\n".join(
            [
                f"timestamp: {datetime.now().isoformat()}",
                f"attempt: {attempt}",
                f"profile_dir: {profile_dir}",
                f"service_log_path: {service_log_path}",
                f"settings: {get_driver_settings()}",
                f"browser_env: {_build_browser_env(settings)}",
                f"error: {error}",
                "traceback:",
                traceback.format_exc(),
            ]
        ),
        encoding="utf-8",
    )


def _classify_driver_error(error: Optional[Exception]) -> str:
    message = str(error or "").lower()
    if "cannot create default profile directory" in message:
        return (
            "ChromeDriver could not initialize a writable browser profile. "
            "Check LOCALAPPDATA/TEMP overrides and Chrome policy restrictions."
        )
    if "devtoolsactiveport file doesn't exist" in message:
        return (
            "Chrome launched and crashed before ChromeDriver could attach. "
            "This environment may block Chrome automation IPC or sandboxed headless startup."
        )
    if "platform_channel.cc" in message or "access is denied" in message:
        return (
            "Chrome automation IPC failed with an access-denied error. "
            "This usually points to an environment-level browser sandbox or policy restriction."
        )
    if message:
        return f"ChromeDriver startup failed: {error}"
    return "ChromeDriver startup failed for an unknown reason."


def setup_driver() -> Optional["webdriver.Chrome"]:
    global LAST_DRIVER_ERROR_SUMMARY
    if not SELENIUM_AVAILABLE:
        print("[LADBS] Selenium not installed. Run: pip install selenium")
        LAST_DRIVER_ERROR_SUMMARY = "Selenium is not installed in this environment."
        return None

    settings = _resolve_driver_settings()
    os.environ["SE_CACHE_PATH"] = str(settings.cache_dir)
    browser_env = _build_browser_env(settings)
    for key, value in browser_env.items():
        if key in {"LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "SE_CACHE_PATH"}:
            os.environ[key] = value
    last_error: Optional[Exception] = None

    for attempt in range(1, settings.start_retries + 1):
        profile_dir = Path(tempfile.mkdtemp(prefix="ladbs-", dir=str(settings.profile_root)))
        service_log_path = settings.logs_dir / (
            f"chromedriver_{datetime.now().strftime('%Y%m%d-%H%M%S')}_attempt{attempt}.log"
        )

        try:
            driver = webdriver.Chrome(
                service=_build_chrome_service(settings, service_log_path),
                options=_build_chrome_options(settings, profile_dir),
            )
            driver.set_page_load_timeout(settings.page_load_timeout_seconds)
            driver.implicitly_wait(settings.implicit_wait_seconds)
            setattr(driver, "_codex_profile_dir", str(profile_dir))
            LAST_DRIVER_ERROR_SUMMARY = ""
            return driver
        except Exception as exc:
            last_error = exc
            _log_driver_failure(settings, attempt, exc, profile_dir, service_log_path)
            _cleanup_profile_dir(profile_dir)
            if attempt < settings.start_retries:
                time.sleep(settings.retry_delay_seconds)

    LAST_DRIVER_ERROR_SUMMARY = _classify_driver_error(last_error)
    print(
        f"[LADBS] Error setting up Chrome driver after {settings.start_retries} attempts: "
        f"{LAST_DRIVER_ERROR_SUMMARY}"
    )
    print(f"[LADBS] Review logs under {settings.logs_dir}")
    return None


def cleanup_driver(driver: Optional["webdriver.Chrome"]) -> None:
    if not driver:
        return

    profile_dir = getattr(driver, "_codex_profile_dir", None)
    try:
        driver.quit()
    except Exception:
        pass

    if profile_dir:
        _cleanup_profile_dir(Path(profile_dir))


def search_plr(driver: "webdriver.Chrome", street_number: str, street_name: str) -> Optional[str]:
    print(f"[LADBS] Opening PLR page: {LADBS_PLR_URL}")
    driver.get(LADBS_PLR_URL)

    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(., 'Street Number')]")))

    try:
        street_no_label = driver.find_element(By.XPATH, "//label[contains(., 'Street Number')]")
        street_no_input = street_no_label.find_element(By.XPATH, ".//following::input[1]")
    except Exception as exc:
        print(f"[LADBS] Could not locate Street Number input: {exc}")
        return None

    try:
        street_name_label = driver.find_element(By.XPATH, "//label[contains(., 'Street Name')]")
        street_name_input = street_name_label.find_element(By.XPATH, ".//following::input[1]")
    except Exception as exc:
        print(f"[LADBS] Could not locate Street Name input: {exc}")
        return None

    print(f"[LADBS] Filling Single Address Search with: {street_number} {street_name}")
    street_no_input.clear()
    street_no_input.send_keys(street_number)

    street_name_input.clear()
    street_name_input.send_keys(street_name)

    try:
        search_button = driver.find_element(
            By.XPATH,
            "//button[contains(., 'Search')] | //input[@type='submit' and contains(@value, 'Search')]",
        )
        search_button.click()
    except Exception as exc:
        print(f"[LADBS] Could not click Search button: {exc}")
        return None

    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    current_url = driver.current_url

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_street = street_name.replace(" ", "_")
    out_path = RAW_DIR / f"{timestamp}_ladbs_{street_number}_{safe_street}.html"
    out_path.write_text(driver.page_source, encoding="utf-8", errors="ignore")

    return current_url


def get_permit_list(driver: "webdriver.Chrome") -> List[Dict[str, Any]]:
    print("[LADBS] Extracting permit list ...")
    wait = WebDriverWait(driver, 15)

    tables: List[Any] = []
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
            )
        )
        tables = driver.find_elements(By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
        print(f"[LADBS] Found {len(tables)} permit tables directly")
    except Exception:
        print("[LADBS] Direct table lookup failed; trying to expand accordions")

    if not tables:
        try:
            permit_header = wait.until(EC.element_to_be_clickable((By.ID, "pcis")))
            header_class = permit_header.get_attribute("class") or ""
            if "ui-state-active" not in header_class:
                print("[LADBS] Clicking main permit accordion...")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", permit_header)
                time.sleep(0.5)
                permit_header.click()
                time.sleep(1.5)
        except Exception as exc:
            print(f"[LADBS] Could not expand main accordion: {exc}")

        try:
            wait_short = WebDriverWait(driver, 5)
            wait_short.until(
                EC.presence_of_element_located((By.XPATH, "//h3[contains(@class, 'accordianAddress')]"))
            )
            address_rows = driver.find_elements(By.XPATH, "//h3[contains(@class, 'accordianAddress')]")
            print(f"[LADBS] Found {len(address_rows)} address accordions to expand")
            for idx, row in enumerate(address_rows):
                try:
                    row_class = row.get_attribute("class") or ""
                    if "ui-state-active" not in row_class:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                        time.sleep(0.3)
                        row.click()
                        time.sleep(1.0)
                        print(f"[LADBS] Expanded address accordion {idx + 1}")
                except Exception as exc:
                    print(f"[LADBS] Could not expand address accordion {idx + 1}: {exc}")
        except Exception as exc:
            print(f"[LADBS] No address accordions found: {exc}")

        try:
            time.sleep(1.0)
            tables = driver.find_elements(By.XPATH, "//table[.//th[contains(., 'Application/Permit')]]")
            print(f"[LADBS] After expansion, found {len(tables)} permit tables")
        except Exception as exc:
            print(f"[LADBS] Still no tables after expansion: {exc}")
            return []

    if not tables:
        print("[LADBS] No permit tables found after all attempts")
        return []

    permits: List[Dict[str, Any]] = []

    for table_idx, table in enumerate(tables):
        print(f"[LADBS] Processing table {table_idx + 1}/{len(tables)}")
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
                    except ValueError:
                        permit_dt = None

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
            except Exception as exc:
                print(f"[LADBS] Error parsing row: {exc}")
                continue

    return permits


def _get_detail_value(driver: "webdriver.Chrome", label_text: str) -> Optional[str]:
    try:
        dt = driver.find_element(By.XPATH, f"//dt[contains(normalize-space(), '{label_text}')]")
        dd = dt.find_element(By.XPATH, "./following-sibling::dd[1]")
        return dd.text.strip()
    except Exception:
        return None


def get_permit_details(driver: "webdriver.Chrome", permit_url: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    try:
        driver.get(permit_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except Exception:
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

    contact_info: Dict[str, str] = {}
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
    except Exception:
        pass
    details["contact_information"] = contact_info

    status_history: List[Dict[str, str]] = []
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
    except Exception:
        pass
    details["status_history"] = status_history

    return details


def _extract_name_and_license(info: str) -> Tuple[str, Optional[str]]:
    if not info:
        return "", None
    match = re.search(r"(\d{6,})", info)
    license_number = match.group(1) if match else None
    return info, license_number


def _summarize_permit(details: Dict[str, Any]) -> Dict[str, Any]:
    permit_number = details.get("permit_number", "N/A")
    job_number = details.get("job_number", "N/A")
    permit_type = details.get("type", "N/A")
    sub_type = details.get("sub_type", "")
    full_type = permit_type if not sub_type else f"{permit_type} - {sub_type}"
    status = details.get("current_status", "N/A")
    work_desc = details.get("work_description", "N/A")
    issued = details.get("permit_issued", "N/A")

    contact = details.get("contact_information", {})
    contractor_raw = None
    architect_raw = None
    engineer_raw = None

    for role_key, value in contact.items():
        upper_role = role_key.upper()
        if "CONTRACTOR" in upper_role and not contractor_raw:
            contractor_raw = value
        elif "ARCHITECT" in upper_role and not architect_raw:
            architect_raw = value
        elif "ENGINEER" in upper_role and not engineer_raw:
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
        settings = _resolve_driver_settings()
        return {
            "source": "ladbs_stub_driver_error",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": (
                f"{LAST_DRIVER_ERROR_SUMMARY} "
                f"Review LADBS logs under {settings.logs_dir} and confirm Chrome/ChromeDriver settings."
            ),
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

        for permit_basic in permits_basic:
            details = get_permit_details(driver, permit_basic["url"])
            if details:
                if permit_basic.get("status_date"):
                    details.setdefault("status_date", permit_basic["status_date"])
                permits_slim.append(_summarize_permit(details))
    finally:
        cleanup_driver(driver)

    return {
        "source": "ladbs_plr_v6",
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
    for key, value in data.items():
        if key == "permits":
            print(f"{key}: {len(value)} permits")
        else:
            print(f"{key}: {value}")
