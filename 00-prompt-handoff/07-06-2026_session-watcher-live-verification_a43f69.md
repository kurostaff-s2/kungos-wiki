# Session Watcher — End-to-End Runtime Verification

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `a43f69` |
| Entity type | `session` |
| Short description | Trigger real runtime events through production paths and verify the COMPLETE pipeline chain end-to-end — from event trigger through final database record, with explicit baseline/delta measurements |
| Status | `draft` |
| Source references | `06-06-2026_session-summarization-flexible-reconciliation_59130b.md` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — restart service, trigger real events, verify complete pipeline chains |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Related codebases:** `/home/chief/.pi/agent/sessions/` (Pi session JSONL source)
**Key files for this task:**
- `memory_service/session_watcher.py` — SessionWatcher (JSONL → trim → reconcile)
- `arc_summarizer/analyzer.py` — SessionAnalyzer (classify + trim)
- `arc_summarizer/__init__.py` — ArcSummarizer (analyzer wiring)
- `memory_service/__init__.py` — MemoryService (event hints, health check)
- `memory_service/http_endpoints.py` — HTTP tool dispatcher (port 18098)
- `memory_service/store.py` — RelationalStore (DB writes, reconciliation)

## Critical Pre-Condition: Service Restart Required

**All source files were modified after the current service instance started.** The running process (PID 35117, started Jun 06 20:14:56) has stale code. The verification cannot proceed accurately until the service is restarted.

| File | Modified | Service Started | Stale? |
|------|----------|-----------------|--------|
| `memory_service/__init__.py` | Jun 07 02:41 | Jun 06 20:14 | ✅ Yes |
| `memory_service/session_watcher.py` | Jun 07 02:40 | Jun 06 20:14 | ✅ Yes |
| `memory_service/reconciliation.py` | Jun 07 01:55 | Jun 06 20:14 | ✅ Yes |
| `arc_summarizer/analyzer.py` | Jun 07 00:29 | Jun 06 20:14 | ✅ Yes |
| `arc_summarizer/__init__.py` | Jun 07 02:26 | Jun 06 20:14 | ✅ Yes |
| `arc_summarizer/pipeline.py` | Jun 07 01:56 | Jun 06 20:14 | ✅ Yes |
| `arc_summarizer/scheduler.py` | Jun 07 01:44 | Jun 06 20:14 | ✅ Yes |

**Action:** `systemctl --user restart memory-service` before running any verification steps.

---

## Actual Runtime Architecture

The original plan assumed REST endpoints (`/v1/council/*`, `/v1/chat/completions`) that do not exist. The actual runtime uses:

| Component | Actual Endpoint / Access | Port |
|-----------|------------------------|------|
| HTTP health (flat) | `GET /v1/memory/health` | 18098 |
| HTTP tool dispatcher | `POST /v1/memory/tool/{tool_name}` | 18098 |
| MCP SSE (primary) | SSE `/sse` + POST `/messages/` | 18097 |
| Detailed health | `python -m super_council.memory_service --health` (CLI) or `MemoryService.health_check()` (Python API) | N/A |
| LLM server | `POST /v1/chat/completions` (llama-server, not memory_service) | 8091 |
| ARC summarizer | `http://127.0.0.1:18095` (Ollama-compatible) | 18095 |

### Available HTTP Tools (port 18098)

35 tools via `POST /v1/memory/tool/{tool_name}`:
- `upsert_summary` — persist session diary entry
- `reconcile_open_items` — deduplicate + reconcile across diary entries
- `system_health` — service status + consolidation metrics
- `memsearch_status` — memsearch health + collection stats
- `query_session_diary` — query auto-upserted diary entries
- `council-recall` — three-channel unified recall
- `get_recent_events` — recent execution events
- `get_run_snapshot` — full run state
- `summarize_run_issues` — structured failure summary
- `review.start` / `review.log` / `review.verdict` — review lifecycle
- `codegraph_*` — code graph search, callers, callees, impact, trace
- Plus 15 more (see `GET /v1/memory/tools`)

---

## Pipeline Chains To Verify

Three chains plus one composite integration proof:

```
Chain A: HTTP Tool Call → Tool Endpoint / Health Path
  POST /v1/memory/tool/system_health → 200 OK → health check shows live state
  NOTE: _record_activity() is on MCP SSE path, not HTTP debug endpoints. Chain A verifies HTTP surface only.

Chain B: Upsert Summary → Analyzer → Save → DB Upsert → Event Hint → Scheduler Wake → Reconciliation → DB Records
  POST /v1/memory/tool/upsert_summary → SessionAnalyzer.classify() → summary saved →
  upsert_session_diary() → _wake_scheduler("daily_summary_saved") → scheduler._handle_event_hint() →
  reconcile_tasks() → new work_items in DB

Chain C: SessionWatcher → JSONL Detection → Parse → Classify → Trim → Reconcile → DB Records
  (background daemon) new JSONL detected → _parse_jsonl() → _classify() → _trim_session() →
  _reconcile() → new work_items in DB

Chain D: Composite Integration Proof
  Not a separate feature — proves all three trigger paths produce measurable DB + health deltas
  through a single coordinated exercise. Sub-evidence: chat trigger, summarize trigger,
  watcher trigger, DB delta, health delta.
```

**Each chain must show explicit baseline → trigger → final → delta measurements. Assertions without measured change are insufficient.**

---

## Pre-Flight Checklist

- [ ] `systemctl --user restart memory-service` — load current code
- [ ] Verify service healthy: `curl -s http://127.0.0.1:18098/v1/memory/health` → `{"status": "healthy"}`
- [ ] Verify SessionWatcher started: `journalctl --user -u memory-service | grep "SessionWatcher started"`
- [ ] MemoryService database accessible at `~/.council-memory/council_core.db`
- [ ] Pi session JSONL files exist in `~/.pi/agent/sessions/`
- [ ] Supervisor logs accessible via `journalctl --user -u memory-service`

---

## Baseline Capture (Before Any Chain)

Run this ONCE before Chain A and record all values. Every chain references this baseline.

```bash
echo "=== BASELINE CAPTURE ==="
echo "Timestamp: $(date -Iseconds)"

# DB counts
python3 -c "
import sqlite3, json
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
tables = ['work_items', 'session_diary', 'memory_entries', 'session_summaries', 'raw_session_memories']
counts = {}
for t in tables:
    try:
        c.execute(f'SELECT count(*) FROM {t}')
        counts[t] = c.fetchone()[0]
    except:
        counts[t] = 'table_not_found'
print(json.dumps(counts, indent=2))
conn.close()
"

# Health values
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -m json.tool

# Detailed health (if CLI works)
cd ~/Coding-Projects/7-council && PYTHONPATH=/home/chief/Coding-Projects/7-council \
  python3 -m super_council.memory_service --health 2>/dev/null | python3 -m json.tool || \
  echo "Detailed health unavailable via CLI (foreign key constraint — use tool endpoint)"

# Recent DB records for provenance tracking
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
print('=== Latest work_items ===')
c.execute('SELECT id, project_id, kind, title, status, source_summary_id, created_at FROM work_items ORDER BY created_at DESC LIMIT 3')
for r in c.fetchall():
    print(f'  id={r[0]} project_id={r[1]} kind={r[2]} title={r[3]} status={r[4]} source_summary_id={r[5]} created_at={r[6]}')
print('=== Latest session_diary ===')
c.execute('SELECT summary_id, date, source_file, created_at FROM session_diary ORDER BY created_at DESC LIMIT 3')
for r in c.fetchall():
    print(f'  summary_id={r[0]} date={r[1]} source_file={r[2]} created_at={r[3]}')
conn.close()
"
```

**Record these values in the report as the baseline for all chains.**

---

## Chain A: HTTP Tool Call → Tool Endpoint / Health Path

**Complete chain:** Real tool call → 200 OK → health check shows live state.
**Caveat:** This chain verifies the HTTP debug surface. Activity tracking (`_record_activity()`) is wired into the MCP SSE production path, not the HTTP endpoints. To verify activity tracking, test through the SSE path (`POST /messages/` on port 18097).

### Step A1: Capture Baseline (reuse from pre-flight)

Record: `work_items` count, `session_diary` count, `memory_entries` count, health status.

### Step A2: Trigger Real Tool Call

```bash
# Send real tool call through production HTTP endpoint
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/system_health \
  -H "Content-Type: application/json" \
  -d '{"query": "service status", "max_tokens": 2048}' > /tmp/chain_a_response.json

echo "Response status: $(python3 -c "import json; d=json.load(open('/tmp/chain_a_response.json')); print('OK' if 'service_health' in d else 'FAIL')" 2>/dev/null)"
```

### Step A3: Verify Activity Tracking in Logs

```bash
# Find log lines showing activity was recorded AFTER the request
journalctl --user -u memory-service --since "$(date -d '1 minute ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "system_health\|tool.*executed\|18098" | tail -5
```

### Step A4: Verify Scheduler State Changed

```bash
# Check health AFTER the request
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -c "
import sys, json
h = json.load(sys.stdin)
print('AFTER tool call:')
print(f'  status: {h.get(\"status\", \"missing\")}')
print(f'  tools_available: {h.get(\"tools_available\", \"missing\")}')
print(f'  components: {json.dumps(h.get(\"components\", {}), indent=4)}')
"
```

### Chain A Results Block

```markdown
### Chain A Results

**Baseline:**
| Metric | Value |
|--------|-------|
| work_items count | [RECORD] |
| session_diary count | [RECORD] |
| memory_entries count | [RECORD] |
| health status | [RECORD] |
| tools_available | [RECORD] |

**After Trigger:**
| Metric | Value | Delta |
|--------|-------|-------|
| work_items count | [RECORD] | [+N / 0] |
| session_diary count | [RECORD] | [+N / 0] |
| health status | [RECORD] | [same/changed] |
| last_activity (from logs) | [RECORD] | [fresh/stale] |

**Provenance Example:**
| Field | Value |
|-------|-------|
| Log line | [paste one log line showing tool execution] |
| Health value | [paste tools_available or component status] |

**Verdict:** PASS / FAIL
```

### Chain A Success Criteria

- [ ] Health check BEFORE shows baseline values recorded
- [ ] Tool call returns 200 with `service_health` content
- [ ] Log shows tool execution on port 18098
- [ ] Health check AFTER shows `status: healthy`
- [ ] Components all show `available`

---

## Chain B: Upsert Summary → Analyzer → Save → DB Upsert → Event Hint → Scheduler Wake → Reconciliation → DB Records

**Complete chain:** Real upsert request → analyzer classifies content → summary saved to DB → event hint fires → scheduler wakes → reconciliation runs → new DB records created.

### Step B1: Capture Baseline (reuse from pre-flight)

Record exact DB counts and latest record IDs.

### Step B2: Trigger Real Upsert Summary

```bash
# Trigger real upsert through production endpoint
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/upsert_summary \
  -H "Content-Type: application/json" \
  -d '{
    "summary_text": "## Topics Discussed\n- Session watcher runtime verification\n- Pipeline chain validation\n\n## Key Decisions\n- Use actual HTTP endpoints (port 18098) instead of planned /v1/council/* endpoints\n- Add explicit baseline/delta measurements to verification report\n\n## Work Completed\n- Rewrote verification handoff with actual endpoints\n- Added provenance tracking per chain\n- Renamed Chain D to composite integration proof",
    "source": "chain-b-verification"
  }' > /tmp/chain_b_response.json

echo "Response: $(cat /tmp/chain_b_response.json | python3 -m json.tool 2>/dev/null | head -5)"
```

### Step B3: Verify Analyzer Ran (Log Evidence)

```bash
# The analyzer MUST run before summarization — verify in logs
journalctl --user -u memory-service --since "$(date -d '1 minute ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "SessionAnalyzer\|session analyzed\|session_mode\|scores=" | tail -5
```

### Step B4: Verify Summary Saved (DB Evidence)

```bash
# Check for new session_diary entry
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
print('=== AFTER upsert ===')
c.execute('SELECT count(*) FROM session_diary')
print(f'session_diary count: {c.fetchone()[0]}')
c.execute('SELECT summary_id, date, source_file, length(work_completed) as wc_len, created_at FROM session_diary ORDER BY created_at DESC LIMIT 3')
for r in c.fetchall():
    print(f'  summary_id={r[0]} date={r[1]} source_file={r[2]} wc_len={r[3]} created_at={r[4]}')
conn.close()
"
```

### Step B5: Verify Event Hint Fired (Log Evidence)

```bash
# Check for event hint wake in logs
journalctl --user -u memory-service --since "$(date -d '1 minute ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "_wake_scheduler\|_handle_event_hint\|daily_summary_saved\|chat_summary_saved" | tail -5
```

### Step B6: Verify Scheduler Responded (Health Evidence)

```bash
# Check scheduler wake state via system_health tool
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/system_health \
  -H "Content-Type: application/json" \
  -d '{"query": "scheduler wake state", "max_tokens": 2048}' | python3 -c "
import sys, json
h = json.load(sys.stdin)
sh = h.get('service_health', {}).get('services', {})
print('Service health:')
for name, info in sh.items():
    print(f'  {name}: {info.get(\"status\", \"?\")}')
"
```

### Step B7: Verify Reconciliation Ran (DB Evidence)

```bash
# Check for new work_items from reconciliation
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
c.execute('SELECT count(*) FROM work_items')
print(f'work_items count: {c.fetchone()[0]}')
c.execute('SELECT id, project_id, kind, title, status, created_at FROM work_items ORDER BY created_at DESC LIMIT 5')
for r in c.fetchall():
    print(f'  id={r[0]} project_id={r[1]} kind={r[2]} title={r[3]} status={r[4]} created_at={r[5]}')
conn.close()
"
```

### Chain B Results Block

```markdown
### Chain B Results

**Baseline:**
| Metric | Value |
|--------|-------|
| work_items count | [RECORD] |
| session_diary count | [RECORD] |
| latest diary summary_id | [RECORD] |

**After Trigger:**
| Metric | Value | Delta |
|--------|-------|-------|
| work_items count | [RECORD] | [+N / 0] |
| session_diary count | [RECORD] | [+N / 0] |
| latest diary summary_id | [RECORD] | [new/unchanged] |

**Provenance Example:**
| Field | Value |
|-------|-------|
| Record ID | [new session_diary summary_id] |
| Source file | [source_file from DB] |
| Created at | [created_at from DB] |
| Log line | [paste one log line showing upsert or event hint] |
| Health value | [paste scheduler wake status] |

**Verdict:** PASS / FAIL
```

### Chain B Success Criteria

- [ ] Baseline DB counts recorded
- [ ] Upsert endpoint returns 200 with `status: upserted` and `cache_id`
- [ ] Log shows `upsert_summary` executed (tool dispatcher log)
- [ ] `session_diary` count increased by at least 1
- [ ] New row has `source_file` matching the upsert source
- [ ] Log shows `_wake_scheduler("daily_summary_saved")` or `_handle_event_hint`
- [ ] Service health shows all components available
- [ ] New records have traceable provenance (summary_id → source_file → created_at)

---

## Chain C: SessionWatcher → JSONL Detection → Parse → Classify → Trim → Reconcile → DB Records

**Complete chain:** SessionWatcher daemon detects new JSONL → parses into turns → classifies session mode → trims to structured summary → feeds into reconciliation → new DB records created.

### Step C1: Capture Baseline (reuse from pre-flight)

Record exact DB counts.

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
# Check if the SessionWatcher daemon started on service restart
journalctl --user -u memory-service --since "$(date -d '30 minutes ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "SessionWatcher started" | tail -3

# Check health for session watcher status
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -c "
import sys, json
h = json.load(sys.stdin)
print(f'Status: {h.get(\"status\", \"?\")}')
print(f'Components: {json.dumps(h.get(\"components\", {}), indent=2)}')
"
```

### Step C4: Trigger SessionWatcher Processing

```bash
# Touch the file to ensure it's seen as "new" if needed
touch "$latest"
echo "Waiting 30s for SessionWatcher to process (poll interval: 15s)..."
sleep 30
```

### Step C5: Verify SessionWatcher Processed the JSONL (Log Evidence)

```bash
# Check for SessionWatcher processing logs
journalctl --user -u memory-service --since "$(date -d '2 minutes ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "SessionWatcher.*processing\|SessionWatcher.*classified\|SessionWatcher.*completed\|parsed.*turns\|trim_session" | grep -i "$(basename $latest)" | tail -10
```

### Step C6: Verify Classification Occurred (Log Evidence)

```bash
# Check what mode the session was classified as
journalctl --user -u memory-service --since "$(date -d '2 minutes ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "classified as\|session_mode\|session analyzed" | tail -5
```

### Step C7: Verify Reconciliation Ran (Log Evidence)

```bash
# Check for reconciliation activity from session processing
journalctl --user -u memory-service --since "$(date -d '2 minutes ago' --iso-seconds)" --no-pager 2>/dev/null | grep -i "reconcile_tasks\|reconciliation.*applied\|arc_delta\|task.*reconcil" | tail -5
```

### Step C8: Verify DB Records Created (DB Evidence)

```bash
# Check for new work_items from session processing
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
print('=== AFTER SessionWatcher processing ===')
c.execute('SELECT count(*) FROM work_items')
print(f'work_items count: {c.fetchone()[0]}')
c.execute('SELECT count(*) FROM session_diary')
print(f'session_diary count: {c.fetchone()[0]}')
c.execute('SELECT id, project_id, kind, title, status, created_at FROM work_items ORDER BY created_at DESC LIMIT 5')
print('Latest work_items:')
for r in c.fetchall():
    print(f'  id={r[0]} project_id={r[1]} kind={r[2]} title={r[3]} status={r[4]} created_at={r[5]}')
c.execute('SELECT summary_id, date, source_file, created_at FROM session_diary ORDER BY created_at DESC LIMIT 3')
print('Latest session_diary:')
for r in c.fetchall():
    print(f'  summary_id={r[0]} date={r[1]} source_file={r[2]} created_at={r[3]}')
conn.close()
"
```

### Chain C Results Block

```markdown
### Chain C Results

**Baseline:**
| Metric | Value |
|--------|-------|
| work_items count | [RECORD] |
| session_diary count | [RECORD] |

**After Trigger:**
| Metric | Value | Delta |
|--------|-------|-------|
| work_items count | [RECORD] | [+N / 0] |
| session_diary count | [RECORD] | [+N / 0] |

**Provenance Example:**
| Field | Value |
|-------|-------|
| Target JSONL | [path, size, message count] |
| Classification mode | [mode from logs] |
| Record ID | [new DB record id] |
| Source file | [source_file from DB] |
| Created at | [created_at from DB] |
| Log line | [paste one log line showing SessionWatcher processing] |
| Health value | [paste component status] |

**Verdict:** PASS / FAIL
```

### Chain C Success Criteria

- [ ] SessionWatcher log shows "started" on service restart
- [ ] Target JSONL identified and confirmed as this session
- [ ] Log shows `SessionWatcher: processing <filename> (N messages)`
- [ ] Log shows `SessionWatcher: classified as <mode>`
- [ ] Log shows `SessionWatcher: completed <filename> (mode=X, N signals)`
- [ ] Log shows reconciliation activity (`reconcile_tasks` or similar)
- [ ] `work_items` count increased OR `session_diary` count increased
- [ ] New records have traceable provenance (summary_id → source_file → created_at)
- [ ] JSONL file remains unmodified (read-only)

---

## Chain D: Composite Integration Proof

**Purpose:** Not a separate feature — proves all three trigger paths produce measurable DB + health deltas through a single coordinated exercise. Explicit sub-evidence required for each component.

### Step D1: Full Baseline

```bash
echo "=== COMPOSITE BASELINE ==="
echo "Timestamp: $(date -Iseconds)"

# DB counts
python3 -c "
import sqlite3, json
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
counts = {}
for t in ['work_items', 'session_diary', 'memory_entries']:
    c.execute(f'SELECT count(*) FROM {t}')
    counts[t] = c.fetchone()[0]
print(json.dumps(counts, indent=2))
conn.close()
"

# Health check
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -m json.tool
```

### Step D2: Trigger All Three Paths

```bash
# 1. Tool call (Chain A path: activity tracking)
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/system_health \
  -H "Content-Type: application/json" \
  -d '{"query": "integration test", "max_tokens": 1024}' > /dev/null

sleep 1

# 2. Upsert summary (Chain B path: analyzer → save → upsert → wake → reconcile)
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/upsert_summary \
  -H "Content-Type: application/json" \
  -d '{
    "summary_text": "## Integration Test\n- Composite chain D verification\n- All three trigger paths exercised simultaneously\n\n## Work Completed\n- Triggered system_health tool call\n- Triggered upsert_summary with test content\n- SessionWatcher will process JSONL in background",
    "source": "chain-d-integration"
  }' > /dev/null

sleep 1

# 3. Touch latest JSONL for SessionWatcher (Chain C path)
latest=$(ls -t ~/.pi/agent/sessions/--home-chief--/*.jsonl 2>/dev/null | head -1)
touch "$latest"
echo "Waiting 30s for SessionWatcher to process..."
sleep 30
```

### Step D3: Verify Complete Chain in Logs

```bash
# Single grep that should show ALL chain components fired
echo "=== COMPLETE CHAIN LOG EVIDENCE ==="
journalctl --user -u memory-service --since "$(date -d '3 minutes ago' --iso-seconds)" --no-pager 2>/dev/null | grep -iE "system_health|upsert_summary|_wake_scheduler|_handle_event_hint|reconcile_tasks|SessionWatcher.*processing|SessionWatcher.*completed" | tail -20
```

### Step D4: Verify Complete Chain in Database

```bash
echo "=== COMPOSITE FINAL STATE ==="
echo "Timestamp: $(date -Iseconds)"

python3 -c "
import sqlite3, json
conn = sqlite3.connect('$HOME/.council-memory/council_core.db')
c = conn.cursor()
counts = {}
for t in ['work_items', 'session_diary', 'memory_entries']:
    c.execute(f'SELECT count(*) FROM {t}')
    counts[t] = c.fetchone()[0]
print('Final counts:', json.dumps(counts, indent=2))

# Show new records with provenance
c.execute('SELECT id, project_id, kind, title, status, created_at FROM work_items ORDER BY created_at DESC LIMIT 3')
print('Latest work_items:')
for r in c.fetchall():
    print(f'  id={r[0]} project_id={r[1]} kind={r[2]} title={r[3]} status={r[4]} created_at={r[5]}')

c.execute('SELECT summary_id, date, source_file, created_at FROM session_diary ORDER BY created_at DESC LIMIT 3')
print('Latest session_diary:')
for r in c.fetchall():
    print(f'  summary_id={r[0]} date={r[1]} source_file={r[2]} created_at={r[3]}')
conn.close()
"
```

### Step D5: Verify Complete Chain in Health Check

```bash
echo "=== COMPOSITE HEALTH CHECK ==="
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -m json.tool
```

### Chain D Results Block

```markdown
### Chain D Results — Composite Integration Proof

**Baseline:**
| Metric | Value |
|--------|-------|
| work_items count | [RECORD] |
| session_diary count | [RECORD] |
| memory_entries count | [RECORD] |
| health status | [RECORD] |
| tools_available | [RECORD] |

**Final State:**
| Metric | Value | Delta |
|--------|-------|-------|
| work_items count | [RECORD] | [+N / 0] |
| session_diary count | [RECORD] | [+N / 0] |
| memory_entries count | [RECORD] | [+N / 0] |
| health status | [RECORD] | [same/changed] |
| tools_available | [RECORD] | [same/changed] |

**Sub-Evidence:**
| Component | Trigger Fired | Log Matched | DB Delta | Health Delta |
|-----------|--------------|-------------|----------|-------------|
| Chat (Chain A) | ✓/✗ | [log line] | [+N] | [value] |
| Summarize (Chain B) | ✓/✗ | [log line] | [+N] | [value] |
| Watcher (Chain C) | ✓/✗ | [log line] | [+N] | [value] |

**Provenance Example:**
| Field | Value |
|-------|-------|
| Record ID | [newest work_item or session_diary id] |
| Project ID | [project_id from DB] |
| Entity Type | [work_item / session_diary] |
| Source | [source_file or source from upsert] |
| Created at | [created_at from DB] |
| Log line | [paste one log line from complete chain grep] |
| Health value | [paste tools_available or component status] |

**Verdict:** PASS / FAIL
```

### Chain D Success Criteria

- [ ] Baseline captured with timestamp
- [ ] All 3 triggers return 200 (tool call, upsert, JSONL touch)
- [ ] Single log grep shows ALL chain components: tool execution, upsert, wake, reconcile, SessionWatcher
- [ ] Database counts increased from baseline
- [ ] New records have traceable provenance (id → project_id → source → created_at)
- [ ] Health check shows: `status: healthy`, all components `available`
- [ ] No errors in supervisor logs

---

## Summary Table

| Chain | Baseline Captured | Trigger Fired | Logs Matched | DB Delta | Health Delta | Verdict |
|-------|-------------------|---------------|--------------|----------|-------------|---------|
| A     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/PARTIAL |
| B     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |
| C     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |
| D     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |

---

## Deliverables

Save a runtime verification report to:
```
/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_runtime-event-verification-report_[hash].md
```

### Report Structure

```markdown
# Runtime Verification Report

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Entity ID | `a43f69` |
| Entity Type | `session` |
| Status | `[in_progress / completed]` |
| Verification Date | `[date]` |
| Service PID | `[PID from systemctl]` |
| Service Started | `[timestamp from systemctl]` |

## Chain A: HTTP Tool Call → Tool Endpoint / Health Path
**Verdict:** PASS / PARTIAL
**Caveat:** HTTP debug surface verified. Activity tracking (`_record_activity()`) requires MCP SSE path test.

### Baseline
| Metric | Value |
|--------|-------|
| [metric] | [value] |

### After Trigger
| Metric | Value | Delta |
|--------|-------|-------|
| [metric] | [value] | [+N / 0 / changed] |

### Provenance
| Field | Value |
|-------|-------|
| Log line | [paste] |
| Health value | [paste] |

### Gap Analysis
[What worked, what didn't, what needs fixing]

## Chain B: Upsert Summary → Full Pipeline
**Verdict:** PASS / FAIL

### Baseline
[DB counts table]

### After Trigger
[DB counts with delta column]

### Provenance
| Field | Value |
|-------|-------|
| Record ID | [new session_diary summary_id] |
| Source file | [source_file from DB] |
| Created at | [created_at from DB] |
| Log line | [paste] |
| Health value | [paste] |

### Gap Analysis
[What worked, what didn't, what needs fixing]

## Chain C: SessionWatcher → JSONL Processing
**Verdict:** PASS / FAIL

### Baseline
[DB counts table]

### After Trigger
[DB counts with delta column]

### Provenance
| Field | Value |
|-------|-------|
| Target JSONL | [path, size, message count] |
| Classification mode | [mode from logs] |
| Record ID | [new DB record id] |
| Source file | [source_file from DB] |
| Created at | [created_at from DB] |
| Log line | [paste] |
| Health value | [paste] |

### Gap Analysis
[What worked, what didn't, what needs fixing]

## Chain D: Composite Integration Proof
**Verdict:** PASS / FAIL

### Baseline
[All counts + health values]

### Final State
[All counts + health values with delta column]

### Sub-Evidence
| Component | Trigger Fired | Log Matched | DB Delta | Health Delta |
|-----------|--------------|-------------|----------|-------------|
| Chat (A) | ✓/✗ | [log line] | [+N] | [value] |
| Summarize (B) | ✓/✗ | [log line] | [+N] | [value] |
| Watcher (C) | ✓/✗ | [log line] | [+N] | [value] |

### Provenance
| Field | Value |
|-------|-------|
| Record ID | [newest record id] |
| Project ID | [project_id] |
| Entity Type | [work_item / session_diary] |
| Source | [source_file] |
| Created at | [created_at] |
| Log line | [paste] |
| Health value | [paste] |

### Gap Analysis
[What worked, what didn't, what needs fixing]

## Summary Table

| Chain | Baseline Captured | Trigger Fired | Logs Matched | DB Delta | Health Delta | Verdict |
|-------|-------------------|---------------|--------------|----------|-------------|---------|
| A     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/PARTIAL |
| B     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |
| C     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |
| D     | ✓/✗              | ✓/✗           | ✓/✗          | [+N]     | [same/changed] | PASS/FAIL |

## Issues Found
1. [Issue description — with log evidence and measured delta]
2. [Issue description — with log evidence and measured delta]

## Recommendations
1. [Actionable fix or improvement]
```

## Constraints

- **No test scripts:** Use real HTTP endpoints, real logs, real database queries
- **No mocks:** Everything must be the actual production runtime
- **Read-only on JSONL:** Never modify Pi's session files (touch only for mtime)
- **Non-destructive:** Do not delete or modify existing database records
- **Chain completeness:** Each chain must show baseline → trigger → final → delta
- **Provenance required:** At least one concrete DB record per chain with id, project_id, entity_type, source, created_at
- **Health delta required:** Health values before and after each chain
- **Service restart required:** Must restart memory-service before verification to load current code
