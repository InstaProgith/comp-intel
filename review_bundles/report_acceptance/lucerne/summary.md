# Lucerne Review Summary

- Verdict: `accepted-with-review`
- Role: `flagship-baseline`
- Address: `1120 S Lucerne Blvd, Los Angeles, CA 90019`
- URL: https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003
- Payload: [payload.normalized.json](payload.normalized.json)
- Rendered report: [report.html](report.html)

## Key Facts

- APN: `5082004025`
- PIN: `129B185   131`
- Zoning: `R1-1-O`
- General Plan: `Low II Residential`
- Community Plan: `Wilshire`
- Permit count: `7`
- Record count: `14`
- PDF-link count: `10`

## Representative IDs

- Permits: 26044-20000-01885, 25042-10001-22280, 25041-10001-59794
- Documents: 25042-90000-22280, 25041-90000-59794, CERT 40332

## Sources

- redfin: `redfin_parsed_v3`
- zimas: `zimas_profile_v1`
- ladbs_permits: `ladbs_pin_v1`
- ladbs_records: `ladbs_records_v1`

## Report Checks

- Section order matches: `True`
- Property header present: `True`
- Rendered permit items: `7`
- Rendered record items: `14`
- Rendered PDF links: `10`
- Raw None text present: `False`
- Raw null text present: `False`
- Mojibake present: `False`

## Review Flags

- `permit_address_variants`: LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.

## Data Notes

- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Certificate of Occupancy date not found; construction completion timing uncertain.

## Questionable Items

- LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Certificate of Occupancy date not found; construction completion timing uncertain.
- This property is the flagship baseline and should be fully reviewable without hiding the remaining uncertainty that Redfin does not expose the prior developer acquisition event.

## Mismatches / Issues

- None
