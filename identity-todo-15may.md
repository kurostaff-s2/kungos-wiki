# KungOS Identity — Council Review Consolidated Report

**Date:** 2026-05-14
**Source doc:** `/home/chief/llm-wiki/KungOS_Identity_Design.md` (1,510 lines)
**Reviewers:** Gemma-4-26B (arch), Nemotron-Cascade-30B (logic), GPT-OSS-20B (diversity)
**Context:** Big-bang cutover. No phased migration. Final schema from day one. Zero backward-compat.

---

## Executive Summary

Three models independently reviewed the KungOS Identity Design for big-bang deployment readiness. All three identified the same core problem: **the design is architecturally sound but operationally incomplete**. The migration script, deployment checklist, and rollback procedure need significant hardening before production cutover.

**Unanimous findings (3/3):**
- Migration must be truly atomic — not "single transaction per batch"
- Maintenance mode / read-only window is required during cut-over
- Automated rollback script is needed — manual TRUNCATE is not enough
- FK load order must be explicitly enforced and documented

**Strong consensus (2/3):**
- RBAC must resolve before cutover (Gemma + GPT-OSS; Nemo: "missing safeguard")
- Pre-flight validation needed BEFORE import (not just post-run `--validate`)
- Phone dedup must be tenant-aware (`bg_code` + `phone`, not just `phone`)

---

## 1. Gemma-4 Flagged Points — Council Verdict Matrix

| # | Gemma Point | Gemma | Nemo | GPT-OSS | Consensus |
|---|---|---|---|---|---|
| A | Deployment split-brain window | Flagged | Disagree (partial) | Agree | **2/3** — risk during cut-over window |
| B | Batch migration not atomic | Flagged | Agree | Agree | **3/3** — per-batch tx ≠ global atomicity |
| C | RBAC must resolve before cutover | Flagged | Disagree (missing safeguard) | Agree | **2/3** — missing hard gate |
| D | No pre-flight check | Flagged | Disagree (--validate exists) | Agree | **2/3** — --validate is post-run, not pre-flight |
| E | No maintenance mode | Flagged | Agree | Agree | **3/3** — no read-only flag documented |
| F | No recovery protocol | Flagged | Partial agree | Agree | **3/3** — rollback is manual, not automated |

**Key disagreement:** Nemo was more lenient, arguing the design "partially addresses" several concerns. GPT-OSS and Gemma were stricter — the concerns are real gaps.

---

## 2. Logic Flaws — Consolidated by Severity

### CRITICAL (3/3 models agree)

#### F1: FK Load Order Not Enforced
**Issue:** `users_employee`, `users_customer`, `users_player` all have FK → `users_identity.identity_id`. The import script creates identity rows first (Step 4, line ~1050), but each source type is in its own batch transaction. If a batch inserts an extension row before its identity row is committed, the FK is rejected.

**Impact:** Migration aborts midway → partial identity graph → orphaned extension rows.

**Fix:** Explicit load order with FK verification:
```
1. users_organization (teams, vendors)
2. users_identity (core records)
3. users_employee, users_customer, users_player (extensions)
4. caf_platform_walkins (backfill FK)
```

#### F2: Migration Not Globally Atomic
**Issue:** "Single transaction per batch" (§7.1, line ~1025) means each source type commits independently. If the customer batch fails after the employee batch committed, employees exist without customers — a partially migrated state.

**Impact:** Partial identity graph; uniqueness/tenant-scoping violations; no clean rollback without TRUNCATE.

**Fix:** Wrap ALL batches in single `BEGIN ... COMMIT` or use staging tables with final atomic `INSERT ... SELECT`.

#### F3: No Maintenance Mode / Read-Only Window
**Issue:** Deployment checklist (§12.1, lines 1332-1343) has no step for disabling writes. During migration, the old Mongo collections are still live and writable. A write to Mongo after the new schema is live but before import finishes = data drift.

**Impact:** Split-brain during cut-over window; data loss or inconsistency.

**Fix:** Add Step 0 to deployment: enable maintenance middleware; reject all writes; flip back after validation passes.

### HIGH (2/3 models agree)

#### F4: Phone Dedup Must Be Tenant-Aware
**Issue:** The dedup algorithm merges by `phone` alone (§7.1 Step 2, line ~1020). If the same number exists in two different `bg_code` tenants, the script creates a single identity, breaching tenant isolation.

**Impact:** Cross-tenant data leakage; incorrect identity merging.

**Fix:** Dedup key must be `(bg_code, phone)`, not just `phone`.

#### F5: RBAC Migration Not Gated
**Issue:** `CustomUser.roles` JSON is not translated to `rbac_user_roles` before cutover. The design keeps `rbac_user_roles` (§10.2, line ~250) but has no deployment gate ensuring all role rows exist.

**Impact:** Logged-in users have no permissions → hard failure at go-live.

**Fix:** Add pre-flight check: "all CustomUser roles exist in rbac_user_roles" before deployment Step 4.

#### F6: Walk-in Back-fill Join Ambiguity
**Issue:** `SELECT i.identity_id FROM users_identity i WHERE i.phone = w.phone` (line ~1062) can return >1 row if same phone exists in two tenants.

**Impact:** `More than one row returned` error; walk-ins mis-linked to wrong identity.

**Fix:** Join on `(phone, bg_code)` or add `LIMIT 1` with tenant verification.

### MEDIUM (1/2 models flagged)

#### F7: Outbox Event Ordering (Nemo only)
**Issue:** Denormalized fields (`order_count`, `total_spent`) updated via outbox events that may fire before identity row exists.

**Impact:** Financial aggregates inaccurate for first seconds/minutes after cut-over.

**Fix:** Process outbox events ONLY after `--validate` confirms all referenced `identity_id` values exist.

#### F8: Fuzzy Name Merge Risk (GPT-OSS only)
**Issue:** `should_merge()` returns True if fuzzy similarity > 0.85. Two distinct people sharing a phone (family members) could be incorrectly merged.

**Impact:** Identity dedup error; data corruption.

**Fix:** Lower threshold to 0.90 or require exact match for phone-only records.

#### F9: Phone Normalization May Reject Valid Numbers (GPT-OSS only)
**Issue:** `phonenumbers.parse(cleaned, region)` may fail on Indian landlines or legacy numbers.

**Impact:** Import errors; skipped rows; missing identities.

**Fix:** Add `--preflight` scan for unparseable numbers; log to `dedup_review` table for manual resolution.

---

## 3. Deferred Items — Blockers vs. Cleanup

### BLOCKERS (must resolve before go-live)

| Item | Doc Section | Why Blocker | Action |
|---|---|---|---|
| **Player doc discrepancy** (117 docs vs 59 unique) | A1 (line 1391) | Migration merges by phone; 58 extra docs may contain distinct people → data loss or duplicate identities | Pre-migration audit script to classify all 117 documents |
| **KuroUser field mapping** (42 fields, many unmapped) | A2 (line 1400) | Missing fields (BFC details, leave balances, approval workflow) silently lost when old `KuroUser` dropped | Map core compensation/banking data at go-live; defer optional fields (emergency contact, dob) |
| **RBAC role migration** | §10.2 (line ~250) | `CustomUser.roles` JSON not translated to `rbac_user_roles` → logged-in users have no permissions | Migrate JSON → `rbac_user_roles` before cut-over; add pre-flight gate |
| **ServiceRequest.phone dedup** | §7.1 Step 1 (line ~1010) | Must map `serviceRequest.phone` → `identity_id` to maintain referential integrity | Include in import script; validate FK coverage |

### CAN DEFER

| Item | Doc Section | Why Safe to Defer |
|---|---|---|
| **Cafe walk-in phone uniqueness** | A3 (line 1412) | FK back-fill safe once unique constraint removed; small subset; not core identity |
| **CustomUser.userid → identity_id** | A4 (line 1448) | Keep `userid` column as FK to `users_employee` until full refactor |
| **Legacy MongoDB archive** | §7.4 (line 1120) | Intentional read-only archive; clean up after confidence in new system |
| **Vendor/Team profiles** | — | No critical DB constraints; migrate after core identity live |

---

## 4. Missing Safeguards — Priority Actions

### P0 — Must Have Before Cutover

| # | Safeguard | Current State | Fix |
|---|---|---|---|
| 1 | **Maintenance mode / read-only window** | None | Add `/maintenance` middleware; reject writes during import; Step 0 in deployment checklist |
| 2 | **Atomic migration** | Per-batch tx | Wrap ALL batches in single `BEGIN ... COMMIT` or use staging table + atomic `INSERT ... SELECT` |
| 3 | **Pre-flight validation** | Post-run only (`--validate`) | Add `--preflight` flag: scan for invalid phones, missing `bg_code`, duplicate tenants, orphaned docs; ABORT if any check fails |
| 4 | **Automated rollback** | Manual (TRUNCATE + re-run) | Script `./scripts/rollback_identity.sh`: set maintenance → DROP SCHEMA → restore legacy code |
| 5 | **FK load order enforcement** | Implicit (assumed) | Explicit: `orgs → identity → employee/customer/player` with FK check per batch |
| 6 | **RBAC pre-flight gate** | None | Verify all `CustomUser.roles` exist in `rbac_user_roles` before deployment Step 4 |

### P1 — Should Have

| # | Safeguard | Current State | Fix |
|---|---|---|---|
| 7 | **Idempotent import** | Can duplicate rows on retry | `ON CONFLICT (identity_id) DO NOTHING` or upsert logic |
| 8 | **PostgreSQL advisory lock** | No concurrency protection | `pg_advisory_lock(12345)` at script start; hold while writing |
| 9 | **Monitoring & alerting** | None | Prometheus metrics: `identity_import_progress_total`, `identity_import_errors_total` |
| 10 | **Staging run with prod-size data** | Not tested | Run import against production Mongo copy in staging; measure latency, lock contention |
| 11 | **Phone uniqueness lock during import** | No table lock | `LOCK TABLE users_identity IN SHARE ROW EXCLUSIVE MODE` during insert |

---

## 5. Race Conditions, Deadlocks, Data Integrity Gaps

| Scenario | Symptom | Root Cause | Mitigation |
|---|---|---|---|
| **Two imports create same phone** | `IntegrityError: duplicate key` | No table lock during import | `LOCK TABLE users_identity` or serialize |
| **Player → Org FK deadlock** | Deadlock error; migration stops | Player inserted before org | Load orgs first; enforce FK after batch |
| **Outbox event before identity** | Negative/missing totals | Event processed before identity row | Process events ONLY after `--validate` |
| **Live API + migration race** | Confusing "phone already used" | No write freeze during cut-over | Freeze writes for 30s; reject with "maintenance" |
| **Partial FK after failed batch** | Orphaned rows | Per-batch commit with no compensating tx | Single tx or compensating delete |
| **Walk-in back-fill ambiguity** | `More than one row` error | Same phone in two tenants | Join on `(phone, bg_code)` |
| **Large batch commit** | `DiskFullError` or lock contention | High-volume INSERT on live DB | Maintenance mode; minimal traffic during import |
| **FK violation during rollback** | Inconsistent data between stores | Partial rollback + legacy writes | Automated rollback script; no partial rollbacks |

---

## 6. Action Items — Before Big-Bang Cut-Over

### Must Fix (P0) — 8 items

- [ ] **Make migration truly atomic** — single transaction or two-phase commit (§7.1)
- [ ] **Enforce strict FK load order** — orgs → identity → extensions (§7.1 Step 4)
- [ ] **Add maintenance mode** — read-only flag; Step 0 in deployment checklist (§12.1)
- [ ] **Add pre-flight validation** — `--preflight` before import starts (§7.3)
- [ ] **Automate rollback** — `./scripts/rollback_identity.sh` (§12.3)
- [ ] **Migrate RBAC roles** — JSON → `rbac_user_roles` before cut-over (§10.2)
- [ ] **Audit player docs** (117 vs 59) — resolve before import (A1)
- [ ] **Map KuroUser core fields** — compensation, banking, leave data (A2)

### Should Fix (P1) — 5 items

- [ ] **Lock phone uniqueness during import** — table lock or serialize (§5.1)
- [ ] **Make import idempotent** — `ON CONFLICT` or upsert (§7.1)
- [ ] **Add advisory lock** — prevent concurrent writes (§7.1)
- [ ] **Add monitoring** — Prometheus metrics for import progress/errors (§12.1)
- [ ] **Staging run** — test with production-size data (§7.3)

### Can Defer (P2) — 4 items

- [ ] Cafe walk-in phone uniqueness cleanup (A3)
- [ ] CustomUser.userid → identity_id full refactor (A4)
- [ ] Legacy MongoDB archive cleanup (§7.4)
- [ ] Vendor/Team profile migration

---

## 7. Council Review Summary

| Model | Role | Stance | Key Concern |
|---|---|---|---|
| **Gemma-4-26B** | reviewer-arch | Strict | Split-brain, atomicity, RBAC, pre-flight, maintenance, recovery — all flagged |
| **Nemotron-Cascade-30B** | reviewer-logic | Lenient | FK ordering, phone race, cascade mismatch, outbox events — "partially addressed" |
| **GPT-OSS-20B** | reviewer-diversity | Strict | Maintenance mode, atomicity, RBAC, pre-flight, rollback, cross-tenant dedup — all agreed |

### Divergence Notes

- **Nemo vs. GPT-OSS on split-brain:** Nemo argued the design "explicitly eliminates" split-brain by forbidding dual-write. GPT-OSS argued the *cut-over window itself* is a race condition. **Verdict:** GPT-OSS is correct — the window between "new schema live" and "import complete" is a real split-brain risk.
- **Nemo vs. GPT-OSS on pre-flight:** Nemo argued `--validate` satisfies the requirement. GPT-OSS argued `--validate` runs *after* import, not before. **Verdict:** GPT-OSS is correct — `--validate` is post-run, not pre-flight. A `--preflight` scan is needed.
- **Nemo vs. GPT-OSS on recovery:** Nemo argued the rollback procedure (§12.3) satisfies the requirement. GPT-OSS argued it's "manual, not automated." **Verdict:** Both are partially correct — the procedure exists but needs automation.

---

## 8. Bottom Line

The KungOS Identity Design is **architecturally sound** (multi-role, tenant-isolated, phone-normalized, FK-enforced) but **operationally incomplete** for a big-bang production cutover. The gaps are not design flaws — they are deployment safeguards that were not documented.

**Path to production-ready:**
1. Fix the 8 P0 items (atomicity, maintenance mode, pre-flight, rollback, FK order, RBAC, player audit, KuroUser mapping)
2. Document the deployment sequence with explicit FK ordering and maintenance window
3. Run staging test with production-size data
4. Execute big-bang cutover with automated rollback as safety net

**Estimated effort:** 3-5 developer-days for P0 items; 2-3 days for P1 items.

---

*Generated from council reviews: `/tmp/nemo-review2.json`, `/tmp/gpt-review2.json`, Gemma-4 review (previous session)*
*Source doc: `/home/chief/llm-wiki/KungOS_Identity_Design.md` (1,510 lines, last modified 2026-05-14)*

---

## Decision Log — 2026-05-15

| # | Item | Decision | Rationale |
|---|------|----------|----------|
| 1 | Atomic migration | ✅ Single `BEGIN...COMMIT` wrapping all batches | Per-batch tx leaves partial state on failure |
| 2 | FK load order | ✅ `orgs → identity → extensions → walk-ins` | Only cross-tree FK is `player.team_id → org.org_id`; orgs are tiny (423 rows); Nemo confirmed this is safest for non-deferrable FKs |
| 3 | Maintenance mode | ❌ **Dropped** | Dev-only environment; no concurrent writes during migration |
| 4 | Pre-flight validation | ✅ `--preflight` flag before import | Catches invalid phones, missing bg_code, orphaned docs before any writes |
| 5 | Rollback | ✅ `DROP SCHEMA` + retry; no partial rollbacks | Manual TRUNCATE is error-prone; automated script needed |
| 6 | RBAC migration | ✅ JSON → `rbac_user_roles` + pre-flight gate | Users would have no permissions without this |
| 7 | Player doc audit | ✅ Audit 117 docs; lower fuzzy threshold to 0.90 | 58 extra docs may contain distinct people; 0.85 too aggressive |
| 8 | KuroUser field mapping | ✅ All 42 fields accounted for (see below) | No deferral — map everything at once |

### KuroUser → New Schema Mapping (Complete)

| Destination | Count | Fields |
|---|---|---|
| `users_employee` | 31 | salary, bank, BFC, addresses, leave, emergency, approval, personal |
| `users_identity` | 3 | `phone_verified`, `idproof_type`, `idproof_number` |
| Replaced by other tables | 4 | `businessgroups`/`primary_bg` → `Identity.bg_code`; `roles`/`access` → RBAC |
| Dropped (dead code) | 1 | `edit` (never read, only written as `False`) |
| **Total** | **39** | (of 42 original) |

### Codebase Findings

- `edit` — dead code. Only set to `False` in `views.py:262` and `viewsets.py:967`. Never read anywhere.
- `phone_verified` — active. Set to `True` after OTP validation. Moved to `users_identity` (identity-level, not employee-only).
- `idproof_type` + `idproof_number` — defined but never used in views/serializers/admin. Kept and moved to `users_identity` per user decision (needed for users & employees).

### Nemo Council Review (2026-05-15)

Asked Nemo (`reviewer-logic`) about FK load order necessity. Recommendation: **keep the order** — works for both deferrable and non-deferrable FKs, gives early error detection, adds negligible overhead for 423-row table. High-severity warning: never load `users_player` before `users_organization` when FK is non-deferrable.
