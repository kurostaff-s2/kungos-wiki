# Response Envelope Standardization — Verification Checklist

**Date:** 2026-06-29  
**Purpose:** Verify all response envelope fixes are complete and correct  
**Status:** Verification Template

---

## Pre-Flight Checks

```bash
# Check current state
cd /home/chief/Coding-Projects/kteam-dj-chief

# Count remaining non-compliant calls
echo "=== REMAINING NON-COMPLIANT CALLS ==="
grep -rn "return Response" domains/ backend/ --include="*.py" | grep -v "success_response\|error_response\|reporting_response\|unauthorized_response" | wc -l

# List affected files
echo "=== AFFECTED FILES ==="
grep -rn "return Response" domains/ backend/ --include="*.py" | grep -v "success_response\|error_response\|reporting_response\|unauthorized_response" | cut -d: -f1 | sort -u
```

**Expected:** 0 non-compliant calls, 0 affected files

---

## File-by-File Verification

### Phase 1: High Priority

#### 1. domains/cafe_arcade/views.py
```bash
# Check syntax
python3 -m py_compile domains/cafe_arcade/views.py && echo "✅ Syntax OK"

# Check for raw Response() calls
echo "=== RAW RESPONSE CALLS ==="
grep -n "return Response" domains/cafe_arcade/views.py | grep -v "success_response\|error_response\|reporting_response"

# Check import
grep "from backend.response_utils import" domains/cafe_arcade/views.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 2. domains/orders/services.py
```bash
python3 -m py_compile domains/orders/services.py && echo "✅ Syntax OK"
grep -n "return Response" domains/orders/services.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/orders/services.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 3. domains/tournaments/views.py
```bash
python3 -m py_compile domains/tournaments/views.py && echo "✅ Syntax OK"
grep -n "return Response" domains/tournaments/views.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/tournaments/views.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 4. domains/products/viewsets.py
```bash
python3 -m py_compile domains/products/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/products/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/products/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

---

### Phase 2: Medium Priority

#### 5. domains/accounts/viewsets.py
```bash
python3 -m py_compile domains/accounts/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/accounts/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/accounts/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 6. domains/inventory/reports.py
```bash
python3 -m py_compile domains/inventory/reports.py && echo "✅ Syntax OK"
grep -n "return Response" domains/inventory/reports.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/inventory/reports.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 7. domains/cafe_arcade/gamers_views.py
```bash
python3 -m py_compile domains/cafe_arcade/gamers_views.py && echo "✅ Syntax OK"
grep -n "return Response" domains/cafe_arcade/gamers_views.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/cafe_arcade/gamers_views.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 8. domains/orders/estimates/viewsets.py
```bash
python3 -m py_compile domains/orders/estimates/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/orders/estimates/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/orders/estimates/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 9. domains/orders/viewsets.py
```bash
python3 -m py_compile domains/orders/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/orders/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/orders/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

---

### Phase 3: Low Priority

#### 10. domains/shared/millie.py
```bash
python3 -m py_compile domains/shared/millie.py && echo "✅ Syntax OK"
grep -n "return Response" domains/shared/millie.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/shared/millie.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 11. domains/shared/viewsets.py
```bash
python3 -m py_compile domains/shared/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/shared/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/shared/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 12. backend/urls.py
```bash
python3 -m py_compile backend/urls.py && echo "✅ Syntax OK"
grep -n "return Response" backend/urls.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" backend/urls.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 13. backend/views.py
```bash
python3 -m py_compile backend/views.py && echo "✅ Syntax OK"
grep -n "return Response" backend/views.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" backend/views.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 14. domains/products/services.py
```bash
python3 -m py_compile domains/products/services.py && echo "✅ Syntax OK"
grep -n "return Response" domains/products/services.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/products/services.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 15. domains/teams/viewsets.py
```bash
python3 -m py_compile domains/teams/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/teams/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/teams/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

#### 16. domains/vendors/viewsets.py
```bash
python3 -m py_compile domains/vendors/viewsets.py && echo "✅ Syntax OK"
grep -n "return Response" domains/vendors/viewsets.py | grep -v "success_response\|error_response\|reporting_response"
grep "from backend.response_utils import" domains/vendors/viewsets.py && echo "✅ Import present"
```

**Expected:** 0 raw calls, import present

---

### Phase 4: Special Cases

#### 17. backend/response_utils.py
```bash
python3 -m py_compile backend/response_utils.py && echo "✅ Syntax OK"
grep -n "return Response" backend/response_utils.py | grep -v "success_response\|error_response\|reporting_response"
```

**Expected:** May have 9 calls (these are the utility definitions themselves — verify they are not internal calls that need fixing)

---

## Aggregate Verification

```bash
# Total non-compliant calls (should be 0)
echo "=== TOTAL NON-COMPLIANT CALLS ==="
grep -rn "return Response" domains/ backend/ --include="*.py" | grep -v "success_response\|error_response\|reporting_response\|unauthorized_response" | wc -l

# Files with imports (should be 16+)
echo "=== FILES WITH IMPORTS ==="
grep -rl "from backend.response_utils import" domains/ backend/ --include="*.py" | wc -l

# Git diff summary
echo "=== GIT DIFF SUMMARY ==="
git diff --stat
```

---

## Test Suite Verification

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief

# Run full test suite
python3 manage.py test --keepdb 2>&1 | tail -50

# Check for failures
python3 manage.py test --keepdb 2>&1 | grep -E "FAILED|ERROR|OK" | tail -20
```

**Expected:** All tests pass, no regressions

---

## Sign-Off

| Check | Status | Notes |
|-------|--------|-------|
| All 194 calls replaced | ☐ | |
| All 16 files have imports | ☐ | |
| 0 raw Response() calls remain | ☐ | |
| All files compile | ☐ | |
| Test suite passes | ☐ | |
| Git diff shows only response changes | ☐ | |

**Verified by:** _______________  
**Date:** _______________

---

*Verification checklist generated: 29-06-2026*  
*Total checks: 17 files, 194 calls*  
*Pass criteria: 0 non-compliant calls, all tests pass*
