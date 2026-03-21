# QA Run Report

## Scope

This pass stayed on top of the `codex/zimas-records-pass` baseline and focused only on QA hardening:

- correctness
- output-contract stability
- report cleanliness
- diagnostics
- regression protection
- live Lucerne validation

No new providers, PDF download plumbing, VPS changes, or architecture rewrites were added.

## Commands Run

```powershell
git branch --show-current
git status --short
Get-ChildItem QA_PLAN.md,QA_RUN_REPORT.md | Select-Object Name,Length
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m app.property_data_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
.\.venv\Scripts\python.exe -m app.qa_harness --json
.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json
$env:APP_ENV='development'; $env:APP_TESTING='1'; $env:FLASK_SECRET_KEY='qa-smoke-secret'; $env:APP_ACCESS_PASSWORD='qa-smoke-password'; @'
from app.ui_server import app
url = 'https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003'
client = app.test_client()
with client.session_transaction() as session:
    session['logged_in'] = True
response = client.post('/report', data={'redfin_url': url})
html = response.get_data(as_text=True)
checks = {
    'status_code': response.status_code,
    'has_zimas_heading': 'ZIMAS Parcel Profile' in html,
    'has_records_heading': 'LADBS Records' in html,
    'has_review_flags': 'Review Flags' in html,
    'has_data_notes': 'Data Notes' in html,
    'has_zoning': 'R1-1-O' in html,
    'has_permit_id': '25041-90000-59794' in html,
    'has_document_id': '06014-70000-09673' in html,
    'has_pdf_viewer_link': 'StPdfViewer.aspx' in html,
    'contains_none': '>None<' in html,
    'contains_null': 'null' in html,
    'contains_clean_title': 'BLDGBIT - Property Report' in html,
}
for key, value in checks.items():
    print(f'{key}={value!r}')
'@ | .\.venv\Scripts\python.exe -
.\.venv\Scripts\python.exe -m app.qa_harness
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Issues Found

1. The orchestrated payload still had no explicit stable contract layer for sort order and anomaly-code summary fields.
2. The real-property QA harness only summarized counts; it did not enforce known Lucerne facts or rendered-report expectations.
3. LADBS records were not normalized into a stable newest-first review order, creating a noisy `records_not_date_sorted` anomaly.
4. The LADBS smoke header printed `address=None` when a Redfin URL was used without an explicit address, even though the resolved address was present in the result.
5. The report template still contained a few non-ASCII presentation artifacts, including the bad title separator and multiplication glyphs that could render poorly in some environments.
6. The report-render check inside the QA harness inherited development secret/password warnings from `ui_server`, which polluted otherwise clean QA output.

## Fixes Made

### Payload / Diagnostics

- Added [app/payload_contract.py](C:/Users/navid/Desktop/comp-intel/app/payload_contract.py) to enforce a stable payload contract.
- Added explicit `source_diagnostics.anomaly_codes`.
- Normalized `ladbs.permits` and `ladbs_records.documents` to stable newest-first ordering.
- Kept anomaly detection machine-readable and aligned the date-order anomaly with the normalized review order.
- Replaced bad default dash characters with safe ASCII placeholders.

### QA Harness / Regression

- Added [app/qa_harness.py](C:/Users/navid/Desktop/comp-intel/app/qa_harness.py) as the real-property QA harness.
- Added Lucerne expectation checks for:
  - address match
  - ZIMAS PIN/APN/zoning/general plan/community plan
  - minimum permit/document counts
  - representative permit/document IDs
  - rendered report headings and forbidden raw strings
- Added regression tests in:
  - [tests/test_payload_contract.py](C:/Users/navid/Desktop/comp-intel/tests/test_payload_contract.py)
  - [tests/test_orchestrator_contract.py](C:/Users/navid/Desktop/comp-intel/tests/test_orchestrator_contract.py)
  - [tests/test_qa_harness.py](C:/Users/navid/Desktop/comp-intel/tests/test_qa_harness.py)
  - [tests/test_ui_server.py](C:/Users/navid/Desktop/comp-intel/tests/test_ui_server.py)
  - strengthened parser coverage in [tests/test_redfin_scraper.py](C:/Users/navid/Desktop/comp-intel/tests/test_redfin_scraper.py), [tests/test_zimas_client.py](C:/Users/navid/Desktop/comp-intel/tests/test_zimas_client.py), [tests/test_ladbs_scraper.py](C:/Users/navid/Desktop/comp-intel/tests/test_ladbs_scraper.py), and [tests/test_ladbs_records_client.py](C:/Users/navid/Desktop/comp-intel/tests/test_ladbs_records_client.py)

### Report / Smoke Output

- Updated [templates/report.html](C:/Users/navid/Desktop/comp-intel/templates/report.html) so the title and cost labels use safe ASCII output.
- Kept the report free of raw `None` and raw `null`.
- Improved [app/ladbs_smoke.py](C:/Users/navid/Desktop/comp-intel/app/ladbs_smoke.py) so it labels the incoming address as `input_address` and exposes the resolved address in the result payload instead of implying the address is missing.
- Updated [README.md](C:/Users/navid/Desktop/comp-intel/README.md) with the QA harness command and what it validates.

## Tests Run And Results

- `.\.venv\Scripts\python.exe -m compileall app tests` -> passed
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` -> passed, `35/35`

## Lucerne Results

### Full Data Smoke

Command:

```powershell
.\.venv\Scripts\python.exe -m app.property_data_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
```

Result:

- address: `1120 S Lucerne Blvd, Los Angeles, CA 90019`
- Redfin source: `redfin_parsed_v3`
- ZIMAS source: `zimas_profile_v1`
- ZIMAS transport: `http`
- ZIMAS PIN: `129B185   131`
- ZIMAS APN: `5082004025`
- zoning: `R1-1-O`
- general plan: `Low II Residential`
- community plan: `Wilshire`
- nearest fault: `Puente Hills Blind Thrust`
- LADBS permits source: `ladbs_pin_v1`
- permit count: `7`
- LADBS records source: `ladbs_records_v1`
- records transport: `http`
- document count: `14`
- digital-image count: `10`
- PDF-link count: `10`
- representative documents:
  - `06014-70000-09673`
  - `06016-70000-21824`
  - `06014-70001-09673`

### QA Harness

Command:

```powershell
.\.venv\Scripts\python.exe -m app.qa_harness
```

Result:

- schema warnings: `0`
- QA failures: `0`
- anomaly codes:
  - `permit_address_variants`
  - `shared_record_ids`
- source states:
  - Redfin `ok=true`
  - ZIMAS `ok=true`
  - LADBS permits `ok=true`
  - LADBS records `ok=true`

### LADBS Permit Smoke

Command:

```powershell
.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003" --json
```

Result:

- input address: `None`
- resolved address: `1120 S LUCERNE BLVD`
- strategy: `pin-first`
- final source: `ladbs_pin_v1`
- fallback used: `false`
- PIN: `129B185   131`
- permit count: `7`
- representative permits:
  - `25041-90000-59794`
  - `25042-90000-22280`
  - `25014-10000-03595`

### Flask `/report` Smoke

Result:

- status code: `200`
- report headings present:
  - `ZIMAS Parcel Profile`
  - `LADBS Records`
  - `Review Flags`
  - `Data Notes`
- Lucerne-specific content present:
  - `R1-1-O`
  - `25041-90000-59794`
  - `06014-70000-09673`
  - `StPdfViewer.aspx`
- clean output checks:
  - raw `None`: not present
  - raw `null`: not present
  - clean title `BLDGBIT - Property Report`: present

## Remaining Weak Spots

1. `permit_address_variants` remains a real review flag for Lucerne because the live LADBS permit set spans both `1120` and `1122` address labels.
2. `shared_record_ids` remains a real review flag because LADBS records reuse one underlying record ID for multiple document numbers on this parcel.
3. The raw provider smoke in [app/property_data_smoke.py](C:/Users/navid/Desktop/comp-intel/app/property_data_smoke.py) still reflects source order rather than the orchestrated report order. The final payload/report now normalizes newest-first ordering, which is the output contract that matters for review.
4. Real-world counts can change as new permits or records are added. The Lucerne QA harness therefore checks stable facts, minima, and representative IDs instead of pretending the live sources will never evolve.

## Readiness Assessment

Current readiness for the existing feature set is high.

Why:

- the main full-data pipeline stayed green on the real Lucerne property
- the payload contract is now explicit and regression-tested
- the report render is cleaner and more stable
- the QA harness can catch both schema regressions and report regressions on a real property
- remaining flags are honest data-review notes, not silent breakage or formatting noise

This branch is in a stronger QA state and is ready for review/merge as a hardening pass on the existing feature baseline.
