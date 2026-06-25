# Phase 2: Legacy Endpoint Removal

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p2` |
| Entity type | `handoff` |
| Short description | Remove 28 legacy URL paths (14 from users/urls.py + 14 from backend/urls.py) and 2 duplicate ViewSet actions |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 2 of 5 |
| Source references | `25-06-2026_auth-api-target-alignment_9152b4.md` §0C (legacy path inventory) |
| Generated | `26-06-2026` |
| Next action / owner | Execute legacy path removal — owner: agent with code-edit access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Key files for this phase:**
- `users/urls.py` — URL routing (14 paths to remove, 5 to keep)
- `backend/urls.py` — Root URL config (14 duplicate paths to remove)
- `users/api/viewsets.py` — UserViewSet (2 actions to remove)

---

## What This Phase Delivers

Removal of 28 legacy URL paths across two files and 2 duplicate ViewSet actions. After completion, only canonical routes remain. All legacy paths return 404.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (canonical naming in place)
- [ ] Legacy path inventory from Phase 0 verified (28 paths: 14 per file)
- [ ] Frontend team notified (or dual-response mode active)

---

## Implementation Steps

### 2A. Remove Legacy URL Paths

**Step 2A-1: `users/urls.py` — Remove 14 paths**

Open `users/urls.py` and delete these explicit `path()` entries:

```python
path('auth/kuroregister', ...),    # duplicate of register/kuro/
path('auth/rebregister', ...),     # duplicate of register/reb/
path('auth/admin', ...),           # role is inferred, not routed
path('auth/staff', ...),           # role is inferred, not routed
path('auth/reb', ...),             # role is inferred, not routed
path('kuro/user', ...),            # use users/me/
path('reb/user', ...),             # use users/me/
path('empprofile', ...),           # use users/profile/
path('pwdreset', ...),             # router-generated /auth/pwdreset/ survives
path('verify', ...),               # router-generated /auth/verify/ survives
path('accesslevel', ...),          # use access-levels/
path('employeesdata', ...),        # use users/employees/
path('emp_acc', ...),              # use users/emp_acc/
path('bgSwitch', ...),             # use users/bgswitch/
```

**Keep these 5 paths:**
```python
path('auth/login', ...),
path('auth/refresh', ...),
path('auth/logout', ...),
path('auth/health', ...),
path('auth/monitoring/401', ...),
```

**Step 2A-2: `backend/urls.py` — Remove 14 duplicate paths**

Open `backend/urls.py` and delete:

```python
path('api/v1/bgSwitch', ...),
path('api/v1/accesslevel', ...),
path('api/v1/pwdreset', ...),
path('api/v1/verify', ...),
path('api/v1/empprofile', ...),
path('api/v1/employeesdata', ...),
path('api/v1/kuro/user', ...),
path('api/v1/reb/user', ...),
path('api/v1/emp_acc', ...),
path('api/v1/auth/login', ...),      # keep only users/urls.py copy
path('api/v1/auth/kuroregister', ...),
path('api/v1/auth/rebregister', ...),
path('api/v1/auth/refresh', ...),     # keep only users/urls.py copy
path('api/v1/auth/logout', ...),      # keep only users/urls.py copy
```

**pwdreset/verify note:** These are `@action` on `AuthViewSet` → DefaultRouter generates `/auth/pwdreset/` and `/auth/verify/` automatically. The bare explicit `path()` entries are legacy aliases — remove them. The router-generated canonical paths survive.

### 2B. Remove Legacy ViewSet Actions

**Step 2B-1: `users/api/viewsets.py` — Delete `UserViewSet` actions**

1. Delete `UserViewSet.kuro_user` method (duplicate of `me`).
2. Delete `UserViewSet.reb_user` method (duplicate of `me`).
3. Update class docstring to reflect canonical routes only.

### 2C. Remove Legacy Response Fields

**Step 2C-1: `_build_login_response` cleanup**

If not already done in Phase 1B:
1. Remove `accesslevel[]` (AccesslevelSerializer) — use RBAC permissions only.
2. Remove `roles[]` from `KuroUser.roles` JSON — use RBAC-derived roles.
3. Ensure `active_div_code` (string) replaces `division[]` (JSON array).
4. Ensure `active_branch_code` (string) replaces `branches[]` (JSON array).

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/urls.py` | Delete 14 legacy path entries |
| Modify | `backend/urls.py` | Delete 14 duplicate path entries |
| Modify | `users/api/viewsets.py` | Delete `kuro_user`, `reb_user` actions |

---

## Phase-Specific Tests

1. **Canonical routes work:** `GET /api/v1/auth/login/`, `GET /api/v1/users/me/`, `GET /api/v1/auth/refresh/`, `GET /api/v1/auth/logout/` return 200 (or expected response).
2. **Legacy paths 404:** `GET /api/v1/auth/admin`, `GET /api/v1/kuro/user`, `GET /api/v1/empprofile` return 404.
3. **Backend duplicates 404:** `GET /api/v1/bgSwitch`, `GET /api/v1/accesslevel`, `GET /api/v1/auth/login` (from backend/urls.py) return 404.
4. **Router-generated paths work:** `GET /api/v1/auth/pwdreset/` and `GET /api/v1/auth/verify/` return expected responses (not 404).
5. **ViewSet actions gone:** `UserViewSet` has no `kuro_user` or `reb_user` methods.
6. **Existing tests pass:** No regression.

---

## Completion Gate

- [ ] 14 legacy paths removed from `users/urls.py`
- [ ] 14 duplicate paths removed from `backend/urls.py`
- [ ] `kuro_user`, `reb_user` actions removed from `UserViewSet`
- [ ] No 404 on canonical routes (`/api/v1/auth/login/`, `/api/v1/users/me/`, etc.)
- [ ] All legacy paths return 404
- [ ] Router-generated paths (`/auth/pwdreset/`, `/auth/verify/`) still work
- [ ] Existing tests still pass

---

## Notes for Next Phase

Phase 3 removes duplicate functions from `backend/utils.py`. No dependency on Phase 2 — they can execute in parallel. However, Phase 3D (hardcoded `division` rename) should use `active_div_code` from Phase 1 naming.
