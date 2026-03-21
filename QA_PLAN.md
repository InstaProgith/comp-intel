# QA Plan

## Scope

This pass is limited to QA hardening on top of the `codex/zimas-records-pass` baseline.

Allowed:
- correctness fixes
- output-contract stabilization
- diagnostics and anomaly surfacing
- report formatting cleanup
- regression tests
- repeatable real-property QA harness work

Not allowed:
- new providers
- new data-source features
- PDF download plumbing
- VPS or deployment expansion
- architecture rewrites

## Active Data And Report Paths

The current full-data pipeline under QA is:

1. `app.redfin_scraper.get_redfin_data`
2. `app.zimas_pin_client.resolve_pin`
3. `app.zimas_client.get_zimas_profile`
4. `app.ladbs_scraper.get_ladbs_data`
5. `app.ladbs_records_client.get_ladbs_records`
6. `app.orchestrator.run_full_comp_pipeline`
7. `app.ui_server.single_report` rendering `templates/report.html`
8. `app.property_data_smoke`
9. `app.ladbs_smoke`

## Golden-Property Strategy

Primary golden property:
- `https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003`

Why Lucerne is the primary golden:
- stable known-real property
- exercises Redfin sold-page parsing
- exercises browserless ZIMAS profile resolution
- exercises browserless LADBS permit retrieval by PIN
- exercises browserless LADBS records/document retrieval
- exercises final report rendering

Golden checks for Lucerne should focus on:
- source success states
- stable key fields
- representative counts
- representative permit IDs
- representative document IDs
- key ZIMAS zoning/profile values
- clean report section rendering

Additional-property QA strategy:
- add a small configurable harness that can run the same validation pattern against a short list of additional real Redfin URLs
- default to Lucerne only
- allow extra properties through CLI args or a simple JSON property file
- treat non-Lucerne properties as comparative validation, not as new production truths unless explicitly captured and reviewed

## Output Contract Expectations

`run_full_comp_pipeline(...)` should return a stable top-level payload with:
- fixed top-level keys
- stable nested dict/list types
- explicit empty/null behavior instead of missing keys
- auditable source metadata for Redfin, ZIMAS, LADBS permits, and LADBS records
- machine-readable anomalies/review flags

Contract rules:
- dict sections should always be dicts, never `None`, when the report expects nested keys
- list sections should always be lists, never `None`
- counts should be numeric
- optional scalar values may be `None`
- missing strings should render as explicit placeholders in the UI, not raw `None`, `null`, or empty-looking artifacts
- fallback/error payloads should preserve the same shape as success payloads

## Key Correctness Checks

Redfin:
- sold pages do not misread estimate banners as live list prices
- lot size does not disappear when one source is blank
- timeline ordering stays stable

ZIMAS:
- APN lookup preserves PIN spacing
- parcel profile resolves the expected zoning/planning fields
- key hazard/environment fields map to the correct labels

LADBS permits:
- pin-first path stays the default happy path
- representative permit IDs remain present for Lucerne
- parsed status dates and detail fields remain structured
- direct smoke output remains auditable

LADBS records:
- browserless APN search flow still works without accidental submit-button pollution
- document rows preserve stable metadata fields
- public PDF viewer links are resolved only as references, not downloaded artifacts

Orchestrator:
- success and fallback payloads have the same contract shape
- diagnostics and anomalies are always present
- source/path metadata is easy to inspect

Report:
- no raw `None` or `null`
- no malformed separators, dates, or numbers
- readable long values
- sane ordering for source sections and record rows
- Lucerne report includes the expected headings and representative IDs

## Formatting Expectations

The report should:
- display placeholders consistently
- preserve legitimate zero values instead of hiding them as falsy
- avoid awkward duplicated separators
- wrap long addresses, descriptions, and URLs safely
- keep section ordering stable:
  - Property Snapshot
  - Developer Snapshot
  - Timeline Summary
  - Construction Summary
  - Cost Model
  - Permit Overview
  - ZIMAS Parcel Profile
  - LADBS Records
  - Team
  - Strategy Notes
  - Review Flags / Data Notes
  - Links

## Regression Strategy

Automated regression protection should cover:
- Redfin parser edge cases
- ZIMAS field extraction
- LADBS permit parsing
- LADBS records parsing
- orchestrator payload shape
- report render expectations

Real-property regression loop for this pass:
1. `python -m unittest discover -s tests -v`
2. `python -m compileall app tests`
3. `python -m app.property_data_smoke --redfin-url <Lucerne URL>`
4. `python -m app.ladbs_smoke --redfin-url <Lucerne URL> --json`
5. Flask `/report` render smoke with Lucerne
6. inspect output
7. fix
8. rerun until materially cleaner

## Readiness Standard For This Pass

This pass is successful when:
- Lucerne remains green end to end
- payload shape is explicitly validated
- regressions are harder to introduce
- report output is cleaner and more consistent
- anomalies are surfaced clearly instead of silently ignored
- QA documentation states remaining weak spots honestly
