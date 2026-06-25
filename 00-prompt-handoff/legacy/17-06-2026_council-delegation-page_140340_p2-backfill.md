# Unit 2: Backfill Migration — 236 Historical Delegations

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 2 of 6
**Dependencies:** Unit 0 (schema + insert_delegation method must exist)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `scripts/backfill_delegations.py` — migration script (create)
- `~/.council-memory/reviews/deleg-*/` — source MD files
- `~/.council-memory/supervisor-logs/` — for from_model inference

## What This Phase Delivers

CLI script that scans `~/.council-memory/reviews/deleg-*/` directories, parses MD files, and inserts into `delegation_runs` table. Infers `from_model` from supervisor logs where available (±5s window on `DELEGATION START: {from} -> {to}`). Idempotent (skips existing chain_ids).

## Pre-Flight Checklist

- [ ] Unit 0 is complete (delegation_runs table exists)
- [ ] Verify MD file format: `ls ~/.council-memory/reviews/deleg-*/` (should show 236 dirs)
- [ ] Read one MD file to confirm format: `head -20 ~/.council-memory/reviews/deleg-1778597529/*.md`

## Implementation Steps

### Step 1: Create migration script

Create `scripts/backfill_delegations.py`:

```python
#!/usr/bin/env python3
"""Backfill delegation_runs table from filesystem MD files.

Usage: python scripts/backfill_delegations.py [--dry-run]

Scans ~/.council-memory/reviews/deleg-*/ directories.
Parses MD headers and content. Infers from_model from supervisor logs.
Idempotent: skips rows where chain_id already exists.
"""
import argparse
import glob
import os
import re
import sys
from pathlib import Path

# Parse MD file format:
# # Delegation Response
# - **Chain:** `deleg-1778597529`
# - **Role:** reviewer
# - **Alias:** reviewer-arch
# - **Batch:** 0
# - **Retry:** 0
# - **Time:** 2026-05-12 20:22:09
# - **Content:** 5535 chars
# ## Task
# [task text]
# ## Response
# [response text]

# Infer from_model from supervisor logs:
# Pattern: DELEGATION START: {from} -> {to}
# Match within ±5 seconds of delegation timestamp
```

**Algorithm:**
1. Scan `~/.council-memory/reviews/deleg-*/` directories
2. For each directory, read the MD file
3. Parse header fields (Chain, Role, Alias, Batch, Retry, Time, Content)
4. Extract task from `## Task` section, response from `## Response` section
5. Try to infer from_model from supervisor logs (scan all `supervisor-logs/supervisor.log*`)
6. Call `relational_store.insert_delegation()` (skip if chain_id exists — catch IntegrityError)
7. Log summary: total processed, from_model inferred count, from_model unknown count

### Step 2: Run migration

```bash
cd /home/chief/Coding-Projects/7-council
python super_council/scripts/backfill_delegations.py --dry-run  # preview first
python super_council/scripts/backfill_delegations.py              # execute
```

### Step 3: Verify

```sql
SELECT COUNT(*) FROM delegation_runs;  -- should be 236
SELECT from_model, COUNT(*) FROM delegation_runs GROUP BY from_model;  -- check distribution
SELECT * FROM delegation_runs ORDER BY id DESC LIMIT 3;  -- spot check
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `scripts/backfill_delegations.py` | CLI migration script |

## Phase-Specific Tests

1. `--dry-run` mode lists files without inserting
2. Script processes all 236 delegation directories
3. Idempotent: running twice doesn't duplicate rows
4. from_model inference works for recent delegations (Jun 16+)
5. from_model = 'unknown' for older delegations without log correlation

## Completion Gate

- [ ] Script runs without errors
- [ ] `SELECT COUNT(*) FROM delegation_runs` = 236 (or current count)
- [ ] from_model distribution logged (how many inferred vs unknown)
- [ ] Idempotent: second run = 0 new rows
- [ ] Spot check: 3 random delegations have correct data

## Notes for Next Phase

- Unit 1 (API) will serve this data
- If from_model is 'unknown' for most delegations, that's expected (logs don't go back to May 12-20)
