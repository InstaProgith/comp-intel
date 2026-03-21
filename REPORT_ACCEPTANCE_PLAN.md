# Report Acceptance Plan

## Goal

Generate review-grade report bundles for a focused 4-property set and use them to verify that the final reports are correct, useful, and clean.

## Review Set

- `lucerne` - flagship baseline
- `malcolm` - sparse/noisy review case
- `rosewood` - clean report case
- `kelton` - dense-document case

Use `castle-heights` only if one primary property becomes unusable during repeated live review.

## Workflow

Run:

```powershell
python -m app.report_acceptance --property-file validation/report_acceptance_property_pack.json --output-dir review_bundles/report_acceptance
```

For each property, generate:

- `review_bundles/report_acceptance/<slug>/payload.normalized.json`
- `review_bundles/report_acceptance/<slug>/report.html`
- `review_bundles/report_acceptance/<slug>/summary.md`

Also generate:

- `REVIEW_INDEX.md`
- `REPORT_ACCEPTANCE_REPORT.md`

## Acceptance Focus

- address / APN / PIN correctness
- zoning / general plan / community plan correctness
- permit / record / PDF-link correctness
- report section order and readability
- review-flag usefulness
- data-note quality
- duplicate or suspicious report content
- ugly placeholders, mojibake, or misleading wording

## Required Verification

- `python -m unittest discover -s tests -v`
- `python -m compileall app tests`
- `python -m app.report_acceptance --property-file validation/report_acceptance_property_pack.json --output-dir review_bundles/report_acceptance`

Any real correctness or formatting issue found during the bundle review should be fixed, then the affected bundles should be regenerated before finalizing the pass.
