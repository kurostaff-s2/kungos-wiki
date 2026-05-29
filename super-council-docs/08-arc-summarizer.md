# Arc Summarizer — Memory Consolidation on Intel Arc A380

> Consolidation, session summarization, and knowledge extraction routed to Granite-4.1-3B running on the Arc A380 via SYCL llama-server. Canonical path since 2026-05-28 migration.

## Architecture

```
+-------------------+     +----------------------+     +-------------------+
|  super_council.py |     |  arc_summarizer/     |     |  llama-server     |
|  (HTTP proxy)     |     |  (consolidation)     |     |  (Arc A380 SYCL)  |
|                   |     |                      |     |                   |
|  _run_startup_    |     |  ArcSummarizer       |     |  granite-4.1-3b   |
|  consolidation()  |---->|  .consolidate()      |---->|  :18095           |
|                   |     |  .summarize_session()|     |                   |
|  handler injects  |<----|  .extract_knowledge()|     |                   |
|  Tier 1 card      |     |  .health_check()     |     |                   |
+-------------------+     +----------------------+     +-------------------+
        |                          |
        v                          v
   RelationalStore          ArcPipeline.run_consolidation()
   (consolidation_cache)      → semantic-memory/
                              → consolidation_cache
                              → Tier 1 injection
```

## Module Structure

| File | Purpose |
|------|---------|
| `arc_summarizer/__init__.py` | `ArcSummarizer` facade — unified entry point |
| `arc_summarizer/config.py` | `ArcConfig` — loads from `config-subsystem.json["consolidation"]` |
| `arc_summarizer/client.py` | `ArcClient` — HTTP client with retry + fallback |
| `arc_summarizer/pipeline.py` | `ArcPipeline` — full consolidation pipeline |
| `arc_summarizer/prompts.py` | Prompt templates optimized for Granite-4.1-3B |
| `arc_summarizer/start.sh` | systemd wrapper — sources oneAPI, starts llama-server |

## Integration with super_council

### Initialization

```python
# In serve_forever():
self._init_arc_summarizer()  # loads ArcSummarizer with self.relational_store
```

`_init_arc_summarizer()` loads config from `config-subsystem.json["consolidation"]` and creates the `ArcSummarizer` instance with the `RelationalStore` for cache operations.

### consolidation_cache: Arc-Only Write Path

**Important:** `consolidation_cache` is written **only** by the Arc A380 pipeline (`ArcPipeline.run_consolidation()`). It stores structured YAML output from Granite-4.1-3B with provenance prefix `consol-*`.

**Session diary entries from the Pi extension hook** (`message_end` auto-detection) and the `memory.upsert_summary` tool write to the **separate** `session_diary` table (provenance prefix `sess-*`). This separation ensures:
- `consolidation_cache` = Arc A380 pipeline only (model-generated, probation/activation lifecycle)
- `session_diary` = mechanical upsert only (pattern-detected, no model, 14-day TTL, parses both `##` and `###` headers)

See `03-relational-layer.md` for full table separation details.

### Startup Consolidation Flow

```
serve_forever()
  → _init_arc_summarizer()           # load ArcSummarizer
  → health_check()                    # gate: skip if Arc unhealthy
  → thread: _run_startup_consolidation()
      → self._arc.consolidate()       # ArcPipeline.run_consolidation()
          → _gather_input_material()  # chat-summaries + daily logs
          → ArcClient.consolidate()   # POST to Arc server :18095
          → _write_semantic_file()    # ~/.council-memory/semantic-memory/
          → _write_to_cache()         # consolidation_cache table
          → _activate_latest()        # exit probation
          → _inject_tier1()           # query cache, format card
      → memory._auto_index_file()     # memsearch indexing
      → sync tier1 knowledge card     # for handler injection
```

### Tier 1 Injection

After consolidation completes, the Tier 1 knowledge card is synced from `self._arc.tier1_knowledge_card` to `self._tier1_knowledge_card`. The HTTP handler reads this on every request and injects it into the system message:

```python
# In handle_chat_completion():
tier1 = getattr(self, "_tier1_knowledge_card", None)
if tier1:
    payload = self._inject_tier1_into_payload(payload, tier1)
```

## Configuration

### config-subsystem.json

```json
{
  "consolidation": {
    "model": "granite-4.1-3b",
    "server_url": "http://127.0.0.1:18095",
    "timeout_seconds": 120,
    "max_retries": 3,
    "fallback_to_main": true,
    "roles": ["memory-consolidation", "session-summarization", "knowledge-extraction"]
  }
}
```

| Field | Purpose |
|-------|---------|
| `model` | Model alias on Arc server |
| `server_url` | Arc server endpoint |
| `timeout_seconds` | HTTP request timeout |
| `max_retries` | Retries on primary before fallback |
| `fallback_to_main` | Route to main upstream if Arc fails |
| `roles` | Capabilities this server handles |

### systemd Service

```
~/.config/systemd/user/arc-summarizer.service
```

- **ExecStart:** `arc_summarizer/start.sh` (sources oneAPI, starts llama-server)
- **Model:** `/home/chief/Coding-Projects/chief-s2s/models/granite-4.1-3b-Q4_K_M.gguf`
- **Port:** 18095
- **Memory limit:** 8G
- **Restart:** on-failure, 10s delay

## API

### ArcSummarizer (facade)

| Method | Purpose |
|--------|---------|
| `consolidate(input_material)` | Full consolidation pipeline (blocking) |
| `start_consolidation_thread()` | Background consolidation |
| `summarize_session(turns, max_tokens)` | Session summarization |
| `extract_knowledge(text, schema)` | Structured knowledge extraction |
| `inject_tier1()` | Tier 1 knowledge card injection |
| `health_check()` | Server health check |
| `tier1_knowledge_card` | Current Tier 1 card (property) |
| `last_output_path` | Last consolidation output file (property) |

### ArcClient (HTTP)

| Method | Purpose |
|--------|---------|
| `consolidate(input_material)` | POST consolidation prompt → YAML |
| `summarize_session(turns, max_tokens)` | POST session turns → summary |
| `extract_knowledge(text, schema)` | POST text + schema → parsed dict |
| `health_check()` | GET /v1/models → health status |

### ArcPipeline (orchestration)

| Method | Purpose |
|--------|---------|
| `run_consolidation()` | Full pipeline: gather → call → write → cache → activate → inject |
| `start_consolidation_thread()` | Background daemon thread |
| `inject_tier1()` | Query cache → format knowledge card |

## Health Gate

`serve_forever()` checks Arc server health before launching consolidation:

```python
if self._arc:
    health = self._arc.health_check()
    if health.get("healthy"):
        # launch consolidation thread
    else:
        log.warning("Arc server unhealthy, skipping consolidation")
```

## Migration Notes (2026-05-28)

Prior to migration, consolidation methods were inline in `super_council.py` (~600 lines). The migration:

1. **Stripped old methods** from `super_council.py`: `_do_startup_consolidation`, `_build_consolidation_prompt`, `_call_consolidation_model`, `_parse_consolidation_output`, `_write_consolidation_to_cache`, `_activate_latest_consolidation`, `_inject_tier1_startup_context`, and dead methods (`_call_session_summarizer`, `_call_knowledge_extraction`, `_call_summarizer`)
2. **Fixed wiring bug**: `self.store` (SlotStore) → `self.relational_store` (RelationalStore)
3. **Added health gate** before consolidation thread
4. **Added `last_output_path`** property for memsearch indexing
5. **Kept handler methods**: `_inject_tier1_into_payload` and `_injection_fail_silently` (used by HTTP handler)

## File Locations

| Resource | Path |
|----------|------|
| Module source | `~/Coding-Projects/7-council/super_council/arc_summarizer/` |
| Config | `~/Coding-Projects/7-council/super_council/config-subsystem.json` |
| systemd service | `~/.config/systemd/user/arc-summarizer.service` |
| Start script | `~/Coding-Projects/7-council/super_council/arc_summarizer/start.sh` |
| Model file | `~/Coding-Projects/chief-s2s/models/granite-4.1-3b-Q4_K_M.gguf` |
| Semantic memory | `~/.council-memory/semantic-memory/` |
| Chat summaries | `~/.council-memory/chat-summaries/` |
| Daily logs | `~/.council-memory/daily/` |
