# Multi-Property QA Plan

## Scope

This pass stays on top of the current merged `main` baseline and is limited to live validation and polish.

Allowed:
- broader live validation
- correctness fixes
- parser robustness
- output consistency
- report polish
- anomaly signal cleanup
- regression strengthening

Not allowed:
- new providers
- VPS work
- PDF download plumbing
- architecture rewrites
- feature expansion outside the existing Redfin + ZIMAS + LADBS permits + LADBS records + report flow

## Live Validation Surface

The live end-to-end validation surface for this pass is:

1. `app.redfin_scraper.get_redfin_data`
2. `app.zimas_pin_client.resolve_pin`
3. `app.zimas_client.get_zimas_profile`
4. `app.ladbs_scraper.get_ladbs_data`
5. `app.ladbs_records_client.get_ladbs_records`
6. `app.orchestrator.run_full_comp_pipeline`
7. `app.payload_contract.apply_payload_contract`
8. `app.ui_server.single_report` rendering `templates/report.html`
9. `app.qa_harness`

## Validation Set

The validation set for this narrowed run is the five Los Angeles properties the user supplied:

- `malcolm`:
  - `https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382`
  - intended coverage: sparse records, recent sale, permit-endpoint uncertainty
- `rosewood`:
  - `https://www.redfin.com/CA/Los-Angeles/3629-Rosewood-Ave-90066/home/6746236`
  - intended coverage: recently permitted property, multiple LADBS docs, range-style address labels
- `kelton`:
  - `https://www.redfin.com/CA/Los-Angeles/3104-Kelton-Ave-90034/home/6752630`
  - intended coverage: dense older docs, certificate-of-occupancy bundle handling
- `castle-heights`:
  - `https://www.redfin.com/CA/Los-Angeles/2631-Castle-Heights-Pl-90034/home/6792332`
  - intended coverage: different zoning profile, multiple records, historical certificate bundle handling
- `appleton`:
  - `https://www.redfin.com/CA/Los-Angeles/12506-Appleton-Way-90066/home/6748251`
  - intended coverage: newer build, multiple LADBS docs, TEMP address-label normalization

The structured validation pack for these properties lives in:

- `validation/los_angeles_five_property_pack.json`

## Key QA Goals

This pass should materially improve:

- source-state correctness
- parser stability across multiple real properties
- report cleanliness across multiple render outputs
- anomaly precision, especially:
  - `permit_address_variants`
  - `shared_record_ids`
- regression protection for any live bug found during the run

## Expected Checks Per Property

For each property, the QA harness should summarize:

- source statuses for Redfin, ZIMAS, LADBS permits, and LADBS records
- key facts:
  - address
  - PIN
  - APN
  - zoning
  - community plan / hazard context where relevant
  - permit count
  - record count
  - PDF-link count
- schema warnings
- review flags / anomaly codes
- mismatches against expected truths
- report cleanliness checks:
  - no raw `None`
  - no raw `null`
  - expected headings present

## Initial Hypotheses To Validate

Based on the first sweep, the biggest likely improvement areas are:

1. `ladbs_ok` currently treats some LADBS error sources as successful.
2. The LADBS pin-first flow may mishandle percent-encoded PINs from ZIMAS address-search responses.
3. `permit_address_variants` is too noisy when the only differences are TEMP labels or range labels that still include the subject address.
4. `shared_record_ids` is too noisy when the documents form an expected same-day certificate-of-occupancy bundle.
5. The QA harness should summarize more of the actual payload/report contract so multi-property runs are auditable.

## Repeatable Commands

Baseline:

```powershell
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Five-property live validation:

```powershell
.\.venv\Scripts\python.exe -m app.qa_harness --property-file validation\los_angeles_five_property_pack.json
.\.venv\Scripts\python.exe -m app.qa_harness --property-file validation\los_angeles_five_property_pack.json --json
```

Targeted spot checks:

```powershell
.\.venv\Scripts\python.exe -m app.property_data_smoke --redfin-url <url>
.\.venv\Scripts\python.exe -m app.ladbs_smoke --redfin-url <url> --json
```

## Success Standard

This pass is successful when:

- the five-property QA harness produces materially cleaner output than the first sweep
- real correctness bugs found by the live run are fixed
- anomaly noise is reduced without hiding meaningful review cases
- tests cover the fixes introduced in this pass
- report output remains clean and readable across the validation set
- remaining weak spots are documented honestly in `MULTI_PROPERTY_QA_REPORT.md`
