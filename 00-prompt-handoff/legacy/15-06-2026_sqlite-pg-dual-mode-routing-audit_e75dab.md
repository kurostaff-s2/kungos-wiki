# SQLite/PostgreSQL Dual-Mode Routing Audit

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `e75dab` |
| Entity type | `session` |
| Short description | Audit whether SQLite/PostgreSQL dual-mode routing is justified or legacy baggage that should be stripped to SQLite-only |
| Status | `draft` |
| Source references | `super_council/api/db.py`, `super_council/api/core.py`, `super_council/api/revision.py`, `super_council/api/idempotency.py`, `super_council/api/outbox_writer.py` |
| Generated | `15-06-2026` |
| Next action / owner | Agent: execute 3-phase audit (ground truth → code survey → recommendation) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/.pi/agent/skills/first-principles-analysis/SKILL.md`
**Key files for this task:**
- `api/db.py` — `_SQL_NOW`, `SCHEMA`, database URL parsing
- `api/core.py` — `SCHEMA` usage, `_fq()` helper, `RESOURCE_MAP`
- `api/revision.py` — `UPDATE` statements with `_SQL_NOW`
- `api/idempotency.py` — Dual-mode table creation & queries
- `api/outbox_writer.py` — PostgreSQL outbox pattern (SQLite no-op)
- `server.py` — Route registration, CORS config

**Related codebases:** None (self-contained API)

---

## Background

The Super Council API was originally designed for PostgreSQL with multi-schema support (`council_core` schema). During the frontend wiring session (commit `396c401`), dual-mode routing was added to also support SQLite. The live database is SQLite-only at `~/.council-memory/council_core.db`.

**The question:** Is dual-mode routing justified, or is it legacy baggage that should be stripped to SQLite-only?

### Pre-Analysis Hypothesis (to challenge)

The initial first-principles pass suggested SQLite-only is correct because:
- Live database is SQLite only
- No PostgreSQL instance is running
- All data lives in SQLite
- Single-user dev environment

**This hypothesis needs verification, not assumption.** The audit must:
1. Confirm the ground truths (is PostgreSQL actually dead, or is there a planned migration?)
2. Survey the actual conditional code (how many lines, what's the maintenance cost?)
3. Evaluate whether the "cost" of SQLite-only vs dual-mode is material at this scale

---

## Phase 1: Ground Truth Verification

**What:** Confirm the actual database topology — is PostgreSQL truly absent, or is there a planned path?

**Steps:**

1. **Check PostgreSQL connectivity**
   - Run: `python3 -c "import os; print(os.environ.get('DATABASE_URL', 'not set'))"`
   - Check if any PostgreSQL service is running: `systemctl status postgresql` or `pg_isready`
   - Check if `council_core` schema exists anywhere: `psql -U <user> -d <db> -c "\dn"` (if PostgreSQL is accessible)

2. **Check database file**
   - Confirm SQLite file exists: `ls -la ~/.council-memory/council_core.db`
   - Check file size and last modified: `stat ~/.council-memory/council_core.db`
   - Verify it's the active database: `sqlite3 ~/.council-memory/council_core.db ".tables"`

3. **Check project documentation / config**
   - Search for PostgreSQL references in project docs: `grep -r "postgresql\|postgres\|pg_" /home/chief/Coding-Projects/7-council/ --include="*.md" --include="*.yaml" --include="*.json" | head -20`
   - Check if there's a deployment config that expects PostgreSQL: `grep -r "DATABASE_URL\|POSTGRES" /home/chief/Coding-Projects/7-council/super_council/ --include="*.env*" --include="*.yaml" --include="*.json"`

4. **Check git history for intent**
   - Run: `cd /home/chief/Coding-Projects/7-council/super_council && git log --oneline --all --grep="postgres\|PostgreSQL\|pg_" | head -10`
   - Check if original codebase was PostgreSQL-first: `git log --oneline -1 -- api/core.py`

**Tests:**
- [ ] PostgreSQL instance status confirmed (running / not running)
- [ ] SQLite file confirmed as active database
- [ ] No deployment config requires PostgreSQL
- [ ] Git history shows intent (or lack thereof) for PostgreSQL support

---

## Phase 2: Code Survey

**What:** Quantify the dual-mode routing surface area — how many lines, how many conditionals, what's the actual cost?

**Steps:**

1. **Map all dual-mode conditionals**
   - Search for PostgreSQL-specific patterns: `grep -rn "postgresql\|postgres\|_SQL_NOW\|SCHEMA\|_fq\|outbox\|idempotency" super_council/api/ --include="*.py"`
   - For each match, classify: `postgresql-only`, `sqlite-only`, `dual-conditional`

2. **Count lines of conditional code**
   - Count lines in each file that are dual-mode specific (not pure SQLite or pure PostgreSQL)
   - Estimate maintenance cost per file

3. **Identify dead code paths**
   - Mark which conditionals evaluate to `False` in current runtime (SQLite mode)
   - Mark which conditionals evaluate to `True` in current runtime (SQLite mode)

4. **Survey SQLAlchemy usage**
   - Check if SQLAlchemy ORM is used (which would abstract dialect differences) or raw SQL (`sa_text`)
   - If raw SQL: quantify how many queries would need rewriting for PostgreSQL

**Output artifact:** Produce a table:

| File | Total Lines | Dual-Mode Lines | Dead Code (PG) | Live Code (SQLite) | Risk if Stripped |
|------|-------------|-----------------|----------------|---------------------|-------------------|
| `db.py` | ... | ... | ... | ... | ... |
| `core.py` | ... | ... | ... | ... | ... |
| `revision.py` | ... | ... | ... | ... | ... |
| `idempotency.py` | ... | ... | ... | ... | ... |
| `outbox_writer.py` | ... | ... | ... | ... | ... |

**Tests:**
- [ ] All dual-mode conditionals cataloged
- [ ] Dead code quantified (line count + files)
- [ ] Risk assessment per file completed

---

## Phase 3: Recommendation & Plan

**What:** Produce a clear recommendation with trade-offs and implementation plan.

**Steps:**

1. **Evaluate 3 options:**

   | Option | Description | Pros | Cons | Effort |
   |--------|-------------|------|------|--------|
   | A: SQLite-only | Strip all PostgreSQL conditionals | Simple, no dead code | Can't switch to PG later without rework | ~1-2 hrs |
   | B: Dual-mode (current) | Keep conditionals | "Future-proof" for PG migration | ~80 lines of dead code, mental overhead | 0 hrs (status quo) |
   | C: SQLAlchemy ORM | Replace raw SQL with ORM | True dual-mode without conditionals | Major refactor, ~3-5 days | ~3-5 days |

2. **Apply first-principles gates:**
   - Does Option A violate any ground truth? (only if PG is actually needed)
   - Does Option B earn its complexity? (only if PG migration is planned)
   - Does Option C justify the cost? (only if dual-mode is actually needed)

3. **Produce recommendation** with:
   - Clear choice (A, B, or C)
   - Justification traceable to ground truths from Phase 1
   - If A: list exact files/lines to remove
   - If B: document which conditionals are justified vs which are dead
   - If C: produce migration plan from raw SQL to ORM

4. **If Option A (SQLite-only):** produce a concrete diff plan:
   - `db.py`: Remove `_SQL_NOW` conditional, hardcode `datetime('now','utc')`
   - `db.py`: Remove `SCHEMA` conditional, hardcode `""`
   - `core.py`: Remove `_fq()` helper, use direct table names
   - `core.py`: Remove `SCHEMA` from `RESOURCE_MAP` conditionals
   - `revision.py`: Use `datetime('now','utc')` directly
   - `idempotency.py`: Remove PostgreSQL table creation, keep SQLite-only
   - `outbox_writer.py`: Simplify to pure no-op (remove PostgreSQL branch)

**Tests:**
- [ ] Recommendation traceable to Phase 1 ground truths
- [ ] Trade-offs explicitly acknowledged
- [ ] Implementation plan includes exact file/line changes
- [ ] Revisit triggers defined (when to reconsider)

---

## Constraints

- **No schema changes** — do not alter the SQLite database schema during this audit
- **No runtime changes** — this is analysis only; do not modify code until recommendation is approved
- **Evidence-first** — every conclusion must cite specific code, config, or git history
- **Language consistency** — use `SQLite` and `PostgreSQL` (never `sqlite3`, `pg`, `psql` as nouns)

---

## Success Criteria

- [ ] Ground truths verified (PostgreSQL status, SQLite status, deployment config)
- [ ] Dual-mode code surface area quantified (line counts per file)
- [ ] Dead code paths identified and documented
- [ ] Recommendation produced with trade-off analysis
- [ ] Implementation plan includes exact file/line changes (if SQLite-only chosen)
- [ ] Revisit triggers defined (when PostgreSQL might actually be needed)
- [ ] Handoff doc updated with final recommendation

---

## Caveats & Uncertainty

1. **PostgreSQL may be planned** — if there's a deployment target that requires PostgreSQL, the analysis changes. Check with project owner if uncertain.
2. **Original codebase intent** — the original `super_council.py` (8829 lines, deleted) was PostgreSQL-first. The reason for that choice may be documented in git history.
3. **Team context** — if multiple developers work on this, dual-mode may be justified for local dev flexibility (some devs may prefer PostgreSQL locally).
4. **Migration path** — if PostgreSQL is eventually needed, the migration cost from SQLite-only vs dual-mode should be quantified.

---

## Output Location

Save findings to: `/home/chief/llm-wiki/00-prompt-handoff/15-06-2026_sqlite-pg-dual-mode-routing-audit_e75dab.md` (this file)

Update the status field to `complete` when all success criteria are met.
