# Pipeline Architecture Fix — Full Restoration + Reconciliation Path Selection

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `dcb320` |
| Entity type | `handoff` |
| Short description | Restore uncommitted refactoring, fix embedding/memsearch services, evaluate and implement mechanical reconciliation (Option C), remove dead UnifiedVectorStore |
| Status | `draft` |
| Source references | `00-prompt-handoff/pipeline-architecture-fix-20260610-230000.md`, first-principles analysis (session above) |
| Generated | 10-06-2026 |
| Next action / owner | Execute Phase 0 (assessment) → decide reconciliation path → execute remaining phases |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`

**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/pipeline-architecture-fix-20260610-230000.md` — original plan
- `/home/chief/.pi/agent/skills/first-principles-analysis/SKILL.md` — analysis methodology

**Key files for this task:**

| File | Role |
|------|------|
| `super_council/arc_summarizer/pipeline.py` | ArcPipeline — consolidation + reconciliation entry points |
| `super_council/arc_summarizer/reconcile.py` | ArcReconciler — file-based mechanical extraction |
| `super_council/arc_summarizer/client.py` | ArcClient — LLM-based extraction (committed) |
| `super_council/memory_service/__init__.py` | MemoryService — orchestrates all channels |
| `super_council/memory_service/store.py` | RelationalStore — DB operations + reconcile_arc_delta |
| `super_council/memory_service/reconciliation.py` | TaskReconciler — mechanical dedup/classification |
| `super_council/memory_service/vector_store.py` | UnifiedVectorStore — **candidate for removal** |
| `super_council/memory_service/sqlite_indexer.py` | SqliteIndexer — **dead, removed from init** |
| `super_council/memory_service/file_watcher.py` | DocFileWatcher — **dead, removed from init** |
| `~/.config/systemd/user/memsearch-watch.service` | memsearch directory watcher |
| `~/.config/systemd/user/pplx-embed.service` | embedding server |
| `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py` | Python ONNX server |

**Related codebases:** None (self-contained within super_council).

---

## Background

### What Happened

Heavy refactoring of `memory_service` and `arc_summarizer` was performed but **NOT committed**. `git status --short` shows ~25 modified files. The refactoring attempted a shift from DB-based to file-based consolidation/reconciliation but is incomplete and broken.

### Current State

- **82 test failures** across 12 test files (up from 0 before refactoring)
- **Stubs where logic should be:** `reconcile_tasks()` and `reconcile_deviations()` in `pipeline.py` call `ArcReconciler.reconcile_tier()` and return hardcoded results — they ignore `consolidation_text`, `project_id`, `run_id`, `source_summary_id`
- **Removed components:** `SqliteIndexer` and `DocFileWatcher` were removed from `MemoryService.__init__`, breaking the dual-channel indexer
- **Broken API:** `UnifiedVectorStore.reindex_existing_data()` signature changed from `db_connection` to `arc_reconcile_dir`, breaking callers
- **Dead reconciliation thread:** `_start_reconciliation_thread()` exists but doesn't function

### What Was Fixed (Already Done)

- **gRPC keepalive:** `GRPC_KEEPALIVE_TIME_MS` raised to 60000ms in `memsearch-watch.service` — prevents Milvus Lite 3.0 GOAWAY crashes
- **gRPC message size:** Added `GRPC_CLIENT_MAX_SEND_MESSAGE_BYTES` / `GRPC_CLIENT_MAX_RECEIVE_MESSAGE_BYTES` (100MB cap)
- **Both services are currently stopped** — need to restart after fixes

### Root Cause Chain

```
memsearch-watch crash-loop (Milvus GOAWAY)
  → held HTTP connections open
    → ONNX Runtime memory accumulation (known leak on CPU EP)
      → pplx-embed server consumed 23GB RAM over 4 hours
        → embedding server crash-loop
          → memsearch-watch can't connect → more crashes
```

The gRPC keepalive fix breaks this chain. But the services need to be verified stable before proceeding.

---

## Target Pipeline State

```
Raw JSONL → Canonical MD (canonical-raw-session-data/)
    ↓ (Path B — file-based ingestion)
Canonical MD → ARC LLM → Consolidation (arc-memory/)
    ↓ (ArcPipeline — working)
arc-memory/ → memsearch-watch → memsearch_chunks (semantic search)
    ↓ (memsearch-watch — working, needs arc-reconcile/ added)
ARC consolidation → ArcReconciler → arc-reconcile/ (file-based)
    ↓ (ArcReconciler — working, writes files only)
arc-reconcile/ → memsearch-watch → memsearch_chunks (semantic search)
    ↓ (NEW: add arc-reconcile/ to watch list)
arc-reconcile/ → RelationalStore (work_items, plan_deviations)
    ↓ (NEEDS IMPLEMENTATION — see Phase 0 decision)
```

**What's NOT in the pipeline:**
- `UnifiedVectorStore` — redundant with memsearch (see rationale below)
- `SqliteIndexer` — DB → Milvus export replaced by file-based memsearch-watch
- `DocFileWatcher` — same reason

---

## Phase 0: Assessment — Reconciliation Path Decision

**What:** Evaluate reconciliation approaches and select one. This phase MUST complete before Phase 4.

**Context:** The committed code uses LLM-based extraction (`ArcClient.extract_tasks()`) which calls Granite. The refactored code uses file-based mechanical extraction (`ArcReconciler._extract_tasks()`) which uses regex. Both feed into `TaskReconciler` for mechanical dedup/classification.

### Option A: Revert to Committed (LLM extraction + mechanical reconciliation)

**Flow:** `ArcClient.extract_tasks()` → LLM call → `TaskReconciler.reconcile()` → DB

| | Detail |
|---|--------|
| **Extraction** | LLM (Granite on :18095) — understands narrative, infers intent |
| **Reconciliation** | TaskReconciler — fuzzy matching, keyword classification, confidence scoring |
| **Dedup** | Yes — SequenceMatcher, subsystem alignment, confidence thresholds |
| **ARC server needed** | Yes — returns `None` if Granite is down (graceful degradation) |
| **Latency** | ~1-2s per reconciliation (LLM call) |
| **Test coverage** | 45 tests, all passing on committed code |
| **Effort** | ~30 min (git checkout + re-wire reconciliation calls) |

### Option B: ArcReconciler → RelationalStore (mechanical extraction, no dedup)

**Flow:** `ArcReconciler._extract_tasks()` → regex → `RelationalStore.insert_work_item()` → DB

| | Detail |
|---|--------|
| **Extraction** | Regex/parsing — needs explicit headers + bullets |
| **Reconciliation** | None — direct insert, no dedup |
| **Dedup** | **No** — creates duplicates on every run |
| **ARC server needed** | No — fully offline |
| **Latency** | ~ms (regex only) |
| **Test coverage** | 0 (new code) |
| **Effort** | ~1-2 hours (add DB writes to ArcReconciler) |

### Option C: ArcReconciler extraction + TaskReconciler reconciliation (all mechanical)

**Flow:** `ArcReconciler._extract_tasks()` → regex → reshape to `arc_delta` → `TaskReconciler.reconcile()` → DB

| | Detail |
|---|--------|
| **Extraction** | Regex/parsing — needs explicit headers + bullets |
| **Reconciliation** | TaskReconciler — fuzzy matching, keyword classification, confidence scoring |
| **Dedup** | Yes — inherits TaskReconciler's full dedup engine |
| **ARC server needed** | No — fully offline |
| **Latency** | ~ms (regex + mechanical matching) |
| **Test coverage** | Partial — TaskReconciler tests exist, ArcReconciler tests need updating |
| **Effort** | ~1-2 hours (reshape ArcReconciler output + wire to TaskReconciler) |

### Evaluation Matrix

| Criterion | A (LLM) | B (no dedup) | C (all mechanical) |
|---|---|---|---|
| Extraction quality | High — understands narrative | Low — needs explicit bullets | Low — needs explicit bullets |
| Dedup quality | High | **None — noise explosion** | High — inherits TaskReconciler |
| Offline capability | No | Yes | Yes |
| Test coverage | 45 tests | 0 tests | Partial |
| Effort | ~30 min | ~1-2 hours | ~1-2 hours |
| Risk | ARC server dependency | Duplicate work_items | Regex brittleness |

### Recommendation

**Option C** if consolidation outputs are well-structured (headers + bullets). The consolidation prompt produces structured MD, so regex should work. This eliminates LLM dependency while keeping dedup intelligence.

**Option A** if consolidation outputs include narrative prose that regex can't parse. The LLM understands "I sort of fixed X" vs "X is done."

**Option B is rejected** — no dedup means work_items table fills with duplicates. Every consolidation run mentioning the same task creates a new row.

### Phase 0 Steps

1. **Inspect consolidation output format** — Read 2-3 files from `~/.council-memory/arc-memory/daily/` to verify structure (headers + bullets vs narrative)
2. **Test ArcReconciler extraction** — Run `ArcReconciler._extract_tasks()` against actual consolidation files, verify output quality
3. **Compare against LLM extraction** — If ARC server is running, run `ArcClient.extract_tasks()` on same files, compare output
4. **Decision** — Select Option A or C based on extraction quality comparison
5. **Document decision** — Update this handoff with selected option and rationale

### Phase 0 Tests

- [ ] ArcReconciler extracts tasks from actual consolidation files
- [ ] Extracted items have `title`, `evidence`, `status` fields
- [ ] Output can be reshaped to `arc_delta` format for TaskReconciler
- [ ] Decision documented with rationale

### Phase 0 Dependencies

None — can start immediately.

---

## Phase 1: Revert Uncommitted Refactoring

**What:** Restore the codebase to the last committed state (932 passing tests). All refactoring changes are uncommitted and fully recoverable.

**Rationale:** The uncommitted changes are incomplete and broken. Reverting gives a clean baseline to work from. If any refactoring ideas are kept, they're applied selectively after tests pass.

**Files affected:** All 25 modified files in `git status --short`.

### Steps

1. **Stash uncommitted changes** (preserves them for reference):
   ```bash
   cd /home/chief/Coding-Projects/7-council
   git stash push -m "refactoring-incomplete-2026-06-10"
   ```

2. **Verify clean state:**
   ```bash
   git status --short  # should be empty
   ```

3. **Run full test suite:**
   ```bash
   python3 -m pytest tests/ -v --tb=short
   ```
   Expect: **932 passing, 0 failures** (the committed baseline).

4. **Verify MemoryService init:**
   - Confirm `SqliteIndexer` and `DocFileWatcher` are present in `MemoryService.__init__`
   - Confirm `UnifiedVectorStore` is present
   - Confirm `_start_reconciliation_thread()` is wired

5. **Verify reconciliation methods:**
   - Confirm `reconcile_tasks()` calls `self._client.extract_tasks()` → `self._relational_store.reconcile_arc_delta()`
   - Confirm `reconcile_deviations()` calls `self._client.detect_deviations()` → DB

### Phase 1 Tests

- [ ] `git status --short` returns empty
- [ ] `pytest tests/` passes with 0 failures
- [ ] `MemoryService.__init__` includes SqliteIndexer, DocFileWatcher, UnifiedVectorStore
- [ ] `reconcile_tasks()` has full LLM extraction + TaskReconciler flow
- [ ] `reconcile_deviations()` has full LLM detection + DB flow

### Phase 1 Dependencies

None — can start immediately.

---

## Phase 2: Fix pplx-embed Service

**What:** Apply memory limits and verify the embedding server runs stably.

**Current state:** Service file on disk was changed to TEI/Docker but systemd hasn't reloaded. Last run used Python ONNX server (PID 242229, killed by TERM). Service is inactive.

**Root cause of memory leak:** ONNX Runtime 1.26.0 on CPUExecutionProvider has a known memory leak ([microsoft/onnxruntime#22271](https://github.com/microsoft/onnxruntime/issues/22271)). The leak was triggered by memsearch-watch crash-loop holding HTTP connections open. With the gRPC keepalive fix, the crash-loop is stopped, but memory limits are still needed as a safety net.

### Steps

1. **Restore Python ONNX server config** (not TEI/Docker — TEI requires 2.3GB safetensors download, Python server works fine):
   ```ini
   [Unit]
   Description=pplx-embed-v1 Embedding Server (Python ONNX)
   After=network.target

   [Service]
   Type=simple
   ExecStart=/usr/bin/python3 /home/chief/models/embedding/pplx-embed-v1-0.6b-int8/server.py --port 18099
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal
   Environment=PYTHONUNBUFFERED=1

   # Memory safety net (prevents ONNX Runtime leak from OOM)
   MemoryMax=2G
   MemoryHigh=1.5G

   [Install]
   WantedBy=default.target
   ```

2. **Reload systemd:**
   ```bash
   systemctl --user daemon-reload
   ```

3. **Start the service:**
   ```bash
   systemctl --user start pplx-embed.service
   ```

4. **Verify health:**
   ```bash
   curl -s http://127.0.0.1:18099/v1/models | python3 -m json.tool
   ```
   Expect: `{"models": [{"id": "pplx-embed-v1-0.6b", ...}]}`

5. **Monitor memory for 5 minutes:**
   ```bash
   watch -n 5 'systemctl --user status pplx-embed.service | grep Memory'
   ```
   Expect: Memory stable under 1GB with steady request pattern.

### Phase 2 Tests

- [ ] Service starts without error
- [ ] Health endpoint returns model info
- [ ] Memory stays under 1.5G (MemoryHigh threshold) for 5+ minutes
- [ ] No OOM kills or restarts

### Phase 2 Dependencies

None — can start in parallel with Phase 1.

---

## Phase 3: Fix memsearch-watch Service

**What:** Verify gRPC keepalive fix is applied, add `arc-reconcile/` to watch list, verify stable operation.

**Current state:** Service is inactive. gRPC keepalive was fixed (60s) but needs verification. Watch list only includes `arc-memory/`, not `arc-reconcile/`.

### Steps

1. **Verify current service config:**
   ```bash
   systemctl --user cat memsearch-watch.service
   ```
   Confirm:
   - `GRPC_KEEPALIVE_TIME_MS=60000` (60s, not 30s)
   - `GRPC_CLIENT_MAX_SEND_MESSAGE_BYTES=104857600` (100MB)
   - `GRPC_CLIENT_MAX_RECEIVE_MESSAGE_BYTES=104857600` (100MB)

2. **Add `arc-reconcile/` to watch list** (replaces UnifiedVectorStore):
   ```ini
   ExecStart=/home/chief/.local/bin/memsearch watch \
       --provider openai \
       --model pplx-embed-v1-0.6b \
       --base-url http://127.0.0.1:18099/v1 \
       --api-key dummy-local-key \
       /home/chief/.council-memory/arc-memory/ \
       /home/chief/.council-memory/arc-reconcile/ \
       /home/chief/llm-wiki/
   ```

3. **Reload and start:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user start memsearch-watch.service
   ```

4. **Verify stable for 60+ seconds:**
   ```bash
   journalctl --user -u memsearch-watch.service --since "1 min ago" --no-pager
   ```
   Expect: No GOAWAY errors, no ENHANCE_YOUR_CALM, no crash-loop.

5. **Verify arc-reconcile/ is indexed:**
   ```bash
   # Check if arc-reconcile files appear in memsearch collection
   python3 -c "
   from memsearch import search
   result = search('reconciliation', top_k=3)
   for r in result: print(r.get('source', 'unknown'), r.get('score', 0))
   "
   ```

### Phase 3 Tests

- [ ] Service starts without error
- [ ] No GOAWAY/ENHANCE_YOUR_CALM errors in logs for 60+ seconds
- [ ] `arc-reconcile/` files are indexed (search returns results)
- [ ] Memory stable under 300MB

### Phase 3 Dependencies

Phase 2 (pplx-embed must be running for embeddings).

---

## Phase 4: Implement Selected Reconciliation Path

**What:** Implement the reconciliation approach selected in Phase 0. This phase has two branches — execute only the selected one.

### Branch A: Revert + Re-wire (if Option A selected)

**What:** Ensure committed reconciliation is fully wired and tested.

**Steps:**
1. After Phase 1 (git stash), verify `reconcile_tasks()` calls `self._client.extract_tasks()` → `self._relational_store.reconcile_arc_delta()`
2. Verify `reconcile_deviations()` calls `self._client.detect_deviations()` → DB
3. Verify `run_tiered_consolidation()` calls `self.reconcile_tasks()` after consolidation succeeds
4. Run reconciliation tests: `pytest tests/test_reconciliation.py -v`
5. Verify knowledge card includes work_items: `ContextRouter.get_knowledge_card(include_work_items=True)`

**Tests:**
- [ ] `pytest tests/test_reconciliation.py` passes
- [ ] `reconcile_tasks()` returns structured results (not hardcoded)
- [ ] `reconcile_deviations()` returns structured results (not hardcoded)
- [ ] Knowledge card includes active work items

### Branch C: Mechanical Extraction + TaskReconciler (if Option C selected)

**What:** Wire ArcReconciler's mechanical extraction into TaskReconciler's mechanical reconciliation.

**Steps:**
1. **After Phase 1 (git stash)**, apply selective changes:
   - Keep ArcReconciler from stash (or re-implement)
   - Keep TaskReconciler from committed code

2. **Create adapter function** in `pipeline.py`:
   ```python
   def _arc_reconciler_to_delta(self, tier_id: str) -> Optional[dict]:
       """Convert ArcReconciler output to arc_delta format for TaskReconciler."""
       from .reconcile import ArcReconciler
       reconciler = ArcReconciler(memory_base=str(self._memory_base))
       result = reconciler.reconcile_tier(tier_id)
       if not result:
           return None
       # Read reconciliation files and reshape
       reconcile_dir = reconciler.reconcile_dir() / tier_id
       delta = {
           'new_tasks': self._read_reconciliation_items(reconcile_dir, 'tasks'),
           'completed_tasks': [],
           'blocked_tasks': [],
           'task_updates': [],
           'open_questions': [],
       }
       # Classify items by status from evidence
       for item in delta['new_tasks'][:]:
           evidence = item.get('evidence', '').lower()
           if any(kw in evidence for kw in STATUS_KEYWORDS['done']):
               delta['completed_tasks'].append(item)
               delta['new_tasks'].remove(item)
           elif any(kw in evidence for kw in STATUS_KEYWORDS['blocked']):
               delta['blocked_tasks'].append(item)
               delta['new_tasks'].remove(item)
       return delta
   ```

3. **Update `reconcile_tasks()`** to use adapter:
   ```python
   def reconcile_tasks(self, consolidation_text, tier_id, project_id=None, ...):
       arc_delta = self._arc_reconciler_to_delta(tier_id)
       if not arc_delta:
           return None
       if not self._relational_store:
           return None
       # Resolve project_id if needed
       if not project_id:
           resolution = self._relational_store.resolve_project_from_context(is_system_operation=True)
           if resolution.is_writable:
               project_id = resolution.project_id
       # Reconcile via TaskReconciler (mechanical dedup)
       return self._relational_store.reconcile_arc_delta(
           arc_delta=arc_delta,
           project_id=project_id,
           run_id=run_id,
           source_summary_id=source_summary_id,
       )
   ```

4. **Update tests** to test mechanical extraction + reconciliation flow

5. **Add fallback** — if ArcReconciler produces no results, fall back to LLM extraction (if ARC server available):
   ```python
   if not arc_delta and self._client:
       arc_delta = self._client.extract_tasks(consolidation_text)
   ```

**Tests:**
- [ ] ArcReconciler extracts tasks from actual consolidation files
- [ ] Adapter reshapes output to arc_delta format
- [ ] TaskReconciler deduplicates correctly
- [ ] `reconcile_tasks()` returns structured results
- [ ] Fallback to LLM works when ArcReconciler produces no results
- [ ] `pytest tests/test_reconciliation.py` passes

### Phase 4 Dependencies

Phase 0 (decision made), Phase 1 (clean baseline).

---

## Phase 5: Remove UnifiedVectorStore

**What:** Delete UnifiedVectorStore class, remove from MemoryService, remove from tests. Replaced by memsearch-watch watching `arc-reconcile/`.

**Rationale:** UnifiedVectorStore is redundant — memsearch already provides semantic search with project-scoped filtering. Two Milvus collections (`memsearch_chunks` + `unified_vectors`) = two failure modes with no proportional benefit.

**Files to modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/__init__.py` | Remove UnifiedVectorStore from init |
| Delete | `super_council/memory_service/vector_store.py` | Remove dead class |
| Modify | `super_council/tests/test_vector_store.py` | Remove or skip tests |
| Modify | Any import of UnifiedVectorStore | Remove references |

### Steps

1. **Find all references:**
   ```bash
   grep -rn "UnifiedVectorStore\|vector_store" super_council/ --include="*.py" | grep -v __pycache__ | grep -v test
   ```

2. **Remove from MemoryService.__init__:**
   - Remove `self._vector_store = UnifiedVectorStore(...)`
   - Remove `self._vector_store.reindex_existing_data(...)`
   - Remove any `_start_vector_reindex_thread()` calls

3. **Remove from imports:**
   - Remove `from .vector_store import UnifiedVectorStore` from `__init__.py`
   - Remove from `__init__.py` `__all__` if present

4. **Delete vector_store.py:**
   ```bash
   rm super_council/memory_service/vector_store.py
   ```

5. **Update tests:**
   - Remove or skip `test_vector_store.py`
   - Update any test that imports UnifiedVectorStore

6. **Run full test suite:**
   ```bash
   python3 -m pytest tests/ -v --tb=short
   ```
   Expect: All tests pass (no regression).

### Phase 5 Tests

- [ ] `grep -rn "UnifiedVectorStore" super_council/` returns 0 matches (excluding tests)
- [ ] MemoryService starts without UnifiedVectorStore
- [ ] `pytest tests/` passes with 0 failures
- [ ] No import errors on startup

### Phase 5 Dependencies

Phase 3 (memsearch-watch must be indexing arc-reconcile/ as replacement).

---

## Phase 6: Production Wiring + End-to-End Verification

**What:** Wire all components into a running system, verify full pipeline end-to-end.

### Steps

1. **Start services in order:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user start pplx-embed.service
   sleep 5  # wait for model load
   systemctl --user start memsearch-watch.service
   ```

2. **Verify service health:**
   ```bash
   # Embedding server
   curl -s http://127.0.0.1:18099/v1/models | python3 -m json.tool

   # memsearch-watch logs
   journalctl --user -u memsearch-watch.service --since "1 min ago" --no-pager
   ```

3. **Run full consolidation pipeline:**
   ```bash
   python3 -c "
   from super_council.arc_summarizer import ArcPipeline
   pipeline = ArcPipeline(memory_base='~/.council-memory')
   result = pipeline.run_tiered_consolidation(tier_id='daily')
   print('Consolidation result:', result)
   "
   ```

4. **Verify reconciliation:**
   ```bash
   # Check arc-reconcile/ has output
   ls -la ~/.council-memory/arc-reconcile/daily/

   # Check work_items table has entries
   python3 -c "
   from super_council.memory_service import RelationalStore
   store = RelationalStore(db_path='~/.council-memory/council_core.db')
   items = store.get_work_items(project_id=None, status=None)
   print(f'Work items: {len(items)}')
   for item in items[:5]:
       print(f'  - {item[\"title\"]} ({item[\"status\"]})')
   "
   ```

5. **Verify memsearch indexing:**
   ```bash
   python3 -c "
   from memsearch import search
   # Search for reconciliation output
   result = search('task reconciliation', top_k=5)
   for r in result:
       print(r.get('source', 'unknown'), '-', r.get('score', 0))
   "
   ```

6. **Verify knowledge card:**
   ```bash
   python3 -c "
   from super_council.memory_service import ContextRouter
   router = ContextRouter()
   card = router.get_knowledge_card(include_work_items=True, include_deviations=True)
   print(card)
   "
   ```

7. **Monitor for 10 minutes:**
   ```bash
   # Check no crashes, no memory growth
   watch -n 10 'systemctl --user status pplx-embed memsearch-watch | grep -E "(Active|Memory)"'
   ```

### Phase 6 Tests (GATE — must pass before marking complete)

- [ ] pplx-embed starts and responds to health check
- [ ] memsearch-watch starts and indexes both arc-memory/ and arc-reconcile/
- [ ] Full consolidation pipeline runs without error
- [ ] arc-reconcile/ has output files after consolidation
- [ ] work_items table has entries after reconciliation
- [ ] memsearch search returns results from arc-reconcile/
- [ ] Knowledge card includes active work items
- [ ] No service crashes in 10-minute monitoring window
- [ ] Memory stable (pplx-embed under 1.5G, memsearch-watch under 300MB)
- [ ] All existing tests still pass (`pytest tests/` — 0 failures)

### Phase 6 Dependencies

All previous phases (0-5) complete.

---

## Execution Order

```
Phase 0 (assessment) ─────────────────────────────────┐
Phase 1 (revert) ──┐                                 │
Phase 2 (pplx) ─────┼──────── Phase 3 (memsearch) ────┼── Phase 4 (reconciliation) ── Phase 5 (remove UVS) ── Phase 6 (wiring)
                    │                                 │
                    └─────────────────────────────────┘
```

**Parallel:** Phase 0, Phase 1, Phase 2 can run simultaneously.

**Sequential:** Phase 3 → Phase 4 → Phase 5 → Phase 6.

---

## Constraints

- **No LLM calls for reconciliation** if Option C is selected — fully mechanical
- **Memory limits on pplx-embed** — `MemoryMax=2G`, `MemoryHigh=1.5G` — non-negotiable safety net
- **gRPC keepalive ≥ 60s** — Milvus Lite 3.0 rejects below 60s with ENHANCE_YOUR_CALM
- **All changes must pass full test suite** — no regression on 932 baseline tests
- **UnifiedVectorStore must be removed** — not fixed, not kept as backup
- **SqliteIndexer and DocFileWatcher are dead** — do not resurrect unless Phase 0 decides they're needed
- **arc-reconcile/ must be in memsearch-watch scope** — replaces UnifiedVectorStore for semantic search

---

## Caveats & Uncertainty

1. **Consolidation output format:** Option C depends on consolidation producing structured MD with headers + bullets. If the ARC LLM produces narrative prose, regex extraction fails silently. Phase 0 must verify this.

2. **ARC server availability:** Option A requires Granite on :18095. If the server is down, reconciliation returns `None` (graceful degradation — consolidation still works, just no structured tasks).

3. **ONNX Runtime leak:** Even with memory limits, the process will be killed at 2G and restarted. This is acceptable — it's a safety net, not a fix. The real fix is preventing crash-loops (gRPC keepalive).

4. **Milvus Lite single-user:** Both memsearch and UnifiedVectorStore share the same Milvus Lite backend (`~/.memsearch/milvus.db`). Removing UnifiedVectorStore eliminates potential lock conflicts.

5. **Stashed refactoring:** `git stash` preserves all uncommitted changes. If any refactoring ideas are worth keeping (e.g., ArcReconciler structure), they can be selectively cherry-picked from the stash.

---

## Success Criteria

- [ ] Phase 0: Reconciliation path selected with documented rationale
- [ ] Phase 1: Codebase reverted to committed state, 932 tests passing
- [ ] Phase 2: pplx-embed running with MemoryMax=2G, stable under 1.5G
- [ ] Phase 3: memsearch-watch indexing arc-memory/ + arc-reconcile/, no GOAWAY errors
- [ ] Phase 4: Reconciliation produces work_items in DB (Option A or C)
- [ ] Phase 5: UnifiedVectorStore removed, no import errors, tests pass
- [ ] Phase 6: Full end-to-end pipeline verified, services stable for 10+ minutes
- [ ] No regression: All existing tests pass (0 failures)
- [ ] Knowledge card includes active work items and deviations

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `~/.config/systemd/user/pplx-embed.service` | Restore Python ONNX server, add memory limits |
| Modify | `~/.config/systemd/user/memsearch-watch.service` | Add arc-reconcile/ to watch list |
| Modify | `super_council/arc_summarizer/pipeline.py` | Fix reconciliation (Option A or C) |
| Modify | `super_council/memory_service/__init__.py` | Remove UnifiedVectorStore |
| Delete | `super_council/memory_service/vector_store.py` | Remove dead class |
| Modify | `super_council/tests/test_vector_store.py` | Remove or skip tests |
| Create | `super_council/arc_summarizer/reconcile_adapter.py` (Option C only) | Adapter: ArcReconciler → arc_delta → TaskReconciler |
