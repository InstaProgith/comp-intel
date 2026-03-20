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

## Remaining Blockers

- LADBS browser automation still fails in this environment due Chrome/ChromeDriver profile startup restrictions.
- The password that used to live in `access_password.txt` should be treated as exposed and rotated, because deleting it from the current tree does not remove it from git history.
- ZIMAS and exact building-record PDF retrieval were intentionally not started in this run because the baseline needed hardening first.

## Exact Next Best Step

Validate LADBS on the real VPS or a normal local Chrome install with explicit runtime config:

1. Set `LADBS_CHROME_BINARY` and `LADBS_CHROMEDRIVER_PATH`.
2. Confirm Chrome can launch under the configured writable profile/cache directories.
3. Re-run the Lucerne smoke and confirm real permits return.
4. If ChromeDriver remains brittle there too, evaluate a targeted Playwright migration for the LADBS workflow only.

Once LADBS is green, the baseline is stable enough to expand into ZIMAS, building-record PDF retrieval, and final PDF export work.
