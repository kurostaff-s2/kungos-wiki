# Arc Summarizer — Remaining Work

> Items not yet live. Core arc summarizer (Units 1-5) is fully implemented and wired.

## Not Yet Implemented

### 1. TTL Lifecycle Manager

**What:** Transition `session_diary` entries through TTL phases: `active` → `aging` → `expired`

**Current state:** `ttl_phase` column exists with default `'active'`. No code transitions entries between phases or cleans up expired entries.

**Why needed:** Graceful expiry prevents stale digests from polluting recall. Currently all entries stay `'active'` forever.

**Options:**
- **A.** Eager transitions: Scheduler checks TTL on each cycle, updates `ttl_phase` in DB
- **B.** Lazy transitions: Compute phase on-the-fly during queries (no DB write)
- **C.** Hybrid: Lazy for reads, eager batch update during scheduler cycles

**Open question:** Aging threshold — 75% of TTL, or fixed N-day warning window?

---

### 2. Confidence-Calibrated Injection

**What:** Gate knowledge card injection by confidence scores (`high`/`medium`/`low`)

**Current state:** Prompt schemas emit confidence per decision/item. `inject_tier1()` loads all active cache entries indiscrimutately.

**Why needed:** Prevent low-confidence items from polluting system prompt context.

**Options:**
- **A.** Hard gate: Only inject `confidence: high` items
- **B.** Tiered injection: High → full card, medium → summarized, low → omitted
- **C.** Config threshold: Let `config-subsystem.json` set cutoff

**Caveat:** Confidence scores are in YAML response but flattened to text in DB. Need structural storage or re-parsing.

---

### 3. Auto-Tagging Session Diary

**What:** Automatically derive tags (topics, projects, domains) from session diary content

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

### 4. Recall Backend First-Call Issue

**What:** `recall.unified()` returns `backend_unavailable` on first call, works on retry

**Current state:** Happens every session. Second call succeeds.

**Suspected cause:** MemSearch/Milvus lock contention or cold start latency.

**Investigation needed:** Check milvus_lite startup, lock acquisition timing, connection pooling.

---

## Deferred / Decided Against

- **Health dashboard as dedicated MCP tool** — Rejected. Wired into `unified_log_recall` as `consolidation_metrics` section instead. Diagnostic, not model context.
- **Confidence-calibrated injection as high priority** — Low value until confidence scores are stored structurally.

## Test Coverage

| Feature | Tests | Status |
|---------|-------|--------|
| Tiered consolidation (Units 1-5) | 76 | ✅ All passing |
| Consolidation metrics | 17 | ✅ All passing |
| TTL lifecycle | 0 | ❌ Not implemented |
| Confidence injection | 0 | ❌ Not implemented |
| Auto-tagging | 0 | ❌ Not implemented |
| **Total** | **93** | **93 passing, 0 failing** |
