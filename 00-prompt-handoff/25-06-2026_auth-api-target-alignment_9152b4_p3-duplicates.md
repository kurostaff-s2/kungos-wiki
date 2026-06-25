# Phase 3: Duplicate & Dead Code Removal

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p3` |
| Entity type | `handoff` |
| Short description | Remove 9 SIMILAR_TO duplicates from backend/utils.py, delete dead close_mongo_client, canonicalize MongoDB helper params, fix hardcoded division name |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 3 of 5 |
| Source references | `25-06-2026_auth-api-target-alignment_9152b4.md` §0D (SIMILAR_TO inventory), §0E (ownership) |
| Generated | `26-06-2026` |
| Next action / owner | Execute duplicate removal — owner: agent with code-edit access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Key files for this phase:**
- `backend/utils.py` — 9 duplicates to delete, 1 dead function, MongoDB helpers to canonicalize
- `backend/auth_utils.py` — canonical source for access resolution functions
- `users/api/viewsets.py` — hardcoded `division` name (L896)

---

## What This Phase Delivers

Removal of 9 SIMILAR_TO function duplicates from `backend/utils.py` (keep copies in `backend/auth_utils.py`), deletion of dead `close_mongo_client`, canonicalization of MongoDB helper param names, and replacement of hardcoded `'division': 'kurogaming'` with tenant context.

---

## Pre-Flight Checklist

- [ ] SIMILAR_TO inventory from Phase 0 verified (9 functions)
- [ ] `resolve_access_levels` confirmed unique to `utils.py` and imported by `auth_utils.py`
- [ ] MongoDB helper ownership confirmed (`utils.py` owns them)

---

## Implementation Steps

### 3A. SIMILAR_TO Duplicates (9 total)

**Step 3A-1: Verify callers**

For each of the 9 functions, verify that ALL callers import from `backend/auth_utils.py` (not `backend/utils.py`):

| Function | Delete From | Keep In |
|----------|------------|---------|
| `has_read_access` | `backend/utils.py` | `backend/auth_utils.py` |
| `has_write_access` | `backend/utils.py` | `backend/auth_utils.py` |
| `get_branch_fallback` | `backend/utils.py` | `backend/auth_utils.py` |
| `get_accessible_divisions` | `backend/utils.py` | `backend/auth_utils.py` |
| `get_all_divisions` | `backend/utils.py` | `backend/auth_utils.py` |
| `has_division_write_access` | `backend/utils.py` | `backend/auth_utils.py` |
| `check_access` | `backend/utils.py` | `backend/auth_utils.py` |
| `check_write_access` | `backend/utils.py` | `backend/auth_utils.py` |
| `check_division_write_access` | `backend/utils.py` | `backend/auth_utils.py` |

**Step 3A-2: Delete from `backend/utils.py`**

1. Open `backend/utils.py`.
2. Delete all 9 function definitions listed above.
3. Verify no other code in `utils.py` calls these functions internally.

**Step 3A-3: Update imports**

1. Grep for `from backend.utils import` across the codebase.
2. Any import of the 9 deleted functions must be changed to `from backend.auth_utils import`.
3. Verify no broken imports remain.

### 3B. MongoDB Helper Param Name Consistency

**Step 3B-1: Audit MongoDB helpers in `backend/utils.py`**

1. Find all MongoDB helper functions: `find_all`, `find_one`, `count_documents`, `aggregate`, `update_many`, `insert_one`, `delete_many`.
2. Check param names: `find_all` uses `div_code`/`branch_code` (canonical). Others may use `division`/`branch` (legacy).

**Step 3B-2: Canonicalize**

1. For each helper using `division`/`branch`:
   - Rename primary param to `div_code`/`branch_code`.
   - Add keyword-only legacy alias: `division=None, branch=None` → if provided, map to canonical.
   - Add `@deprecated` marker or comment.

Example:
```python
def find_one(collection, div_code=None, branch_code=None, *, division=None, branch=None):
    """... @deprecated: use div_code/branch_code instead of division/branch ..."""
    if division is not None and div_code is None:
        div_code = division
    if branch is not None and branch_code is None:
        branch_code = branch
    # ... rest of function
```

### 3C. Dead Code

**Step 3C-1: Delete `close_mongo_client`**

1. Verify `close_mongo_client` has 0 callers (grep + CBM trace).
2. Delete the function from `backend/utils.py`.

### 3D. Hardcoded Division Name

**Step 3D-1: Replace hardcoded `'division': 'kurogaming'`**

1. Open `users/api/viewsets.py` and find the line with `'division': 'kurogaming'` (approximately L896).
2. Replace with tenant context value:
```python
# Before:
employees = [{**e, 'division': 'kurogaming'} for e in employees]

# After:
employees = [{**e, 'active_div_code': request.active_div_code} for e in employees]
```
3. If `request.active_div_code` is not available, derive from `request.div_code` or tenant context middleware.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/utils.py` | Delete 9 SIMILAR_TO functions, delete `close_mongo_client`, canonicalize MongoDB helper params |
| Modify | `users/api/viewsets.py` | Replace hardcoded `'division': 'kurogaming'` with `active_div_code` from tenant context |
| Modify | Various callers | Update imports from `backend.utils` to `backend.auth_utils` for the 9 functions |

---

## Phase-Specific Tests

1. **No broken imports:** `python -c "from backend.auth_utils import has_read_access"` succeeds. `python -c "from backend.utils import has_read_access"` raises ImportError.
2. **MongoDB helpers work with canonical params:** `find_one(coll, div_code="X")` works. `find_one(coll, division="X")` works (deprecated alias).
3. **No dead code:** `close_mongo_client` does not exist in `backend/utils.py`.
4. **No hardcoded division:** Grep for `'kurogaming'` in `users/api/viewsets.py` — zero results.
5. **Existing tests pass:** No regression.

---

## Completion Gate

- [ ] 9 SIMILAR_TO duplicates removed from `backend/utils.py`
- [ ] `close_mongo_client` deleted
- [ ] MongoDB helpers use canonical param names consistently
- [ ] Hardcoded `'division': 'kurogaming'` replaced with `active_div_code` from tenant context
- [ ] All imports updated (callers import from `auth_utils.py`)
- [ ] Existing tests still pass

---

## Notes for Next Phase

Phase 4 creates M1 identity models. No dependency on Phase 3 — they can execute in parallel. Phase 4 models use canonical field names from Phase 1.
