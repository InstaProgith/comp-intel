# Kelton Review Summary

- Verdict: `accepted-with-review`
- Role: `dense-document-case`
- Address: `3104 Kelton Ave, Los Angeles, CA 90034`
- URL: https://www.redfin.com/CA/Los-Angeles/3104-Kelton-Ave-90034/home/6752630
- Payload: [payload.normalized.json](payload.normalized.json)
- Rendered report: [report.html](report.html)

## Key Facts

- APN: `4254007013`
- PIN: `120B157   124`
- Zoning: `R1-1`
- General Plan: `Low Residential`
- Community Plan: `Palms - Mar Vista - Del Rey`
- Permit count: `7`
- Record count: `20`
- PDF-link count: `10`

## Representative IDs

- Permits: 24014-20000-00638, 24030-70000-01144, 24014-20001-00638
- Documents: CERT 273648, 24014-20001-00638, 24014-20000-00638

## Sources

- redfin: `redfin_parsed_v3`
- zimas: `zimas_profile_v1`
- ladbs_permits: `ladbs_pin_v1`
- ladbs_records: `ladbs_records_v1`

## Report Checks

- Section order matches: `True`
- Property header present: `True`
- Rendered permit items: `7`
- Rendered record items: `20`
- Rendered PDF links: `10`
- Raw None text present: `False`
- Raw null text present: `False`
- Mojibake present: `False`

## Review Flags

- None

## Data Notes

- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.

## Questionable Items

- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Certificate-of-occupancy bundles can reuse a record ID; the report should present them cleanly without implying a suspicious duplicate.

## Mismatches / Issues

- None
