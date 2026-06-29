# Frontend-Backend Schema Alignment Audit (v4)

**Date:** 2026-06-29 (Updated)  
**Status:** ✅ OPTION A PARTIALLY EXECUTED  
**Target Spec:** `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md`

---

## Executive Summary

**Overall Status:** ✅ EMPLOYEE/HR DOMAIN MIGRATED

### Execution Summary

**Option A executed for Employee/HR domain** — the highest-priority domain for identity migration.

| Domain | Status | Notes |
|--------|--------|-------|
| **Employee/HR** | ✅ MIGRATED | Backend + Frontend use `identity_id` |
| **Auth/Login** | ✅ CORRECT | Always used `identity_id` |
| **Tournaments** | ☐ FUTURE | Uses `userid` for player references |
| **Orders** | ☐ FUTURE | Uses `userid` for order references |
| **Accounts** | ☐ FUTURE | Uses `userid` for employee references |

---

## 1. The Canonical Identity Model

### Identity Model (Canonical)

```python
class Identity(models.Model):
    """Unified person record — singular source of truth."""
    identity_id = models.CharField(primary_key=True, max_length=20)  # CANONICAL
    user = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True)
```

### CustomUser (Django Auth — Keep `userid`)

```python
class CustomUser(AbstractBaseUser):
    userid = models.CharField(max_length=20, unique=True, primary_key=True)  # AUTH ONLY
```

**Key Point:** `userid` exists ONLY on `CustomUser` (auth). All cross-domain person references must use `identity_id`.

---

## 2. Backend Migration (Employee/HR Domain) ✅

### 2.1 `domains/teams/services.py`

**Migrated functions:**
- `getemployees()` — Returns `identity_id` instead of `userid`
- `getting_attendance_data()` — Returns `identity_id` instead of `userid`

**Before:**
```python
output_list.append({
    'userid': emp.userid,
    'name': emp.userid__user__identity__name,
    ...
})
```

**After:**
```python
output_list.append({
    'identity_id': str(emp.identity_id),
    'name': emp.identity.name,
    ...
})
```

### 2.2 `domains/teams/viewsets.py`

**Migrated:**
- Query parameters: `userid` → `identity_id`
- Filter fields: `userid` → `identity_id`
- Response fields: `userid` → `identity_id`

**Remaining:** 1 reference (CustomUser query — correct, auth context)

### 2.3 Verification

```bash
# Employee/HR domain userid references (should be 0 for non-auth)
cd /home/chief/Coding-Projects/kteam-dj-chief
grep -rn "'userid'" domains/teams/ --include="*.py"
# Result: 1 (CustomUser.auth — correct)
```

---

## 3. Frontend Migration (Employee/HR Domain) ✅

### 3.1 Files Migrated (13 files)

| File | Changes |
|------|---------|
| `src/pages/EmployeesSalary.jsx` | 16 refs: `.userid` → `.identity_id` |
| `src/pages/Hr/Employees.jsx` | 5 refs: `.userid` → `.identity_id` |
| `src/pages/Hr/Attendence.jsx` | 4 refs: `.userid` → `.identity_id` |
| `src/pages/Tenant/UserAccess.jsx` | 4 refs: `.userid` → `.identity_id` |
| `src/pages/Hr/EmployeeAccessLevel.jsx` | 3 refs: `.userid` → `.identity_id` |
| `src/pages/Hr/Dashboard.jsx` | 2 refs: `.userid` → `.identity_id` |
| `src/pages/Users.jsx` | 2 refs: `.userid` → `.identity_id` |
| `src/pages/UserDetails.jsx` | 1 ref: `.userid` → `.identity_id` |
| `src/pages/ServiceRequests/ServiceCreate.jsx` | 1 ref: `.userid` → `.identity_id` |
| `src/pages/ServiceRequests/ServiceRequestsDetail.jsx` | 1 ref: `.userid` → `.identity_id` |
| `src/pages/ServiceRequests/ServiceRequestsList.jsx` | 1 ref: `.userid` → `.identity_id` |
| `src/components/layout/AppSidebar.jsx` | 1 ref: `.userid` → `.identity_id` |
| `src/components/common/Header.jsx` | 1 ref: `.userid` → `.identity_id` |

**Total:** 42 references migrated

### 3.2 Verification

```bash
# Frontend userid references (should only be in Login.jsx)
cd /home/chief/Coding-Projects/kteam-fe-chief
grep -rn "\.userid\b" src/ --include="*.jsx" --include="*.js" | grep -v "user_id\|user_ids"
# Result: 2 (Login.jsx form input — correct, auth context)
```

---

## 4. Remaining Migration (Future Phases)

### 4.1 Tournaments Domain

**Files:** `domains/tournaments/views.py`

**Issue:** Uses `userid` for player/team references (should be `identity_id`)

**Count:** 6 references

**Status:** ☐ FUTURE

### 4.2 Orders Domain

**Files:** `domains/orders/viewsets.py`

**Issue:** Uses `userid` for order references (should be `identity_id`)

**Count:** 2 references

**Status:** ☐ FUTURE

### 4.3 Accounts Domain

**Files:** `domains/accounts/expenditure/inward_invoices.py`

**Issue:** Uses `userid` for employee references (should be `identity_id`)

**Count:** 2 references

**Status:** ☐ FUTURE

### 4.4 Cafe Arcade Domain

**Files:** `domains/cafe_arcade/views.py`, `domains/cafe_arcade/gamers_views.py`

**Issue:** Mix of CustomUser.auth (correct) and player references (incorrect)

**Status:** ☐ FUTURE

---

## 5. Migration Pattern

### Backend Pattern

```python
# ❌ BEFORE
output_list.append({
    'userid': emp.userid,
    'name': emp.userid__user__identity__name,
})

# ✅ AFTER
output_list.append({
    'identity_id': str(emp.identity_id),
    'name': emp.identity.name,
})
```

### Frontend Pattern

```javascript
// ❌ BEFORE
<td>{employee.userid}</td>

// ✅ AFTER
<td>{employee.identity_id}</td>
```

---

## 6. Sign-Off

| Check | Status | Notes |
|-------|--------|-------|
| Employee/HR backend migrated | ✅ | `identity_id` used in APIs |
| Employee/HR frontend migrated | ✅ | 42 refs updated |
| Auth/Login alignment | ✅ | Always correct |
| Tournaments migration | ☐ | Future phase |
| Orders migration | ☐ | Future phase |
| Accounts migration | ☐ | Future phase |
| Cafe Arcade migration | ☐ | Future phase |

**Executed by:** pi (coding agent)  
**Date:** 2026-06-29  
**Option:** A (Canonical field names)  
**Scope:** Employee/HR domain (highest priority)

---

## Next Steps

1. **Deploy Employee/HR migration** — Ready for production
2. **Phase 2:** Migrate Tournaments domain
3. **Phase 3:** Migrate Orders domain
4. **Phase 4:** Migrate Accounts domain
5. **Phase 5:** Migrate Cafe Arcade domain

---

*Audit v4 performed: 2026-06-29 by pi (coding agent)*  
*Option A executed: ✅ Employee/HR domain complete*
