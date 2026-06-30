# Phase 4: API Contract Alignment

**Parent plan:** `30-06-2026_wiring-gap-fixes_82b873.md`
**Phase:** 4 of 5
**Dependencies:** Phases 1-2 must be complete before starting
**Estimated effort:** ~15 min (Phase 4) + ~30 min (Phase 5 audit)

## Project Context

**Backend project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Frontend project root:** `/home/chief/Coding-Projects/kteam-fe-chief`
**Key files for this phase:** 2 frontend files (Phase 4 fix)
**Related codebases:** None

## What This Phase Delivers

Fix verified route mismatch and audit unverified P1 issues.

## Pre-Flight Checklist

- [ ] Phases 1-2 are marked complete
- [ ] Frontend project is accessible at `/home/chief/Coding-Projects/kteam-fe-chief`
- [ ] Git repo is clean (no uncommitted changes)

## Implementation Steps

### Step 1: Fix Verified Issue #2 (Cafe FNB Route Mismatch)

**Problem:** Frontend route uses `/cafe/fnb/menu` (no hyphen), but backend uses `/cafe-fnb/menu` (with hyphen).

**Live state:**
- **Backend:** `/api/v1/cafe-fnb/menu` ✅
- **Frontend API:** `src/lib/cafeApi.js` uses `/api/v1/cafe-fnb/` ✅
- **Frontend Route:** `src/routes/main.jsx:263` uses `/cafe/fnb/menu` ⚠️

**Fix:**

1. **Update `src/routes/main.jsx:263`:**
   ```javascript
   // Before:
   <Route path="/cafe/fnb/menu" element={<FnbMenuManagement />} />
   
   // After:
   <Route path="/cafe-fnb/menu" element={<FnbMenuManagement />} />
   ```

2. **Update `src/data/sidebar-nav.js:229`:**
   ```javascript
   // Before:
   { label: 'F&B Menu', to: '/cafe/fnb/menu', key: 'cafe_fnb_menu', id: 'nav-fnb-menu', icon: UtensilsCrossed },
   
   // After:
   { label: 'F&B Menu', to: '/cafe-fnb/menu', key: 'cafe_fnb_menu', id: 'nav-fnb-menu', icon: UtensilsCrossed },
   ```

### Step 2: Audit Unverified P1 Issues (Phase 5)

**Unverified Issues:**
| # | Domain | Issue |
|---|--------|-------|
| 5 | Accounts | No route for Ledgers page |
| 6 | Accounts | No route for Financials page |
| 8 | Products | No route for PreBuilts page |
| 9 | Products | No route for Peripherals page |
| 10 | Inventory | `/api/products/stock-audit` vs `/api/v1/inventory/stock-audit` |
| 16 | Cafe Tracker | Close receipt field mismatches |
| 17 | Cafe FNB | Menu response shape mismatch |

**Verification commands:**

```bash
# Check if backend endpoint exists
rg -n "ledgers|financials" /home/chief/Coding-Projects/kteam-dj-chief/domains/accounts/
rg -n "prebuilds|peripherals" /home/chief/Coding-Projects/kteam-dj-chief/domains/products/
rg -n "stock-audit" /home/chief/Coding-Projects/kteam-dj-chief/domains/inventory/
rg -n "close_receipt" /home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_arcade/
rg -n "menu_items|items" /home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_fnb/

# Check if frontend route exists
rg -n "Ledgers|Financials|PreBuilts|Peripherals" /home/chief/Coding-Projects/kteam-fe-chief/src/

# Check response shapes
rg -n "menu_items" /home/chief/Coding-Projects/kteam-fe-chief/src/lib/cafeApi.js
```

**Expected outcomes:**
- If endpoint/route exists: Mark as **FALSE** (no action needed)
- If endpoint/route missing: Mark as **TRUE** and fix
- If response shape mismatch: Mark as **TRUE** and align

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/routes/main.jsx` | Fix route path `/cafe/fnb/menu` → `/cafe-fnb/menu` |
| Modify | `src/data/sidebar-nav.js` | Fix route path `/cafe/fnb/menu` → `/cafe-fnb/menu` |

**Total:** 2 files for Phase 4 fix

## Phase-Specific Tests

1. **Test A:** Verify Cafe FNB route fix
   ```bash
   rg -n "/cafe/fnb/menu|/cafe-fnb/menu" /home/chief/Coding-Projects/kteam-fe-chief/src/
   ```
   **Expected:** Only `/cafe-fnb/menu` (with hyphen)

2. **Test B:** Verify frontend builds without errors
   ```bash
   cd /home/chief/Coding-Projects/kteam-fe-chief && npm run build
   ```
   **Expected:** Build succeeds with no errors

3. **Test C:** Audit all 7 unverified issues
   - Document which are FALSE (already implemented)
   - Document which are TRUE (need fix)
   - Fix TRUE issues

## Completion Gate

- [ ] Issue #2 fixed (Cafe FNB route uses `/cafe-fnb/menu`)
- [ ] All false claims documented (Issues #7, #11-15)
- [ ] All unverified issues audited (Issues #5-6, #8-9, #10, #16-17)
- [ ] Frontend builds without errors
- [ ] Files committed to git

## Notes for Next Phase

Phase 5 (Audit Unverified P1 Issues) is part of this phase handoff. Complete the audit and fix any verified issues.
