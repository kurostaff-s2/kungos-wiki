# Response Envelope Standardization — Final Fix Task Handoff

**Date:** 2026-06-29  
**Priority:** P1 (blocking ~95% alignment)  
**Status:** Task Handoff — Ready for Execution  
**Predecessor:** `28-06-2026_api-contract-audit-v2.md`

---

## Executive Summary

**Current State:** 194 raw `Response()` calls across 17 files remain non-compliant.  
**Target State:** 0 raw `Response()` calls (all use `success_response()`/`error_response()`).  
**Effort:** Medium — 17 files, ~194 response calls to update.

**Critical Constraint:** Previous subagent attempts failed (exit code 143) or produced partial fixes. This handoff provides detailed instructions and verification steps.

---

## Affected Files (17 total)

| Domain | File | Non-Compliant Calls | Priority |
|--------|------|---------------------|----------|
| **Cafe Arcade** | `domains/cafe_arcade/views.py` | 49 | HIGH |
| **Orders** | `domains/orders/services.py` | 27 | HIGH |
| **Tournaments** | `domains/tournaments/views.py` | 24 | MEDIUM |
| **Products** | `domains/products/viewsets.py` | 20 | MEDIUM |
| **Shared** | `domains/shared/millie.py` | 15 | LOW |
| **Accounts** | `domains/accounts/viewsets.py` | 13 | MEDIUM |
| **Inventory** | `domains/inventory/reports.py` | 9 | LOW |
| **Cafe Arcade** | `domains/cafe_arcade/gamers_views.py` | 8 | LOW |
| **Orders** | `domains/orders/estimates/viewsets.py` | 7 | MEDIUM |
| **Backend** | `backend/response_utils.py` | 9 | LOW |
| **Backend** | `backend/views.py` | 1 | LOW |
| **Backend** | `backend/urls.py` | 2 | LOW |
| **Orders** | `domains/orders/viewsets.py` | 5 | MEDIUM |
| **Products** | `domains/products/services.py` | 1 | LOW |
| **Shared** | `domains/shared/viewsets.py` | 4 | LOW |
| **Teams** | `domains/teams/viewsets.py` | 1 | LOW |
| **Vendors** | `domains/vendors/viewsets.py` | 1 | LOW |
| **TOTAL** | | **194** | |

---

## Canonical Response Utilities

**Location:** `backend/response_utils.py`

### Success Response
```python
from backend.response_utils import success_response

# Basic success
return success_response(data)

# With custom status code
return success_response(data, status_code=status.HTTP_201_CREATED)
```

**Envelope:** `{status: "success", data, meta}`

### Error Response
```python
from backend.response_utils import error_response

# Basic error
return error_response("Error message", code='NOT_FOUND')

# With details
return error_response(exc, code='VALIDATION_ERROR', details={'field': 'error'})
```

**Envelope:** `{status: "error", error: {code, message, details}, meta}`

### Reporting Response (for reports endpoints)
```python
from backend.response_utils import reporting_response

return reporting_response(data, meta={'generated_at': '...'})
```

**Envelope:** `{status: "success", data, meta}`

---

## Error Code Mapping

| Scenario | Error Code |
|----------|-----------|
| Validation failed | `VALIDATION_ERROR` |
| Not authenticated | `AUTH_REQUIRED` |
| Permission denied | `PERMISSION_DENIED` |
| Resource not found | `NOT_FOUND` |
| Conflict (duplicate) | `CONFLICT` |
| Internal server error | `INTERNAL_ERROR` |
| Service unavailable | `SERVICE_UNAVAILABLE` |
| Rate limited | `RATE_LIMITED` |

---

## Execution Instructions

### Phase 1: High Priority Files (49 + 27 + 24 + 20 = 120 calls)

**1. domains/cafe_arcade/views.py (49 calls)**
```bash
# Read entire file first
cat domains/cafe_arcade/views.py

# Add import at top (after existing imports)
from backend.response_utils import success_response, error_response

# Replace ALL raw Response() calls
# Example transformation:
# BEFORE: return Response({'user_id': user.userid, ...}, status=status.HTTP_201_CREATED)
# AFTER:  return success_response({'user_id': user.userid, ...}, status_code=status.HTTP_201_CREATED)

# Example error transformation:
# BEFORE: return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)
# AFTER:  return error_response('Customer not found', code='NOT_FOUND')
```

**2. domains/orders/services.py (27 calls)**
```bash
# Same pattern — read file, add import, replace all Response() calls
```

**3. domains/tournaments/views.py (24 calls)**
```bash
# Same pattern
```

**4. domains/products/viewsets.py (20 calls)**
```bash
# Same pattern
```

### Phase 2: Medium Priority Files (13 + 9 + 8 + 7 + 5 = 42 calls)

**5. domains/accounts/viewsets.py (13 calls)**  
**6. domains/inventory/reports.py (9 calls)**  
**7. domains/cafe_arcade/gamers_views.py (8 calls)**  
**8. domains/orders/estimates/viewsets.py (7 calls)**  
**9. domains/orders/viewsets.py (5 calls)**  

### Phase 3: Low Priority Files (15 + 4 + 2 + 1 + 1 + 1 + 1 = 25 calls)

**10. domains/shared/millie.py (15 calls)**  
**11. domains/shared/viewsets.py (4 calls)**  
**12. backend/urls.py (2 calls)**  
**13. backend/views.py (1 call)**  
**14. domains/products/services.py (1 call)**  
**15. domains/teams/viewsets.py (1 call)**  
**16. domains/vendors/viewsets.py (1 call)**  

### Phase 4: Special Cases (9 calls)

**17. backend/response_utils.py (9 calls)**  
⚠️ **CAUTION:** This file DEFINES the response utilities. Check if these are internal helper calls or if they should remain as-is. May not need changes.

---

## Verification Steps

### Step 1: Syntax Check (after each file)
```bash
python3 -m py_compile <file.py>
```

### Step 2: Compliance Check (after all files)
```bash
# Should return 0 lines
grep -rn "return Response" domains/ backend/ --include="*.py" | grep -v "success_response\|error_response\|reporting_response\|unauthorized_response"
```

### Step 3: Import Check (verify each file has import)
```bash
grep -l "from backend.response_utils import" domains/**/*.py backend/*.py
```

### Step 4: Run Test Suite
```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
python3 manage.py test --keepdb 2>&1 | tail -50
```

### Step 5: Git Diff Review
```bash
git diff --stat
# Verify only response patterns changed, no logic changes
```

---

## Anti-Patterns to Avoid

1. **DO NOT** change business logic — only response wrappers
2. **DO NOT** modify function signatures or parameters
3. **DO NOT** remove existing imports
4. **DO NOT** add new dependencies
5. **DO** preserve exact data structures being returned
6. **DO** use appropriate error codes from the mapping table
7. **DO** verify syntax after each file change

---

## Common Mistakes (from Previous Attempts)

1. **Partial fixes:** Subagents only fixed some Response() calls, leaving others
2. **File corruption:** Exit code 143 (SIGTERM) during large file edits
3. **Missing imports:** Forgetting to add `from backend.response_utils import`
4. **Wrong parameter names:** Using `status=` instead of `status_code=`

---

## Recommended Execution Strategy

**Option A: Single Subagent (Large Task)**
- Dispatch one worker with all 17 files
- Risk: May hit timeout or produce partial fixes
- Mitigation: Provide detailed instructions, verify after

**Option B: Parallel Subagents (Recommended)**
- Group files by domain (4-5 subagents)
- Each subagent handles 3-4 files
- Verify each subagent independently
- Risk: Coordination overhead
- Mitigation: Use git worktrees for isolation

**Option C: Manual Fix (Safest)**
- Fix files manually one at a time
- Verify each file before moving to next
- Risk: Time-consuming
- Mitigation: Use search-and-replace with care

---

## Success Criteria

- [ ] All 194 raw `Response()` calls replaced
- [ ] All 16 files have `from backend.response_utils import`
- [ ] `grep` returns 0 non-compliant lines
- [ ] All files pass `py_compile`
- [ ] Test suite passes (no regressions)
- [ ] Git diff shows only response pattern changes

---

## Expected Outcome

**Alignment:** ~95% (up from ~85%)  
**Remaining Issues:** None (or minimal edge cases)  
**Next Audit:** Recommended after completion

---

## References

- **Spec:** `endpoint_contract_spec_revised.md` §3.1
- **Utilities:** `backend/response_utils.py`
- **Previous Audit:** `28-06-2026_api-contract-audit-v2.md`
- **Review Run:** `review-60e0b2c17029`

---

*Handoff generated: 29-06-2026*  
*Total calls to fix: 194*  
*Files to update: 17*  
*Estimated effort: 2-3 hours*  
*Priority: P1*
