# Arc Summarizer — Status Record (2026-05-28)

> **MIGRATION COMPLETE** — Arc summarizer is now the canonical consolidation path.
> Old methods stripped from `super_council.py` (597 lines removed).

## Server Status: ✅ RUNNING

| Field | Value |
|-------|-------|
| Service | `arc-summarizer.service` (user-level systemd) |
| PID | 78875 |
| Model | granite-4.1-3b-Q4_K_M.gguf (3.4B params, 2.0GB) |
| Host | 127.0.0.1:18095 |
| Runtime | llama-server SYCL (Intel Arc A380) |
| Memory | 1.3G peak / 8G limit |
| CPU | 9min 20s cumulative |
| Started | 2026-05-28 17:01:46 IST |
| Health | `/v1/models` returns granite-4.1-3b ✅ |

## Code State: ✅ MIGRATED — Arc Is Canonical

### Migration Log (2026-05-28)

**Changes applied:**

1. **Fixed wiring bug**: `_init_arc_summarizer` was passing `self.store` (SlotStore) instead of `self.relational_store` (RelationalStore) — ArcPipeline needs RelationalStore for cache operations
2. **Rewrote `_run_startup_consolidation`**: Now delegates to `self._arc.consolidate()` + memsearch indexing + Tier 1 sync
3. **Added health gate**: `serve_forever` checks `self._arc.health_check()` before launching consolidation thread
4. **Added `last_output_path`**: ArcPipeline tracks output file path for memsearch indexing
5. **Stripped 597 lines** of old consolidation methods from `super_council.py`

**Methods removed:**
- `_do_startup_consolidation()` — replaced by `ArcPipeline.run_consolidation()`
- `_build_consolidation_prompt()` — replaced by `prompts.build_consolidation_prompt()`
- `_load_consolidation_config()` — replaced by `ArcConfig.load()`
- `_call_consolidation_model()` — replaced by `ArcClient._call_with_fallback()`
- `_call_session_summarizer()` — replaced by `ArcClient.summarize_session()`
- `_call_knowledge_extraction()` — replaced by `ArcClient.extract_knowledge()`
- `_call_summarizer()` — legacy alias, removed
- `_parse_consolidation_output()` — replaced by `ArcClient._parse_yaml()`
- `_parse_yaml_fallback()` — replaced by `ArcClient._parse_yaml()`
- `_render_consolidation_yaml()` — replaced by `prompts.render_consolidation_yaml()`
- `_write_consolidation_to_cache()` — replaced by `ArcPipeline._write_to_cache()`
- `_activate_latest_consolidation()` — replaced by `ArcPipeline._activate_latest()`
- `_inject_tier1_startup_context()` — replaced by `ArcPipeline.inject_tier1()`

**Methods kept (used by handler):**
- `_injection_fail_silently()` — config check for handler
- `_inject_tier1_into_payload()` — injects knowledge card into HTTP payload

### What's Happening

`serve_forever()` (line 9600) does two things:

1. **Loads `self._arc`** via `_init_arc_summarizer()` (line 9590) — ArcSummarizer is fully initialized with config, client, and pipeline
2. **Launches old consolidation thread** — `threading.Thread(target=self._run_startup_consolidation)` (line 9636)

The thread target `_run_startup_consolidation` (line 8800) calls the **old methods exclusively**:
- `_do_startup_consolidation()` — gathers input, builds prompt, calls model, parses output
- `_activate_latest_consolidation()` — exits probation
- `_inject_tier1_startup_context()` — loads Tier 1 knowledge card

`self._arc` is **never used for consolidation**. The only reference is a log message at line 9595.

### Active Old Methods (Lines ~8800–9500)

| Method | Line | Called From | Status |
|--------|------|-------------|--------|
| `_run_startup_consolidation()` | 8800 | thread target @ 9636 | **ACTIVE** |
| `_do_startup_consolidation()` | 8835 | `_run_startup_consolidation` @ 8814 | **ACTIVE** |
| `_build_consolidation_prompt()` | 8937 | `_do_startup_consolidation` @ 8893 | **ACTIVE** |
| `_call_consolidation_model()` | 9009 | `_do_startup_consolidation` @ 8897 | **ACTIVE** |
| `_parse_consolidation_output()` | 9210 | `_do_startup_consolidation` @ 8904 | **ACTIVE** |
| `_parse_yaml_fallback()` | 9228 | `_parse_consolidation_output` @ 9223 | **ACTIVE** |
| `_render_consolidation_yaml()` | 9289 | `_do_startup_consolidation` @ 8921 | **ACTIVE** |
| `_write_consolidation_to_cache()` | 9317 | `_do_startup_consolidation` @ 8927 | **ACTIVE** |
| `_activate_latest_consolidation()` | 9456 | `_run_startup_consolidation` @ 8818 | **ACTIVE** |
| `_inject_tier1_startup_context()` | 9470 | `_run_startup_consolidation` @ 8824 | **ACTIVE** |
| `_load_consolidation_config()` | 8984 | old methods @ 9018,9096,9160 | **ACTIVE** |

### Dormant New Code (arc_summarizer module)

| Method | File | Why Dormant |
|--------|------|-------------|
| `ArcSummarizer.consolidate()` | `__init__.py` | Never called |
| `ArcSummarizer.start_consolidation_thread()` | `__init__.py` | Never called |
| `ArcSummarizer.summarize_session()` | `__init__.py` | Never called |
| `ArcSummarizer.extract_knowledge()` | `__init__.py` | Never called |
| `ArcSummarizer.inject_tier1()` | `__init__.py` | Never called |
| `ArcPipeline.run_consolidation()` | `pipeline.py` | Never called |
| `ArcPipeline._gather_input_material()` | `pipeline.py` | Duplicated in old code |
| `ArcPipeline._write_to_cache()` | `pipeline.py` | Old method is active |
| `ArcPipeline._activate_latest()` | `pipeline.py` | Old method is active |
| `ArcPipeline._inject_tier1()` | `pipeline.py` | Old method is active |
| `ArcClient.consolidate()` | `client.py` | Never called |
| `ArcClient.summarize_session()` | `client.py` | Never called |
| `ArcClient.extract_knowledge()` | `client.py` | Never called |

### Truly Dead Old Methods (never called from anywhere)

| Method | Line | Reason |
|--------|------|--------|
| `_call_session_summarizer()` | 9083 | No callers |
| `_call_knowledge_extraction()` | 9148 | No callers |
| `_call_summarizer()` | 9206 | Alias, no callers |

### Methods to KEEP (used outside consolidation)

| Method | Line | Used By |
|--------|------|---------|
| `_inject_tier1_into_payload()` | 9380 | `handle_chat_completion` @ 7064 |
| `_injection_fail_silently()` | 9370 | handler @ 7066 |

## Migration Plan: Make Arc Canonical

### Phase 1: Wire `self._arc` into `serve_forever`

Replace the old thread target with Arc delegation:

```python
# OLD (line 9634-9640):
consolidation_thread = threading.Thread(
    target=self._run_startup_consolidation,
    name="startup-consolidation",
    daemon=True,
)
consolidation_thread.start()

# NEW:
if self._arc:
    self._arc.start_consolidation_thread()
else:
    log.warning("Arc unavailable, skipping startup consolidation")
```

### Phase 2: Strip Old Methods

Remove these ~700 lines from `super_council.py`:
- `_run_startup_consolidation()` (8800–8833)
- `_do_startup_consolidation()` (8835–8935)
- `_build_consolidation_prompt()` (8937–8982)
- `_load_consolidation_config()` (8984–9016)
- `_call_consolidation_model()` (9009–9081)
- `_call_session_summarizer()` (9083–9146)
- `_call_knowledge_extraction()` (9148–9208)
- `_call_summarizer()` (9206–9208) — legacy alias
- `_parse_consolidation_output()` (9210–9227)
- `_parse_yaml_fallback()` (9228–9287)
- `_render_consolidation_yaml()` (9289–9315)
- `_write_consolidation_to_cache()` (9317–9417)
- `_injection_fail_silently()` (9419–9428) — move to arc module or keep
- `_inject_tier1_into_payload()` (9430–9454) — KEEP, used by handler
- `_activate_latest_consolidation()` (9456–9468)
- `_inject_tier1_startup_context()` (9470–9578)

### Phase 3: Wire Tier 1 from Arc

After `self._arc.start_consolidation_thread()`, Tier 1 injection happens automatically via `ArcPipeline._inject_tier1()`. The result is available at `self._arc.tier1_knowledge_card`.

Add post-consolidation hook or poll `self._arc.tier1_knowledge_card` to populate `self._tier1_knowledge_card`.

### Phase 4: Health Gate (P3 fix)

```python
if self._arc and self._arc.health_check().get("healthy"):
    self._arc.start_consolidation_thread()
else:
    log.warning("Arc server unhealthy, skipping startup consolidation")
```

### Phase 5: Race Condition Fix (P0 fix)

Add `threading.Event` gate so HTTP server waits for Tier 1:

```python
self._tier1_ready = threading.Event()
# In consolidation callback:
self._tier1_ready.set()
# In serve_forever, before HTTP server:
self._tier1_ready.wait(timeout=30)
```

## Gap Analysis

| Item | Arc Module Has It? | Old Code Has It? | Action |
|------|-------------------|------------------|--------|
| Input material gathering | ✅ `ArcPipeline._gather_input_material()` | ✅ `_do_startup_consolidation()` | Arc version is canonical |
| Prompt building | ✅ `prompts.build_consolidation_prompt()` | ✅ `_build_consolidation_prompt()` | Arc version is canonical |
| Model calling with retry | ✅ `ArcClient._call_with_fallback()` | ✅ `_call_consolidation_model()` | Arc version has better retry |
| YAML parsing | ✅ `ArcClient._parse_yaml()` | ✅ `_parse_consolidation_output()` | Arc version is canonical |
| Cache writing | ✅ `ArcPipeline._write_to_cache()` | ✅ `_write_consolidation_to_cache()` | Arc version is canonical |
| Cache activation | ✅ `ArcPipeline._activate_latest()` | ✅ `_activate_latest_consolidation()` | Arc version is canonical |
| Tier 1 injection | ✅ `ArcPipeline.inject_tier1()` | ✅ `_inject_tier1_startup_context()` | Arc version is canonical |
| Session summarization | ✅ `ArcClient.summarize_session()` | ✅ `_call_session_summarizer()` (dead) | Arc version is canonical |
| Knowledge extraction | ✅ `ArcClient.extract_knowledge()` | ✅ `_call_knowledge_extraction()` (dead) | Arc version is canonical |
| Health check | ✅ `ArcClient.health_check()` | ❌ None | Arc-only capability |
| Tier 1 payload injection | ❌ (not needed) | ✅ `_inject_tier1_into_payload()` | KEEP in super_council.py |

## Conclusion

The Arc summarizer server is running and healthy. The `arc_summarizer` module is complete and covers every capability the old code provides. The migration is a straightforward delegation swap: replace `self._run_startup_consolidation` with `self._arc.start_consolidation_thread()` and strip ~700 lines of old methods from `super_council.py`.
