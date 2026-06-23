# LlamaSwap → SGM Full Decoupling

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `541155` |
| Entity type | `handoff` |
| Short description | Remove deprecated LlamaSwap client, rename remaining references to SGM, clean up models.json |
| Status | `draft` |
| Source references | `super_council/api/llama_swap_client.py`, `super_council/api/super_go_manager_client.py`, `super_council/api/infra_status.py`, `super_council/memory_service/health/checker.py`, `~/.pi/agent/models.json` |
| Generated | `23-06-2026` |
| Next action / owner | Subagent execution — read this doc and execute phases sequentially |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this task:** `api/llama_swap_client.py`, `api/test_llama_swap_client.py`, `api/infra_status.py`, `memory_service/health/checker.py`, `test_llama_swap_integration.py`, `~/.pi/agent/models.json`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super-go-manager/` (SGM Go service, read-only context)

## Background

The council previously used `LlamaSwapClient` (direct HTTP to SGM) for model management. This was replaced by `SuperGoManagerClient` which provides a cleaner API aligned with the SGM-exclusive architecture. The old client and its tests are now dead code. Additionally, `main-llama` provider entries in `models.json` for council models bypass SGM routing.

## Execution Order

```
Phase 1 (delete dead code) → Phase 2 (rename references) → Phase 3 (models.json cleanup) → Phase 4 (verify)
```

All phases are sequential. Each phase must pass its completion gate before proceeding.

---

### Phase 1: Delete Dead Code

**What:** Remove the old LlamaSwap client and its test suite. These files have zero production imports.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Delete | `api/llama_swap_client.py` | Old client, replaced by `super_go_manager_client.py` |
| Delete | `api/test_llama_swap_client.py` | Tests dead client |
| Delete | `api/__pycache__/llama_swap_client*` | Cached bytecode |
| Delete | `api/__pycache__/test_llama_swap_client*` | Cached bytecode |

**Steps:**
1. Verify no production imports: `grep -rn "from.*llama_swap_client\|import.*llama_swap_client" super_council/ --include="*.py" | grep -v test_ | grep -v __pycache__` — should return nothing
2. Delete `api/llama_swap_client.py`
3. Delete `api/test_llama_swap_client.py`
4. Clean `__pycache__` artifacts
5. Run existing tests: `python3 -m pytest super_council/test_llama_swap_integration.py -v` — all 19 must pass

**Dependencies:** None
**Completion Gate:** All 19 integration tests pass, no import errors

---

### Phase 2: Rename LlamaSwap References

**What:** Update remaining `llama_swap` labels and method names to `super_go_manager` / `sgm` throughout the codebase.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `api/infra_status.py` | Rename `"llama_swap"` keys to `"super_go_manager"`, update labels and function names |
| Modify | `memory_service/health/checker.py` | Rename `check_llama_swap()` to `check_sgm()`, update dict key |
| Rename | `test_llama_swap_integration.py` → `test_super_go_manager_integration.py` | Align filename with content |
| Modify | `api/super_go_manager_client.py` | Remove legacy "replaces LlamaSwapClient" docstring references |

**Steps:**
1. **infra_status.py:**
   - Line 44: `"llama_swap"` → `"super_go_manager"`, label `"Llama Swap"` → `"SGM"`
   - Line 432: `probe_llama_swap()` → `probe_super_go_manager()`
   - Line 513: dict key `"llama_swap"` → `"super_go_manager"`, value `probe_llama_swap` → `probe_super_go_manager`
   - Update any internal references within `probe_llama_swap()` function body

2. **checker.py:**
   - Line 410: `check_llama_swap()` → `check_sgm()`
   - Line 453: dict key `"llama_swap"` → `"sgm"`
   - Update function body to reference SGM (port 9293) instead of old llama_swap port

3. **Rename test file:**
   - `mv test_llama_swap_integration.py test_super_go_manager_integration.py`
   - Update any internal references (e.g., docstring mentions of "llama_swap")

4. **super_go_manager_client.py:**
   - Line 1: Remove "replaces LlamaSwapClient" from docstring
   - Line 71: Remove "Matches LlamaSwapClient interface" comment

**Dependencies:** Phase 1 complete
**Completion Gate:** No `llama_swap` or `LlamaSwap` references remain in production code (grep clean)

---

### Phase 3: Models.json Cleanup

**What:** Remove `qwen-160k-UD-fast` and `gemma-4-26b-mtp-vision` from `main-llama` provider to force resolution through `llama-swap` (SGM).

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `~/.pi/agent/models.json` | Remove duplicate model entries from `main-llama` provider |

**Steps:**
1. Read current `models.json`
2. Identify models present in BOTH `main-llama` AND `llama-swap` providers
3. Remove entries from `main-llama` that should route through SGM:
   - `qwen-160k-UD-fast` (if present in `main-llama`)
   - `gemma-4-26b-mtp-vision` (if present in `main-llama`)
   - Any other council delegation models
4. Verify `nemotron-cascade`, `mellum2-12b`, `gemma-4-26b` are NOT in `main-llama` (they should already be SGM-only)
5. Save updated `models.json`

**Dependencies:** Phase 2 complete
**Completion Gate:** Models resolve to `llama-swap` provider (verify with `python3 -c "import json; ..."` resolution test)

---

### Phase 4: Verification

**What:** Full test suite run and verification that no regressions exist.

**Steps:**
1. Run integration tests: `python3 -m pytest super_council/test_super_go_manager_integration.py -v` — 19/19 pass
2. Run any other council tests: `python3 -m pytest super_council/ -v --tb=short` — no failures
3. Verify no `llama_swap` references remain: `grep -rn "llama_swap\|LlamaSwap" super_council/ --include="*.py" | grep -v __pycache__` — should be empty
4. Verify SGM routing: check that `qwen-160k-UD-fast` resolves to `llama-swap` provider in `models.json`

**Dependencies:** Phase 3 complete
**Completion Gate:** All tests pass, grep clean, routing verified

---

### Constraints

- **No new dependencies:** Use only existing stdlib and installed packages
- **No behavioral changes:** This is a rename/cleanup, not a feature change
- **SGM port:** 9293 (do not change)
- **ARC router port:** 18093 (consolidation, do not touch)
- **Main router port:** 18094 (upstream, do not touch)
- **Test count:** Must remain 19 passing tests (no test deletion without replacement)

### Success Criteria

- [ ] `llama_swap_client.py` deleted (310 lines removed)
- [ ] `test_llama_swap_client.py` deleted (280 lines removed)
- [ ] All `llama_swap` references renamed to `super_go_manager`/`sgm` in production code
- [ ] Test file renamed to `test_super_go_manager_integration.py`
- [ ] Legacy docstrings removed from `super_go_manager_client.py`
- [ ] Models.json cleaned — council models resolve through `llama-swap` only
- [ ] All 19 integration tests pass
- [ ] No regression in existing test suite
- [ ] Grep clean: zero `llama_swap`/`LlamaSwap` references in production code

### Caveats & Uncertainty

- **infra_status.py `probe_llama_swap()` body:** May contain port-specific logic (9293 vs other). Verify before renaming.
- **checker.py `check_llama_swap()` body:** May probe different endpoints than SGM. Verify it's actually checking port 9293.
- **models.json:** If `qwen-160k-UD-fast` is NOT in `main-llama`, skip that removal — it may already be SGM-only.
- **Consolidation routing:** ARC router (18093) with LFM models is separate from SGM. Do NOT modify consolidation paths.
