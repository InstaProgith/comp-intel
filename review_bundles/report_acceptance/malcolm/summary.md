# Malcolm Review Summary

- Verdict: `accepted-with-review`
- Role: `sparse-noisy-review-case`
- Address: `2831 Malcolm Ave, Los Angeles, CA 90064`
- URL: https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382
- Payload: [payload.normalized.json](payload.normalized.json)
- Rendered report: [report.html](report.html)

## Key Facts

- APN: `4255013007`
- PIN: `123B157   607`
- Zoning: `R1-1`
- General Plan: `Low Residential`
- Community Plan: `West Los Angeles`
- Permit count: `14`
- Record count: `1`
- PDF-link count: `1`

## Representative IDs

- Permits: 24047-10000-00180, 23010-10000-05197, 24030-10000-00868
- Documents: 23010-20000-03343

## Sources

- redfin: `redfin_parsed_v3`
- zimas: `zimas_profile_v1`
- ladbs_permits: `ladbs_pin_v1`
- ladbs_records: `ladbs_records_v1`

## Report Checks

- Section order matches: `True`
- Property header present: `True`
- Rendered permit items: `14`
- Rendered record items: `1`
- Rendered PDF links: `1`
- Raw None text present: `False`
- Raw null text present: `False`
- Mojibake present: `False`

## Review Flags

- `permit_address_variants`: LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.

## Data Notes

- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.

## Questionable Items

- LADBS permits reference address labels that extend beyond the subject address; review the permit set for parcel/address crossover.
- Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.
- LADBS parcel-level permit output may span 2831 and 2831 1/2 labels; that should remain an explicit review item rather than being silently suppressed.

## Browser Review Links

- Local report: [report.html](report.html)
- Normalized payload: [payload.normalized.json](payload.normalized.json)
- Summary: [summary.md](summary.md)
- ZIMAS page: [https://zimas.lacity.org/map.aspx?pin=123B157%20%20%20607&ajax=yes](https://zimas.lacity.org/map.aspx?pin=123B157%20%20%20607&ajax=yes)
- LADBS permit portal: [https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr](https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr)
- LADBS docs page: [https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW](https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW)
- First record summary link: [https://ladbsdoc.lacity.org/IDISPublic_Records/idis/Report.aspx?Record_Id=126286468&Image=Visible&ImageToOpen=%7B7054AB8E-0000-CF18-98B4-28549FB1280B%7D%2C](https://ladbsdoc.lacity.org/IDISPublic_Records/idis/Report.aspx?Record_Id=126286468&Image=Visible&ImageToOpen=%7B7054AB8E-0000-CF18-98B4-28549FB1280B%7D%2C)
- First available PDF link: [https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?Library=IDIS&Id=%7B7054AB8E-0000-CF18-98B4-28549FB1280B%7D&ObjType=2&Op=View](https://ladbsdoc.lacity.org/IDISPublic_Records/idis/StPdfViewer.aspx?Library=IDIS&Id=%7B7054AB8E-0000-CF18-98B4-28549FB1280B%7D&ObjType=2&Op=View)
- PIN-based LADBS permit-results link: [https://www.ladbsservices2.lacity.org/OnlineServices/?service=plr&view=permit&pin=123B157%20607](https://www.ladbsservices2.lacity.org/OnlineServices/?service=plr&view=permit&pin=123B157%20607)

## Mismatches / Issues

- None
