# Accesslevel → RBAC Migration — Complete

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `e1ae60` |
| Entity type | `handoff` |
| Short description | Migrate permission resolution from deprecated `users_accesslevel` (55-col flat table) to normalized RBAC tables. **Complete — no backward compat, target spec only.** |
| Status | `done` |
| Source references | `Kung_OS/architecture/rbac_system.md`, `Kung_OS/specs/database_schemas/postgresql_schema.md` (§2.4 DEPRECATED, §5 RBAC), `Kung_OS/specs/endpoint_contract_spec.md` (§4.3 Auth Migration Notes) |
| Generated | 26-06-2026 |
| Completed | 26-06-2026 |
| Commit | `d3eb960` on `origin/develop` |

## Result

**All Accesslevel/Switchgroupmodel wiring removed. Codebase is RBAC-only.**

| Layer | Before (Legacy) | After (Target) |
|-------|-----------------|----------------|
| **DB** | `Accesslevel` model (55-col flat), `Switchgroupmodel` | `rbac_*` tables: `Role`, `Permission`, `RolePermission`, `UserRole`, `UserRoleBranch`, `UserPermission`, `UserTenantContext` |
| **Migrations** | 0002–0014 incremental legacy migrations | Fresh `0001_initial.py` per app — zero legacy table references |
| **Resolution** | `resolve_access()` → `Accesslevel.objects.filter()` → flat dict | `resolve_access()` → `build_permissions_object()` → RBAC cascading (override → role → default) |
| **Helpers** | `has_read_access(access_dict, field)` — flat field scan | Same signatures, RBAC-backed `access_dict` from `resolve_access_levels()` adapter |
| **Serialization** | `AccesslevelSerializer` | `RoleSerializer`, `UserRoleSerializer`, `UserPermissionSerializer` (`users/api/rbac_serializers.py`) |
| **Response** | `accesslevel[]` (flat perm strings) | `permissions[]` (RBAC perm_codes) + `roles[]` |
| **Admin CRUD** | `business_accesslevel()` → `Accesslevel.objects.create()` | `business_accesslevel()` → `UserRole.objects.get_or_create()` |

## What Was Done

### Migrations
- Deleted legacy migrations: `users/0007`–`0013`, `kungos_admin/0002`, `domains/cafe_arcade/0002`–`0003`
- Deleted `migrate_accesslevels.py` (superseded by `users/management/commands/migrate_identity.py`)
- Fresh `0001_initial.py` generated per app — clean snapshot, zero legacy table references
- Django check: 0 issues

### Code Changes (~30 files, 45 files changed, +948 / −1941 lines)

**Removed:**
- `Accesslevel` model class and all imports
- `Switchgroupmodel` model class and all imports
- `AccesslevelSerializer` (zero references remain)
- `migrate_accesslevels.py`

**Replaced with:**
- `UserRole` / `UserPermission` instead of `Accesslevel`
- `UserTenantContext` instead of `Switchgroupmodel`
- `resolve_permission()` / `build_permissions_object()` instead of flat field scans

**Adapter layer (transitional, marked with `ponytail:` comments):**
- `users/rbac_mapping.py` — `LEGACY_TO_RBAC` field mapping (44 legacy fields → RBAC perm_codes)
- `backend/utils.py::resolve_access_levels()` — queries RBAC, returns legacy-compatible `{div: {field: int}}` shape for `has_*_access()` helpers
- `backend/auth_utils.py::resolve_access()` — uses `UserTenantContext` + `build_permissions_object()`, returns `permissions`, `roles`, `access_dict`

### Endpoint Responses

**Login response (target spec, no dual-mode):**
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
      "roles": ["employee"],
      "permissions": ["orders.view", "products.view"],
      "is_admin": false
    }
  }
}
```

**`/me` response:** Same shape + `employee_profile`, `customer_profile` extension subobjects.

No `accesslevel[]` field — frontend must consume `permissions[]` + `roles[]`.

## Remaining Work

### Backend
- **None.** Migration is complete.

### Frontend (`kteam-fe-chief`)
- Update login/me response consumers to read `permissions[]` + `roles[]` instead of `accesslevel[]`
- Update permission checks to use RBAC perm_codes (e.g., `orders.view`) instead of legacy field names (e.g., `orders`)

### Database
- `users_accesslevel` table can be dropped from PostgreSQL once frontend migration is verified
- `users_switchgroupmodel` table can be dropped once no code path writes to it

## Files

| File | Role |
|------|------|
| `users/models.py` | RBAC models: `Role`, `Permission`, `RolePermission`, `UserRole`, `UserRoleBranch`, `UserPermission`, `UserTenantContext` |
| `users/permissions.py` | Resolution engine: `resolve_permission()`, `build_permissions_object()` (with Redis caching) |
| `users/rbac_mapping.py` | Legacy field → RBAC perm_code mapping (adapter only) |
| `backend/auth_utils.py` | `resolve_access()`, `resolve_minimal()`, permission helpers |
| `backend/utils.py` | `resolve_access_levels()` adapter |
| `users/api/rbac_serializers.py` | `RoleSerializer`, `UserRoleSerializer`, `UserPermissionSerializer` |
| `users/api/rbac_views.py` | `UserRoleViewSet`, `UserPermissionViewSet` |
| `users/api/viewsets.py` | Login, `/me`, `_build_user_data()` — RBAC responses |
| `users/views.py` | `business_accesslevel()` → `UserRole` CRUD |

## Decision Log

| Decision | Rationale |
|----------|-----------|
| No backward compat in responses | Frontend migration is the only blocker — shipping dual-mode adds bandwidth for unknown duration. Ship target, let frontend catch up. |
| Adapter layer kept for `has_*_access()` helpers | ~520 call sites. Adapter makes `access_dict` RBAC-backed transparently — zero call-site changes needed. |
| `Accesslevel` model deleted (not deprecated) | No data loss risk — RBAC tables are the source of truth. Legacy data was migrated via `migrate_identity.py`. |
| `Switchgroupmodel` replaced by `UserTenantContext` | Same purpose (tenant scope), normalized schema. |
| Fresh `0001_initial.py` per app | Cleaner than incremental migrations. Single snapshot aligned with target spec. |
