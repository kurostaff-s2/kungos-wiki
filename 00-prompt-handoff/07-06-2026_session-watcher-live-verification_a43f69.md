# Session Watcher — Runtime Event Verification

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `a43f69` |
| Entity type | `session` |
| Short description | Trigger real runtime events through production paths and verify actual behavior in logs, database, and file system — no test scripts |
| Status | `draft` |
| Source references | `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`, `memory_service/session_watcher.py` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — trigger real events, observe actual runtime behavior |

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
4. **Summaries → reconciliation** → wired in ArcPipeline
5. **SessionWatcher** → watches Pi JSONL sessions, parses, classifies, trims, feeds into reconciliation

**What needs verification:** Trigger real events through production paths and observe actual runtime behavior. No test scripts, no mocks — just real production interaction.

## Approach: Observe, Don't Test

**Do NOT run pytest or test scripts.** The 118 tests already pass. Instead:

1. **Trigger real events** through actual production HTTP endpoints
2. **Observe actual behavior** in logs, database state, and file system changes
3. **Verify the chain works** with real data flowing through real paths
4. **Measure actual latency** from real requests, not synthetic benchmarks

## Pre-Flight Checklist

- [ ] Supervisor process is running (check `curl http://127.0.0.1:8090/v1/council/status` or equivalent)
- [ ] MemoryService database is accessible at `~/.council-memory/council_core.db`
- [ ] Pi session JSONL files exist in `~/.pi/agent/sessions/`
- [ ] Recent supervisor logs are available (check `~/.council-memory/supervisor-logs/` or journal)

## Task: Runtime Event Verification

### Step 1: Baseline — Capture Pre-Event State

Record the system state before triggering any events:

```bash
# Database state: count existing work items and diary entries
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) FROM work_items;"
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) FROM session_diary;"
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) FROM memory_entries;"

# File system state: note latest chat summary and diary files
ls -lt ~/.council-memory/chat-summaries/ | head -3
ls -lt ~/.council-memory/daily/ | head -3

# Process state: check supervisor is running
ps aux | grep super_council | grep -v grep

# Log state: note current log position
tail -5 ~/.council-memory/supervisor-logs/*.log 2>/dev/null || journalctl -u council-supervisor --no-pager -n 5 2>/dev/null
```

### Step 2: Trigger Real Chat Completion → Observe Activity Tracking

Send a real chat completion through the production endpoint and verify activity/tokens are pushed to the scheduler:

```bash
# Send a real chat completion (use any model available)
curl -s -X POST http://127.0.0.1:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [
      {"role": "user", "content": "What files were modified in the session summarization wiring task?"}
    ],
    "max_tokens": 256
  }' | python3 -m json.tool | head -20

# Immediately check: did the log show activity tracking?
# Look for: "scheduler._record_activity" or "_add_tokens" in logs
grep -i "record_activity\|add_tokens\|_last_activity" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5

# Alternative: check the health endpoint for live scheduler state
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -m json.tool 2>/dev/null | grep -A5 "adaptive_triggers\|event_hints"
```

**Expected evidence:** Log lines showing `_record_activity()` and `_add_tokens()` called after the request. Health check showing `last_activity_age_seconds` < 60.

### Step 3: Trigger Real Session Summary → Observe Analyzer + Event Hint

Trigger a real session summary and verify the analyzer runs before summarization, and the event hint wakes the scheduler:

```bash
# Trigger real session summary through production endpoint
curl -s -X POST http://127.0.0.1:8090/v1/council/summarize \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool | head -20

# Check logs for: analyzer classification, event hint wake
grep -i "SessionAnalyzer\|session_mode\|session analyzed\|_wake\|event_hint\|daily_summary_saved" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -10

# Check if a new diary entry was created
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) FROM session_diary ORDER BY created_at DESC LIMIT 1;"

# Check if a new chat summary file was created
ls -lt ~/.council-memory/chat-summaries/ | head -3
```

**Expected evidence:**
- Log line: `Session analyzed: mode=code scores={...}`
- Log line: `_wake_scheduler("daily_summary_saved")` or `_handle_event_hint`
- New row in `session_diary` table
- New file in `chat-summaries/` directory

### Step 4: Trigger Real Chat Summary → Observe Full Chain

Trigger a real chat summary (the Pi /quit hook path) and verify the full chain:

```bash
# Trigger real chat summary through production endpoint
# This exercises the _summarize_chat() path with analyzer + event hint
curl -s -X POST http://127.0.0.1:8090/v1/council/summarize-chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Check the session watcher implementation"},
      {"role": "assistant", "content": "The SessionWatcher is in memory_service/session_watcher.py. It parses JSONL, classifies sessions, and feeds trimmed summaries into reconciliation."}
    ]
  }' | python3 -m json.tool | head -30

# Check logs for full chain: analyze → summarize → save → upsert → wake
grep -i "summarize\|chat_summary\|upsert_session_diary\|_wake_scheduler\|chat_summary_saved" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -10

# Verify new diary entry
sqlite3 ~/.council-memory/council_core.db "SELECT id, source, length(summary_text) as len FROM session_diary ORDER BY created_at DESC LIMIT 3;"
```

**Expected evidence:**
- Log: `Session analyzed: mode=code` (analyzer ran before summarization)
- Log: `CHAT SUMMARY: saved to /path/...` (summary saved)
- Log: `_wake_scheduler("chat_summary_saved")` (event hint fired)
- Log: `upsert_session_diary` → `_wake_scheduler("daily_summary_saved")` (chain continued)
- New row in `session_diary` with the summary content

### Step 5: Observe SessionWatcher Processing Real JSONL

The SessionWatcher runs as a background daemon. Verify it's processing real sessions:

```bash
# Check if the session watcher thread is running
ps aux | grep -i "session.watcher\|session-watcher" | grep -v grep

# Check logs for session watcher activity
grep -i "SessionWatcher\|session.*watcher\|processing.*jsonl\|parsed.*turns\|classified as" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -20

# Check database for any work items created from session processing
sqlite3 ~/.council-memory/council_core.db "SELECT id, title, kind, first_seen_run_id FROM work_items ORDER BY created_at DESC LIMIT 5;"

# Check if reconciliation ran (look for reconcile_tasks in logs)
grep -i "reconcile\|reconciliation\|arc_delta\|task.*reconcil" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -10
```

**Expected evidence:**
- Log: `SessionWatcher started (JSONL → trim → reconcile active)`
- Log: `SessionWatcher: processing <filename> (N messages, X.XKB)`
- Log: `SessionWatcher: classified as <mode>`
- Log: `SessionWatcher: completed <filename> (mode=X, N signals)`
- New work_items in database from session processing

### Step 6: Verify Health Check Reports Live State

Check the health endpoint and verify it reports actual live state, not just capability:

```bash
# Get full health check response
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -m json.tool

# Specifically check: live_mode, live_scores, last_activity_age, current_token_count, thread_alive
# These should have real values, not static strings like "wired"
```

**Expected evidence:**
- `live_mode`: actual mode string (e.g., "code"), not "unavailable"
- `live_scores`: actual score dict from real classification
- `last_activity_age_seconds`: real number (seconds since last activity)
- `current_token_count`: actual accumulated token count
- `thread_alive`: true (scheduler thread running)
- `last_wake_age_seconds`: real number (seconds since last wake)

### Step 7: Verify Reconciliation Wrote Canonical Records

Check the database for actual reconciliation output:

```bash
# Check work_items for entries from session processing
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, title, kind, status, first_seen_run_id, source_summary_id
  FROM work_items
  ORDER BY created_at DESC
  LIMIT 10;
"

# Check session_diary for entries from session processing
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, source, length(summary_text) as text_len, created_at
  FROM session_diary
  ORDER BY created_at DESC
  LIMIT 5;
"

# Check memory_entries for consolidation entries
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, entry_type, tier, title, source
  FROM memory_entries
  ORDER BY created_at DESC
  LIMIT 5;
"
```

**Expected evidence:**
- Work items with `source_summary_id` pointing to session files
- Session diary entries with summaries from real sessions
- Memory entries with `entry_type='diary'` from consolidation

## Success Criteria

- [ ] Real chat completion triggered → activity tracking visible in logs
- [ ] Real session summary triggered → analyzer classification visible in logs
- [ ] Real chat summary triggered → full chain visible (analyze → save → upsert → wake)
- [ ] SessionWatcher processing real JSONL → log evidence of parse/classify/trim
- [ ] Health check reports live values (not static "wired" strings)
- [ ] Database has new records from real event processing (work_items, session_diary)
- [ ] No errors in supervisor logs during event triggering
- [ ] JSONL files remain unmodified (read-only verification)

## Evidence Collection Template

For each event triggered, record:

```markdown
### Event: [event name]
**Trigger:** [command/endpoint used]
**Timestamp:** [when it was triggered]

**Log Evidence:**
```
[paste relevant log lines]
```

**Database Evidence:**
```
[sqlite3 query output showing new/changed records]
```

**File System Evidence:**
```
[ls output showing new files]
```

**Verdict:** PASS / FAIL — [reason]
```

## Constraints

- **No test scripts:** Use real HTTP endpoints and observe real logs/database/files
- **Read-only on JSONL:** Never modify Pi's session files
- **Non-destructive:** Do not delete or modify existing database records
- **Use real endpoints:** Hit the actual production supervisor, not mocked versions

## Deliverables

Save a runtime verification report to:
```
/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_runtime-event-verification-report_[hash].md
```

Include:
1. **Pre-event baseline** — database counts, file listing, process state
2. **Event-by-event evidence** — logs, database changes, file changes for each triggered event
3. **Health check output** — full JSON response with live values highlighted
4. **Database diff** — new records created during verification
5. **Issues found** — any gaps, missing log lines, unexpected behavior
6. **Pass/fail summary** — each of the 5 wiring points verified or not
