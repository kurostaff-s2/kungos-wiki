# Accesslevel → RBAC Migration — Deprecated Wiring Removal

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `e1ae60` |
| Entity type | `handoff` |
| Short description | Migrate permission resolution from deprecated `users_accesslevel` (55-col flat table) to normalized `rbac_*` tables, refactoring DB → backend utils → endpoint contracts |
| Status | `draft` |
| Source references | `Kung_OS/architecture/rbac_system.md`, `Kung_OS/specs/database_schemas/postgresql_schema.md` (§2.4 DEPRECATED, §5 RBAC), `Kung_OS/specs/endpoint_contract_spec.md` (§4.3 Auth Migration Notes) |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 (field mapping), Phase 2 (adapter layer), Phase 3 (resolve_access rewrite), Phase 4 (permission helpers), Phase 5 (endpoint contracts), Phase 6 (AccesslevelSerializer removal) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md` (RBAC constitution — resolution engine, schema, decisions)
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` (§2.4 `users_accesslevel` DEPRECATED, §5 RBAC LIVE=TARGET)
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` (§4.3 Login Response Contract — `accesslevel[]` → `permissions[]`)
- `/home/chief/llm-wiki/Kung_OS/architecture/identity_layer.md` (Identity layer — `CustomUser` → `Identity`+`EmployeeProfile`)
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend consumes `accesslevel[]` in login/me responses)
**Key files for this task:**
- `users/models.py` (`Accesslevel` DEPRECATED model, `rbac_*` TARGET models)
- `users/permissions.py` (RBAC resolution engine — `resolve_permission()`, `build_permissions_object()`)
- `backend/auth_utils.py` (deprecated: `resolve_access()`, `has_*_access()`, `check_*()`, `get_*_divisions()`)
- `backend/utils.py` (deprecated: `resolve_access_levels()`)
- `users/serializers.py` (`AccesslevelSerializer` — serializes deprecated model)
- `users/views.py` (`business_accesslevel()`, `division_accesslevel()`)
- `users/api/viewsets.py` (`_build_user_data()`, `AccessLevelViewSet`)

## Background

The `users_accesslevel` table (55 columns, flat permission fields) is **DEPRECATED** per spec §2.4:

> `users_accesslevel` — 55 columns, flat permission fields. **DEPRECATED** — 50+ varchar permission fields. Replaced by RBAC tables.

The normalized RBAC tables (`rbac_permissions`, `rbac_roles`, `rbac_role_permissions`, `rbac_user_roles`, `rbac_user_role_branches`, `rbac_user_permissions`) are **LIVE and stable** per spec §5.

The RBAC resolution engine (`users/permissions.py`) is implemented and operational:
- `resolve_permission(userid, perm_code, bg_code, division)` — cascading resolution (override → role → default)
- `build_permissions_object(userid, bg_code)` — bulk pre-computation for API responses
- Redis caching layer with TTL invalidation

**However, the deprecated wiring is still the active path:**

| Layer | Deprecated (LIVE) | Target (LIVE but unused) |
|-------|-------------------|--------------------------|
| **DB** | `Accesslevel.objects.filter(userid=X)` (55-col flat scan) | `rbac_*` tables (normalized queries) |
| **Resolution** | `resolve_access()` → `resolve_access_levels()` → flat `{div_code: {field: int}}` dict | `resolve_permission()` → cascading override→role→default |
| **Helpers** | `has_read_access(access_dict, 'orders')` (flat field check) | `resolve_permission(userid, 'orders.view', bg_code, div_code)` |
| **Serialization** | `AccesslevelSerializer(access_data, many=True)` | RBAC serializers (not yet built) |
| **Response** | `accesslevel[]` (flat perm strings) in login/me | `permissions[]` (RBAC perm_codes) + `roles[]` |

**Call site inventory:**

| Function | Call Sites | Pattern |
|---|---|---|
| `resolve_access(request)` | 184 | Full tenant context + access levels |
| `has_read_access(access_dict, field)` | ~60 | Any-division read check |
| `has_write_access(access_dict, field, level)` | ~50 | Any-division write check |
| `has_division_read_access(...)` | ~40 | Specific-division read check |
| `has_division_write_access(...)` | ~35 | Specific-division write check |
| `check_access(user_access, field, access_dict)` | ~40 | Super OR field check |
| `check_write_access(...)` | ~30 | Super OR write check |
| `check_division_access(...)` | ~20 | Super OR division check |
| `check_division_write_access(...)` | ~15 | Super OR division write |
| `get_accessible_divisions(access_dict, field)` | ~10 | List divisions with permission |
| `get_all_divisions(access_dict)` | ~5 | All divisions |
| `get_branch_fallback(access_dict)` | ~3 | First branch fallback |
| `resolve_minimal(request)` | 15 | BG + switchgroup only |
| `resolve_user_with_bg(request)` | 10 | User + BG + switchgroup |
| `resolve_user(request)` | 8 | KuroUser only |
| `business_accesslevel(acc_data, userid)` | ~5 | CRUD on Accesslevel records |
| `division_accesslevel(division, bg_code)` | ~3 | Division-level access CRUD |
| `AccesslevelSerializer` imports | 10+ files | Serialization |
| `Accesslevel.objects` direct queries | 20+ files | Raw model access |

**Total: ~520+ call sites across the codebase.**

Individual call-site migration is infeasible. The strategy is **adapter-layer transparency**: rewrite the deprecated functions to use RBAC internally while maintaining identical signatures and return shapes. Callers need zero changes.

---

## Migration Strategy

### Principle: Adapter-First, Call-Sites-Zero

1. **Create a field mapping** (legacy field name → RBAC perm_code)
2. **Rewrite `resolve_access_levels()`** to query RBAC tables and return the same `{div_code: {field: int}}` shape
3. **Rewrite `resolve_access()`** to use RBAC tenant context (`UserTenantContext`) instead of `Switchgroupmodel`+`Accesslevel`
4. **Rewrite permission helpers** to call `resolve_permission()` internally
5. **Update endpoint contracts** to return `permissions[]` alongside `accesslevel[]` (transitional dual-mode)
6. **Deprecate `AccesslevelSerializer`** — replace with RBAC serializers in endpoints
7. **Keep `Accesslevel` model** (DEPRECATED but not dropped) until frontend fully migrates

### Why Not Drop Accesslevel Immediately?

- `business_accesslevel()` writes to `Accesslevel` (CRUD for employee permission management)
- Frontend may still POST to access-level endpoints with flat permission data
- Dropping the table before frontend migration = data loss

### Field Mapping Strategy

The legacy `Accesslevel` model has 44 permission fields (integer 0-3). The RBAC `Permission` model uses `{module}.{resource}` codes. The adapter maps between them:

```python
# Legacy field → RBAC perm_code mapping
LEGACY_TO_RBAC = {
    'inward_invoices': 'invoices.inward',
    'inward_creditnotes': 'invoices.inward_credit',
    'inward_debitnotes': 'invoices.inward_debit',
    'outward_invoices': 'invoices.outward',
    'outward_creditnotes': 'invoices.outward_credit',
    'outward_debitnotes': 'invoices.outward_debit',
    'purchase_orders': 'orders.purchase',
    'purchases': 'orders.purchase',
    'counters': 'admin.counters',
    'vendors': 'vendors.view',
    'export_data': 'admin.export',
    'user_list': 'users.view',
    'estimates': 'estimates.view',
    'inward_payments': 'payments.inward',
    'outward_payments': 'payments.outward',
    'orders': 'orders.view',
    'offline_orders': 'orders.offline',
    'online_orders': 'orders.online',
    'products': 'products.view',
    'inventory': 'inventory.view',
    'indent': 'indent.view',
    'stock': 'stock.view',
    'sales': 'sales.view',
    'outward': 'outward.view',
    'audit': 'audit.view',
    'tp_builds': 'products.tp_build',
    'bulk_payments': 'payments.bulk',
    'paymentvouchers': 'invoices.payment_voucher',
    'replace_presets': 'presets.replace',
    'presets': 'presets.view',
    'service_request': 'service.view',
    'hr': 'hr.view',
    'emp_attendance': 'hr.attendance',
    'financials': 'financials.view',
    'analytics': 'analytics.view',
    'profile': 'profile.view',
    'product_finder': 'products.find',
    'peripherals': 'peripherals.view',
    'portal_editor': 'admin.portal',
    'employees': 'hr.employees',
    'employees_salary': 'hr.salary',
    'employee_accesslevel': 'hr.accesslevel',
    'bg_group': 'admin.bg_group',
    'job_application': 'careers.application',
    'pre_builts_finder': 'products.pre_built',
}
```

**Level mapping:** Legacy uses integer 0-3 (None/View/Edit/Supervisor). RBAC uses the same 0-3 scale. Direct 1:1 mapping — no conversion needed.

---

## Phase 1: Field Mapping Registry

**What:** Create the legacy-to-RBAC field mapping as a maintainable registry.

**Files:**
- Create `users/rbac_mapping.py`

**Steps:**

1. Read `rbac_permissions` table to get the authoritative list of active perm_codes:
   ```python
   from users.models import Permission
   perms = Permission.objects.filter(is_active=True).values_list('perm_code', flat=True)
   ```

2. Create `users/rbac_mapping.py`:
   ```python
   """Legacy Accesslevel field → RBAC perm_code mapping.

   Used by adapter layer to translate between deprecated flat permissions
   and normalized RBAC permissions. Remove when Accesslevel model is dropped.
   """

   # Legacy field name (Accesslevel model column) → RBAC perm_code
   LEGACY_TO_RBAC = { ... }  # See mapping table above

   # Reverse mapping: RBAC perm_code → legacy field name
   RBAC_TO_LEGACY = {v: k for k, v in LEGACY_TO_RBAC.items()}

   # Legacy fields with no RBAC equivalent (dropped in target)
   LEGACY_DROPPED_FIELDS = set()  # Populate if any legacy fields have no RBAC mapping

   # Cafe-specific fields added by resolve_access_levels() but not on Accesslevel model
   CAFE_FIELDS = {
       'station_management': 'cafe.station',
       'wallet_management': 'cafe.wallet',
       'wallet_recharge': 'cafe.wallet_recharge',
       'pricing_management': 'cafe.pricing',
       'cafe_dashboard': 'cafe.dashboard',
       'cafe_sessions': 'cafe.sessions',
       'cafe_payments': 'cafe.payments',
   }
   LEGACY_TO_RBAC.update(CAFE_FIELDS)
   RBAC_TO_LEGACY.update({v: k for k, v in CAFE_FIELDS.items()})

   def legacy_field_to_rbac(field_name):
       """Convert legacy field name to RBAC perm_code. Returns None if unmapped."""
       return LEGACY_TO_RBAC.get(field_name)

   def rbac_to_legacy_field(perm_code):
       """Convert RBAC perm_code to legacy field name. Returns None if unmapped."""
       return RBAC_TO_LEGACY.get(perm_code)
   ```

3. Verify mapping completeness:
   ```python
   # Check that all Accesslevel permission fields have RBAC mappings
   from users.models import Accesslevel
   model_fields = [f.name for f in Accesslevel._meta.get_fields()
                   if isinstance(f, (models.IntegerField,))]
   unmapped = [f for f in model_fields if f not in LEGACY_TO_RBAC]
   assert not unmapped, f"Unmapped legacy fields: {unmapped}"
   ```

**Tests:**
1. **Mapping completeness:** All `Accesslevel` IntegerField columns have RBAC mappings.
2. **Bidirectional consistency:** `legacy_field_to_rbac(rbac_to_legacy_field(code)) == code` for all mapped codes.
3. **Cafe fields included:** All 7 cafe fields map to RBAC perm_codes.

**Dependencies:** None.

---

## Phase 2: `resolve_access_levels()` Adapter

**What:** Rewrite `resolve_access_levels()` in `backend/utils.py` to query RBAC tables instead of `Accesslevel`, while returning the same `{div_code: {field: int}}` shape.

**Current signature:**
```python
def resolve_access_levels(access_query, bg_code):
    # access_query = Accesslevel.objects.filter(userid=X)
    # Returns: {div_code: {field_name: int_value, ...}, ...}
```

**New implementation:**
```python
def resolve_access_levels(access_query=None, bg_code=None, userid=None):
    """Resolve permissions to legacy-compatible dict keyed by division.

    DEPRECATED adapter — translates RBAC permissions to legacy flat format.
    Maintains backward compatibility with has_*_access() helpers.

    Args:
        access_query: (DEPRECATED) Accesslevel QuerySet — ignored if userid provided.
        bg_code: Business Group code for scoping.
        userid: User ID for RBAC resolution (preferred over access_query).

    Returns:
        dict: {div_code: {field_name: int_value, ...}, ...}
              Same shape as legacy Accesslevel-based resolution.
    """
    from users.permissions import resolve_permission
    from users.rbac_mapping import LEGACY_TO_RBAC, CAFE_FIELDS
    from users.models import UserRole

    if not userid:
        # Fallback: if only access_query provided, extract userid from it
        if hasattr(access_query, 'first'):
            first = access_query.first()
            userid = first.userid if first else None

    if not userid:
        return {}

    # Get all divisions this user has roles in (for this BG)
    user_roles = UserRole.objects.filter(
        userid=userid,
        bg_code__in=[bg_code or '', '']  # BG-scoped + global
    )
    divisions = set()
    for ur in user_roles:
        if ur.division:
            divisions.add(ur.division)
    if not divisions:
        divisions.add('')  # Global scope — use empty string as key

    # Build legacy-compatible access dict
    access_dict = {}
    all_legacy_fields = list(LEGACY_TO_RBAC.keys())

    for div_code in divisions:
        field_values = {}
        for legacy_field in all_legacy_fields:
            rbac_code = LEGACY_TO_RBAC[legacy_field]
            resolved = resolve_permission(userid, rbac_code, bg_code=bg_code, division=div_code)
            field_values[legacy_field] = resolved['level']
        access_dict[div_code] = field_values

    return access_dict
```

**Key design decisions:**
- **Signature preserved:** `resolve_access_levels(access_query, bg_code)` still works (access_query is read for userid, then ignored).
- **Return shape preserved:** `{div_code: {field: int}}` — identical to legacy.
- **RBAC internally:** Uses `resolve_permission()` for each field/division combination.
- **Performance:** This is O(fields × divisions × RBAC_queries). For 44 fields × 3 divisions = 132 queries. Mitigated by Redis caching in `users/permissions.py` (15-min TTL). Add bulk resolution in Phase 4 if performance is an issue.

**Files:**
- Modify `backend/utils.py`

**Steps:**

1. Read current `resolve_access_levels()` in `backend/utils.py`.
2. Replace with RBAC-based adapter (see implementation above).
3. Add `ponytail:` comment marking the adapter as transitional.
4. Verify Python syntax.

**Tests:**
1. **Shape check:** Return value is `{str: {str: int}}` — same as legacy.
2. **Field completeness:** All legacy fields present in each division's dict.
3. **Level accuracy:** RBAC level 0 → 0, level 1 → 1, etc.
4. **Backward compat:** `has_read_access(result, 'orders')` still works.

**Dependencies:** Phase 1 (field mapping).

---

## Phase 3: `resolve_access()` Rewrite

**What:** Rewrite `resolve_access()` in `backend/auth_utils.py` to use `UserTenantContext` (target) instead of `Switchgroupmodel` (legacy), and RBAC instead of `Accesslevel`.

**Current return shape:**
```python
{
    'user': KuroUser,           # Legacy
    'switchgroup': Switchgroupmodel,  # Legacy
    'bg': BusinessGroup,
    'bg_code': str,
    'db_name': str,
    'access': Accesslevel QuerySet,   # Legacy
    'access_dict': {div_code: {field: int}},  # From resolve_access_levels()
}
```

**New return shape (backward compatible):**
```python
{
    'user': KuroUser,                    # Kept for compat (until KuroUser→EmployeeProfile migration)
    'switchgroup': Switchgroupmodel,     # Kept for compat (populated from UserTenantContext)
    'bg': BusinessGroup,
    'bg_code': str,
    'db_name': str,
    'access': Accesslevel QuerySet,      # Kept for compat (empty or stub, callers should use access_dict)
    'access_dict': {div_code: {field: int}},  # Now from RBAC (via Phase 2 adapter)
    # New fields (additive, no caller breaks):
    'tenant_context': UserTenantContext,  # Target: canonical tenant scope
    'permissions': {perm_code: {level, source}},  # Target: RBAC permissions object
    'roles': [{role_code, bg_code, div_code}],    # Target: user's roles
}
```

**Files:**
- Modify `backend/auth_utils.py`

**Steps:**

1. Read current `resolve_access()` in `backend/auth_utils.py`.
2. Replace tenant context resolution:
   - Primary: `UserTenantContext.objects.filter(userid=X).order_by('-updated_at').first()`
   - Fallback: `Switchgroupmodel` (if no tenant context exists)
3. Replace access resolution:
   - Call `resolve_access_levels(userid=userid, bg_code=bg_code)` (Phase 2 adapter)
   - Also call `build_permissions_object(userid, bg_code)` for new `permissions`/`roles` fields
4. Maintain `KuroUser` and `Switchgroupmodel` in return dict for backward compat.
5. Add new `tenant_context`, `permissions`, `roles` fields (additive — don't break existing callers).
6. Add `ponytail:` comment on legacy fallback paths.

**Tests:**
1. **Return shape:** All legacy keys present (`user`, `switchgroup`, `bg`, `bg_code`, `db_name`, `access`, `access_dict`).
2. **New keys:** `tenant_context`, `permissions`, `roles` present when RBAC data exists.
3. **Tenant context:** `bg_code` matches `UserTenantContext.bg_code`.
4. **Backward compat:** `has_read_access(result['access_dict'], 'orders')` still works.

**Dependencies:** Phase 2 (`resolve_access_levels` adapter).

---

## Phase 4: Permission Helpers → RBAC

**What:** Rewrite the 11 permission helper functions in `backend/auth_utils.py` to use `resolve_permission()` internally while maintaining identical signatures.

**Functions to rewrite:**

| Function | Current Logic | New Logic |
|---|---|---|
| `has_read_access(access_dict, field)` | Scan `access_dict` for non-zero value | `resolve_permission(userid, rbac_code, bg_code, division)` — any division |
| `has_write_access(access_dict, field, level)` | Scan `access_dict` for value > level | Same, with level threshold |
| `has_division_read_access(access_dict, field, div)` | Check specific division | Same, specific division |
| `has_division_write_access(access_dict, field, div, level)` | Check specific division + level | Same |
| `check_access(user_access, field, access_dict)` | Super OR has_read_access | Super OR resolve_permission |
| `check_write_access(user_access, field, access_dict, level)` | Super OR has_write_access | Same |
| `check_division_access(user_access, field, div, access_dict)` | Super OR division read | Same |
| `check_division_write_access(user_access, field, div, access_dict, level)` | Super OR division write | Same |
| `get_accessible_divisions(access_dict, field)` | Scan divisions for non-zero | Query UserRole divisions, filter by permission |
| `get_all_divisions(access_dict)` | `list(access_dict.keys())` | Query UserRole divisions |
| `get_branch_fallback(access_dict)` | First branch from access records | Query UserRoleBranch |

**Challenge:** The current helpers accept `access_dict` (pre-computed dict), not `userid`. To use RBAC, they need `userid`. Two options:

- **Option A (preferred):** Keep `access_dict` as the argument (since it's now RBAC-backed via Phase 2). The helpers don't change — they still scan the dict. **Zero call-site changes.**
- **Option B:** Add `userid` parameter and deprecate `access_dict`. Requires ~303 call-site changes.

**Decision: Option A.** Since Phase 2 makes `access_dict` RBAC-backed, the helpers already use RBAC data indirectly. No changes needed to the helper functions themselves. The "rewrite" is already complete via Phase 2.

**However**, `get_accessible_divisions` and `get_all_divisions` can be optimized to query RBAC directly instead of scanning the dict. This is a performance improvement, not a correctness change.

**Files:**
- Modify `backend/auth_utils.py` (optimization only, no signature changes)

**Steps:**

1. Verify that all permission helpers work correctly with the RBAC-backed `access_dict` from Phase 2.
2. Optimize `get_accessible_divisions` to accept optional `userid` and query RBAC directly when available.
3. Optimize `get_all_divisions` similarly.
4. Add `ponytail:` comments on legacy dict-scan paths.

**Tests:**
1. **Correctness:** All 11 helpers return same results as before (with RBAC-backed data).
2. **Super user bypass:** `check_access("Super", ...)` returns True without RBAC query.
3. **Division scoping:** `has_division_read_access` only checks specified division.

**Dependencies:** Phase 2 (`resolve_access_levels` adapter), Phase 3 (`resolve_access` rewrite).

---

## Phase 5: Endpoint Contract Alignment

**What:** Update login and `/me` endpoint responses to include RBAC `permissions[]` and `roles[]` alongside legacy `accesslevel[]` (transitional dual-mode).

**Target login response (spec §4.3):**
```json
{
    "status": "success",
    "data": {
        "access_token": "...",
        "refresh_token": "...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+919876543210",
            "name": "John Doe",
            "email": "john@example.com",
            "bg_code": "KURO0001",
            "active_div_code": "KURO0001_001",
            "active_branch_code": null,
            "roles": ["employee", "customer"],
            "permissions": ["orders.view", "products.view"],
            "is_admin": false
        }
    }
}
```

**Current login response:**
```json
{
    "status": "success",
    "data": {
        "access_token": "...",
        "user": {
            "userid": "KCTM006",
            "phone": "9876543210",
            "name": "John Doe",
            "bg_code": "KURO0001",
            "accesslevel": ["user_view", "order_create"],
            "is_admin": false
        }
    }
}
```

**Transitional response (dual-mode):**
```json
{
    "status": "success",
    "data": {
        "access_token": "...",
        "refresh_token": "...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "userid": "KCTM006",           // Kept for frontend compat
            "identity_id": "ID000001",     // New (from M1 migration)
            "phone": "+919876543210",      // E.164 normalized
            "name": "John Doe",
            "email": "john@example.com",
            "bg_code": "KURO0001",
            "active_div_code": "KURO0001_001",    // New
            "active_branch_code": null,            // New
            "accesslevel": [...],                  // Transitional — ponytail: remove when frontend migrates
            "roles": ["employee"],                 // New — from RBAC
            "permissions": ["orders.view"],        // New — from RBAC
            "is_admin": false
        }
    }
}
```

**Files:**
- Modify `users/api/viewsets.py` (`_build_login_response`, `_build_user_data`, `me` method)

**Steps:**

1. Read `_build_login_response` and `_build_user_data` in `users/api/viewsets.py`.
2. Add RBAC permission resolution:
   ```python
   from users.permissions import build_permissions_object
   perms_obj = build_permissions_object(userid, bg_code)
   ```
3. Add `permissions` field (list of perm_codes with level > 0):
   ```python
   "permissions": [
       {"code": perm_code, "level": info["level"], "source": info["source"]}
       for perm_code, info in perms_obj["_permissions"].items()
       if info["level"] > 0
   ]
   ```
4. Add `roles` field from `perms_obj["_roles"]`.
5. Add `active_div_code` and `active_branch_code` from `UserTenantContext`.
6. Keep `accesslevel[]` with `ponytail:` comment.
7. Update `me` method similarly.
8. Verify Python syntax.

**Tests:**
1. **Login response shape:** Contains both `accesslevel[]` (transitional) and `permissions[]` (target).
2. **`/me` response shape:** Contains `active_div_code`, `active_branch_code`, `roles[]`, `permissions[]`.
3. **RBAC data accuracy:** `permissions[]` matches `resolve_permission()` results.
4. **Frontward compat:** Frontend still receives `accesslevel[]` (no break).

**Dependencies:** Phase 3 (`resolve_access` rewrite with new fields).

---

## Phase 6: AccesslevelSerializer Deprecation

**What:** Create RBAC serializers and deprecate `AccesslevelSerializer` in endpoint responses. Keep `AccesslevelSerializer` for `business_accesslevel()` CRUD operations (still needed for employee permission management until RBAC admin UI is built).

**New serializers:**
```python
class RoleAssignmentSerializer(serializers.ModelSerializer):
    """Serialize UserRole assignments for API responses."""
    class Meta:
        model = UserRole
        fields = ('role_id', 'bg_code', 'division')

class PermissionOverrideSerializer(serializers.ModelSerializer):
    """Serialize UserPermission overrides for API responses."""
    class Meta:
        model = UserPermission
        fields = ('permission_id', 'level', 'reason', 'expires_at', 'bg_code', 'division')

class RBACUserPermissionsSerializer(serializers.Serializer):
    """Serialize full RBAC permissions object for API responses.

    Wraps build_permissions_object() output in spec-compliant format.
    """
    permissions = serializers.DictField()
    roles = serializers.ListField()
    overrides = serializers.ListField()

    def to_representation(self, instance):
        # instance is (userid, bg_code) tuple
        userid, bg_code = instance
        from users.permissions import build_permissions_object
        perms = build_permissions_object(userid, bg_code)
        return {
            "permissions": perms["_permissions"],
            "roles": perms["_roles"],
            "overrides": perms["_overrides"],
        }
```

**Files:**
- Modify `users/serializers.py` (add RBAC serializers, keep `AccesslevelSerializer` with deprecation comment)
- Modify `users/api/viewsets.py` (use RBAC serializers in new endpoints)

**Steps:**

1. Add three new RBAC serializers to `users/serializers.py`.
2. Add deprecation comment to `AccesslevelSerializer`:
   ```python
   # ponytail: AccesslevelSerializer kept for business_accesslevel() CRUD.
   # Deprecated — replace with RBACUserPermissionsSerializer when RBAC admin UI is built.
   class AccesslevelSerializer(serializers.ModelSerializer):
       ...
   ```
3. Update `AccessLevelViewSet` to return RBAC data alongside legacy data (dual-mode).
4. Create new `RBACPermissionsViewSet` for pure RBAC endpoints (optional, can be Phase 7).

**Tests:**
1. **RBAC serializers:** Serialize/deserialize correctly.
2. **AccessLevelViewSet dual-mode:** Returns both `accesslevel[]` and `permissions[]`.
3. **business_accesslevel() still works:** CRUD on Accesslevel records unchanged.

**Dependencies:** Phase 5 (endpoint contract alignment).

---

## Phase 7: `business_accesslevel()` → RBAC Admin

**What:** Rewrite `business_accesslevel()` in `users/views.py` to manage RBAC assignments instead of `Accesslevel` records.

**Current behavior:** Creates/deletes `Accesslevel` records based on `businessgroups` list.

**New behavior:** Creates/deletes `UserRole` assignments based on `businessgroups` list and a default role.

**Files:**
- Modify `users/views.py`

**Steps:**

1. Read `business_accesslevel()` and `division_accesslevel()` in `users/views.py`.
2. Replace `Accesslevel.objects.create()` with `UserRole.objects.get_or_create()`.
3. Replace `Accesslevel.objects.filter(...).delete()` with `UserRole.objects.filter(...).delete()`.
4. Map legacy permission levels to RBAC role assignments (use a default role or derive from request data).
5. Keep `Accesslevel` writes as fallback if RBAC role mapping is incomplete (transitional dual-write).
6. Add `ponytail:` comment on dual-write path.

**Tests:**
1. **Role assignment:** Creating access for a new BG creates `UserRole` record.
2. **Role removal:** Removing BG access deletes `UserRole` record.
3. **Backward compat:** `Accesslevel` records still created (dual-write) until frontend fully migrates.

**Dependencies:** Phase 6 (RBAC serializers).

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/rbac_mapping.py` | Legacy field → RBAC perm_code mapping registry |
| Modify | `backend/utils.py` | `resolve_access_levels()` → RBAC adapter |
| Modify | `backend/auth_utils.py` | `resolve_access()` → UserTenantContext + RBAC |
| Modify | `users/api/viewsets.py` | Login/me responses: dual-mode (accesslevel + permissions) |
| Modify | `users/serializers.py` | Add RBAC serializers, deprecate AccesslevelSerializer |
| Modify | `users/views.py` | `business_accesslevel()` → RBAC admin |

## Constraints

- **No data loss:** `users_accesslevel` table must NOT be dropped. Keep for `business_accesslevel()` CRUD until RBAC admin UI replaces it.
- **No call-site changes:** All deprecated functions maintain identical signatures and return shapes. Callers need zero modifications.
- **Backward compat on login/me:** Keep `accesslevel[]` in responses alongside `permissions[]` until frontend migration is verified.
- **`Switchgroupmodel` preserved:** `resolve_access()` still returns `switchgroup` key (populated from `UserTenantContext` if no Switchgroupmodel exists).
- **`KuroUser` preserved:** `resolve_access()` still returns `user` as KuroUser (until M1 identity migration completes).
- **Django 6.0.4 compatibility:** All changes must work with Django 6.0.4.
- **Redis is optional:** RBAC caching via Redis is best-effort. Functions must work without Redis.

## Success Criteria

- [ ] `users/rbac_mapping.py` created with complete legacy→RBAC field mapping
- [ ] `resolve_access_levels()` returns RBAC-backed `{div_code: {field: int}}` dict
- [ ] `resolve_access()` uses `UserTenantContext` as primary tenant source
- [ ] `resolve_access()` return dict includes `permissions` and `roles` fields
- [ ] All 11 permission helpers work correctly with RBAC-backed `access_dict`
- [ ] Login response includes `permissions[]` and `roles[]` alongside `accesslevel[]`
- [ ] `/me` response includes `active_div_code`, `active_branch_code`, `roles[]`, `permissions[]`
- [ ] RBAC serializers (`RoleAssignmentSerializer`, `PermissionOverrideSerializer`, `RBACUserPermissionsSerializer`) created
- [ ] `AccesslevelSerializer` marked deprecated with `ponytail:` comment
- [ ] `business_accesslevel()` manages RBAC assignments (with dual-write fallback)
- [ ] Python syntax verification passes for all modified files
- [ ] All existing tests still pass (no regression)
- [ ] Zero call-site modifications required (adapter transparency verified)

## Execution Order

```
Phase 1 (field mapping)
       │
Phase 2 (resolve_access_levels adapter)
       │
Phase 3 (resolve_access rewrite)
       │
Phase 4 (permission helpers — validation only, no changes needed)
       │
Phase 5 (endpoint contracts — dual-mode responses)
       │
Phase 6 (AccesslevelSerializer deprecation + RBAC serializers)
       │
Phase 7 (business_accesslevel → RBAC admin)
```

All phases sequential. Each phase maintains backward compatibility with all existing callers.

## Caveats & Uncertainty

1. **Field mapping completeness:** The 44 legacy fields must map to existing RBAC perm_codes. If `rbac_permissions` table doesn't have a matching perm_code, the adapter returns level 0 (no access). Verify mapping against live `rbac_permissions` data.
2. **Performance:** Phase 2 adapter is O(fields × divisions) RBAC queries. With Redis caching (15-min TTL), this is acceptable. If latency is an issue, replace with bulk `build_permissions_object()` call.
3. **`resolve_access_levels()` bug:** Current implementation uses `item['div_code']` but query returns `division` field. This may already be broken. The RBAC adapter fixes this by using `UserRole.division` directly.
4. **Frontend migration timeline:** Unknown when `kteam-fe-chief` will stop using `accesslevel[]`. Dual-mode responses add bandwidth cost. Set a review date (e.g., 90 days) to audit frontend usage.
5. **`business_accesslevel()` dual-write:** Writing to both `Accesslevel` and `UserRole` creates data duplication. Remove `Accesslevel` writes only after RBAC admin UI is operational and tested.
6. **`Switchgroupmodel` vs `UserTenantContext`:** Some code paths may still create `Switchgroupmodel` records (e.g., legacy bgSwitch endpoint). The adapter handles both, but prefer `UserTenantContext` going forward.
7. **M1 identity migration dependency:** The `identity_id` field in login responses requires M1 migration (`26-06-2026_m1-identity-migration_1a1902.md`) to be complete. Keep `userid` as primary until then.

## Anti-Patterns to Avoid

- ❌ Dropping `Accesslevel` table before frontend migration → ✅ Keep table, mark DEPRECATED
- ❌ Changing `resolve_access()` return shape → ✅ Additive fields only (keep legacy keys)
- ❌ Modifying 520+ call sites → ✅ Adapter transparency — zero call-site changes
- ❌ Removing `accesslevel[]` from login response → ✅ Dual-mode until frontend verified
- ❌ Removing `Switchgroupmodel` queries → ✅ Fallback to Switchgroupmodel if UserTenantContext missing
- ❌ Assuming Redis is available → ✅ Best-effort caching, no-op without Redis
- ❌ Hardcoding perm_codes in adapter → ✅ Use `users/rbac_mapping.py` registry
