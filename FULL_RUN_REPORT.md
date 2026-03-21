# FULL RUN REPORT

## Run Summary

- Date: 2026-03-20
- Repo: `C:\Users\navid\Desktop\comp-intel`
- Remote: `origin https://github.com/InstaProgith/comp-intel.git`
- Branch for this run: `codex/lucerne-full-run-hardening`
- Main live validation target: `https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003`

This run stayed inside the current local repo, compared it against `origin/main`, reconciled the meaningful differences selectively, ran the app for real, exercised the Lucerne property as the primary smoke test, tightened security/config behavior, improved scraper reliability, added regression tests, and isolated the remaining LADBS blocker.

## Differences vs origin/main

`origin/main` was fetched and used as the comparison baseline. The local repo was already aligned to the latest upstream commit history, so the meaningful differences at the end of this run are the targeted hardening changes below rather than a blind overwrite from GitHub.

### Meaningful local improvements kept

- Replaced tracked password-file behavior with env-first runtime config and safe local examples.
- Removed the committed `access_password.txt` secret from the working tree and added local-only ignore coverage.
- Made Flask secret handling fail closed in production-like mode.
- Hardened LADBS driver startup for server use with configurable paths, retries, writable cache/profile directories, and bootstrap logs.
- Fixed Redfin lot size retention when public records omit lot size.
- Fixed sold/off-market Redfin parsing so estimate banners do not get misread as current list price.
- Fixed the single-report route so it accepts either `urls` or `redfin_url`.
- Added tests for runtime config, Redfin parsing, LADBS driver settings, and report-route behavior.
- Added VPS deployment guidance and updated README guidance.

### Local-only or stale items discarded / untracked

- Removed tracked `access_password.txt`.
- Ignored top-level `chromedriver/` so local runtime binaries do not drift into git.
- Kept generated data, logs, raw HTML, and temp smoke outputs out of git.

## Key Files Changed

- `.gitignore`
- `.env.example`
- `README.md`
- `VPS_DEPLOYMENT.md`
- `access_password.example.txt`
- `app/runtime_config.py`
- `app/ui_server.py`
- `app/redfin_scraper.py`
- `app/ladbs_scraper.py`
- `app/ladbs_smoke.py`
- `tests/test_runtime_config.py`
- `tests/test_redfin_scraper.py`
- `tests/test_ladbs_scraper.py`
- `tests/test_ui_server.py`
- Deleted: `access_password.txt`

## What Was Merged vs Kept vs Discarded

### Merged / carried forward

- Existing upstream UI/login/search-history/report improvements from `origin/main`.
- Existing orchestrator/report structure already present upstream.
- Existing Redfin/LADBS integration paths, but with targeted hardening rather than replacement.

### Kept after review

- Current repo structure and the current local repo as the source of truth for edits.
- The upstream report/template structure, with route compatibility improved instead of rewritten.
- Existing LADBS Selenium approach, with server-safety improvements added before considering a scraper migration.

### Discarded or intentionally not promoted

- Blind file copying from GitHub or ZIP snapshots.
- The committed password file pattern.
- Treating sold-page Redfin estimate banners as current list price.
- Local runtime binaries and generated artifacts as trackable repo content.

## Commands Run

Key commands executed during this run included:

- `git fetch origin`
- `git diff --name-status origin/main`
- `git diff --stat origin/main`
- `git status --short`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- `.\.venv\Scripts\python.exe -m compileall app tests`
- `run_full_comp_pipeline("https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003")`
- Live Flask smoke via `python -m app.ui_server` in a background job plus `Invoke-WebRequest` login/report POSTs
- `get_ladbs_data(apn=None, address="1120 S Lucerne Blvd, Los Angeles, CA 90019", redfin_url="https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003")`
- Targeted repo/code inspection with `rg`, `Get-Content`, `Select-String`, and `Get-ChildItem`

## Tests Run and Results

### Automated tests

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- Result: `7/7` tests passed

Covered areas:

- runtime config fail-closed behavior
- dev password fallback behavior
- Redfin lot-size retention
- Redfin sold-page estimate-banner rejection
- LADBS writable workspace driver settings
- login/history smoke
- single report route acceptance of `redfin_url`

### Compile check

- `.\.venv\Scripts\python.exe -m compileall app tests`
- Result: passed

## Live Lucerne Smoke-Test Result

### Direct pipeline smoke

Command target:

- `https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003`

Observed result:

- property status: `Sold`
- sold price: `$800,000`
- current Redfin `list_price`: `None` after fix
- lot size: `8,379 SF`
- timeline tail: sold event on `2025-09-05` for `$800,000`

This confirms the sold/off-market parsing fix worked for the real Lucerne page: the Redfin estimate banner is no longer being misclassified as a current listing price.

### Live Flask app smoke

Actual app run and browserless HTTP validation:

- `GET /` -> `200`
- login POST -> `200`
- `POST /report` with the Lucerne URL -> `200`
- rendered report contained:
  - Lucerne address
  - sold price
  - permit section
  - data notes section

## LADBS Smoke-Test Result

### Direct LADBS smoke

- source: `ladbs_stub_driver_error`
- permit count: `0`
- result: blocked locally by ChromeDriver startup

Current error:

- `ChromeDriver could not initialize a writable browser profile. Check LOCALAPPDATA/TEMP overrides and Chrome policy restrictions.`

Latest logs captured during this run:

- `data/logs/ladbs/chromedriver_20260320-161416_attempt1.log`
- `data/logs/ladbs/driver_bootstrap_20260320-161418_attempt1.log`
- `data/logs/ladbs/chromedriver_20260320-161420_attempt2.log`
- `data/logs/ladbs/driver_bootstrap_20260320-161423_attempt2.log`

Assessment:

- LADBS is still the primary external blocker.
- The failure is now explicit, retried, and logged instead of silent.
- The repo is in a better state for VPS validation because browser paths, cache dirs, and profile dirs are configurable.

## Follow-Up Pass: LADBS Startup Resolution

This follow-up pass stayed on `codex/lucerne-full-run-hardening` and focused only on the remaining LADBS startup blocker.

### Baseline re-check on this pass

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` -> `9/9` passed
- `.\.venv\Scripts\python.exe -m compileall app tests` -> passed
- `.\.venv\Scripts\python.exe -c "from app.redfin_scraper import get_redfin_data; ..."` Lucerne Redfin smoke still returned:
  - address `1120 S Lucerne Blvd, Los Angeles, CA 90019`
  - `list_price=None`
  - sold event on `2025-09-05` for `$800,000`

### What changed in this pass

- Added explicit Chrome and ChromeDriver autodetection from env, PATH, and common local locations.
- Added direct-address parsing for LADBS debugging without requiring a Redfin URL.
- Added Chromium environment sanitization before browser launch.
- Added headless plus headed fallback startup modes.
- Added direct browser-startup probes so the scraper can distinguish WebDriver issues from raw browser startup failures.
- Added `app/ladbs_smoke.py` as the repeatable live LADBS smoke entrypoint.
- Added tests for direct-address parsing and direct-address LADBS smoke routing.
- Updated docs with the exact smoke command and exact env vars used to make Lucerne green.

### Exact commands used in this pass

Baseline:

- `Get-Location`
- `git remote -v`
- `git branch --show-current`
- `git status --short --branch`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- `.\.venv\Scripts\python.exe -m compileall app tests`
- `.\.venv\Scripts\python.exe -c "from app.redfin_scraper import get_redfin_data; ..."`

Repeatable LADBS smoke command added to the repo:

- `python -m app.ladbs_smoke --show-diagnostics --json`
- `python -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019" --json`

Exact Windows PowerShell env vars that produced a successful live LADBS smoke in this environment:

```powershell
$env:LADBS_SELENIUM_PROFILE_DIR = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\profiles'
$env:LADBS_BROWSER_ENV_DIR = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\browser-env'
$env:SE_CACHE_PATH = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\selenium-cache'
python -m app.ladbs_smoke --show-diagnostics --json
python -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019" --json
```

### Exact LADBS smoke result

Working Lucerne LADBS smoke with the env vars above:

- source: `ladbs_plr_v6`
- outcome: real LADBS page visit, real search flow, real permit extraction
- permits found with status date >= 2018: `3`
- permit numbers returned:
  - `25041-90000-59794`
  - `25042-90000-22280`
  - `25014-10000-03595`

Direct-address smoke also succeeded:

- command shape: `python -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019" --json`
- source: `ladbs_plr_v6`
- permits found with status date >= 2018: `3`

### Root cause learned from this pass

- The earlier repo-local browser/profile/cache paths under the Desktop workspace were not sufficient for Chromium startup in this Codex environment.
- With AppData-based LADBS profile/cache/browser-env dirs, direct Chromium launch succeeded and the real LADBS flow completed.
- The branch now has the exact diagnostics and smoke path needed to reproduce both the failure mode and the successful workaround.

## Remaining Blockers

- No blocker remains for the Lucerne LADBS smoke when the AppData-based LADBS env vars above are used.
- Repo-local Chromium profile/cache dirs inside this Codex workspace can still trigger startup restrictions; use the documented AppData-based env vars for local Windows smoke runs.
- The password that used to live in `access_password.txt` should be treated as exposed and rotated, because deleting it from the current tree does not remove it from git history.
- ZIMAS and exact building-record PDF retrieval were intentionally not started in this run because the baseline needed hardening first.

## Exact Next Best Step

Promote the successful LADBS smoke path into your normal local/VPS workflow:

1. Re-run `python -m app.ladbs_smoke --show-diagnostics --json` with the documented writable LADBS env vars and confirm Lucerne stays green.
2. Validate the same smoke command on the VPS with writable non-protected browser/cache/profile dirs.
3. Once that is stable, move into ZIMAS and building-record/PDF expansion work.

Once LADBS is green, the baseline is stable enough to expand into ZIMAS, building-record PDF retrieval, and final PDF export work.

## Follow-Up Pass: ZIMAS PIN-First LADBS Path

This pass stayed on `codex/lucerne-full-run-hardening` and implemented the targeted ZIMAS PIN-first LADBS strategy without starting broader ZIMAS feature work or building-record PDF expansion.

### What changed in this pass

- Added `app/zimas_pin_client.py` for browserless ZIMAS PIN resolution from either a Redfin URL or a direct address.
- Updated `app/ladbs_scraper.py` so `get_ladbs_data(...)` now defaults to `pin-first`:
  - resolve parcel PIN from ZIMAS
  - fetch LADBS `PermitResultsbyPin`
  - load permit drilldown partials over HTTP
  - fetch `PcisPermitDetail` pages over HTTP
  - fall back to the existing Selenium PLR flow only if the PIN route is not usable
- Added result metadata for `pin`, `pin_source`, `requested_strategy`, `retrieval_strategy`, `fallback_used`, `pin_route_source`, and `pin_route_note`.
- Added parser and strategy regression tests for the new ZIMAS and LADBS by-PIN code paths.
- Hardened LADBS runtime-directory creation so `SE_CACHE_PATH` or related browser dirs can recover when a target path already exists as a file.
- Updated `app/ladbs_smoke.py`, `README.md`, and `VPS_DEPLOYMENT.md` with the new repeatable commands and strategy documentation.

### Exact commands used in this pass

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- `.\.venv\Scripts\python.exe -m compileall app tests`
- `.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json`
- `.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"`
- `.\.venv\Scripts\python.exe -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019"`
- `.\.venv\Scripts\python.exe -m app.ladbs_smoke --strategy plr --address "1120 S Lucerne Blvd, Los Angeles, CA 90019"` with writable `%LOCALAPPDATA%` LADBS env vars

### Tests run and results

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` -> `17/17` passed
- `.\.venv\Scripts\python.exe -m compileall app tests` -> passed

### Live Lucerne smoke-test result

Primary live command:

- `python -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json`

Result:

- source: `ladbs_pin_v1`
- retrieval strategy: `pin-first`
- fallback used: `False`
- ZIMAS PIN: `129B185   131`
- ZIMAS PIN source: `zimas_ajax_v1`
- permits found with status date >= 2018: `7`
- representative permit numbers:
  - `25041-90000-59794`
  - `25042-90000-22280`
  - `25014-10000-03595`
  - `25016-10000-27059`
  - `25041-10001-59794`
  - `26044-20000-01885`
  - `25042-10001-22280`

Direct-address smoke also succeeded:

- command shape: `python -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019"`
- source: `ladbs_pin_v1`
- fallback used: `False`
- permits found with status date >= 2018: `7`

Preserved PLR fallback also re-verified after the directory-hardening fix:

- command shape: `python -m app.ladbs_smoke --strategy plr --address "1120 S Lucerne Blvd, Los Angeles, CA 90019"`
- source: `ladbs_plr_v6`
- retrieval strategy: `plr-address`
- permits found with status date >= 2018: `3`

### What was learned

- The Lucerne property no longer needs browser startup for the main LADBS permit flow.
- ZIMAS address search can resolve the parcel PIN browserlessly through `ajaxSearchResults.aspx`.
- LADBS `PermitResultsbyPin`, `_PcisAddressPartial2`, `_IparPcisAddressDrillDownPartial`, and `PcisPermitDetail` are replayable over HTTP for this case.
- The previous Selenium PLR path remains useful as a guarded fallback, but it is no longer the preferred Lucerne path.
- Browser fallback path handling is also more resilient now because runtime cache/profile/env dirs can auto-step aside from file collisions instead of crashing immediately.

### Remaining blockers

- No blocker remains for the Lucerne permit path on the new `pin-first` strategy.
- Browser fallback still depends on writable Chrome profile/cache/temp directories if it is needed for other properties.
- ZIMAS parcel/PIN resolution is intentionally limited to this lookup use case in this pass; broader zoning/profile integration is still future work.

### Exact next best step

Use the new browserless-by-default path as the repo baseline:

1. Keep validating `python -m app.ladbs_smoke --redfin-url <property> --json` on real properties to learn where the by-PIN path succeeds or needs PLR fallback.
2. Once the PIN-first path is stable across a broader sample, promote that metadata into reports/templates where useful.
3. Only after that, start the next expansion into ZIMAS zoning/profile data or LADBS building-record/PDF retrieval.

## Feature Pass: Browserless ZIMAS Parcel Profile + LADBS Records

This pass continued from the stable PIN-first LADBS baseline on branch `codex/zimas-records-pass`. The goal was to add browserless ZIMAS parcel-profile data and browserless LADBS records/document retrieval without destabilizing the Lucerne permit smoke.

### What changed in this pass

- Added `app/zimas_client.py` as the browserless ZIMAS parcel-profile client.
- Added `app/ladbs_records_client.py` as the browserless LADBS records/document search client.
- Added `app/property_data_smoke.py` as a repeatable Lucerne-style smoke entrypoint for Redfin + ZIMAS + LADBS permits + LADBS records.
- Extended `app/orchestrator.py` so the report payload now includes:
  - `zimas_profile`
  - `ladbs_records`
  - source/path metadata for both
- Extended `templates/report.html` with:
  - a ZIMAS parcel-profile section
  - a LADBS records/documents section
  - source metadata and public document/PDF viewer links
- Added regression coverage in:
  - `tests/test_zimas_client.py`
  - `tests/test_ladbs_records_client.py`

### Key implementation choices kept

- Preserved the existing Lucerne-proven permit path in `app/ladbs_scraper.py`.
- Kept the legacy PLR browser route as fallback only.
- Did not store downloaded PDFs, raw HTML, screenshots, or other generated artifacts in git.

### Important findings learned in this pass

- ZIMAS APN lookup returns the parcel PIN with meaningful internal spacing, and that spacing must be preserved for `map.aspx?pin=...&ajax=yes` to resolve the correct parcel profile.
- The LADBS records flow is replayable over plain HTTP:
  - bootstrap with `DefaultCustom.aspx`
  - post the APN search to `DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW`
  - if the site returns address candidates, submit only the chosen checkbox rows and the clicked `Continue` button
  - parse the result grid and then resolve digital document links through `ImageMain.aspx -> ImageList.aspx -> StPdfViewer.aspx`
- The critical ASP.NET form detail is that unclicked submit/reset controls must not be echoed back in the POST payload. Once those controls were excluded, the records flow worked browserlessly.

### Exact commands run in this pass

- `.\.venv\Scripts\python.exe -m compileall app tests`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- `.\.venv\Scripts\python.exe -m app.property_data_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"`
- `.\.venv\Scripts\python.exe -m app.property_data_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json`
- `.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json`
- Live Flask report render via `app.ui_server` test client posting to `/report` with the Lucerne Redfin URL

### Tests run and results

- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` -> `26/26` passed
- `.\.venv\Scripts\python.exe -m compileall app tests` -> passed

### Live Lucerne smoke result

Primary smoke command:

- `python -m app.property_data_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"`

Observed result:

- Redfin source: `redfin_parsed_v3`
- ZIMAS source: `zimas_profile_v1`
- ZIMAS transport: `http`
- ZIMAS PIN: `129B185   131`
- ZIMAS APN: `5082004025`
- ZIMAS zoning: `R1-1-O`
- ZIMAS general plan: `Low II Residential`
- ZIMAS community plan: `Wilshire`
- ZIMAS nearest fault: `Puente Hills Blind Thrust`
- LADBS permit source: `ladbs_pin_v1`
- LADBS permit count: `7`
- LADBS records source: `ladbs_records_v1`
- LADBS records transport: `http`
- LADBS records count: `14`
- LADBS records with digital images: `10`
- LADBS records with resolved public PDF viewer links: `10`

Representative LADBS records returned:

- `06014-70000-09673` - `BUILDING PERMIT` - `10/27/2006`
- `06016-70000-21824` - `BUILDING PERMIT` - `10/30/2006`
- `06014-70001-09673` - `BUILDING PERMIT` - `11/14/2006`
- `CERT 40332` - `CERTIFICATE OF OCCUPANCY` - `2/16/2016`
- `25041-90000-59794` - `ELECTRICAL PERMIT` - `12/22/2025`
- `25042-90000-22280` - `MECHANICAL PERMIT` - `12/22/2025`

### Live report render result

The actual Flask report render for Lucerne returned `200` and the HTML contained:

- `ZIMAS Parcel Profile`
- `LADBS Records`
- `R1-1-O`
- `25041-90000-59794`
- `06014-70000-09673`
- `StPdfViewer.aspx`

This confirmed the new browserless ZIMAS and LADBS records data made it all the way into the report template without breaking the current pipeline.

### Remaining blockers

- No blocker remains for the Lucerne browserless ZIMAS profile path.
- No blocker remains for the Lucerne browserless LADBS records/document path.
- The legacy PLR browser fallback still depends on writable Chrome profile/cache/temp directories when it is needed for non-PIN cases.
- The current LADBS records client intentionally returns the public result rows as surfaced by LADBS, including cases where multiple document numbers point at the same underlying record ID.

### Exact next best step

Build on this baseline by moving into richer parcel/report coverage, not more transport debugging:

1. Add a normalized ZIMAS field map for the highest-signal parcel/zoning fields used repeatedly in investment decisions.
2. Add optional artifact-download plumbing that can save selected LADBS PDFs outside git when explicitly requested.
3. Expand live validation to a broader set of properties so the browserless records and parcel-profile paths are proven beyond Lucerne.
