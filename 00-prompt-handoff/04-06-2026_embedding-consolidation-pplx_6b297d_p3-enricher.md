# Phase 3: Wire MicroModelEnricher into memory-service

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 3 of 6
**Dependencies:** None (independent of Phases 2, 4)
**Estimated effort:** ~30 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/memory_service/mcp_server.py` — MCP tool registration
- `super_council/memory_service/__main__.py` — Service startup
- `super_council/micro_model.py` — MicroModelEnricher class (already exists)

---

## What This Phase Delivers

MicroModelEnricher available as MCP tools in memory-service. `summarize_artifact` and `classify_failure` callable via MCP protocol. Model loaded directly via ONNX (not HTTP) for low-latency async enrichment.

---

## Pre-Flight Checklist

- [ ] micro_model.py exists: `ls super_council/micro_model.py`
- [ ] Model directory exists: `ls ~/models/embedding/pplx-embed-v1-0.6b-int8/model_quantized.onnx`
- [ ] memory-service is running

---

## Implementation Steps

### Step 1: Check current mcp_server.py

```bash
grep -n "enricher\|MicroModel\|summarize_artifact\|classify_failure" \
  super_council/memory_service/mcp_server.py
```

Note existing enrichment tool definitions (they may already exist but be disabled).

### Step 2: Add enricher parameter to MemoryServiceMCP

In `mcp_server.py`, find the `MemoryServiceMCP.__init__()` method. Add:

```python
def __init__(
    self,
    store: RelationalStore,
    # ... existing params ...
    enricher: Optional[Any] = None,  # NEW
):
    # ... existing init ...
    self._enricher = enricher  # NEW
```

### Step 3: Wire enrichment tools

In `mcp_server.py`, find where tools are registered. The tools may already exist (check lines ~764-792). Ensure they're registered:

```python
# summarize_artifact — requires MicroModelEnricher
if self._enricher is not None:
    self._tools["summarize_artifact"] = Tool(
        name="summarize_artifact",
        description="Generate summary for an artifact",
        inputSchema={"artifact_id": {"type": "string"}},
        handler=self._handle_summarize_artifact,
    )

# classify_failure — requires MicroModelEnricher
if self._enricher is not None:
    self._tools["classify_failure"] = Tool(
        name="classify_failure",
        description="Classify a failure using MicroModelEnricher",
        inputSchema={"run_id": {"type": "string"}, "error": {"type": "string"}},
        handler=self._handle_classify_failure,
    )
```

### Step 4: Initialize in __main__.py

In `__main__.py`, after RelationalStore is created, add:

```python
# MicroModelEnricher — async post-commit enrichment
enricher = None
try:
    from super_council.micro_model import MicroModelEnricher
    enricher = MicroModelEnricher(
        store,
        bonsai_url=config.get('bonsai_url'),  # Optional, for LLM summaries
    )
    log.info(
        "MicroModelEnricher initialized (model_available=%s)",
        enricher._model_available,
    )
except Exception as e:
    log.warning("MicroModelEnricher init failed (non-fatal): %s", e)
```

Then pass `enricher` to `MemoryServiceMCP(store, ..., enricher=enricher)`.

### Step 5: Restart and verify

```bash
systemctl --user restart memory-service.service
sleep 10
# Check logs for enricher init
journalctl --user -u memory-service.service --since "1 minute ago" | grep -i "micro\|enrich"
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/mcp_server.py` | Add enricher param + tools |
| Modify | `super_council/memory_service/__main__.py` | Initialize MicroModelEnricher |

---

## Phase-Specific Tests

1. **Enricher loaded:** Check logs for `MicroModelEnricher initialized (model_available=True)`
2. **classify_failure works:** Call via MCP with test error → get classification
3. **summarize_artifact works:** Call via MCP with existing artifact_id → get summary
4. **Model available:** `enricher._model_available == True`

---

## Completion Gate

- [ ] MicroModelEnricher initialized in memory-service
- [ ] model_available=True (pplx ONNX loaded)
- [ ] classify_failure tool works via MCP
- [ ] summarize_artifact tool works via MCP
- [ ] All phase-specific tests pass

---

## Notes for Next Phase

Phase 4 (Odysseus) is independent. Phase 5 (cleanup) blocks on Phases 2, 3, 4 all passing.
