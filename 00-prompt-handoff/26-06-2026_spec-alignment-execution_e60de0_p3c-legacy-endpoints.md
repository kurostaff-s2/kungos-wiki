# Phase 3C: Legacy Endpoint Removal

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 3C of 5 (parallel with 3A, 3B)
**Dependencies:** Phase 2B (login response must be new shape), Phase 2D (/rbac/ namespace must exist)
**Estimated effort:** ~15 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p3c` |
| Entity type | `handoff` |
| Short description | Remove legacy endpoints per spec Appendix B. Clean up `/kuro/user` alias and other deprecated routes. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` Appendix B |
| Generated | `26-06-2026` |
| Next action / owner | Execute legacy endpoint removal — audit, remove, verify |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/urls.py` (remove legacy routes)
- `users/api/viewsets.py` (remove legacy actions)
- `domains/cafe_arcade/urls.py` (remove legacy actions)
- `tests/test_legacy_endpoint_removal.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

Legacy endpoints removed per spec Appendix B. `/kuro/user` alias removed. `cafe/sessions/start` legacy action removed. No 404 regressions for active endpoints.

## Implementation Steps

### Step 1: Audit Legacy Endpoints

```bash
# Search for legacy endpoint patterns
grep -rn "kuro/user\|kuro/accesslevel\|kuro/switchgroup" --include="*.py" | grep -v __pycache__ | grep -v venv/
grep -rn "sessions/start\|session_start" --include="*.py" | grep -v __pycache__ | grep -v venv/
```

### Step 2: Remove `/kuro/user` Alias

In `users/urls.py` or `users/api/viewsets.py`, remove the `/kuro/user` route/action.

### Step 3: Remove `cafe/sessions/start` Legacy Action

In `domains/cafe_arcade/urls.py` or viewsets, remove the legacy `sessions/start` action. Replace with standard DRF create action.

### Step 4: Verify No Broken References

```bash
# Search for references to removed endpoints
grep -rn "kuro/user\|sessions/start" --include="*.py" | grep -v __pycache__ | grep -v venv/ | grep -v test_
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/urls.py` | Remove legacy routes |
| Modify | `users/api/viewsets.py` | Remove legacy actions |
| Modify | `domains/cafe_arcade/urls.py` | Remove legacy actions |
| Create | `tests/test_legacy_endpoint_removal.py` | Verify removal |

## Phase-Specific Tests

Create `tests/test_legacy_endpoint_removal.py`:

1. **Test /kuro/user returns 404:**
   ```python
   def test_kuro_user_removed():
       response = client.get('/api/v1/users/kuro/user/')
       assert response.status_code == 404
   ```

2. **Test active endpoints still work:**
   ```python
   def test_active_endpoints_still_work():
       response = client.get('/api/v1/users/me/')
       assert response.status_code in [200, 401]
   ```

## Completion Gate

- [ ] All legacy endpoints removed
- [ ] Active endpoints functional
- [ ] No 404 regressions
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Consistency Rules

**This phase defers to:**
- Wire shapes: `endpoint_contract_spec.md`
- Migration ordering: `migration_spec.md`
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes beyond what the spec allows
- Migration steps beyond what the spec defines
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._

