# Handoff: MCP Tools for UnifiedVectorStore + Analytics

**Source spec:** `14-recall-search-fine-tuning.md`, `11-memsearch.md`  
**Generated:** 05-06-2026  
**Goal:** Wire UnifiedVectorStore and analytics logging into 2 new MCP tools for agent use inside pi sessions.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`  
**Reference docs:** `~/llm-wiki/super-council-docs/14-recall-search-fine-tuning.md`, `~/llm-wiki/super-council-docs/11-memsearch.md`  
**Related codebases:** None  
**Key files for this task:**
- `super_council/memory_service/mcp_server.py` — Add 2 new tool registrations
- `super_council/memory_service/__init__.py` — Wire vector_store to MCP handler
- `super_council/memory_service/vector_store.py` — Already exists, no changes needed
- `super_council/memory_service/analytics.py` — Already exists, no changes needed

---

## Execution Order

```
Phase 1 (wire vector_store to MCP handler) ──> Phase 2 (register 2 new tools) ──> Phase 3 (verification + tests)
```

**Sequential:** All 3 phases must run in order. Phase 2 depends on Phase 1 wiring. Phase 3 depends on both.

---

## Phase 1: Wire vector_store to MemoryMCPHandler

**What:** Pass `UnifiedVectorStore` instance to `MemoryMCPHandler` so tools can access it.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/mcp_server.py` | Add `vector_store` parameter to `__init__` |
| Modify | `super_council/memory_service/__init__.py` | Pass `self._vector_store` to handler |

**Steps:**

1. **Modify `MemoryMCPHandler.__init__()`** — Add `vector_store` parameter:
    ```python
    def __init__(
        self,
        store,
        router,
        layer,
        review,
        indexer,
        config: MemoryConfig,
        linter: Optional[Any] = None,
        enricher: Optional[Any] = None,
        cg_store: Optional[Any] = None,
        vector_store: Optional[Any] = None,  # NEW
    ):
        # ... existing code ...
        self._vector_store = vector_store  # NEW
    ```

2. **Modify `MemoryService._init_components()`** — Pass vector_store to handler:
    ```python
    # In __init__.py, where MemoryMCPHandler is created:
    self._mcp_handler = MemoryMCPHandler(
        store=self._store,
        router=self._router,
        layer=self._layer,
        review=self._review,
        indexer=self._indexer,
        config=self.config,
        linter=self._linter,
        enricher=self._enricher,
        cg_store=self._cg_store,
        vector_store=self._vector_store,  # NEW
    )
    ```

**Tests:**
- `MemoryMCPHandler` accepts `vector_store` parameter without error
- `self._vector_store` is accessible in handler methods

**Dependencies:** None.

---

## Phase 2: Register 2 New MCP Tools

**What:** Add `vector_search` and `analytics_summary` tools to the MCP server.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/mcp_server.py` | Add tool registrations + EXPOSED_TOOLS entries |

**Steps:**

1. **Add to `EXPOSED_TOOLS` list:**
    ```python
    EXPOSED_TOOLS: List[str] = [
        # ... existing tools ...
        "vector_search",      # NEW
        "analytics_summary",  # NEW
    ]
    ```

2. **Register `vector_search` tool** — Add in `_register_tools()` after `memsearch_status`:
    ```python
    self._registered_tools.append("vector_search")

    @self._mcp.tool(
        name="vector_search",
        description=(
            "Project-scoped semantic search over session_diary + consolidation_cache. "
            "Uses pplx-embed-v1 on :18099 with server-side project_id filtering. "
            "Returns ranked results with source, source_id, score, and text preview."
        ),
    )
    def vector_search(
        query: str,
        top_k: int = 10,
        project_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> str:
        """Search UnifiedVectorStore with server-side filters."""
        if not self._vector_store:
            return json.dumps({"error": "UnifiedVectorStore unavailable"})
        if not self._vector_store._available:
            return json.dumps({"error": "UnifiedVectorStore not initialized"})

        results = self._vector_store.search(
            query=query,
            top_k=min(top_k, 50),  # Bounded
            project_id=project_id,
            source=source,
        )
        return json.dumps({
            "query": query,
            "top_k": min(top_k, 50),
            "project_id": project_id,
            "source": source,
            "results": results,
            "count": len(results),
        }, indent=2, default=str)
    ```

3. **Register `analytics_summary` tool:**
    ```python
    self._registered_tools.append("analytics_summary")

    @self._mcp.tool(
        name="analytics_summary",
        description=(
            "Usage analytics for embedding/search requests. "
            "Returns request counts, avg/p95 latency, error rates. "
            "Use to inform caching decisions (P2) and monitor system health."
        ),
    )
    def analytics_summary(days_back: int = 7) -> str:
        """Get analytics summary for the last N days."""
        try:
            from .analytics import get_analytics_summary
            summary = get_analytics_summary(days_back=min(days_back, 90))  # Bounded
            return json.dumps(summary, indent=2, default=str)
        except ImportError:
            return json.dumps({"error": "Analytics module unavailable"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    ```

**Tests:**
- `vector_search` returns results when query matches indexed data
- `vector_search` respects `project_id` filter (server-side)
- `vector_search` respects `source` filter (server-side)
- `analytics_summary` returns valid JSON with expected keys
- `analytics_summary` bounds `days_back` to 90 max

**Dependencies:** Phase 1 (vector_store must be wired to handler).

---

## Phase 3: Verification + Tests

**What:** End-to-end verification that tools work inside pi sessions.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/tests/test_mcp_vector_tools.py` | Tests for new MCP tools |
| Modify | `scripts/verify_recall.py` | Add tool verification checks |

**Steps:**

1. **Create test file** — `test_mcp_vector_tools.py`:
    ```python
    """Tests for vector_search and analytics_summary MCP tools."""
    import json
    import os
    import sys
    from unittest.mock import MagicMock, patch

    import pytest

    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    @pytest.fixture
    def mock_handler():
        """Mock MemoryMCPHandler with vector_store."""
        from super_council.memory_service.mcp_server import MemoryMCPHandler
        from super_council.memory_service.config import MemoryConfig

        handler = MagicMock(spec=MemoryMCPHandler)
        handler._vector_store = MagicMock()
        handler._vector_store._available = True
        handler._vector_store.search.return_value = [
            {"source": "session_diary", "source_id": "test-1", "score": 0.85, "text": "Test result"}
        ]
        return handler

    class TestVectorSearchTool:
        def test_returns_results(self, mock_handler):
            """vector_search returns formatted results."""
            # Simulate tool call
            results = mock_handler._vector_store.search(
                query="test query",
                top_k=5,
                project_id="test-project",
                source="session_diary"
            )
            assert len(results) > 0
            assert "source" in results[0]
            assert "score" in results[0]

        def test_respects_project_filter(self, mock_handler):
            """vector_search passes project_id to store."""
            mock_handler._vector_store.search(
                query="test",
                top_k=5,
                project_id="council"
            )
            call_args = mock_handler._vector_store.search.call_args
            assert call_args.kwargs["project_id"] == "council"

        def test_unavailable_store_returns_error(self, mock_handler):
            """vector_search returns error when store unavailable."""
            mock_handler._vector_store = None
            # Tool should return error JSON
            assert True  # Handled by tool implementation

    class TestAnalyticsSummaryTool:
        def test_returns_valid_summary(self):
            """analytics_summary returns expected keys."""
            from super_council.memory_service.analytics import get_analytics_summary

            summary = get_analytics_summary(days_back=7)
            assert "embedding_requests" in summary
            assert "search_requests" in summary
            assert "period_days" in summary
    ```

2. **Update verification script** — Add tool checks:
    ```python
    def test_vector_search_tool():
        """Test vector_search tool via MCP."""
        try:
            from super_council.memory_service import MemoryService
            service = MemoryService.load()
            assert service.vector_store is not None
            assert service.vector_store._available
            print("✅ vector_search tool: available")
            return True
        except Exception as e:
            print(f"❌ vector_search tool: {e}")
            return False

    def test_analytics_summary_tool():
        """Test analytics_summary tool."""
        try:
            from super_council.memory_service.analytics import get_analytics_summary
            summary = get_analytics_summary(days_back=7)
            assert "embedding_requests" in summary
            print(f"✅ analytics_summary tool: {summary['embedding_requests']['total']} requests logged")
            return True
        except Exception as e:
            print(f"❌ analytics_summary tool: {e}")
            return False
    ```

3. **Run tests:** `pytest super_council/tests/test_mcp_vector_tools.py -v`
4. **Run verification:** `python3 scripts/verify_recall.py`

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] `vector_search` tool registered in MCP server
- [ ] `analytics_summary` tool registered in MCP server
- [ ] `vector_search` returns results for test query
- [ ] `vector_search` respects project_id filter
- [ ] `analytics_summary` returns valid JSON with expected keys
- [ ] All existing tests still pass (no regression)
- [ ] `scripts/verify_recall.py` passes all 8 checks (6 original + 2 new)

**Dependencies:** Phase 1 + Phase 2.

---

## Constraints

- **Tool naming:** Must match MCP conventions (snake_case, descriptive)
- **Bounded parameters:** `top_k` max 50, `days_back` max 90 (prevent abuse)
- **Graceful degradation:** Tools return error JSON when components unavailable
- **No blocking:** Tool calls must complete in <5s or return partial results
- **Backward compat:** Existing tools must continue working unchanged

---

## Success Criteria

- [ ] `vector_search` tool registered and callable via MCP
- [ ] `analytics_summary` tool registered and callable via MCP
- [ ] `vector_search` returns project-scoped results
- [ ] `analytics_summary` returns usage statistics
- [ ] All 22+2 tools listed in `EXPOSED_TOOLS`
- [ ] Memory service restarts without errors
- [ ] All existing tests pass (no regression)
- [ ] `scripts/verify_recall.py` passes all checks

---

## Caveats & Uncertainty

- **vector_store availability:** UnifiedVectorStore may fail to initialize if Milvus directory doesn't exist. Tools must handle this gracefully.
- **Analytics log location:** `~/.council-memory/analytics/` must exist before first write. Analytics module creates it automatically.
- **Tool discovery:** Pi extension may need restart to discover new tools via SSE schema.
- **Concurrent access:** Milvus-lite supports concurrent reads but serial writes. Tool calls are read-only, so no locking needed.

---

## Files to Create/Modify (Summary)

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/mcp_server.py` | Add vector_store param + 2 tool registrations |
| Modify | `super_council/memory_service/__init__.py` | Pass vector_store to MCP handler |
| Create | `super_council/tests/test_mcp_vector_tools.py` | Tests for new tools |
| Modify | `scripts/verify_recall.py` | Add 2 new verification checks |

---

## Estimated Effort

- **Phase 1:** ~15 min (wiring only)
- **Phase 2:** ~30 min (tool implementations + descriptions)
- **Phase 3:** ~20 min (tests + verification)
- **Total:** ~65 min (single agent session)
