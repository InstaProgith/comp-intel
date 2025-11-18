# Developer-Focused Report Format

## Target Output Example (3025 Midvale Ave)

### Project Snapshot
- **Address**: 3025 Midvale Ave, Los Angeles, CA 90034
- **Purchase**: Jul 11, 2022 for $1,358,000
- **Original house**: 1,379 SF → **New house**: 3,890 SF (+2,511 SF / +182%)
- **Plans submitted**: Sep 1, 2022 (52 days after purchase)
- **Plans approved**: Dec 1, 2022 (91 days after submission)
- **Construction completed**: Sep 8, 2023 (281 days after approval)
- **Total time**: 424 days (purchase → completion)

### Team
- **Contractor**: Owner builder
- **Architect**: None on record  
- **Engineer**: Jesus Eduardo Carrillo (Lic. NA77737)

### Deal Metrics
- **Purchase price**: $1,358,000
- **Exit/List price**: $X,XXX,XXX
- **Gross spread**: $X,XXX,XXX
- **ROI**: XXX%
- **Hold period**: YYY days

---

## Implementation Goals

1. **Parse square footage changes** from Redfin public records (original SF) vs current listing (new SF)
2. **Extract permit timeline milestones**:
   - Date plans submitted (first permit app date)
   - Date plans approved (plan check approval date)
   - Date construction completed (finaled/CO date)
3. **Calculate durations**:
   - Days from purchase → plans submitted
   - Days from submitted → approved
   - Days from approved → completed
   - Total project duration
4. **Extract team members** with licenses from LADBS contact information
5. **Clean, scannable UI** - remove chart, simplify metrics

