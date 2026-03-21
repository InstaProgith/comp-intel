# Multi-Property QA Report

## Scope

This pass stayed on the latest merged `main` baseline and used the narrowed five-property Los Angeles validation set supplied by the user.

No new providers, VPS work, PDF download plumbing, or architecture rewrites were added.

## Properties Tested

- `malcolm`
  - `https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382`
  - tags: sparse records, recent sale, permit-endpoint uncertainty
- `rosewood`
  - `https://www.redfin.com/CA/Los-Angeles/3629-Rosewood-Ave-90066/home/6746236`
  - tags: recently permitted, multiple LADBS docs, range-style address labels
- `kelton`
  - `https://www.redfin.com/CA/Los-Angeles/3104-Kelton-Ave-90034/home/6752630`
  - tags: older records, certificate bundle, dense document history
- `castle-heights`
  - `https://www.redfin.com/CA/Los-Angeles/2631-Castle-Heights-Pl-90034/home/6792332`
  - tags: multiple LADBS docs, certificate bundle, different zoning profile
- `appleton`
  - `https://www.redfin.com/CA/Los-Angeles/12506-Appleton-Way-90066/home/6748251`
  - tags: newer build, multiple LADBS docs, TEMP address label

The structured validation pack lives in:

- [los_angeles_five_property_pack.json](C:/Users/navid/Desktop/comp-intel/validation/los_angeles_five_property_pack.json)

## Commands Run

Baseline:

```powershell
git branch --show-current
git status --short
git fetch origin main
git checkout main
git pull --ff-only origin main
git checkout -b codex/multi-property-qa-pass
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m app.qa_harness
```

Initial live probes:

```powershell
@'
from app.redfin_scraper import get_redfin_data
urls = [
    'https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382',
    'https://www.redfin.com/CA/Los-Angeles/3629-Rosewood-Ave-90066/home/6746236',
    'https://www.redfin.com/CA/Los-Angeles/3104-Kelton-Ave-90034/home/6752630',
    'https://www.redfin.com/CA/Los-Angeles/2631-Castle-Heights-Pl-90034/home/6792332',
    'https://www.redfin.com/CA/Los-Angeles/12506-Appleton-Way-90066/home/6748251',
]
...
'@ | .\.venv\Scripts\python.exe -

@'
from app.orchestrator import run_full_comp_pipeline
urls = [
    ('malcolm','https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382'),
    ('rosewood','https://www.redfin.com/CA/Los-Angeles/3629-Rosewood-Ave-90066/home/6746236'),
    ('kelton','https://www.redfin.com/CA/Los-Angeles/3104-Kelton-Ave-90034/home/6752630'),
    ('castle-heights','https://www.redfin.com/CA/Los-Angeles/2631-Castle-Heights-Pl-90034/home/6792332'),
    ('appleton','https://www.redfin.com/CA/Los-Angeles/12506-Appleton-Way-90066/home/6748251'),
]
...
'@ | .\.venv\Scripts\python.exe -
```

Targeted diagnosis and reruns:

```powershell
@'
from app.orchestrator import run_full_comp_pipeline
payload = run_full_comp_pipeline('https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382')
...
'@ | .\.venv\Scripts\python.exe -

@'
from app.ladbs_scraper import get_ladbs_data
result = get_ladbs_data(
    apn='4255013007',
    address='2831 Malcolm Ave, Los Angeles, CA 90064',
    redfin_url='https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382',
)
...
'@ | .\.venv\Scripts\python.exe -

@'
from app.zimas_client import get_zimas_profile
result = get_zimas_profile(
    apn='4255013007',
    address='2831 Malcolm Ave, Los Angeles, CA 90064',
    redfin_url='https://www.redfin.com/CA/Los-Angeles/2831-Malcolm-Ave-90064/home/6753382',
)
...
'@ | .\.venv\Scripts\python.exe -
```

Final verification:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m app.qa_harness --property-file validation\los_angeles_five_property_pack.json
.\.venv\Scripts\python.exe -m app.qa_harness --property-file validation\los_angeles_five_property_pack.json --json
.\\.venv\\Scripts\\python.exe -m app.qa_harness --property-file validation\\los_angeles_five_property_pack.json
```

## Issues Found

1. `ladbs_ok` was overly permissive. A property could return `ladbs_pin_error` with zero permits and still be marked successful.
2. The address-based ZIMAS PIN resolver could return percent-encoded PINs and matched addresses. That caused the Malcolm LADBS by-PIN request to fail even though the underlying parcel could be resolved.
3. The LADBS by-PIN address-section parsing could pull unrelated street sections into the permit set. Malcolm exposed a spurious `24137 W ALBERS ST 91367` section.
4. `permit_address_variants` was too noisy for TEMP labels and range labels that still clearly belonged to the subject address.
5. `shared_record_ids` was too noisy for same-day certificate-of-occupancy document bundles, especially when LADBS reused one record ID for related CO documents.
6. The report omitted the `Review Flags` section entirely for clean properties, which made layout and harness expectations inconsistent across the set.
7. After the first fixes, broader reruns exposed transient upstream instability in both browserless live clients:
   - LADBS `PermitResultsbyPin` could briefly return service-unavailable content during a five-property batch even though an immediate rerun succeeded.
   - ZIMAS parcel-profile requests could briefly fail for individual properties during a batch even though immediate single-property reruns succeeded.

## Fixes Made

### Correctness

- Updated [app/orchestrator.py](C:/Users/navid/Desktop/comp-intel/app/orchestrator.py) so only real LADBS success/no-result sources count as `ladbs_ok`.
- Updated [app/orchestrator.py](C:/Users/navid/Desktop/comp-intel/app/orchestrator.py) fallback/report defaults to use clean ASCII-safe `N/A` placeholders in normalized error payloads.
- Updated [app/zimas_pin_client.py](C:/Users/navid/Desktop/comp-intel/app/zimas_pin_client.py) so percent-encoded PINs and matched addresses are decoded before downstream use.
- Updated [app/ladbs_scraper.py](C:/Users/navid/Desktop/comp-intel/app/ladbs_scraper.py) to filter PIN address sections by the subject street signature and ignore unrelated sections when valid matching sections exist.
- Updated [app/ladbs_scraper.py](C:/Users/navid/Desktop/comp-intel/app/ladbs_scraper.py) to retry transient `PermitResultsbyPin` request failures and service-unavailable responses before falling back.
- Updated [app/zimas_client.py](C:/Users/navid/Desktop/comp-intel/app/zimas_client.py) to retry transient parcel-profile HTTP failures and preserve request-attempt diagnostics.

### Anomaly Cleanup

- Updated [app/payload_contract.py](C:/Users/navid/Desktop/comp-intel/app/payload_contract.py) so `permit_address_variants` ignores TEMP and range-style labels that still include the subject address.
- Updated [app/payload_contract.py](C:/Users/navid/Desktop/comp-intel/app/payload_contract.py) so `shared_record_ids` ignores same-day certificate-of-occupancy bundles instead of flagging them as suspicious duplicates.
- Updated source diagnostics so `duplicate_record_id_count` follows the same quieter logic.

### Harness / Report / Regression

- Expanded [app/qa_harness.py](C:/Users/navid/Desktop/comp-intel/app/qa_harness.py) to:
  - load richer property-pack metadata
  - summarize key fields per property
  - summarize report cleanliness checks
  - compare allowed source lists and minimum PDF-link counts
  - include known truths, key fields to verify, and acceptable uncertainty notes in the summary
- Updated [templates/report.html](C:/Users/navid/Desktop/comp-intel/templates/report.html) so `Review Flags` always renders. Clean properties now show `No review flags.`
- Added/strengthened regression coverage in:
  - [tests/test_ladbs_scraper.py](C:/Users/navid/Desktop/comp-intel/tests/test_ladbs_scraper.py)
  - [tests/test_orchestrator_contract.py](C:/Users/navid/Desktop/comp-intel/tests/test_orchestrator_contract.py)
  - [tests/test_payload_contract.py](C:/Users/navid/Desktop/comp-intel/tests/test_payload_contract.py)
  - [tests/test_qa_harness.py](C:/Users/navid/Desktop/comp-intel/tests/test_qa_harness.py)
  - [tests/test_ui_server.py](C:/Users/navid/Desktop/comp-intel/tests/test_ui_server.py)
  - [tests/test_zimas_pin_client.py](C:/Users/navid/Desktop/comp-intel/tests/test_zimas_pin_client.py)
- Added retry regressions for transient live-client failures in:
  - [tests/test_ladbs_scraper.py](C:/Users/navid/Desktop/comp-intel/tests/test_ladbs_scraper.py)
  - [tests/test_zimas_client.py](C:/Users/navid/Desktop/comp-intel/tests/test_zimas_client.py)
- Updated [README.md](C:/Users/navid/Desktop/comp-intel/README.md) with the five-property harness command.

## Before / After

Before:

- Malcolm returned `ladbs_pin_error`, `ladbs_ok=True`, and `permit_count=0`.
- Rosewood, Kelton, Castle Heights, and Appleton all carried noisy anomaly output tied to address-label formatting or certificate bundles.
- Clean properties omitted the `Review Flags` section entirely, which made the report layout inconsistent.

After:

- Malcolm now returns `ladbs_pin_v1`, `ladbs_ok=True`, and `permit_count=14`.
- Rosewood, Kelton, Castle Heights, and Appleton all validate with `anomaly_count=0`.
- `duplicate_record_id_count` is `0` for all five final results.
- The report now always renders `Review Flags`, with either real flags or `No review flags.`
- The five-property harness stayed green across text mode, JSON mode, and a second consecutive full rerun after the live-client retry hardening.

## Final Results Summary

- `malcolm`
  - Redfin: `redfin_parsed_v3`
  - ZIMAS: `zimas_profile_v1`
  - LADBS permits: `ladbs_pin_v1`
  - LADBS records: `ladbs_records_v1`
  - permits: `14`
  - records: `1`
  - pdf links: `1`
  - anomalies: `permit_address_variants`
- `rosewood`
  - Redfin: `redfin_parsed_v3`
  - ZIMAS: `zimas_profile_v1`
  - LADBS permits: `ladbs_pin_v1`
  - LADBS records: `ladbs_records_v1`
  - permits: `9`
  - records: `10`
  - pdf links: `9`
  - anomalies: none
- `kelton`
  - Redfin: `redfin_parsed_v3`
  - ZIMAS: `zimas_profile_v1`
  - LADBS permits: `ladbs_pin_v1`
  - LADBS records: `ladbs_records_v1`
  - permits: `7`
  - records: `20`
  - pdf links: `10`
  - anomalies: none
- `castle-heights`
  - Redfin: `redfin_parsed_v3`
  - ZIMAS: `zimas_profile_v1`
  - LADBS permits: `ladbs_pin_v1`
  - LADBS records: `ladbs_records_v1`
  - permits: `9`
  - records: `17`
  - pdf links: `14`
  - anomalies: none
- `appleton`
  - Redfin: `redfin_parsed_v3`
  - ZIMAS: `zimas_profile_v1`
  - LADBS permits: `ladbs_pin_v1`
  - LADBS records: `ladbs_records_v1`
  - permits: `11`
  - records: `13`
  - pdf links: `12`
  - anomalies: none

## Remaining Weak Spots

1. Malcolm still carries one real `permit_address_variants` review flag because the live permit set spans `2831` and `2831 1/2` address labels on the parcel. That now looks like a real parcel/address review case, not formatting noise.
2. All five properties still show the data note about unknown purchase price because the Redfin histories in these current live pages do not expose a prior developer-acquisition sale event. That is an honest limitation, not a parser bug.
3. This validation pack is intentionally live-data-tolerant. It uses stable truths and minimum counts rather than pretending that permit/document counts will never change.

## Readiness Assessment

Outcome A: full green finish.

Readiness for the current feature set is strong for this five-property set.

Why:

- the validation pack passed end-to-end on five real Los Angeles properties
- tests increased from `35` to `43` and the new tests directly cover live bugs found during this run
- the report contract is cleaner and more consistent
- the anomaly signal is materially more precise
- the remaining review signal is small and explainable rather than noisy or misleading
- the browserless LADBS and ZIMAS clients now tolerate the transient live instability that showed up during repeated multi-property reruns
