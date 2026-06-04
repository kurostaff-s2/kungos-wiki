# Handoff: Recall & Search Fine-Tuning

**Source spec:** `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
**Live audit:** Verified via MCP SSE (`:18097`) + HTTP dispatch (`:18098`) on 2026-06-04
**Generated:** 04-06-2026
**Goal:** Fix 6 operational weaknesses in search/recall (wrong model, LIKE queries, timeout, wrong data indexed, no project filter, dead ChromaDB code) to deliver real outcomes for five usage flows.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/` (ChromaDB imports to remove)
**Key files:**
- Embedding: `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py`
- Memory service: `super_council/memory_service/` (layer.py, router.py, index.py, memsearch_wrapper.py)
- Migrations: `migrations/` (new: 10_fts5_indexes.sql, 11_projects.sql)
- Odysseus: `vendor/odysseus/src/memory_vector.py`, `vendor/odysseus/src/rag_vector.py`

---

## Execution Order

```
Phase 1 (start pplx server) ──────────────────────────────────┐
                                                               ├──> Phase 3 (FTS5 indexes) ──> Phase 5 (Production Wiring)
Phase 2 (drop ChromaDB) ──────────────────────────────────────┘                                        │
                                                               ───> Phase 4 (vector re-index) ────────┘
```

**Parallelizable:** Phase 1 + Phase 2 can run simultaneously.
**Sequential:** Phase 3 + Phase 4 after Phase 1 (need pplx running). Phase 5 last.

---

## Phase 1: Start pplx Embedding Server on :18099

**What:** Get the existing pplx-embed-v1 HTTP server running. Model (688MB) and server.py exist. Just not started.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Read | `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py` | Verify port, endpoints |
| Create | `~/.config/systemd/user/pplx-embedding.service` | Systemd user service |
| Modify | `memory_service/layer.py` | Change embedding URL from ONNX to HTTP |

**Steps:**

1. **Verify server.py:**
   ```bash
   head -50 ~/models/embedding/pplx-embed-v1-0.6b-int8/server.py
   ```
   Confirm: port `18099`, endpoints `/v1/embeddings` + `/v1/models`, health `/health`.

2. **Create systemd service:**
   ```ini
   [Unit]
   Description=pplx-embed-v1 Embedding Server
   After=network.target

   [Service]
   Type=simple
   ExecStart=/usr/bin/python3 /home/chief/models/embedding/pplx-embed-v1-0.6b-int8/server.py
   Restart=on-failure
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=default.target
   ```

3. **Start and enable:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user start pplx-embedding.service
   systemctl --user enable pplx-embedding.service
   ```

4. **Verify:**
   ```bash
   curl -s http://127.0.0.1:18099/v1/models
   curl -s http://127.0.0.1:18099/health
   ```

5. **Update layer.py** — Change council-recall Channel 1 from bge-m3 ONNX to pplx HTTP:
   ```python
   # In layer.py unified_recall(), Channel 1:
   # OLD:
   ms = MemSearch(
       embedding_provider="onnx",
       embedding_model="gpahal/bge-m3-onnx-int8",
       ...
   )
   # NEW:
   ms = MemSearch(
       embedding_provider="http",
       embedding_url="http://127.0.0.1:18099/v1/embeddings",
       ...
   )
   ```

**Tests:**
- `curl :18099/v1/models` returns model list
- `curl :18099/health` returns 200
- council-recall returns results (no regression)

**Dependencies:** None.

---

## Phase 2: Drop ChromaDB Imports

**What:** Remove dead ChromaDB code from Odysseus. ChromaDB is not running, has zero data. Pure cleanup.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `vendor/odysseus/src/memory_vector.py` | Remove ChromaDB imports, graceful no-op |
| Modify | `vendor/odysseus/src/rag_vector.py` | Remove ChromaDB imports, graceful no-op |
| Modify | `vendor/odysseus/src/ai_interaction.py` | Remove `_memory_vector` references |

**Steps:**

1. **Audit ChromaDB references:**
   ```bash
   grep -rn 'chroma\|Chroma\|MemoryVectorStore\|VectorRAG' vendor/odysseus/src/
   ```

2. **Modify `memory_vector.py`:**
   - Replace ChromaDB import with `healthy = False` default
   - `add()` and `search()` return no-ops with log warning
   - Keep class interface (don't break callers)

3. **Modify `rag_vector.py`:**
   - Same pattern — graceful degradation, no crashes

4. **Modify `ai_interaction.py`:**
   - Remove `_memory_vector` global references
   - Or: keep references but they hit no-op implementations

5. **Verify Odysseus still starts:**
   ```bash
   cd vendor/odysseus && python3 -c "from src.ai_interaction import do_manage_memory; print('OK')"
   ```

**Tests:**
- No `ImportError` on ChromaDB
- Odysseus imports succeed
- `manage_memory` tool returns gracefully (no crash)

**Dependencies:** None. Runs parallel with Phase 1.

---

## Phase 3: FTS5 Indexes

**What:** Replace LIKE queries with FTS5 on content-bearing tables. Immediate quality gain for keyword search.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/10_fts5_indexes.sql` | FTS5 virtual tables |
| Modify | `memory_service/router.py` | Replace LIKE with FTS5 MATCH |
| Modify | `memory_service/layer.py` | Replace LIKE with FTS5 MATCH in council-recall Ch.3 |

**Steps:**

1. **Create migration:**
   ```sql
   -- FTS5 on session_diary (decisions, open_items, work_completed)
   CREATE VIRTUAL TABLE IF NOT EXISTS session_diary_fts USING fts5(
       decisions, open_items, work_completed,
       content='session_diary', content_rowid='rowid'
   );

   -- Sync trigger: INSERT
   CREATE TRIGGER IF NOT EXISTS session_diary_fts_insert AFTER INSERT ON session_diary
   BEGIN
       INSERT INTO session_diary_fts(rowid, decisions, open_items, work_completed)
       VALUES (NEW.rowid, NEW.decisions, NEW.open_items, NEW.work_completed);
   END;

   -- Sync trigger: UPDATE
   CREATE TRIGGER IF NOT EXISTS session_diary_fts_update AFTER UPDATE ON session_diary
   BEGIN
       UPDATE session_diary_fts
       SET decisions=NEW.decisions, open_items=NEW.open_items, work_completed=NEW.work_completed
       WHERE rowid=NEW.rowid;
   END;

   -- Sync trigger: DELETE
   CREATE TRIGGER IF NOT EXISTS session_diary_fts_delete AFTER DELETE ON session_diary
   BEGIN
       DELETE FROM session_diary_fts WHERE rowid=OLD.rowid;
   END;

   -- FTS5 on artifacts (content)
   CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
       content, content='artifacts', content_rowid='rowid'
   );
   -- ... triggers ...

   -- FTS5 on event_log (message)
   CREATE VIRTUAL TABLE IF NOT EXISTS event_log_fts USING fts5(
       message, content='event_log', content_rowid='rowid'
   );
   -- ... triggers ...

   -- Seed existing data
   INSERT INTO session_diary_fts(rowid, decisions, open_items, work_completed)
   SELECT rowid, decisions, open_items, work_completed FROM session_diary;

   INSERT INTO artifacts_fts(rowid, content)
   SELECT rowid, content FROM artifacts;

   INSERT INTO event_log_fts(rowid, message)
   SELECT rowid, message FROM event_log;
   ```

2. **Run migration:**
   ```python
   import sqlite3, os
   db = os.path.expanduser('~/.council-memory/pipelines.db')
   conn = sqlite3.connect(db)
   conn.executescript(open('migrations/10_fts5_indexes.sql').read())
   conn.close()
   ```

3. **Update router.py** — `query_session_diary()`:
   ```python
   # OLD:
   like_pattern = f"%{query}%"
   conditions.append("(decisions LIKE ? OR open_items LIKE ? OR work_completed LIKE ?)")

   # NEW:
   conditions.append("session_diary_fts MATCH ?")
   params.append(query)
   # Join with session_diary on rowid for full row data
   ```

4. **Update layer.py** — council-recall Channel 3:
   ```python
   # OLD:
   rows = self._db.execute(
       "SELECT phase, key, content FROM artifacts WHERE content LIKE ?",
       (f"%{query}%",),
   ).fetchall()

   # NEW:
   rows = self._db.execute(
       """SELECT a.phase, a.key, a.content FROM artifacts a
          JOIN artifacts_fts f ON a.rowid = f.rowid
          WHERE artifacts_fts MATCH ? ORDER BY rank LIMIT 5""",
       (query,),
   ).fetchall()
   ```

**Tests:**
- `query_session_diary("decisions")` returns results (was 0 before)
- `council-recall("how does memory service work")` returns ranked results
- FTS5 handles stemming ("decision" matches "decisions")
- No regression on existing queries

**Dependencies:** None.

---

## Phase 4: Vector Store Re-index + Project Scoping

**What:** Index canonical knowledge (memories, session_diary, consolidation_cache) into Milvus. Add project_id as Milvus dynamic field for server-side filtering.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/vector_store.py` | UnifiedVectorStore class |
| Modify | `memory_service/index.py` | Replace MemIndex with UnifiedVectorStore |
| Modify | `memory_service/memsearch_wrapper.py` | Add project_id tagging |
| Modify | `memory_service/layer.py` | Index on write |

**Steps:**

1. **Create UnifiedVectorStore** — `memory_service/vector_store.py`:
   ```python
   class UnifiedVectorStore:
       COLLECTION_NAME = "unified_vectors"
       SOURCES = ("memory", "session_diary", "consolidation_cache", "knowledge_card", "document", "note")

       def __init__(self, embedding_url: str = "http://127.0.0.1:18099"):
           self._embed_url = embedding_url
           self._milvus_uri = os.path.expanduser("~/.memsearch/milvus.db")

       def index(self, source: str, source_id: str, text: str, project_id: str = None, metadata: Dict = None):
           """Index a text chunk into Milvus with source tagging."""
           embedding = self._get_embedding(text)
           data = {
               "source": source,
               "source_id": source_id,
               "text": text,
               "embedding": embedding,
               "project_id": project_id or "",
               **(metadata or {}),
           }
           self._upsert(data)

       def search(self, query: str, top_k: int = 10, project_id: str = None, source: str = None) -> List[Dict]:
           """Search with server-side filters."""
           embedding = self._get_embedding(query)
           filter_expr = ""
           if project_id:
               filter_expr += f'project_id == "{project_id}"'
           if source:
               if filter_expr: filter_expr += " and "
               filter_expr += f'source == "{source}"'
           return self._query(embedding, top_k, filter_expr)

       def _get_embedding(self, text: str) -> List[float]:
           """Get embedding from pplx HTTP server."""
           resp = httpx.post(f"{self._embed_url}/v1/embeddings", json={
               "input": [text], "model": "pplx-embed-v1"
           })
           return resp.json()["data"][0]["embedding"]
   ```

2. **Re-index existing data:**
   ```python
   # Index existing session_diary entries
   for row in db.execute("SELECT summary_id, decisions, work_completed FROM session_diary"):
       vs.index("session_diary", row[0], f"{row[1] or ''} {row[2] or ''}")

   # Index existing consolidation_cache entries
   for row in db.execute("SELECT cache_id, continuity_notes, active_context FROM consolidation_cache"):
       vs.index("consolidation_cache", row[0], f"{row[1] or ''} {row[2] or ''}")
   ```

3. **Update memsearch_wrapper.py** — Add project_id to Milvus dynamic fields:
   ```python
   def _tag_project(self, source: str, project_id: str):
       hashes = self._ms.store.hashes_by_source(source)
       data = [{"chunk_hash": h, "project_id": project_id} for h in hashes]
       self._ms.store._client.upsert(collection_name=self._ms.store._collection, data=data)
   ```

4. **Update layer.py** — Index on write:
   ```python
   # In upsert_summary() or similar write paths:
   if self._vector_store:
       self._vector_store.index(
           source="session_diary",
           source_id=summary_id,
           text=f"{decisions} {open_items} {work_completed}",
           project_id=project_id,
       )
   ```

**Tests:**
- UnifiedVectorStore indexes and retrieves documents
- `search(project_id="xyz")` returns only matching project (server-side filter)
- `search(source="session_diary")` returns only diary entries
- Existing memsearch still works (backward compat)

**Dependencies:** Phase 1 (pplx server must be running).

---

## Phase 5: Production Wiring + Verification

**What:** Wire all components, restart memory-service, verify full flow end-to-end.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/__init__.py` | Wire UnifiedVectorStore |
| Create | `scripts/verify_recall.py` | End-to-end verification |

**Steps:**

1. **Restart memory-service:**
   ```bash
   systemctl --user restart memory-service.service
   ```

2. **Run verification script** — `scripts/verify_recall.py`:
   ```python
   import httpx, json

   BASE = "http://127.0.0.1:18098/v1/memory/tool"

   def verify():
       errors = []

       # Check 1: pplx server
       resp = httpx.get("http://127.0.0.1:18099/health", timeout=3.0)
       if resp.status_code != 200:
           errors.append("pplx server not responding on :18099")

       # Check 2: memory-service health
       resp = httpx.get(f"{BASE}/../health", timeout=3.0)
       if resp.status_code != 200:
           errors.append("memory-service not healthy")

       # Check 3: council-recall works
       resp = httpx.post(f"{BASE}/council-recall", json={
           "query": "memory service", "max_tokens": 1024
       }, timeout=10.0)
       data = resp.json()
       if "channels" not in data:
           errors.append("council-recall missing channels")

       # Check 4: query_session_diary with FTS5
       resp = httpx.post(f"{BASE}/query_session_diary", json={
           "query": "CodeGraph", "limit": 3, "days_back": 14
       }, timeout=5.0)
       data = resp.json()
       if not data:
           errors.append("query_session_diary returned empty (FTS5 not working?)")

       # Check 5: memsearch_status
       resp = httpx.post(f"{BASE}/memsearch_status", json={}, timeout=5.0)
       data = resp.json()
       if not data.get("available"):
           errors.append("memsearch not available")

       # Check 6: reconcile_open_items
       resp = httpx.post(f"{BASE}/reconcile_open_items", json={"days_back": 14}, timeout=5.0)
       data = resp.json()
       if "items" not in data:
           errors.append("reconcile_open_items missing items")

       if errors:
           print("FAIL:")
           for e in errors:
               print(f"  - {e}")
       else:
           print("All checks passed!")
       return len(errors) == 0

   if __name__ == "__main__":
       import sys
       sys.exit(0 if verify() else 1)
   ```

3. **Run:** `python3 scripts/verify_recall.py`

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] pplx server responds on `:18099/v1/models`
- [ ] memory-service health check passes
- [ ] council-recall returns results with vector channel populated
- [ ] query_session_diary("CodeGraph") returns results (FTS5 working)
- [ ] query_session_diary("decisions") returns results (was 0 before FTS5)
- [ ] memsearch_status shows available + collection stats
- [ ] reconcile_open_items returns deduplicated items
- [ ] No ChromaDB ImportError in Odysseus
- [ ] All existing tests pass (no regression)

**Dependencies:** All previous phases.

---

## Constraints

- **pplx server on :18099** — Avoids conflict with memory-service SSE on :18097
- **FTS5 triggers** — Must sync on INSERT/UPDATE/DELETE. No manual re-index.
- **Milvus dynamic fields** — project_id stored as dynamic field, not schema column
- **Backward compat** — Existing memsearch API must still work during transition
- **No data loss** — Keep `pipelines.db` as backup until verification passes
- **WAL mode preserved** — No PRAGMA changes to journal_mode

---

## Success Criteria

- [ ] pplx-embed-v1 server running on `:18099` (systemd service, auto-restart)
- [ ] council-recall uses pplx embeddings (not bge-m3)
- [ ] FTS5 indexes exist on session_diary, artifacts, event_log
- [ ] query_session_diary uses FTS5 MATCH (not LIKE)
- [ ] council-recall Channel 3 uses FTS5 MATCH (not LIKE)
- [ ] Milvus indexes session_diary + consolidation_cache (not just chat summaries)
- [ ] project_id filter works in Milvus (server-side, not client-side)
- [ ] unified_log_recall completes in <2s (or gracefully degrades)
- [ ] ChromaDB imports removed from Odysseus (no crashes)
- [ ] `scripts/verify_recall.py` passes all checks
- [ ] All existing tests pass (no regression)

---

## Caveats & Uncertainty

- **pplx server.py port:** May need port change from 18097 → 18099. Verify before starting.
- **Memsearch HTTP client:** May need `embedding_provider="http"` support. Check MemSearch class.
- **FTS5 trigger sync:** Existing data needs seed INSERT after FTS5 table creation.
- **Milvus dynamic fields:** project_id stored as string. Empty string for unscoped entries.
- **Concurrent access:** memory-service restart = ~5s downtime. Plan accordingly.
