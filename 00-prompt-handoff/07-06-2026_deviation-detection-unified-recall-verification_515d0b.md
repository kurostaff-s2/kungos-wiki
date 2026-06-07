# Handoff: Deviation Detection + Unified Recall Runtime Verification

**Date:** 07-06-2026
**ID:** 515d0b
**Parent:** Arc summarizer extraction accuracy fix (6b7b43)
**Priority:** High — validates core memory pipeline

## Problem Statement

After moving deviation detection outside the diary gate, we need to verify:
1. **Deviation detection** works for main pi sessions (not just subagent chains)
2. **Unified recall** returns valid data from all three channels
3. **Context management** preserves decisions, work completed, and open items across runtime sessions

### Known Gaps Being Verified

| Gap | Status | Verification Target |
|-----|--------|---------------------|
| Deviation detection gated behind diary | ✅ Fixed | Main sessions now detect deviations |
| Arc summaries missing decisions | ⚠️ Partial | Diary-first merge wired, needs runtime validation |
| Memory rollups empty | ⚠️ Timing | Daily tier not overdue yet; verify when due |
| Context router execution history | ❌ Empty | `recall.recent_events()` returns [] |

## Pre-Flight Checklist

- [ ] Verify `memory-service` and `arc-summarizer` are running
- [ ] Confirm `session_watcher.py` has deviation detection at line ~399 (outside `_merge_with_diary`)
- [ ] Check `carry_forward` table has items (needed for deviation comparison)
- [ ] Verify `memory_entries` has raw/diary entries (input for consolidation)
- [ ] Note current tier status: `daily` last run, `weekly` due June 8

## Phase 1: Deviation Detection Verification

### 1A. Confirm Carry-Forward Plans Exist

```python
import sqlite3
conn = sqlite3.connect('/home/chief/.council-memory/council_core.db')
rows = conn.execute("""
    SELECT kind, COUNT(*), MAX(created_at)
    FROM carry_forward
    WHERE is_deleted = 0
    GROUP BY kind
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} items, last={r[2]}")
```

**Expected:** At least 1 item with kind `plan`, `task`, or `work_item`

### 1B. Trigger a Session with Known Deviation

**Action:** In this session, make a decision that differs from a carry_forward plan.

Example: If carry_forward has "Use PostgreSQL", decide "Use SQLite instead".

**Verification:** After session ends, check:

```python
# Check session summary for notable_deviations
import os
sessions_dir = '/home/chief/.council-memory/sessions/'
latest = sorted(os.listdir(sessions_dir), key=lambda f: os.path.getmtime(os.path.join(sessions_dir, f)), reverse=True)[0]
with open(os.path.join(sessions_dir, latest)) as f:
    content = f.read()
    if 'Deviations' in content or 'notable_deviations' in content:
        print("✅ Deviations detected in session summary")
        # Extract deviation section
        for line in content.split('\n'):
            if 'deviation' in line.lower() or 'planned' in line.lower() or 'unplanned' in line.lower():
                print(f"  {line}")
    else:
        print("❌ No deviations in session summary")
```

### 1C. Verify Deviation Classification

**Check:** Deviations are classified as `planned`, `unplanned`, or `optimization` based on:
- Keyword overlap < 0.5 between decision and plan = deviation
- "instead of", "changed from", "shifted to" = planned
- Error/bug language = unplanned
- "improved", "optimized", "better" = optimization

**Acceptance criteria:**
- At least 1 deviation detected when decision differs from plan
- Deviation type matches classification rules
- Deviation string includes both decision text and plan reference

## Phase 2: Unified Recall Verification

### 2A. Three-Channel Recall Test

```python
# Test all three channels simultaneously
from super_council.memory_service.layer import MemoryLayer

# Or via MCP tools:
# recall.unified(query="deviation detection", scope="all")
# recall.recent_events(limit=5)
# codegraph_search(query="SessionWatcher")
```

**Expected results:**
| Channel | Tool | Expected |
|---------|------|----------|
| Text (memsearch) | `recall.unified(scope="decision")` | Scored matches from memory_entries |
| Structural (codegraph) | `codegraph_search()` | Symbol matches from index |
| Execution (context router) | `recall.recent_events()` | **KNOWN GAP** — returns [] |

### 2B. Memory Rollups Query

```python
import sqlite3
conn = sqlite3.connect('/home/chief/.council-memory/council_core.db')

# Check rollups
rows = conn.execute("""
    SELECT tier, COUNT(*), MAX(created_at)
    FROM memory_rollups
    WHERE is_deleted = 0
    GROUP BY tier
""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} entries, last={r[2]}")

# Check consolidation tiers
rows = conn.execute("""
    SELECT tier_id, window_days, last_run_at
    FROM consolidation_tiers
    ORDER BY window_days
""").fetchall()
for r in rows:
    print(f"  {r[0]}: window={r[1]}d, last_run={r[2]}")
```

**Expected:**
- `memory_rollups`: 2 weekly entries from June 2 (migration data)
- `daily` tier: last run today, next due tomorrow
- `weekly` tier: last run June 1, due June 8

### 2C. Session Diary vs Session Summaries

```python
# Compare diary entries (ground truth) vs arc summaries (extracted)
import sqlite3
conn = sqlite3.connect('/home/chief/.council-memory/council_core.db')

print("=== SESSION DIARY (ground truth) ===")
rows = conn.execute("""
    SELECT summary_id, decisions, work_completed
    FROM session_diary
    ORDER BY created_at DESC LIMIT 3
""").fetchall()
for r in rows:
    print(f"  {r[0]}: decisions={r[1][:60] if r[1] else 'none'}, work={r[2][:60] if r[2] else 'none'}")

print("\n=== SESSION SUMMARIES (arc-extracted) ===")
rows = conn.execute("""
    SELECT summary_id, decisions, work_completed
    FROM session_summaries
    ORDER BY created_at DESC LIMIT 3
""").fetchall()
print(f"  Count: {len(rows)} (expected: 0 — table not populated)")
```

**Expected:**
- `session_diary`: Has entries with structured decisions/work_completed
- `session_summaries`: Empty (arc writes MD files, not DB rows) — **known gap**

## Phase 3: Context Management Verification

### 3A. Session Context Preservation

**Action:** During this session, track:
1. Decisions made (explicit statements)
2. Work completed (files modified, tests run)
3. Open items (carried forward to next session)

**Verification:** After session ends, check the arc summary:

```python
import os, glob
sessions_dir = '/home/chief/.council-memory/sessions/'
# Find latest session MD
latest = sorted(glob.glob(os.path.join(sessions_dir, '*.md')), key=os.path.getmtime, reverse=True)[0]
with open(latest) as f:
    content = f.read()

# Check for structured fields
checks = {
    'Decisions': '## Decisions' in content,
    'Open Items': '## Open Items' in content,
    'Work Completed': '## Work Completed' in content,
    'Deviations': '## Deviations' in content,
}
for field, found in checks.items():
    status = "✅" if found else "❌"
    print(f"  {status} {field}")
```

### 3B. Decision Accuracy Check

**Compare:** Arc summary decisions vs actual JSONL decisions

```python
import json

# Extract user messages from JSONL (canonical source)
jsonl_path = '/home/chief/.pi/agent/sessions/--home-chief--/LATEST_SESSION.jsonl'
with open(jsonl_path) as f:
    lines = f.readlines()

actual_decisions = []
for line in lines:
    obj = json.loads(line)
    msg = obj.get('message', {})
    if msg.get('role') == 'user':
        content = msg.get('content', '')
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text = item.get('text', '')
                    if any(kw in text.lower() for kw in ['decision', 'decide', 'use', 'adopt']):
                        actual_decisions.append(text[:100])

print(f"Actual decisions in JSONL: {len(actual_decisions)}")
for d in actual_decisions:
    print(f"  - {d}")
```

**Acceptance criteria:**
- Arc summary decisions match JSONL decisions (± paraphrasing)
- No hallucinated decisions (not in JSONL)
- No missing decisions (in JSONL but not in summary)

### 3C. Context Router Execution History

**Known gap:** `recall.recent_events()` returns empty.

**Verification:**

```python
# Check if context router is wired
from super_council.memory_service import ContextRouter
# Or via MCP: recall.recent_events(limit=5)

# Expected: [] (execution history not captured yet)
# This is a known gap — context router needs wiring
```

**Action item:** Document this gap for future wiring.

## Phase 4: End-to-End Runtime Validation

### 4A. Full Pipeline Test

**Action:** Complete this session with:
1. A decision that differs from a carry_forward plan
2. File modifications (track actual work)
3. An open item carried forward

**Verification after session ends:**

1. Check session summary for deviations
2. Check unified recall for all three channels
3. Check memory rollups for new entries
4. Check context router for execution history

### 4B. Accuracy Scorecard

| Metric | Target | Actual |
|--------|--------|--------|
| Decisions captured | 100% of JSONL | ??? |
| Work completed accuracy | >80% match | ??? |
| Open items (no hallucination) | 0% noise | ??? |
| Deviations detected | ≥1 when plan differs | ??? |
| Unified recall (text) | Scored matches | ??? |
| Unified recall (structural) | Symbol matches | ??? |
| Unified recall (execution) | Events captured | ❌ Known gap |

## Files to Inspect

| File | Purpose |
|------|---------|
| `memory_service/session_watcher.py` | Deviation detection (line ~399) |
| `memory_service/layer.py` | Unified recall channels |
| `arc_summarizer/pipeline.py` | Consolidation → memory_rollups |
| `arc_summarizer/scheduler.py` | Tier triggering |
| `~/.council-memory/sessions/*.md` | Arc-written summaries |
| `~/.pi/agent/sessions/--home-chief--/*.jsonl` | Canonical JSONL source |
| `~/.council-memory/council_core.db` | All relational data |

## Completion Gates

- [ ] Deviation detected for main pi session (not just subagent chain)
- [ ] Deviation classification matches rules (planned/unplanned/optimization)
- [ ] Unified recall returns data from text + structural channels
- [ ] Memory rollups queried (timing gap documented)
- [ ] Context router gap documented (execution history empty)
- [ ] Accuracy scorecard completed
- [ ] Session summary accuracy vs JSONL validated

## Notes for Next Phase

If deviation detection works but arc summaries are still inaccurate, the issue is in the **extraction regex** (analyzer.py), not the deviation pipeline. The diary-first merge is wired but may need tighter extraction patterns.

If unified recall returns empty for text channel, check memsearch indexing (milvus.db). If structural channel is empty, check codegraph index status.

If memory rollups remain empty after daily tier runs, check `_gather_tier_input()` for daily tier (should read raw/diary entries).
