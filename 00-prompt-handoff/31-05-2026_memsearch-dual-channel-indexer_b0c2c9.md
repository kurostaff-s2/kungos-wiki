**Source spec:** `~/.llm-wiki/super-council-docs/11-memsearch.md`
**Generated:** 31-05-2026 by Pi agent (task-handoff skill)
**Goal:** Replace temp-file indexing with dual-channel indexer (DB poller + file watcher) → unified Milvus collection with enriched metadata.

---

## Execution Prompt: MemSearch Dual-Channel Indexer

---

### Phase 1: Schema Migrations

Add `is_indexed INTEGER DEFAULT 0` to three tables: `consolidation_cache` (`summary_text`), `review_findings` (`summary+details+fix`), `artifacts` (`content`).

Create `migrations/09_memsearch_index_flags.sql`. Each table: `ALTER TABLE ... ADD COLUMN is_indexed INTEGER DEFAULT 0` + `CREATE INDEX IF NOT EXISTS idx_{table}_indexed ON {table}(is_indexed)`.

---

### Phase 2: DB Poller (Channel A — Workflow Data)

Create `memory_service/db_poller.py` — background thread that polls SQLite for unindexed rows and upserts them directly to Milvus.

**Class: `DbIndexPoller(store, config)`**

`_poll_and_index()`: Queries 5 tables for `WHERE is_indexed = 0 ORDER BY created_at ASC LIMIT 50`:

| Table | Source ID | Text | Metadata |
|-------|-----------|------|----------|
| `raw_session_memories` | `raw_session_memories:trace-{id}` | `raw_text` | type=workflow |
| `session_diary` | `session_diary:{id}` | `context+decisions+completed` | type=workflow |
| `consolidation_cache` | `consolidation_cache:{id}` | `summary_text` | type=workflow |
| `review_findings` | `review_findings:{id}` | `summary+details+fix` | type=review, severity={s} |
| `artifacts` | `artifacts:{id}` | `content` | type=artifact, phase={p} |

Per row: `chunk_markdown(text, source=id)` → build record dicts (`chunk_hash`, `content`, `source`, `project_id`, `type`, `start_line`, `end_line`) → batch `store._client.upsert()` → `UPDATE {table} SET is_indexed=1`.

`start(interval=30)`: Daemon thread, catches all exceptions. `stop()`: sets `_running=False`, joins.

**Wiring:** In `memory_service/__init__.py`: if `indexer.available` → `self._poller = DbIndexPoller(store, config).start()`.

---

### Phase 3: File Watcher (Channel B — Documentation)

Create `memory_service/file_watcher.py` — wraps `memsearch watch` for selected directories.

**Class: `DocFileWatcher(config)`**

Defaults: `~/llm-wiki/super-council-docs/`, `~/.council-memory/daily/`, `~/.council-memory/specs/` (if exists).

`start()`: Creates MemSearch → `ms.watch(paths)` → returns watcher. If unavailable: logs warning, returns None.
`stop()`: `watcher.stop()`.

**Wiring:** In `memory_service/__init__.py`: if `indexer.available` → `self._watcher = DocFileWatcher(config).start()`.

---

### Phase 4: Replace Temp-File Indexing

Modify `store.py:_try_index_raw_memory()` to stop using temp files.

**Current code:** `tempfile.mkstemp()` → write → `index_file(path)` → `os.unlink(path)`.

**Replace with:** Direct call to poller's chunking logic. Since the poller now handles `raw_session_memories WHERE is_indexed = 0`, the `_try_index_raw_memory()` background thread becomes redundant. Remove it entirely. The poller will pick up the row on its next cycle (≤30s latency, acceptable).

**Change:** In `upsert_raw_session_memory()`, after `INSERT INTO raw_session_memories`, remove the `threading.Thread(target=_try_index_raw_memory)` block. Row starts with `is_indexed=0`, poller handles it.

---

### Phase 5: Metadata Enrichment in Search

Modify `memory_service/index.py:MemIndex.search()` to accept and apply metadata filters.

**New parameters:** `type_filter: Optional[str] = None`, `source_prefix: Optional[str] = None`

**Filtering logic (client-side, post-retrieval):**
- If `type_filter`: keep only results where `metadata.get("type") == type_filter`
- If `source_prefix`: keep only results where `metadata.get("source", "").startswith(source_prefix)`

**Propagate to callers:**
- `_active_recall()` in `super_council.py`: pass `type_filter` from phase context
- `recall.unified()` in `layer.py`: pass `source_prefix` for channel-specific queries

---

### Phase 6: Health & Diagnostics

Add to `/health` endpoint response:

```json
{
  "memsearch": {
    "status": "available",
    "poller": {"running": true, "indexed_last_cycle": 12},
    "watcher": {"running": true, "watched_dirs": 3},
    "collection_stats": {"row_count": 4521, "chunk_count": 18930}
  }
}
```

Add MCP tool: `memsearch_status()` → returns poller stats + watcher status + collection row count.

---

### Phase 7: Tests

1. **Test DB poller:** Seed 3 rows with `is_indexed=0` in each table. Run `_poll_and_index()`. Assert all rows indexed, `is_indexed=1` in DB, chunks exist in Milvus.
2. **Test file watcher:** Create temp dir with 2 `.md` files. Start watcher. Assert files indexed. Modify one file. Assert re-indexed. Stop watcher. Assert no further indexing.
3. **Test temp-file removal:** Call `upsert_raw_session_memory()`. Assert no `/tmp/trace-*` file created. Assert row appears with `is_indexed=0`. Wait for poller cycle. Assert `is_indexed=1`.
4. **Test metadata filtering:** `search(query, type_filter="review")` → assert all results have type=review.
5. **Test graceful degradation:** Unset memsearch package. Assert poller/watcher both return None, no crashes.

---

### Constraints

- **Zero direct MemSearch in `super_council.py`.** All routing through `memory_service.indexer`.
- **Graceful degradation.** If memsearch unavailable, poller/watcher are no-ops. All callers handle empty results.
- **Fire-and-forget.** Poller catches all exceptions. Never blocks the main thread.
- **Backwards-compatible.** `is_indexed` defaults to 0. Existing rows are picked up on first poll.
- **No schema changes to Milvus collection.** Uses existing dynamic fields (`project_id`, `type`, `severity`, `phase`).

### Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/09_memsearch_index_flags.sql` | Add `is_indexed` to 3 tables |
| Create | `memory_service/db_poller.py` | DB poller (Channel A) |
| Create | `memory_service/file_watcher.py` | File watcher (Channel B) |
| Modify | `memory_service/__init__.py` | Wire poller + watcher |
| Modify | `memory_service/store.py` | Remove temp-file indexing |
| Modify | `memory_service/index.py` | Metadata filtering in search |
| Modify | `super_council.py` | Propagate type_filter to _active_recall |
| Modify | `memory_service/layer.py` | Propagate source_prefix to recall.unified |
| Create | `tests/test_db_poller.py` | Poller tests |
| Create | `tests/test_file_watcher.py` | Watcher tests |
| Modify | `tests/test_memsearch.py` | Metadata filtering + temp-file removal |

### Success Criteria

- `/tmp/trace-*` files no longer created during indexing
- All 5 tables indexed via poller (verify: `SELECT COUNT(*) FROM {table} WHERE is_indexed = 1`)
- File watcher indexes docs from 3+ directories
- Search returns results with enriched metadata (`source`, `type`, `project_id`)
- Health endpoint reports poller + watcher status
- All tests pass, graceful degradation verified
