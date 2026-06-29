# Frontend-Backend Schema Alignment Audit (v3)

**Date:** 2026-06-29 (Updated)  
**Status:** ⚠️ CRITICAL MISMATCH FOUND  
**Target Spec:** `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md`

---

## Executive Summary

**Overall Status:** ❌ SCHEMA MISMATCH — `userid` misuse across frontend and backend

### Critical Finding

**`userid` is ONLY for CustomUser (Django auth) and Identity table mapping.**  
It is **deprecated** for target state. All cross-domain person references must use `identity_id`.

### Current Misuse

| Location | Field Used | Should Use | Status |
|----------|-----------|------------|--------|
| **Frontend employee data** | `userid` | `identity_id` | ❌ MISMATCH |
| **Backend employee API** | `userid` | `identity_id` | ❌ MISMATCH |
| **Backend MongoDB projections** | `userid` | `identity_id` | ❌ MISMATCH |
| **Auth/Login response** | `identity_id` | ✅ | CORRECT |

---

## 1. The Canonical Identity Model

### Identity Model (Canonical)

**File:** `users/models.py` — `Identity`

```python
class Identity(models.Model):
    """Unified person record — singular source of truth."""
    identity_id = models.CharField(primary_key=True, max_length=20)  # CANONICAL
    phone = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    bg_code = models.CharField(max_length=10)
    user = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True)
```

### EmployeeProfile (Extension of Identity)

```python
class EmployeeProfile(models.Model):
    """Employee extension of Identity."""
    identity = models.OneToOneField('users.Identity', on_delete=models.CASCADE, primary_key=True)
    userid = models.CharField(max_length=20, unique=True)  # LEGACY — deprecated
    role = models.CharField(max_length=20)
    ...
```

### CustomUser (Django Auth — Keep `userid`)

```python
class CustomUser(AbstractBaseUser):
    userid = models.CharField(max_length=20, unique=True, primary_key=True)  # AUTH ONLY
    phone = models.CharField(max_length=20)
    ...
```

**Key Point:** `userid` exists ONLY on `CustomUser` (auth) and as a legacy field on `EmployeeProfile`. It should NOT be used for cross-domain person references.

---

## 2. Backend Mismatches

### 2.1 Employee List API

**File:** `domains/teams/services.py` — `getemployees()`

```python
# ❌ CURRENT (uses legacy userid)
output_list.append({
    'userid': emp.userid,  # LEGACY — should be identity_id
    'name': emp.userid__user__identity__name,
    ...
})

# ✅ TARGET (uses canonical identity_id)
output_list.append({
    'identity_id': str(emp.identity_id),  # CANONICAL
    'name': emp.identity.name,
    ...
})
```

### 2.2 MongoDB Projections

**File:** `backend/utils.py`

```python
# ❌ CURRENT
PROJ_EMPLOYEE_ATTENDANCE_LIST = {"_id": 0, "userid": 1, ...}
PROJ_EMPLOYEE_DATA = {"_id": 0, "userid": 1, ...}

# ✅ TARGET
PROJ_EMPLOYEE_ATTENDANCE_LIST = {"_id": 0, "identity_id": 1, ...}
PROJ_EMPLOYEE_DATA = {"_id": 0, "identity_id": 1, ...}
```

### 2.3 Attendance Data

**File:** `domains/teams/services.py` — `getting_attendance_data()`

Likely returns `userid` — needs migration to `identity_id`.

---

## 3. Frontend Mismatches

### 3.1 Employee Data Usage

**Files with `userid` references (44 total):**

| File | Count | Issue |
|------|-------|-------|
| `src/pages/EmployeesSalary.jsx` | 16 | Uses `employee.userid` → should be `employee.identity_id` |
| `src/pages/Hr/Employees.jsx` | 5 | Uses `emp.userid` → should be `emp.identity_id` |
| `src/pages/Hr/Attendence.jsx` | 4 | Uses `emp.userid` → should be `emp.identity_id` |
| `src/pages/Tenant/UserAccess.jsx` | 4 | Uses `u.userid` → should be `u.identity_id` |
| `src/pages/Hr/EmployeeAccessLevel.jsx` | 3 | Uses `emp.userid` → should be `emp.identity_id` |
| `src/pages/Hr/Dashboard.jsx` | 2 | Uses `userid` accessor → should be `identity_id` |
| `src/pages/Users.jsx` | 2 | Uses `user.userid` → should be `user.identity_id` |
| `src/pages/Login.jsx` | 2 | Login form input (keep as-is — auth field) |
| `src/pages/UserDetails.jsx` | 1 | Uses `item.profile.userid` → should be `item.profile.identity_id` |
| `src/pages/ServiceRequests/*.jsx` | 3 | Uses `emp.userid` → should be `emp.identity_id` |
| `src/components/layout/AppSidebar.jsx` | 1 | Uses `userDetails?.userid` → should be `userDetails?.identity_id` |
| `src/components/common/Header.jsx` | 1 | Uses `userDetails?.userid` → should be `userDetails?.identity_id` |

### 3.2 Auth/Login (Correct)

**File:** `src/actions/user.jsx`

```javascript
// ✅ CORRECT — uses identity_id from login response
setBgCode(userData.bg_code)
```

---

## 4. Option A Execution Plan

### Phase 1: Backend API Migration

#### 4.1 Fix `domains/teams/services.py`

**File:** `domains/teams/services.py` — `getemployees()`

```python
def getemployees(empidentity_id=None, divisions_list=None, business_group=None):
    """Get list of employees with optional filters."""
    from users.models import EmployeeProfile
    employees_qs = EmployeeProfile.objects.filter(
        identity__bg_code=business_group
    )
    
    if empidentity_id:
        employees_qs = employees_qs.filter(identity_id=empidentity_id)
    
    if divisions_list:
        employees_qs = employees_qs.filter(
            identity__div_code__in=divisions_list
        )
    
    output_list = []
    for emp in employees_qs:
        output_list.append({
            'identity_id': str(emp.identity_id),  # CANONICAL
            'name': emp.identity.name,
            'phone': str(emp.identity.phone),
            'email': emp.identity.email,
            'role': emp.role,
            'department': emp.department,
            'paid_offs': emp.paid_offs,
            'available_offs': emp.available_offs,
            'festival_offs': emp.festival_offs,
        })
    
    return output_list
```

#### 4.2 Fix MongoDB Projections

**File:** `backend/utils.py`

```python
PROJ_EMPLOYEE_ATTENDANCE_LIST = {"_id": 0, "identity_id": 1, "month": 1, "year": 1, "list": 1}
PROJ_EMPLOYEE_DATA = {"_id": 0, "identity_id": 1, "name": 1, "designation": 1, "department": 1, "phone": 1, "email": 1}
PROJ_FNB_USER = {"_id": 0, "identity_id": 1}
```

#### 4.3 Fix Attendance Data

**File:** `domains/teams/services.py` — `getting_attendance_data()`

Migrate from `userid` to `identity_id`.

### Phase 2: Frontend Migration

#### 4.4 Update All `userid` References

**Files to update (42 references):**

1. `src/pages/EmployeesSalary.jsx` — 16 refs
2. `src/pages/Hr/Employees.jsx` — 5 refs
3. `src/pages/Hr/Attendence.jsx` — 4 refs
4. `src/pages/Tenant/UserAccess.jsx` — 4 refs
5. `src/pages/Hr/EmployeeAccessLevel.jsx` — 3 refs
6. `src/pages/Hr/Dashboard.jsx` — 2 refs
7. `src/pages/Users.jsx` — 2 refs
8. `src/pages/UserDetails.jsx` — 1 ref
9. `src/pages/ServiceRequests/ServiceCreate.jsx` — 1 ref
10. `src/pages/ServiceRequests/ServiceRequestsDetail.jsx` — 1 ref
11. `src/pages/ServiceRequests/ServiceRequestsList.jsx` — 1 ref
12. `src/components/layout/AppSidebar.jsx` — 1 ref
13. `src/components/common/Header.jsx` — 1 ref

**Pattern:** Replace `.userid` with `.identity_id`

### Phase 3: Verification

```bash
# Backend: No userid in employee APIs (except CustomUser auth)
cd /home/chief/Coding-Projects/kteam-dj-chief
grep -rn "'userid'" domains/teams/ backend/utils.py | grep -v "CustomUser\|auth"

# Frontend: No userid in data usage (except login form)
cd /home/chief/Coding-Projects/kteam-fe-chief
grep -rn "\.userid\b" src/ --include="*.jsx" --include="*.js" | grep -v "user_id\|user_ids\|Login"
```

---

## 5. Backward Compatibility Strategy

### Transitional Approach (Recommended)

If frontend migration is complex, backend can include both fields temporarily:

```python
output_list.append({
    'identity_id': str(emp.identity_id),  # Canonical
    'userid': str(emp.identity_id),  # Legacy alias (remove after frontend update)
    ...
})
```

Then update frontend in phases:
1. **Phase 1:** Update login/auth to use `identity_id` (already done)
2. **Phase 2:** Update employee pages (one at a time)
3. **Phase 3:** Remove `userid` alias from backend

---

## 6. Sign-Off

| Check | Status | Notes |
|-------|--------|-------|
| Identity model understanding | ✅ | `userid` is auth-only, `identity_id` is canonical |
| Backend employee API mismatch | ❌ | Returns `userid`, should return `identity_id` |
| Frontend employee data mismatch | ❌ | Uses `userid`, should use `identity_id` |
| MongoDB projection mismatch | ❌ | Uses `userid`, should use `identity_id` |
| Option A execution | ☐ | Pending — requires backend + frontend changes |

**Next Steps:**
1. Execute Phase 1: Backend API migration
2. Execute Phase 2: Frontend migration
3. Verify with tests

---

*Audit v3 performed: 2026-06-29 by pi (coding agent)*  
*Status: ⚠️ CRITICAL MISMATCH — Option A execution pending*
