# Ponytail Audit Cleanup — 7-council

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `429d6a` |
| Entity type | `handoff` |
| Short description | Delete dead modules, shrink god class, remove noop stubs across 7-council |
| Status | `draft` |
| Source references | Ponytail audit findings (session 2026-06-23) |
| Generated | 23-06-2026 |
| Next action / owner | Execute Phase 1 (deletions) — any agent |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Key files for this task:** Listed per phase below
**Related codebases:** None

---

## Summary

12 over-engineering findings across the 7-council codebase. Three phases: delete dead code (biggest impact), shrink Python god class, clean Go SGM. Estimated total: ~1,200 lines removed.

### Execution Order

```
Phase 1 (deletions)  →  Phase 2 (Python shrinks)  →  Phase 3 (Go cleanup)
   [parallel OK]          [depends on P1]              [depends on P2]
```

Phase 1 has three independent sub-tasks that can execute in parallel.

---

## Phase 1: Delete Dead Modules

**What:** Remove three dead code regions: voice_pipeline (entire module), arc_summarizer (re-export facade), llama_swap_client (superseded).
**Dependencies:** None.
**Estimated effort:** ~15 min.

### Phase 1A: Delete voice_pipeline

**What:** 10-file module, zero imports outside itself. Entirely dead.

**Steps:**
1. Confirm no imports: `grep -rn "from.*voice_pipeline\|import.*voice_pipeline" Coding-Projects/7-council --include="*.py" | grep -v voice_pipeline/`
2. Delete directory: `rm -rf Coding-Projects/7-council/super_council/voice_pipeline/`

**Files to Delete:**
| Action | File |
|--------|------|
| Delete | `super_council/voice_pipeline/` (entire directory) |

**Completion Gate:**
- [ ] Directory removed
- [ ] No remaining imports (grep confirms 0 hits)

### Phase 1B: Delete arc_summarizer

**What:** 7-file re-export facade over `memory_service.consolidate`. Only tests import it. Every file is `from memory_service.consolidate import *`.

**Steps:**
1. Confirm only tests import it: `grep -rn "from.*arc_summarizer" Coding-Projects/7-council --include="*.py" | grep -v test | grep -v arc_summarizer/`
2. Delete directory: `rm -rf Coding-Projects/7-council/super_council/arc_summarizer/`
3. **Do NOT update tests** — they will fail, which signals the next agent to re-point them at `memory_service.consolidate`. That's a separate task.

**Files to Delete:**
| Action | File |
|--------|------|
| Delete | `super_council/arc_summarizer/` (entire directory) |

**Completion Gate:**
- [ ] Directory removed
- [ ] No production imports remain (test imports are expected to break — that's the signal)

### Phase 1C: Delete llama_swap_client

**What:** 399-line file replaced by `SuperGoManagerClient`. Only dead test files import it.

**Steps:**
1. Confirm no production imports: `grep -rn "from.*llama_swap_client\|import.*llama_swap_client" Coding-Projects/7-council/super_council --include="*.py" | grep -v test`
2. Delete main file: `rm Coding-Projects/7-council/super_council/api/llama_swap_client.py`
3. Delete test files: `rm Coding-Projects/7-council/super_council/api/test_llama_swap_client.py`
4. Delete integration test: `rm Coding-Projects/7-council/super_council/test_llama_swap_integration.py`

**Files to Delete:**
| Action | File |
|--------|------|
| Delete | `super_council/api/llama_swap_client.py` |
| Delete | `super_council/api/test_llama_swap_client.py` |
| Delete | `super_council/test_llama_swap_integration.py` |

**Completion Gate:**
- [ ] All three files removed
- [ ] No remaining imports

### Phase 1 Notes for Phase 2

After Phase 1, run the full test suite to establish a baseline of broken tests (from arc_summarizer deletion). Phase 2 does NOT fix these — that's out of scope.

---

## Phase 2: Shrink Python Code

**What:** Remove dead aliases, noop stubs, and commented code from council_main.py and SuperGoManagerClient.
**Dependencies:** Phase 1 complete.
**Estimated effort:** ~20 min.

### Phase 2A: Inline _resolve_*_alias wrappers

**What:** 6 one-line methods that just call `_resolve_role_alias("name")`. Inline at call sites.

**File:** `super_council/council_main.py`

**Steps:**
1. Replace each call site with the direct call:
   - `self._resolve_planner_alias()` → `self._resolve_role_alias("planner") or self._get_default_alias()`
   - `self._resolve_builder_alias()` → `self._resolve_role_alias("builder") or self._get_default_alias()`
   - `self._resolve_cochair_alias()` → `self._resolve_role_alias("co-chair")`
   - `self._resolve_reviewer_alias()` → `self._resolve_role_alias("reviewer")`
   - `self._resolve_scout_alias()` → `self._resolve_role_alias("scout")`
   - `self._resolve_vice_chair_alias()` → `self._resolve_role_alias("vice-chair")`
2. Delete the 6 method definitions (lines 5909-5931).
3. Delete the 2 legacy aliases (lines 5934-5935):
   ```python
   _resolve_scout_alias_legacy = _resolve_scout_alias
   _resolve_vice_chair_alias_legacy = _resolve_vice_chair_alias
   ```

**Completion Gate:**
- [ ] All call sites inlined
- [ ] 6 methods + 2 aliases deleted
- [ ] No `NameError` on import

### Phase 2B: Delete commented-out code

**What:** One commented-out method definition.

**File:** `super_council/council_main.py`, line 2586

**Steps:**
1. Delete the comment block: `# def _invalidate_slot(self, config, reason: str) -> None:`

**Completion Gate:**
- [ ] Comment removed

### Phase 2C: Clean SuperGoManagerClient noop stubs

**What:** 5 methods that return `{"status": "noop"}` or raise `NotImplementedError`. Also delete the `GPUStats` class (never populated with real data).

**File:** `super_council/api/super_go_manager_client.py`

**Steps:**
1. Delete `GPUStats` class (lines 31-52) — callers use `nvidia-smi` directly.
2. Delete `ModelInfo` class (lines 55-66) — only used by `list_models` which returns it; check if callers use it. If yes, keep. If no, delete.
3. Replace noop methods with documented stubs or delete:
   - `unload_model` → delete (SGM swap implicitly unloads)
   - `unload_all` → delete
   - `get_performance` → delete
   - `cleanup_slots` → delete
   - `stream_events` → delete (SGM doesn't support it)
4. Check callers of each deleted method. If any exist, replace with inline logic or raise a clear error.

**Completion Gate:**
- [ ] Dead methods removed
- [ ] No callers broken (grep each method name before deleting)
- [ ] File imports cleanly

---

## Phase 3: Clean SGM Go Code

**What:** Remove unused `ModelMeta` struct from SGM.
**Dependencies:** Phase 2 complete.
**Estimated effort:** ~5 min.

### Phase 3A: Delete ModelMeta

**What:** `ModelMeta` struct defined but never read. Router doesn't populate it.

**File:** `super-go-manager/main.go`

**Steps:**
1. Delete `ModelMeta` struct (lines 73-77):
   ```go
   type ModelMeta struct {
       NParams uint64 `json:"n_params"`
       Size    uint64 `json:"size"`
   }
   ```
2. Delete `Meta *ModelMeta` field from `ModelStatus` (line 65):
   ```go
   Meta   *ModelMeta  `json:"meta"`
   ```
3. Verify: `go build` succeeds.

**Completion Gate:**
- [ ] `ModelMeta` struct removed
- [ ] `Meta` field removed from `ModelStatus`
- [ ] `go build ./...` passes

---

## Constraints

- **No behavioral changes:** Only delete dead code and inline trivial wrappers. Do not change logic.
- **Test failures expected:** Phase 1B (arc_summarizer deletion) will break tests that import from it. Do NOT fix these — they signal a separate re-pointing task.
- **Caller check required:** Before deleting any method, grep for callers. If a caller exists, either inline the logic or keep the method.
- **Go build required:** Phase 3 must pass `go build` before marking complete.

## Success Criteria

- [ ] Phase 1A: `voice_pipeline/` deleted, 0 remaining imports
- [ ] Phase 1B: `arc_summarizer/` deleted, 0 production imports remain
- [ ] Phase 1C: `llama_swap_client.py` + 2 test files deleted
- [ ] Phase 2A: 6 `_resolve_*_alias` methods inlined at call sites, legacy aliases deleted
- [ ] Phase 2B: Commented-out `_invalidate_slot` removed
- [ ] Phase 2C: Noop stubs removed from `SuperGoManagerClient`
- [ ] Phase 3A: `ModelMeta` removed from SGM, `go build` passes
- [ ] `council_main.py` imports without errors
- [ ] Net reduction: ~1,200 lines removed
- [ ] All existing passing tests still pass (excluding arc_summarizer tests which are expected to break)
