# Report Review Index

| Property | Role | Verdict | Address | Key Facts | Flags | Bundle |
| --- | --- | --- | --- | --- | --- | --- |
| lucerne | flagship-baseline | `accepted-with-review` | 1120 S Lucerne Blvd, Los Angeles, CA 90019 | PIN `129B185   131` / APN `5082004025` / permits `7` / records `14` | permit_address_variants | [summary](./review_bundles/report_acceptance/lucerne/summary.md) / [payload](./review_bundles/report_acceptance/lucerne/payload.normalized.json) / [html](./review_bundles/report_acceptance/lucerne/report.html) |
| malcolm | sparse-noisy-review-case | `accepted-with-review` | 2831 Malcolm Ave, Los Angeles, CA 90064 | PIN `123B157   607` / APN `4255013007` / permits `14` / records `1` | permit_address_variants | [summary](./review_bundles/report_acceptance/malcolm/summary.md) / [payload](./review_bundles/report_acceptance/malcolm/payload.normalized.json) / [html](./review_bundles/report_acceptance/malcolm/report.html) |
| rosewood | clean-report-case | `accepted-with-review` | 3629 Rosewood Ave, Los Angeles, CA 90066 | PIN `111B149   315` / APN `4245011018` / permits `9` / records `10` | none | [summary](./review_bundles/report_acceptance/rosewood/summary.md) / [payload](./review_bundles/report_acceptance/rosewood/payload.normalized.json) / [html](./review_bundles/report_acceptance/rosewood/report.html) |
| kelton | dense-document-case | `accepted-with-review` | 3104 Kelton Ave, Los Angeles, CA 90034 | PIN `120B157   124` / APN `4254007013` / permits `7` / records `20` | none | [summary](./review_bundles/report_acceptance/kelton/summary.md) / [payload](./review_bundles/report_acceptance/kelton/payload.normalized.json) / [html](./review_bundles/report_acceptance/kelton/report.html) |

## Questionable Items

### lucerne
- LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Certificate of Occupancy date not found; construction completion timing uncertain.
- This property is the flagship baseline and should be fully reviewable without hiding the remaining uncertainty that Redfin does not expose the prior developer acquisition event.

### malcolm
- LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- LADBS parcel-level permit output may span 2831 and 2831 1/2 labels; that should remain an explicit review item rather than being silently suppressed.

### rosewood
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Range-style and TEMP address variants should not create noisy review output when the property is otherwise clean.

### kelton
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- Certificate-of-occupancy bundles can reuse a record ID; the report should present them cleanly without implying a suspicious duplicate.
