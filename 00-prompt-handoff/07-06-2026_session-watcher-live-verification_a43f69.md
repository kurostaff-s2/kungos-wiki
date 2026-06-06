# Session Watcher — End-to-End Runtime Verification

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `a43f69` |
| Entity type | `session` |
| Short description | Trigger real runtime events through production paths and verify the COMPLETE pipeline chain end-to-end — from event trigger through final database record |
| Status | `draft` |
| Source references | `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`, `memory_service/session_watcher.py` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — trigger real events, verify complete pipeline chains |

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

**What needs verification:** Trigger real events and verify the **complete pipeline chain** end-to-end. Not individual parts — the full chain from trigger through final database record.

## Pipeline Chains To Verify

Three complete chains must be tested end-to-end:

```
Chain A: Chat Completion → Activity Tracking → Scheduler State
  curl /chat/completions → _record_activity() → _add_tokens() → health check shows live state

Chain B: Session Summary → Analyzer → Summarize → Save → Upsert → Event Hint → Scheduler Wake → Reconciliation → DB Records
  curl /summarize → SessionAnalyzer.classify() → mode-aware prompt → summary saved →
  upsert_session_diary() → _wake_scheduler("daily_summary_saved") → scheduler._handle_event_hint() →
  reconcile_tasks() → new work_items in DB

Chain C: SessionWatcher → JSONL Detection → Parse → Classify → Trim → Reconcile → DB Records
  (background daemon) new JSONL detected → _parse_jsonl() → _classify() → _trim_session() →
  _reconcile() → new work_items in DB
```

**Each chain must be verified from trigger to final observable result. Partial verification is insufficient.**

## Pre-Flight Checklist

- [ ] Supervisor process is running
- [ ] MemoryService database accessible at `~/.council-memory/council_core.db`
- [ ] Pi session JSONL files exist in `~/.pi/agent/sessions/`
- [ ] Supervisor logs accessible (check `~/.council-memory/supervisor-logs/` or systemd journal)

---

## Chain A: Chat Completion → Activity Tracking → Scheduler State

**Complete chain:** Real chat request → activity recorded → tokens tracked → scheduler state updated → health check reflects it.

### Step A1: Capture Baseline

```bash
# Record scheduler state BEFORE the request
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
at = h.get('adaptive_triggers', {})
print('BEFORE request:')
print(f'  last_activity_age: {at.get(\"last_activity_age_seconds\", \"missing\")}')
print(f'  token_count: {at.get(\"current_token_count\", \"missing\")}')
print(f'  thread_alive: {at.get(\"thread_alive\", \"missing\")}')
"
```

### Step A2: Trigger Real Chat Completion

```bash
# Send real chat completion through production endpoint
curl -s -X POST http://127.0.0.1:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "List the files modified in the session summarization wiring task"}],
    "max_tokens": 256
  }' > /tmp/chat_response.json

echo "Response status: $(python3 -c "import json; d=json.load(open('/tmp/chat_response.json')); print('OK' if 'choices' in d else 'FAIL')" 2>/dev/null)"
```

### Step A3: Verify Activity Tracking in Logs

```bash
# Find log lines showing activity was recorded AFTER the request
grep -i "_record_activity\|_add_tokens\|last_activity" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5
```

### Step A4: Verify Scheduler State Changed

```bash
# Check scheduler state AFTER the request
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
at = h.get('adaptive_triggers', {})
print('AFTER request:')
print(f'  last_activity_age: {at.get(\"last_activity_age_seconds\", \"missing\")}')
print(f'  token_count: {at.get(\"current_token_count\", \"missing\")}')
print(f'  thread_alive: {at.get(\"thread_alive\", \"missing\")}')
print(f'  event_score: {at.get(\"current_event_score\", \"missing\")}')
"
```

### Chain A Success Criteria

- [ ] Health check BEFORE shows baseline values
- [ ] Chat completion returns 200 with content
- [ ] Log shows `_record_activity()` called
- [ ] Health check AFTER shows `last_activity_age_seconds` < 5 (freshly updated)
- [ ] Health check AFTER shows `current_token_count` > 0 (tokens accumulated)
- [ ] `thread_alive` = true

---

## Chain B: Session Summary → Analyzer → Summarize → Save → Upsert → Event Hint → Scheduler Wake → Reconciliation → DB Records

**Complete chain:** Real summary request → analyzer classifies session → mode-aware summarization → summary saved to file → diary upserted → event hint fires → scheduler wakes → reconciliation runs → new DB records created.

### Step B1: Capture Baseline

```bash
# Record DB state BEFORE
echo "=== BEFORE summary ==="
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as diary_count FROM session_diary;"
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as work_item_count FROM work_items;"
ls -lt ~/.council-memory/chat-summaries/ | head -2
```

### Step B2: Trigger Real Session Summary

```bash
# Trigger real session summary through production endpoint
curl -s -X POST http://127.0.0.1:8090/v1/council/summarize \
  -H "Content-Type: application/json" \
  -d '{}' > /tmp/summarize_response.json

echo "Response: $(cat /tmp/summarize_response.json | python3 -m json.tool 2>/dev/null | head -5)"
```

### Step B3: Verify Analyzer Ran (Log Evidence)

```bash
# The analyzer MUST run before summarization — verify in logs
grep -i "SessionAnalyzer\|session analyzed\|session_mode\|scores=" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5
```

### Step B4: Verify Summary Saved (File Evidence)

```bash
# Check for new chat summary file
ls -lt ~/.council-memory/chat-summaries/ | head -3
```

### Step B5: Verify Diary Upserted (DB Evidence)

```bash
# Check for new session_diary entry
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, source, length(summary_text) as text_len, created_at
  FROM session_diary
  ORDER BY created_at DESC
  LIMIT 3;
"
```

### Step B6: Verify Event Hint Fired (Log Evidence)

```bash
# Check for event hint wake in logs
grep -i "_wake_scheduler\|_handle_event_hint\|daily_summary_saved\|chat_summary_saved" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5
```

### Step B7: Verify Scheduler Responded (Health Evidence)

```bash
# Check scheduler wake state
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
eh = h.get('event_hints', {})
print('Event hints state:')
print(f'  wake_method: {eh.get(\"wake_method\", \"missing\")}')
print(f'  last_wake_age: {eh.get(\"last_wake_age_seconds\", \"missing\")}')
print(f'  wired_into_production: {eh.get(\"wired_into_production\", \"missing\")}')
"
```

### Step B8: Verify Reconciliation Ran (DB Evidence)

```bash
# Check for new work_items from reconciliation
echo "=== AFTER summary ==="
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as work_item_count FROM work_items;"
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, title, kind, source_summary_id
  FROM work_items
  ORDER BY created_at DESC
  LIMIT 5;
"
```

### Chain B Success Criteria

- [ ] Baseline DB counts recorded
- [ ] Summary endpoint returns 200 with summary content
- [ ] Log shows `Session analyzed: mode=X` (analyzer ran before summarization)
- [ ] New file in `chat-summaries/` directory
- [ ] New row in `session_diary` table
- [ ] Log shows `_wake_scheduler("daily_summary_saved")` or `_handle_event_hint`
- [ ] Health check shows `last_wake_age_seconds` < 60 (scheduler woke recently)
- [ ] `work_items` count increased OR `session_diary` count increased
- [ ] New records have `source_summary_id` linking to the summary

---

## Chain C: SessionWatcher → JSONL Detection → Parse → Classify → Trim → Reconcile → DB Records

**Complete chain:** SessionWatcher daemon detects new JSONL → parses into turns → classifies session mode → trims to 12-field summary → feeds into reconciliation → new DB records created.

### Step C1: Capture Baseline

```bash
# Record DB state BEFORE
echo "=== BEFORE SessionWatcher processing ==="
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as work_item_count FROM work_items;"
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as diary_count FROM session_diary;"
```

### Step C2: Identify Target JSONL (This Session)

```bash
# Find the most recent JSONL that contains this session's conversation
latest=$(ls -t ~/.pi/agent/sessions/--home-chief--/*.jsonl 2>/dev/null | head -1)
echo "Target: $latest"
echo "Size: $(du -h "$latest" | cut -f1)"
echo "Messages: $(grep -c '"type": "message"' "$latest" 2>/dev/null)"
# Verify it contains this session's content
grep -l "SessionWatcher\|session_watcher\|production wiring" "$latest" 2>/dev/null && echo "Confirmed: this session"
```

### Step C3: Verify SessionWatcher Is Running

```bash
# Check if the SessionWatcher daemon is active
grep -i "SessionWatcher started\|session-watcher" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -3

# Check health for session watcher status
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
# Session watcher may not have dedicated health field yet — check scheduler
at = h.get('adaptive_triggers', {})
print(f'Scheduler thread alive: {at.get(\"thread_alive\", \"missing\")}')
"
```

### Step C4: Wait for SessionWatcher to Process

```bash
# The SessionWatcher polls every 15 seconds. Wait for it to detect and process the JSONL.
# Touch the file to ensure it's seen as "new" if needed
touch "$latest"
echo "Waiting 30s for SessionWatcher to process..."
sleep 30
```

### Step C5: Verify SessionWatcher Processed the JSONL (Log Evidence)

```bash
# Check for SessionWatcher processing logs
grep -i "SessionWatcher.*processing\|SessionWatcher.*classified\|SessionWatcher.*completed\|parsed.*turns\|trim_session" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | grep -i "$(basename $latest)" | tail -10
```

### Step C6: Verify Classification Occurred (Log Evidence)

```bash
# Check what mode the session was classified as
grep -i "classified as\|session_mode\|session analyzed" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5
```

### Step C7: Verify Reconciliation Ran (Log Evidence)

```bash
# Check for reconciliation activity from session processing
grep -i "reconcile_tasks\|reconciliation.*applied\|arc_delta\|task.*reconcil" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -5
```

### Step C8: Verify DB Records Created (DB Evidence)

```bash
# Check for new work_items from session processing
echo "=== AFTER SessionWatcher processing ==="
sqlite3 ~/.council-memory/council_core.db "SELECT count(*) as work_item_count FROM work_items;"
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, title, kind, source_summary_id
  FROM work_items
  ORDER BY created_at DESC
  LIMIT 5;
"

# Check for new session_diary entries
sqlite3 ~/.council-memory/council_core.db "
  SELECT id, source, length(summary_text) as text_len, created_at
  FROM session_diary
  ORDER BY created_at DESC
  LIMIT 3;
"
```

### Chain C Success Criteria

- [ ] SessionWatcher log shows "started" on service init
- [ ] Target JSONL identified and confirmed as this session
- [ ] Log shows `SessionWatcher: processing <filename> (N messages)`
- [ ] Log shows `SessionWatcher: classified as <mode>`
- [ ] Log shows `SessionWatcher: completed <filename> (mode=X, N signals)`
- [ ] Log shows reconciliation activity (`reconcile_tasks` or similar)
- [ ] `work_items` count increased OR `session_diary` count increased
- [ ] New records have `source_summary_id` linking to the JSONL file stem
- [ ] JSONL file remains unmodified (read-only)

---

## Chain D: Full Integration — All Three Chains Together

**Complete integration test:** Trigger a real event, verify it flows through ALL components, and confirm final state reflects the complete chain.

### Step D1: Full Baseline

```bash
echo "=== FULL INTEGRATION BASELINE ==="
echo "Timestamp: $(date -Iseconds)"
sqlite3 ~/.council-memory/council_core.db "SELECT 'work_items', count(*) FROM work_items UNION ALL SELECT 'session_diary', count(*) FROM session_diary UNION ALL SELECT 'memory_entries', count(*) FROM memory_entries;"
ls -lt ~/.council-memory/chat-summaries/ | head -2
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
at = h.get('adaptive_triggers', {})
eh = h.get('event_hints', {})
print(f'last_activity_age: {at.get(\"last_activity_age_seconds\", \"?\")}')
print(f'token_count: {at.get(\"current_token_count\", \"?\")}')
print(f'last_wake_age: {eh.get(\"last_wake_age_seconds\", \"?\")}')
"
```

### Step D2: Trigger Complete Pipeline

```bash
# 1. Chat completion (Chain A: activity tracking)
curl -s -X POST http://127.0.0.1:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "What is the session summarization pipeline?"}],
    "max_tokens": 128
  }' > /dev/null

sleep 2

# 2. Session summary (Chain B: analyzer → save → upsert → wake → reconcile)
curl -s -X POST http://127.0.0.1:8090/v1/council/summarize \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null

sleep 2

# 3. Chat summary (Chain B variant: chat summary path)
curl -s -X POST http://127.0.0.1:8090/v1/council/summarize-chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Verify the session watcher pipeline"},
      {"role": "assistant", "content": "The SessionWatcher parses JSONL, classifies sessions, trims summaries, and feeds them into reconciliation."}
    ]
  }' > /dev/null
```

### Step D3: Verify Complete Chain in Logs

```bash
# Single grep that should show ALL chain components fired
echo "=== COMPLETE CHAIN LOG EVIDENCE ==="
grep -iE "record_activity|add_tokens|session analyzed|summarize.*written|upsert_session_diary|_wake_scheduler|_handle_event_hint|reconcile_tasks|SessionWatcher.*processing|SessionWatcher.*completed" ~/.council-memory/supervisor-logs/*.log 2>/dev/null | tail -20
```

### Step D4: Verify Complete Chain in Database

```bash
echo "=== FULL INTEGRATION FINAL STATE ==="
echo "Timestamp: $(date -Iseconds)"
sqlite3 ~/.council-memory/council_core.db "SELECT 'work_items', count(*) FROM work_items UNION ALL SELECT 'session_diary', count(*) FROM session_diary UNION ALL SELECT 'memory_entries', count(*) FROM memory_entries;"

# Show new records
sqlite3 ~/.council-memory/council_core.db "
  SELECT 'work_item', id, title, source_summary_id, created_at
  FROM work_items ORDER BY created_at DESC LIMIT 3
  UNION ALL
  SELECT 'diary', id, source, source_summary_id, created_at
  FROM session_diary ORDER BY created_at DESC LIMIT 3;
"
```

### Step D5: Verify Complete Chain in Health Check

```bash
echo "=== FULL INTEGRATION HEALTH CHECK ==="
curl -s http://127.0.0.1:8090/v1/council/health 2>/dev/null | python3 -c "
import sys, json
h = json.load(sys.stdin)
at = h.get('adaptive_triggers', {})
eh = h.get('event_hints', {})
sa = h.get('session_analyzer', {})
print('--- Adaptive Triggers ---')
print(f'  last_activity_age: {at.get(\"last_activity_age_seconds\", \"?\")}s')
print(f'  token_count: {at.get(\"current_token_count\", \"?\")}')
print(f'  event_score: {at.get(\"current_event_score\", \"?\")}')
print(f'  thread_alive: {at.get(\"thread_alive\", \"?\")}')
print('--- Event Hints ---')
print(f'  wake_method: {eh.get(\"wake_method\", \"?\")}')
print(f'  last_wake_age: {eh.get(\"last_wake_age_seconds\", \"?\")}s')
print(f'  wired_into_production: {eh.get(\"wired_into_production\", \"?\")}')
print('--- Session Analyzer ---')
print(f'  available: {sa.get(\"available\", \"?\")}')
print(f'  live_mode: {sa.get(\"live_mode\", \"?\")}')
print(f'  wired_into_production: {sa.get(\"wired_into_production\", \"?\")}')
"
```

### Chain D Success Criteria

- [ ] Baseline captured with timestamp
- [ ] All 3 endpoints return 200 (chat completion, summarize, summarize-chat)
- [ ] Single log grep shows ALL chain components: activity, analyzer, save, upsert, wake, reconcile
- [ ] Database counts increased from baseline
- [ ] New records have proper `source_summary_id` provenance linkage
- [ ] Health check shows: `last_activity_age` < 30, `token_count` > 0, `last_wake_age` < 30, `thread_alive` = true, `live_mode` = actual mode
- [ ] No errors in supervisor logs

---

## Deliverables

Save a runtime verification report to:
```
/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_runtime-event-verification-report_[hash].md
```

### Report Structure

```markdown
# Runtime Verification Report

## Chain A: Chat Completion → Activity Tracking
**Verdict:** PASS / FAIL
- Baseline: [values]
- After request: [values]
- Log evidence: [paste]
- Gap analysis: [what worked, what didn't]

## Chain B: Session Summary → Full Pipeline
**Verdict:** PASS / FAIL
- Baseline DB: [counts]
- After summary: [counts]
- Analyzer log: [paste]
- Event hint log: [paste]
- DB records: [paste]
- Gap analysis: [what worked, what didn't]

## Chain C: SessionWatcher → JSONL Processing
**Verdict:** PASS / FAIL
- Target JSONL: [path, size, message count]
- Processing log: [paste]
- Classification: [mode detected]
- Reconciliation log: [paste]
- DB records: [paste]
- Gap analysis: [what worked, what didn't]

## Chain D: Full Integration
**Verdict:** PASS / FAIL
- Baseline: [all counts + health values]
- Final state: [all counts + health values]
- Complete chain log: [paste]
- Gap analysis: [what worked, what didn't]

## Summary Table

| Chain | Activity | Analyzer | Save | Upsert | Wake | Reconcile | DB Records | Verdict |
|-------|----------|----------|------|--------|------|-----------|------------|---------|
| A     | ✓/✗      | N/A      | N/A  | N/A    | N/A  | N/A       | N/A        | PASS/FAIL |
| B     | N/A      | ✓/✗      | ✓/✗  | ✓/✗    | ✓/✗  | ✓/✗       | ✓/✗        | PASS/FAIL |
| C     | N/A      | ✓/✗      | ✓/✗  | ✓/✗    | ✓/✗  | ✓/✗       | ✓/✗        | PASS/FAIL |
| D     | ✓/✗      | ✓/✗      | ✓/✗  | ✓/✗    | ✓/✗  | ✓/✗       | ✓/✗        | PASS/FAIL |

## Issues Found
1. [Issue description — with log evidence]
2. [Issue description — with log evidence]

## Recommendations
1. [Actionable fix or improvement]
```

## Constraints

- **No test scripts:** Use real HTTP endpoints, real logs, real database queries
- **No mocks:** Everything must be the actual production runtime
- **Read-only on JSONL:** Never modify Pi's session files
- **Non-destructive:** Do not delete or modify existing database records
- **Chain completeness:** Each chain must be verified from trigger through final observable result
