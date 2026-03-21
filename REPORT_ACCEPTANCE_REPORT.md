# Report Acceptance Report

## Properties Reviewed

- `lucerne` - flagship baseline
- `malcolm` - sparse/noisy review case
- `rosewood` - clean report case
- `kelton` - dense-document case

## Commands Run

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m app.report_acceptance --property-file validation\report_acceptance_property_pack.json --output-dir review_bundles\report_acceptance
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m app.report_acceptance --property-file validation\report_acceptance_property_pack.json --output-dir review_bundles\report_acceptance
```

## Issues Found

### Malcolm

- The report rendered `16` permit cards from a `14`-permit payload.
- Root cause: `Bldg-Demolition` permits matched both the template's building bucket and demolition bucket, so demolition cards were double-rendered.

### Lucerne / Malcolm / Rosewood / Kelton

- No blocking truth mismatches were found in address, APN, PIN, zoning, general plan, or community plan.
- No raw `None`, `null`, or mojibake appeared in the final rendered reports.
- Section order and record/PDF link rendering were clean in the final rerendered bundles.

## Fixes Made

- Added [app/report_acceptance.py](C:/Users/navid/Desktop/comp-intel/app/report_acceptance.py) to generate tracked review bundles, evaluate report correctness, and write [REVIEW_INDEX.md](C:/Users/navid/Desktop/comp-intel/REVIEW_INDEX.md).
- Added [validation/report_acceptance_property_pack.json](C:/Users/navid/Desktop/comp-intel/validation/report_acceptance_property_pack.json) for the 4-property review set.
- Updated [templates/report.html](C:/Users/navid/Desktop/comp-intel/templates/report.html) to render Permit Overview from the orchestrator's categorized permit lists instead of overlapping regex buckets.
- Added a Supplements / Revisions section in Permit Overview so categorized permit output stays complete and non-overlapping.
- Added [tests/test_report_acceptance.py](C:/Users/navid/Desktop/comp-intel/tests/test_report_acceptance.py) to lock:
  - section-order checks
  - placeholder/mojibake detection
  - verdict classification
  - no double-render of demolition permits
- Updated [README.md](C:/Users/navid/Desktop/comp-intel/README.md) with the report-acceptance command.

## Final Acceptance by Property

- `lucerne`: `accepted-with-review`
  - core facts matched
  - report clean and section order correct
  - remaining review items are honest uncertainty notes and one real parcel-level address-variant flag
- `malcolm`: `accepted-with-review`
  - core facts matched
  - report clean after Permit Overview fix
  - remaining review item is the real `permit_address_variants` parcel-level crossover note
- `rosewood`: `accepted-with-review`
  - core facts matched
  - clean report with no anomaly flags
  - remaining review note is the honest purchase-price limitation from Redfin history
- `kelton`: `accepted-with-review`
  - core facts matched
  - dense LADBS records remained readable and correctly counted
  - remaining review note is the certificate-bundle interpretation reminder plus purchase-price limitation

## Remaining Questionable Items

- `lucerne`
  - `permit_address_variants`
  - purchase price unknown from current Redfin history
  - construction completion timing remains uncertain because a certificate-of-occupancy date is not surfaced
- `malcolm`
  - `permit_address_variants`
  - parcel-level permit output spans `2831` and `2831 1/2`, which should stay visible for review
  - purchase price unknown from current Redfin history
- `rosewood`
  - purchase price unknown from current Redfin history
- `kelton`
  - purchase price unknown from current Redfin history
  - certificate bundle reuse of record IDs is normal here and should remain a review note, not an anomaly

## Final Readiness Assessment

Readiness is strong for report review.

Why:

- all four properties produced tracked review bundles
- no property remained in `needs-fix`
- the one real report-rendering defect found in this pass was fixed and regression-tested
- final rendered reports are clean: correct section order, no raw placeholders, no mojibake, and counts aligned with payloads
- remaining items are honest review notes, not report correctness failures
