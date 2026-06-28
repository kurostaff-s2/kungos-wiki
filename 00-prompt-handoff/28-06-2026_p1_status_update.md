# P1 Issues — Status Update

**Date**: 2026-06-28  
**Status**: In Progress

---

## Already Fixed (Pre-existing)

| # | Issue | Status |
|---|-------|--------|
| 5 | Accounts - Ledgers route | ✅ Already in `src/routes/main.jsx:169` |
| 6 | Accounts - Financials route | ✅ Already in `src/routes/main.jsx:166` |
| 7 | Products - kurodata | ⏭️ Commented out in frontend, not needed |
| 8 | Products - PreBuilts route | ✅ Already in `src/routes/main.jsx:206` |
| 9 | Products - Peripherals route | ✅ Already in `src/routes/main.jsx:207` |

---

## Fixed This Session

| # | Issue | Fix |
|---|-------|-----|
| 15 | Auth - pwdreset | ✅ Added to `users/api/auth_urls.py` |

---

## Remaining P1 Issues (7)

| # | Domain | Issue | Effort | Priority |
|---|--------|-------|--------|----------|
| 10 | Inventory | stock-audit URL mismatch | 5 min | Low (Vite proxy handles it) |
| 11 | Teams | employeesdata endpoint | 30 min | Medium |
| 12 | Teams | emp-attendance endpoint | 30 min | Medium |
| 13 | Teams | emp-attendancedate endpoint | 30 min | Medium |
| 14 | Shared | checklist endpoint | 15 min | Low |
| 16 | Cafe Tracker | Close receipt field mismatches | 20 min | Medium |
| 17 | Cafe FNB | Menu response shape mismatch | 15 min | Medium |

---

## Notes

### Issue #10 (stock-audit URL)
- **Frontend**: Calls `/api/products/stock-audit` (via Vite proxy → `/api/v1/products/stock-audit`)
- **Backend**: Exists at `/api/v1/products/stock-audit` in `domains/products/urls.py:71`
- **Status**: ✅ Works via Vite proxy rewrite. No fix needed.

### Issues #11-13 (Teams attendance endpoints)
- **Status**: These are legacy endpoints that need to be created
- **Effort**: ~30 min each (create FBVs + register URLs)
- **Priority**: Medium (used by EmployeesSalary and Attendence pages)

### Issue #14 (checklist)
- **Status**: Could be alias to existing `doc-generator` endpoint
- **Effort**: 5 min (add URL route)
- **Priority**: Low (only used in OrdersList for PDF download)

### Issue #16 (Cafe Tracker receipt)
- **Status**: Need to verify actual field names in backend response
- **Effort**: 20 min
- **Priority**: Medium

### Issue #17 (Cafe FNB menu shape)
- **Status**: Need to verify actual response shape
- **Effort**: 15 min
- **Priority**: Medium

---

## Recommended Next Steps

1. **Skip #10** — Works via Vite proxy
2. **Skip #14** — Low priority, can use doc-generator
3. **Focus on #11-13** — Create attendance endpoints (30 min each)
4. **Then #16-17** — Fix response shape mismatches (20 min each)

**Total remaining effort**: ~2.5 hours

---

*Update created: 2026-06-28*
