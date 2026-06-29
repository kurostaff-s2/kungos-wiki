# Frontend-Backend Schema Alignment Audit

**Date:** 2026-06-29  
**Status:** ⚠️ ISSUES FOUND  
**Target Spec:** `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md`

---

## Executive Summary

**Overall Status:** ⚠️ PARTIALLY ALIGNED

The frontend correctly consumes the canonical response envelope (`{status, data, meta}`) but uses **legacy field names** in several places where the backend now returns canonical names.

### Critical Mismatches

| Field | Backend Returns | Frontend Expects | Status |
|-------|----------------|------------------|--------|
| User identity | `identity_id` | `userid` | ❌ MISMATCH |
| Tenant context | `bg_code`, `div_codes`, `branch_codes` | `bg_code`, `div_codes`, `branch_codes` | ✅ ALIGNED |
| Response envelope | `{status, data, meta}` | `{status, data}` or `{data, meta}` | ✅ ALIGNED |

---

## 1. Response Envelope Alignment ✅

### Spec Requirement (§3.1)

```json
{
    "status": "success",
    "data": { ... },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

### Frontend Implementation

**File:** `src/lib/api.jsx` — `unwrapEnvelope()` function

```javascript
const unwrapEnvelope = (response) => {
    if (!response || typeof response !== 'object') return response
    // Reporting envelope: {data, meta}
    if ('data' in response && 'meta' in response) return response.data
    // Legacy envelope: {status, data}
    if ('status' in response && 'data' in response) return response.data
    return response
}
```

### Status: ✅ PASS

Frontend correctly handles both envelope formats. Backend consistently returns `{status, data, meta}`.

---

## 2. Tenant Context Alignment ✅

### Spec Requirement (§5)

JWT claims: `bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`

### Backend Implementation

**File:** `backend/auth_utils.py` — `resolve_access()`

```python
return {
    'user': user,
    'identity_id': identity_id,
    'bg_code': bg_code,
    'div_codes': getattr(ctx, 'div_codes', []),
    'branch_codes': getattr(ctx, 'branch_codes', []),
    ...
}
```

### Frontend Implementation

**Files:** `src/actions/user.jsx`, `src/actions/admin.jsx`

```javascript
setBgCode(userData.bg_code)
if (userData.div_codes?.length) setDivCodes(userData.div_codes)
if (userData.branch_codes?.length) setBranchCodes(userData.branch_codes)
if (userData.active_div_code) setActiveDivCode(userData.active_div_code)
if (userData.active_branch_code) setActiveBranchCode(userData.active_branch_code)
```

### Status: ✅ PASS

Frontend correctly consumes tenant context fields.

---

## 3. Identity Field Alignment ❌ CRITICAL MISMATCH

### Spec Requirement (§4.2, §5.1)

Login response must include `identity_id` (not `userid`):

```json
{
    "user": {
        "identity_id": "ID000001",
        "phone": "+919876543210",
        "name": "John Doe",
        ...
    }
}
```

### Backend Implementation

**File:** `users/api/viewsets.py` — `_build_login_response()`

```python
user_data = {
    'identity_id': identity_id,  # ✅ Canonical
    'phone': phone,
    'name': getattr(user, 'name', ''),
    ...
}
```

### Frontend Implementation ❌

**File:** `src/pages/Tenant/UserAccess.jsx`

```javascript
<TableRow key={u.userid} ...>
    <TableCell>{u.userid}</TableCell>
    ...
    onClick={() => setSelectedUser(u.userid)}>
```

**File:** `src/pages/UserDetails.jsx`

```javascript
<td>{item.profile.userid}</td>
```

**File:** `src/pages/EmployeesSalary.jsx`

```javascript
const empAttendance = attendance.find(emp => emp.userid === employee.userid);
...
<td>{employee.userid}</td>
```

**File:** `src/actions/admin.jsx`

```javascript
return accesslevels[0]?.entity;  // ❌ Legacy
```

### Impact

Frontend will receive `identity_id` from backend but is looking for `userid`. This will cause:
- Empty/undefined user IDs in UI
- Broken user lookup functionality
- Inconsistent identity references

### Status: ❌ FAIL

---

## 4. Legacy Field References

### Found in Frontend

| File | Line | Legacy Field | Should Be |
|------|------|--------------|-----------|
| `src/pages/Tenant/UserAccess.jsx` | 131-146 | `u.userid` | `u.identity_id` |
| `src/pages/UserDetails.jsx` | 46 | `item.profile.userid` | `item.profile.identity_id` |
| `src/pages/EmployeesSalary.jsx` | 113-423 | `employee.userid` | `employee.identity_id` |
| `src/actions/admin.jsx` | 150 | `accesslevels[0]?.entity` | `accesslevels[0]?.bg_code` |

### Backend MongoDB Projections (for reference)

**File:** `backend/utils.py`

```python
PROJ_EMPLOYEE_ATTENDANCE_LIST = {"_id": 0, "userid": 1, ...}  # Still uses userid
PROJ_EMPLOYEE_DATA = {"_id": 0, "userid": 1, ...}  # Still uses userid
PROJ_FNB_USER = {"_id": 0, "userid": 1}  # Still uses userid
```

**Note:** Backend MongoDB still uses `userid` in some projections. This may need migration to `identity_id` for full consistency.

---

## 5. Recommendations

### Immediate Fixes (Frontend)

1. **Update UserAccess.jsx** — Replace `u.userid` with `u.identity_id`
2. **Update UserDetails.jsx** — Replace `item.profile.userid` with `item.profile.identity_id`
3. **Update EmployeesSalary.jsx** — Replace `employee.userid` with `employee.identity_id`
4. **Update admin.jsx** — Replace `accesslevels[0]?.entity` with `accesslevels[0]?.bg_code`

### Backend Considerations

1. **MongoDB Projections** — Consider migrating `userid` to `identity_id` in:
   - `PROJ_EMPLOYEE_ATTENDANCE_LIST`
   - `PROJ_EMPLOYEE_DATA`
   - `PROJ_FNB_USER`

2. **Backward Compatibility** — If frontend migration is complex, backend could temporarily include both fields:
   ```python
   user_data = {
       'identity_id': identity_id,
       'userid': identity_id,  # Legacy alias (remove after frontend update)
       ...
   }
   ```

### Verification Steps

After frontend fixes:

```bash
# Check no legacy userid references in frontend
grep -rn "\.userid" src/ --include="*.jsx" --include="*.js" | grep -v "user_id\|user_ids"

# Check no legacy entity references (except migration context)
grep -rn "\.entity" src/ --include="*.jsx" --include="*.js" | grep -v "entity_id\|entity_type\|entity_name"
```

---

## Sign-Off

| Check | Status | Notes |
|-------|--------|-------|
| Response envelope alignment | ✅ PASS | Frontend handles both formats |
| Tenant context alignment | ✅ PASS | Fields match spec |
| Identity field alignment | ❌ FAIL | Frontend uses `userid`, backend returns `identity_id` |
| Legacy field cleanup | ❌ FAIL | 4 locations with legacy references |

**Next Steps:**
1. Fix frontend field references (`userid` → `identity_id`)
2. Consider backend MongoDB projection migration
3. Re-verify alignment

---

*Audit performed: 2026-06-29 by pi (coding agent)*
