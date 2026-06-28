# P1 Issues Fix Plan

**Date**: 2026-06-28  
**Status**: In Progress

---

## Already Fixed (Pre-existing)

The following P1 issues from the audit were **already resolved** before this session:

| # | Issue | Status |
|---|-------|--------|
| 5 | Accounts - Ledgers route | ✅ Already exists in `src/routes/main.jsx:169` |
| 6 | Accounts - Financials route | ✅ Already exists in `src/routes/main.jsx:166` |
| 8 | Products - PreBuilts route | ✅ Already exists in `src/routes/main.jsx:206` |
| 9 | Products - Peripherals route | ✅ Already exists in `src/routes/main.jsx:207` |

---

## P1 Issues to Fix (9 remaining)

| # | Domain | Issue | Frontend Call | Backend Status |
|---|--------|-------|---------------|----------------|
| 7 | Products | `kurodata` not in urls.py | Commented out | Not needed |
| 10 | Inventory | stock-audit URL mismatch | `/api/products/stock-audit` | `/api/v1/inventory/stock-audit` |
| 11 | Teams | `employeesdata` not in urls.py | `/api/v1/teams/employeesdata` | Not registered |
| 12 | Teams | `emp-attendance` not in urls.py | `/teams/emp-attendance` | Not registered |
| 13 | Teams | `emp-attendancedate` not in urls.py | `/api/v1/teams/emp-attendancedate` | Not registered |
| 14 | Shared | `checklist` not in urls.py | `/api/v1/shared/checklist` | Not registered |
| 15 | Auth | `pwdreset` not in urls.py | `/pwdreset` | Action exists, not routed |
| 16 | Cafe Tracker | Close receipt field mismatches | — | Need to check |
| 17 | Cafe FNB | Menu response shape mismatch | — | Need to check |

---

## Fix Order

### Phase 1: Backend Endpoints (Quick Wins)
1. Add `pwdreset` to auth_urls.py (5 min)
2. Add `employeesdata` to teams/urls.py (10 min)
3. Add `emp-attendance` to teams/urls.py (10 min)
4. Add `emp-attendancedate` to teams/urls.py (10 min)
5. Add `checklist` to shared/urls.py (10 min)

### Phase 2: Frontend URL Fixes
6. Fix stock-audit URL in frontend (10 min)
7. Fix employeesdata URL in frontend (5 min)
8. Fix emp-attendance URL in frontend (5 min)

### Phase 3: Response Shape Fixes
9. Fix Cafe Tracker close receipt fields (20 min)
10. Fix Cafe FNB menu response shape (15 min)

---

## Notes

- **Issue #7 (kurodata)**: Frontend calls are commented out or use external URLs — not needed
- **Issues #5, #6, #8, #9**: Routes already exist in `src/routes/main.jsx`

---

*Plan created: 2026-06-28*
