# Session Watcher Live Verification & Performance Analysis

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `a43f69` |
| Entity type | `session` |
| Short description | Verify SessionWatcher end-to-end performance by processing this session's Pi JSONL and measuring actual runtime behavior |
| Status | `draft` |
| Source references | `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`, `memory_service/session_watcher.py` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — run live verification against current session JSONL |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Related codebases:** `/home/chief/.pi/agent/sessions/` (Pi session JSONL source)
**Key files for this task:**
- `memory_service/session_watcher.py` — SessionWatcher (JSONL → trim → reconcile)
- `arc_summarizer/analyzer.py` — SessionAnalyzer (classify + trim)
- `arc_summarizer/__init__.py` — ArcSummarizer (analyzer wiring)
- `memory_service/__init__.py` — MemoryService (event hints, health check)
- `super_council.py` — production wiring (activity tracking, event hints)

## Background

**What was built:** Production wiring for session summarization and flexible reconciliation. Five components wired:

1. **SessionAnalyzer** → called before every summarization (mode-aware prompts)
2. **Activity/token tracking** → pushed into scheduler on each chat completion
3. **Event hints** → scheduler wakes on diary/chat summary saves
4. **Summaries → reconciliation** → already wired in ArcPipeline
5. **SessionWatcher** → new component that watches Pi JSONL sessions, parses them, classifies, trims, and feeds into reconciliation

**What needs verification:** The next agent should process **this session's JSONL file** through the full pipeline and measure actual performance, not just run unit tests.

## Pre-Flight Checklist

- [ ] SessionWatcher code is merged/available in `memory_service/session_watcher.py`
- [ ] All 118 tests pass (baseline: no regressions)
- [ ] Pi session JSONL files exist in `~/.pi/agent/sessions/`
- [ ] MemoryService can be loaded (database accessible)

## Task: Live Runtime Verification

### Step 1: Identify This Session's JSONL

```bash
# Find the latest session (should be this session)
ls -lt ~/.pi/agent/sessions/--home-chief--/*.jsonl | head -3
```

The target file should be the most recent JSONL, likely matching today's date (2026-06-07). Verify it contains the conversation about production wiring (search for "SessionWatcher" or "session_watcher" in the file).

### Step 2: Process Through Full Pipeline

Run the SessionWatcher against the target JSONL and capture all metrics:

```python
import time
import json
from pathlib import Path
from super_council.memory_service.session_watcher import SessionWatcher

jsonl_path = Path("/path/to/target/session.jsonl")
watcher = SessionWatcher()

# Measure full pipeline
start = time.monotonic()

# Step A: Parse
parse_start = time.monotonic()
turns = watcher._parse_jsonl(jsonl_path)
parse_ms = (time.monotonic() - parse_start) * 1000

# Step B: Classify
classify_start = time.monotonic()
mode = watcher._classify(turns)
classify_ms = (time.monotonic() - classify_start) * 1000

# Step C: Trim
trim_start = time.monotonic()
trimmed = watcher._trim_session(turns, mode, jsonl_path)
trim_ms = (time.monotonic() - trim_start) * 1000

# Step D: Reconciliation text
recon_start = time.monotonic()
recon_text = watcher._trimmed_to_text(trimmed)
recon_ms = (time.monotonic() - recon_start) * 1000

total_ms = (time.monotonic() - start) * 1000

# Report
signals = watcher._count_signals(trimmed)
print(f"""
=== Performance Report ===
File: {jsonl_path.name}
Size: {jsonl_path.stat().st_size / 1024:.1f} KB
Messages: {len(turns)}

--- Timing ---
Parse:     {parse_ms:.1f}ms
Classify:  {classify_ms:.1f}ms
Trim:      {trim_ms:.1f}ms
Reconcile: {recon_ms:.1f}ms
Total:     {total_ms:.1f}ms

--- Output ---
Mode: {mode}
Signals: {signals}
Recon text: {len(recon_text)} chars
""")
```

### Step 3: Verify Design Expectations

Compare actual output against the design spec's expectations:

| Design Expectation | Verification Check |
|---|---|
| Raw JSONL stays as source of truth (read-only) | Confirm JSONL file is unmodified after processing |
| Trimmed summary has 12-field schema | Assert all 12 fields present in `trimmed` dict |
| Session mode detected correctly | Verify mode matches session content (this session = code/planning mix) |
| Task-bearing signals preserved | Count signals > 0, verify files/functions/decisions detected |
| ARC receives trimmed summary (not raw) | Verify `recon_text` is structured, not raw JSONL dump |
| Reconciliation writes canonical records | Verify `reconcile_tasks()` is called with trimmed input |

### Step 4: Verify Production Wiring Points

Check each of the 5 wired components is actually callable from production paths:

```python
# 1. Analyzer wired into ArcSummarizer
from super_council.arc_summarizer import ArcSummarizer, ArcConfig
# Verify summarize_session() calls analyzer (check source or add debug log)

# 2. Activity tracking wired into handle_chat_completion
# Check super_council.py for scheduler._record_activity() call

# 3. Event hints wired into memory service
# Check memory_service/__init__.py for _wake_scheduler() calls

# 4. Summaries flow into reconciliation
# Check ArcPipeline.run_tiered_consolidation() calls reconcile_tasks()

# 5. Health check reports live state
from super_council.memory_service import MemoryService
ms = MemoryService.load()
health = ms.health_check()
# Verify: live_mode, live_scores, last_activity_age_seconds, current_token_count
```

### Step 5: Process Multiple Sessions

Process at least 3 recent sessions to verify consistency:

```python
sessions_dir = Path("~/.pi/agent/sessions/--home-chief--").expanduser()
jsonl_files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

results = []
for jsonl in jsonl_files:
    watcher = SessionWatcher()
    turns = watcher._parse_jsonl(jsonl)
    if len(turns) < 2:
        continue
    mode = watcher._classify(turns)
    trimmed = watcher._trim_session(turns, mode, jsonl)
    signals = watcher._count_signals(trimmed)
    results.append({
        "file": jsonl.name,
        "size_kb": jsonl.stat().st_size / 1024,
        "messages": len(turns),
        "mode": mode,
        "signals": signals,
    })

# Report distribution
print(f"Processed {len(results)} sessions:")
for r in results:
    print(f"  {r['mode']:10s} | {r['messages']:3d} msgs | {r['signals']:2d} signals | {r['size_kb']:6.1f}KB")
```

### Step 6: Verify Scheduler Integration

Confirm the scheduler receives event hints and reacts:

```python
from super_council.memory_service import MemoryService
ms = MemoryService.load()

# Check scheduler state
scheduler = ms.scheduler
if scheduler:
    print(f"Scheduler thread alive: {scheduler._thread.is_alive()}")
    print(f"Last activity age: {time.time() - scheduler._last_activity:.1f}s")
    print(f"Token count: {scheduler._get_token_count()}")
    print(f"Event score: {scheduler._get_event_score()}")
    print(f"Wake cooldown: {scheduler._wake_cooldown}")
else:
    print("Scheduler: unavailable")

# Check session watcher
watcher = ms.session_watcher
if watcher:
    print(f"SessionWatcher running: {watcher._running}")
    print(f"SessionWatcher stats: {watcher.stats()}")
else:
    print("SessionWatcher: unavailable")
```

## Success Criteria

- [ ] Target JSONL identified and contains this session's conversation
- [ ] Full pipeline timing captured (parse, classify, trim, reconcile)
- [ ] Total pipeline time < 5 seconds for sessions under 1MB
- [ ] Session mode correctly detected (this session should be `code` or `mixed`)
- [ ] At least 5 task-bearing signals extracted from this session
- [ ] Trimmed summary contains all 12 schema fields
- [ ] Reconciliation text is structured (not raw JSONL dump)
- [ ] All 5 production wiring points verified callable
- [ ] Health check reports live state (not just capability presence)
- [ ] At least 3 sessions processed with consistent results
- [ ] Scheduler thread alive and responsive
- [ ] SessionWatcher running and tracking processed files
- [ ] No regressions in existing 118 tests

## Expected Outcomes

### This Session's Profile

Based on the conversation content (production wiring discussion, code changes, test results):

- **Expected mode:** `code` or `mixed` (heavy code references + planning signals)
- **Expected signals:** 15-30 (file paths, function names, decisions, completed work)
- **Expected files detected:** `session_watcher.py`, `analyzer.py`, `__init__.py`, `super_council.py`, `scheduler.py`
- **Expected decisions:** analyzer wiring, event hint wiring, health check enhancement

### Performance Baselines

| Operation | Expected Range | Notes |
|-----------|----------------|-------|
| Parse (100 msgs) | 10-50ms | JSON parsing, text extraction |
| Classify | 5-20ms | Regex signal counting |
| Trim | 10-30ms | Pattern matching on raw text |
| Reconcile text build | <1ms | Dict → string formatting |
| Total pipeline | <100ms | For sessions under 100 messages |

## Deliverables

Produce a verification report with:

1. **Performance numbers** — actual timing for each pipeline stage
2. **Signal quality** — what was detected, what was missed, false positives
3. **Mode accuracy** — was the session classified correctly? Why/why not?
4. **Wiring verification** — pass/fail for each of the 5 production points
5. **Health check output** — actual live health check response
6. **Multi-session consistency** — mode distribution, signal counts across 3+ sessions
7. **Issues found** — any gaps, bugs, or performance problems discovered

Save the report to:
```
/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_session-watcher-verification-report_[hash].md
```

## Constraints

- **Read-only on JSONL:** Never modify Pi's session files
- **Non-blocking:** Pipeline must complete in <5 seconds for sessions under 1MB
- **Graceful degradation:** Missing components (pipeline, scheduler) should not crash the watcher
- **Idempotent:** Processing the same JSONL twice should produce the same trimmed output
- **No model calls for classification:** SessionAnalyzer uses regex/heuristics only (no LLM)

## Caveats & Uncertainty

1. **Session content varies widely:** Code sessions have clear signals; research/planning sessions may produce lower signal counts. This is expected — the 12-field schema handles sparse signals.

2. **Thinking blocks included:** Pi sessions include `[thinking]` content. This adds noise but also contains useful signals (decisions, analysis). The classifier should handle this correctly.

3. **Tool results are nested:** Tool output appears as nested content blocks. The `_extract_text()` method handles recursion, but deeply nested structures may lose some context.

4. **Reconciliation needs live database:** Full reconciliation verification requires the MemoryService with a live RelationalStore. If unavailable, verify the pipeline calls are made (mock the store).

5. **Scheduler state is ephemeral:** Token counts and event scores reset after summarization fires. The health check shows point-in-time state, not historical totals.
