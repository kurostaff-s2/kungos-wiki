# Arc Summarizer — Remaining Work

> Core consolidation pipeline (ArcPipeline) is fully implemented and wired. Items below are not yet live.

## Not Yet Implemented

### 1. TTL Lifecycle Manager

**What:** Transition `memory_rollups` entries through TTL phases: `active` → `aging` → `expired`

**Current state:** `ttl_days` column exists with tier-specific defaults (14d daily, 30d short, 60d weekly, 90d bimonthly). No code transitions entries between phases or cleans up expired entries.

**Why needed:** Graceful expiry prevents stale digests from polluting recall. Currently all entries stay active forever.

**Options:**
- **A.** Eager transitions: Scheduler checks TTL on each cycle, updates phase in DB
- **B.** Lazy transitions: Compute phase on-the-fly during queries (no DB write)
- **C.** Hybrid: Lazy for reads, eager batch update during scheduler cycles

**Open question:** Aging threshold — 75% of TTL, or fixed N-day warning window?

---

### 2. Auto-Tagging Rollups

**What:** Automatically derive tags (topics, projects, domains) from rollup content

**Current state:** Not implemented. No tag column or taxonomy defined.

**Options:**
- **A.** Rule-based: Extract file paths, function names, project keywords via regex
- **B.** LLM-assisted: Send to Arc with extraction schema → structured tags
- **C.** Hybrid: Rule-based first pass, LLM refinement on high-value entries

**Open questions:**
- Tag taxonomy? (free-form vs controlled vocabulary)
- Storage format? (JSON array in one column, or separate tags table?)
- When does tagging run? (on upsert, or batch during consolidation?)

---

### 3. Legacy Data Cleanup

**What:** Archive or remove legacy duplicate rollups (pre-June 16, timestamp-based IDs)

**Current state:** ~10 sessions with 2-6 duplicate rollups each. Deterministic ID scheme (`rollup-daily-{source_id}`) prevents new duplicates.

**Options:**
- **A.** Soft archive: Mark legacy duplicates as `archived` state, exclude from queries
- **B.** Hard delete: Remove duplicates, keep only the latest per source_id
- **C.** Merge: Consolidate duplicate content into single rollup

**Risk:** Hard delete is irreversible. Soft archive preserves data but adds query complexity.

---

### 4. Failed Session Retry

**What:** Retry the ~24 sessions that failed with `partial failure: not all 1 parts succeeded`

**Current state:** Sessions exist in DB but rollups are unlinked. Some have empty `summary_text`.

**Options:**
- **A.** Manual retry: Re-run consolidation for specific source_files
- **B.** Automatic retry: Scheduler detects failed state, retries on next cycle
- **C.** Investigate first: Root-cause the failures (context overflow? malformed input?) before retrying

---

## Deferred / Decided Against

- **ArcSummarizer facade** — Removed 2026-06-16. Never instantiated in production; `council_main.py` had `self._arc = None` and startup consolidation was dead code.
- **Confidence-calibrated injection** — Low value until confidence scores are stored structurally.
- **Health dashboard as dedicated MCP tool** — Rejected. Wired into `system_health` as consolidation metrics section instead.
- **session_diary table** — Dropped 2026-06-12. Replaced by `memory_rollups` as single source of truth.
- **consolidation_cache table** — Zombie table (exists but empty). All consolidation data lives in `memory_rollups`.

## Test Coverage

| Feature | Tests | Status |
|---------|-------|--------|
| Consolidation pipeline (ArcPipeline) | ✅ | Passing |
| ArcClient (HTTP + retry) | ✅ | Passing |
| LLMRequestQueue | ✅ | Passing |
| TierWriter | ✅ | Passing |
| ConsolidationStore | ✅ | Passing |
| TTL lifecycle | 0 | ❌ Not implemented |
| Auto-tagging | 0 | ❌ Not implemented |
