from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import os
import re
import shutil
import subprocess
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
WINDOWS_CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Chromium\Application\chrome.exe"),
]
WINDOWS_CHROMEDRIVER_CANDIDATES = [
    BASE_DIR / "chromedriver.exe",
]
INHERITED_BROWSER_ENV_KEYS_TO_REMOVE = {
    "CHROME_CRASHPAD_PIPE_NAME",
    "CHROME_HEADLESS",
    "ELECTRON_RUN_AS_NODE",
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


@dataclass
class DriverSettings:
    chrome_binary: Optional[str]
    chrome_binary_source: Optional[str]
    chromedriver_path: Optional[str]
    chromedriver_source: Optional[str]
    cache_dir: Path
    profile_root: Path
    browser_env_root: Path
    logs_dir: Path
    start_retries: int
    retry_delay_seconds: float
    page_load_timeout_seconds: int
    implicit_wait_seconds: int
    headless: bool
    allow_headed_fallback: bool
    use_remote_debugging_pipe: bool
    browser_probe_timeout_seconds: int


@dataclass(frozen=True)
class BrowserStartupMode:
    name: str
    headless: bool
    use_remote_debugging_pipe: bool


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


def _first_existing_path(candidates: List[Tuple[Path, str]]) -> Tuple[Optional[str], Optional[str]]:
    seen: set[str] = set()
    for candidate, source in candidates:
        candidate_str = str(candidate)
        key = candidate_str.lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate_str, source
    return None, None


def _discover_chrome_binary() -> Tuple[Optional[str], Optional[str]]:
    env_candidates: List[Tuple[Path, str]] = []
    for env_name in ("LADBS_CHROME_BINARY", "CHROME_BINARY"):
        value = os.environ.get(env_name)
        if value:
            env_candidates.append((Path(value), f"env:{env_name}"))

    path_candidates: List[Tuple[Path, str]] = []
    for command_name in ("chrome.exe", "chrome"):
        resolved = shutil.which(command_name)
        if resolved:
            path_candidates.append((Path(resolved), f"path:{command_name}"))

    common_candidates = [(path, "common-path") for path in WINDOWS_CHROME_CANDIDATES]
    return _first_existing_path(env_candidates + path_candidates + common_candidates)


def _discover_chromedriver_path() -> Tuple[Optional[str], Optional[str]]:
    env_candidates: List[Tuple[Path, str]] = []
    for env_name in ("LADBS_CHROMEDRIVER_PATH", "CHROMEDRIVER_PATH"):
        value = os.environ.get(env_name)
        if value:
            env_candidates.append((Path(value), f"env:{env_name}"))

    path_candidates: List[Tuple[Path, str]] = []
    for command_name in ("chromedriver.exe", "chromedriver"):
        resolved = shutil.which(command_name)
        if resolved:
            path_candidates.append((Path(resolved), f"path:{command_name}"))

    repo_candidates: List[Tuple[Path, str]] = [(path, "repo:chromedriver") for path in WINDOWS_CHROMEDRIVER_CANDIDATES]
    repo_root = BASE_DIR / "chromedriver"
    if repo_root.exists():
        for path in sorted(repo_root.rglob("chromedriver.exe"), reverse=True):
            repo_candidates.append((path, "repo:chromedriver"))

    return _first_existing_path(env_candidates + path_candidates + repo_candidates)


def _resolve_driver_settings() -> DriverSettings:
    cache_dir = Path(os.environ.get("SE_CACHE_PATH") or (DATA_DIR / "selenium-cache"))
    profile_root = Path(
        os.environ.get("LADBS_SELENIUM_PROFILE_DIR") or (DATA_DIR / "browser" / "chrome")
    )
    browser_env_root = Path(os.environ.get("LADBS_BROWSER_ENV_DIR") or (DATA_DIR / "browser-env"))
    logs_dir = DATA_DIR / "logs" / "ladbs"
    chrome_binary, chrome_binary_source = _discover_chrome_binary()
    chromedriver_path, chromedriver_source = _discover_chromedriver_path()

    for path in (cache_dir, profile_root, browser_env_root, logs_dir):
        path.mkdir(parents=True, exist_ok=True)

    return DriverSettings(
        chrome_binary=chrome_binary,
        chrome_binary_source=chrome_binary_source,
        chromedriver_path=chromedriver_path,
        chromedriver_source=chromedriver_source,
        cache_dir=cache_dir,
        profile_root=profile_root,
        browser_env_root=browser_env_root,
        logs_dir=logs_dir,
        start_retries=max(1, _env_int("LADBS_DRIVER_START_RETRIES", 2)),
        retry_delay_seconds=max(0.0, _env_float("LADBS_DRIVER_START_RETRY_DELAY_SECONDS", 2.0)),
        page_load_timeout_seconds=max(10, _env_int("LADBS_PAGE_LOAD_TIMEOUT", 45)),
        implicit_wait_seconds=max(0, _env_int("LADBS_IMPLICIT_WAIT", 1)),
        headless=_env_flag("LADBS_HEADLESS", True),
        allow_headed_fallback=_env_flag("LADBS_ALLOW_HEADED_FALLBACK", True),
        use_remote_debugging_pipe=_env_flag("LADBS_USE_REMOTE_DEBUGGING_PIPE", False),
        browser_probe_timeout_seconds=max(3, _env_int("LADBS_BROWSER_PROBE_TIMEOUT", 6)),
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
        street_name = _normalize_street_name_parts(address_components[1:])
        return street_number, street_name
    except Exception as exc:
        print(f"[LADBS] Error extracting address from URL: {exc}")
        return None, None


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


def extract_address_from_text(address: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        street_line = (address or "").split(",", 1)[0].strip()
        match = re.match(r"^(\d+[A-Za-z]?)\s+(.+)$", street_line)
        if not match:
            return None, None
        street_number = match.group(1)
        street_name = _normalize_street_name_parts(match.group(2).split())
        return street_number, street_name
    except Exception as exc:
        print(f"[LADBS] Error extracting address from text: {exc}")
        return None, None


def _build_startup_modes(settings: DriverSettings) -> List[BrowserStartupMode]:
    modes = [
        BrowserStartupMode(
            name="headless" if settings.headless else "headed",
            headless=settings.headless,
            use_remote_debugging_pipe=settings.use_remote_debugging_pipe,
        )
    ]
    if settings.allow_headed_fallback:
        alternate_headless = not settings.headless
        modes.append(
            BrowserStartupMode(
                name="headed-fallback" if not alternate_headless else "headless-fallback",
                headless=alternate_headless,
                use_remote_debugging_pipe=settings.use_remote_debugging_pipe,
            )
        )
    return modes


def _build_common_browser_args(
    profile_dir: Path,
    *,
    headless: bool,
    use_remote_debugging_pipe: bool,
) -> List[str]:
    args: List[str] = []
    if headless:
        args.append("--headless=new")
    args.extend(
        [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-setuid-sandbox",
            "--disable-background-networking",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--disable-sync",
            "--disable-features=Translate,OptimizationGuideModelDownloading",
            "--hide-crash-restore-bubble",
            "--metrics-recording-only",
            "--no-default-browser-check",
            "--no-first-run",
            "--password-store=basic",
            "--window-size=1920,1080",
            f"--user-data-dir={profile_dir}",
        ]
    )
    if use_remote_debugging_pipe:
        args.append("--remote-debugging-pipe")
    return args


def _build_chrome_options(
    settings: DriverSettings,
    profile_dir: Path,
    mode: BrowserStartupMode,
) -> "Options":
    chrome_options = Options()
    for arg in _build_common_browser_args(
        profile_dir,
        headless=mode.headless,
        use_remote_debugging_pipe=mode.use_remote_debugging_pipe,
    ):
        chrome_options.add_argument(arg)
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
    for key in INHERITED_BROWSER_ENV_KEYS_TO_REMOVE:
        env.pop(key, None)

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
    mode: BrowserStartupMode,
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
                f"startup_mode: {mode.name}",
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


def _probe_browser_launch(settings: DriverSettings, headless: bool) -> Dict[str, Any]:
    mode_label = "headless" if headless else "headed"
    profile_dir = Path(tempfile.mkdtemp(prefix=f"ladbs-probe-{mode_label}-", dir=str(settings.profile_root)))
    log_path = settings.logs_dir / (
        f"browser_probe_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{mode_label}.log"
    )
    if not settings.chrome_binary:
        return {
            "mode": mode_label,
            "headless": headless,
            "ok": False,
            "returncode": None,
            "stdout_excerpt": "",
            "stderr_excerpt": "No Chrome binary was discovered for direct browser probing.",
            "log_path": str(log_path),
        }

    command = [
        settings.chrome_binary,
        *(
            _build_common_browser_args(
                profile_dir,
                headless=headless,
                use_remote_debugging_pipe=False,
            )
        ),
    ]
    if headless:
        command.extend(["--dump-dom", "about:blank"])
    else:
        command.append("about:blank")

    env = _build_browser_env(settings)
    stdout_text = ""
    stderr_text = ""
    returncode: Optional[int] = None
    ok = False

    try:
        if headless:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.browser_probe_timeout_seconds,
                env=env,
            )
            stdout_text = completed.stdout or ""
            stderr_text = completed.stderr or ""
            returncode = completed.returncode
            ok = completed.returncode == 0
        else:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            time.sleep(settings.browser_probe_timeout_seconds)
            if process.poll() is None:
                ok = True
                process.terminate()
                try:
                    stdout_text, stderr_text = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout_text, stderr_text = process.communicate()
                returncode = process.returncode
            else:
                stdout_text, stderr_text = process.communicate()
                returncode = process.returncode
                ok = process.returncode == 0
    except subprocess.TimeoutExpired:
        stderr_text = "Browser probe timed out before reporting readiness."
    except Exception as exc:
        stderr_text = f"Browser probe exception: {exc}"
    finally:
        log_path.write_text(
            "\n".join(
                [
                    f"timestamp: {datetime.now().isoformat()}",
                    f"mode: {mode_label}",
                    f"command: {command}",
                    f"returncode: {returncode}",
                    "stdout:",
                    stdout_text,
                    "stderr:",
                    stderr_text,
                ]
            ),
            encoding="utf-8",
        )
        _cleanup_profile_dir(profile_dir)

    return {
        "mode": mode_label,
        "headless": headless,
        "ok": ok,
        "returncode": returncode,
        "stdout_excerpt": stdout_text[:1000],
        "stderr_excerpt": stderr_text[:1000],
        "log_path": str(log_path),
    }


def diagnose_browser_startup() -> Dict[str, Any]:
    settings = _resolve_driver_settings()
    seen_headless_modes: set[bool] = set()
    probe_results: List[Dict[str, Any]] = []
    for mode in _build_startup_modes(settings):
        if mode.headless in seen_headless_modes:
            continue
        seen_headless_modes.add(mode.headless)
        probe_results.append(_probe_browser_launch(settings, mode.headless))
    return {
        "settings": get_driver_settings(),
        "probe_results": probe_results,
    }


def _classify_driver_error(
    error: Optional[Exception],
    settings: DriverSettings,
    probe_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    message = str(error or "").lower()
    if probe_results:
        failed_results = [result for result in probe_results if not result.get("ok")]
        if failed_results and len(failed_results) == len(probe_results):
            combined = " ".join(
                f"{result.get('stdout_excerpt', '')} {result.get('stderr_excerpt', '')}"
                for result in failed_results
            ).lower()
            if "crashpad" in combined and "access is denied" in combined:
                return (
                    "Direct Chromium launch also failed before WebDriver could attach. "
                    "Detected Crashpad/Mojo access-denied errors even with repo-local "
                    "browser env and profile directories. This is an environment-level "
                    "Chromium startup restriction, not a LADBS page/search failure."
                )
            if "processsingleton" in combined or "lock file can not be created" in combined:
                return (
                    "Chromium could not obtain a usable profile/process lock during direct "
                    "browser startup. Close other Chromium instances and clear repo-local "
                    "profile directories before retrying."
                )
        if any(result.get("ok") for result in probe_results):
            return (
                "Chromium can launch directly, but WebDriver session creation still failed. "
                "Check Chrome/ChromeDriver version compatibility and the selected driver path."
            )
    if "cannot create default profile directory" in message:
        return (
            "ChromeDriver could not initialize a writable browser profile. "
            "Check repo-local profile/cache dirs plus Chrome policy restrictions."
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
    startup_modes = _build_startup_modes(settings)
    total_attempts = len(startup_modes) * settings.start_retries

    for mode in startup_modes:
        for attempt in range(1, settings.start_retries + 1):
            profile_dir = Path(
                tempfile.mkdtemp(prefix=f"ladbs-{mode.name}-", dir=str(settings.profile_root))
            )
            service_log_path = settings.logs_dir / (
                f"chromedriver_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{mode.name}_attempt{attempt}.log"
            )

            try:
                driver = webdriver.Chrome(
                    service=_build_chrome_service(settings, service_log_path),
                    options=_build_chrome_options(settings, profile_dir, mode),
                )
                driver.set_page_load_timeout(settings.page_load_timeout_seconds)
                driver.implicitly_wait(settings.implicit_wait_seconds)
                setattr(driver, "_codex_profile_dir", str(profile_dir))
                LAST_DRIVER_ERROR_SUMMARY = ""
                return driver
            except Exception as exc:
                last_error = exc
                _log_driver_failure(settings, attempt, mode, exc, profile_dir, service_log_path)
                _cleanup_profile_dir(profile_dir)
                if attempt < settings.start_retries:
                    time.sleep(settings.retry_delay_seconds)

    diagnostics = diagnose_browser_startup()
    LAST_DRIVER_ERROR_SUMMARY = _classify_driver_error(
        last_error,
        settings,
        diagnostics.get("probe_results"),
    )
    print(
        f"[LADBS] Error setting up Chrome driver after {total_attempts} startup attempts: "
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

    street_number: Optional[str] = None
    street_name: Optional[str] = None
    address_source = None
    if redfin_url:
        street_number, street_name = extract_address_from_redfin_url(redfin_url)
        address_source = "redfin_url"
    if (not street_number or not street_name) and address:
        street_number, street_name = extract_address_from_text(address)
        address_source = "address"

    if not street_number or not street_name:
        return {
            "source": "ladbs_stub_bad_address",
            "apn": apn,
            "address": address,
            "fetched_at": fetched_at,
            "permits": [],
            "note": (
                "Could not extract LADBS street number/name from the provided inputs. "
                f"redfin_url={redfin_url!r} address={address!r}"
            ),
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
                f"Chrome={settings.chrome_binary or 'not-found'} "
                f"({settings.chrome_binary_source or 'no-source'}); "
                f"ChromeDriver={settings.chromedriver_path or 'selenium-manager'} "
                f"({settings.chromedriver_source or 'auto'}). "
                f"Review LADBS logs under {settings.logs_dir}."
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
                "note": (
                    f"PLR search did not return a results page for {street_number} {street_name} "
                    f"(derived from {address_source})."
                ),
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
