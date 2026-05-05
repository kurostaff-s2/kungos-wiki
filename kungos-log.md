# KungOS Modernization — Decision & Change Log

> Track non-trivial decisions, guardrail violations, and significant changes.
> Format: `YYYY-MM-DD | Area | Description | Rationale | Approver`

---

## 2026-05-05

### Collection Naming Standardization (camelCase → lowercase)
- **Area:** MongoDB Collections, Backend Code, Design Doc
- **Change:** Renamed 7 collections from camelCase to lowercase (`inwardInvoices` → `inwardinvoices`, `outwardInvoices` → `outwardinvoices`, `paymentVouchers` → `paymentvouchers`, `inwardCreditNotes` → `inwardcreditnotes`, `inwardDebitNotes` → `inwarddebitnotes`, `outwardCreditNotes` → `outwardcreditnotes`, `outwardDebitNotes` → `outwarddebitnotes`)
- **Rationale:** Design doc §3/§5 documents lowercase names. Legacy camelCase caused silent query failures (e.g., `FinancialsViewSet` queried `inwardinvoices` but collection was `inwardInvoices` → returned 0 results). No alias layer — rename collections to match spec per "no backend workarounds" guardrail.
- **Files:** 21 Python files, `KungOS_Analytics_Design.md` §11.6, `SKILL.md`, `db/README.md`
- **Commit:** `e540d21`

### Period Alias Expansion
- **Area:** Period Parsing, ReportingViewSet
- **Change:** `ALLOWED_PERIODS` now includes `curr_month`, `last_month`, `curr_quarter`, `last_quarter`, `curr_fy`, `last_fy` in base `ReportingViewSet` + all child ViewSets
- **Rationale:** `PeriodParser` supports these aliases but `ALLOWED_PERIODS` whitelist rejected them, causing silent fallback to `monthly`. Users passing `?period=curr_fy` got May-only data instead of FY data.
- **Files:** `backend/reporting_base.py`, `domains/accounts/viewsets.py`, `domains/shared/viewsets.py`
- **Commit:** `e540d21`

### Data Gap Discovery — inwardinvoices
- **Area:** Data Integrity, E2E Testing
- **Finding:** Current `KungOS_Mongo_One.inwardinvoices` has 16 docs (2022-2023, KG-100xxx series). Production dump has 4,626 docs (2020-2026). ITC-GST endpoint returns 0 for current periods.
- **Action:** Documented in `db/README.md`. Full data available in dump. Restoration deferred — requires careful merge to avoid duplicate keys and data corruption.
- **Status:** Documented, not yet restored

---
