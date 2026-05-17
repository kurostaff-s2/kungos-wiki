# Chief Review — Spec Council Assessment

**Date:** 2026-05-17  
**Scope:** 7 spec files (~102KB) in `specs/database_schemas/` and `specs/domain_specs/`  
**Reviewers:** Gemma-4-26B (arch), Nemotron-Cascade-30B (logic/security), GPT-OSS-20B (ops/developer experience)  
**Method:** Sequential delegation via `/v1/council/delegate` (VRAM-safe, one-at-a-time)

---

## Executive Summary

All three reviewers agree: **the specs are architecturally sound and form a coherent system**, but there are operational and security gaps that must be closed before implementation begins.

The specs correctly implement KungOS principles (identity-first, tenant isolation, outbox pattern, protocol interfaces). The gaps are mostly *how to run it* rather than *what to build*.

---

## Council Verdicts

### Gemma-4 (Architecture Review)
- **Verdict:** Architecturally sound, operationally risky
- **Strengths:** Identity integration is strong, order/procurement bridge is coherent, migration plan is robust
- **Concerns:** MongoDB naming skew (security), Cafe domain protocol bypass, missing DLQ for outbox failures

### Nemotron-Cascade (Logic & Security Review)
- **Verdict:** 4 CRITICAL, 6 HIGH, 9 MEDIUM findings
- **Strengths:** Comprehensive security surface analysis, line-referenced findings, actionable remediation
- **Concerns:** Privilege escalation via JSON role columns, cross-tenant data exposure from tenant field mismatch, financial double-spend from missing webhook HMAC, split-brain from cross-store writes

### GPT-OSS (Ops & Developer Experience Review)
- **Verdict:** Buildable but assumes mature ops practice not documented
- **Strengths:** Best-written multitenant modernization spec seen, tenant isolation baked into every data model
- **Concerns:** No backup/DR strategy, no monitoring/alerting, no migration orchestration, no outbox worker implementation, no rate limiting on identity lookup

---

## Consolidated Findings

### CRITICAL (4 items — all must be fixed before implementation)

| # | Issue | File(s) | Risk |
|---|---|---|---|
| **C1** | MongoDB tenant field naming skew (`bgcode` vs `bg_code`) | `mongodb_schema.md` §2.1 | Cross-tenant data exposure |
| **C2** | Split-brain on cross-store writes (PG + Mongo in same request) | `cafe_spec.md` §2.4, `ecommerce_spec.md` §7.1 | Financial inconsistency |
| **C3** | Cashfree webhook missing HMAC-SHA256 verification | `ecommerce_spec.md` §6.2 | Payment replay/forge attacks |
| **C4** | JSON columns for roles/businessgroups — no FK enforcement | `postgresql_schema.md` §2.2 | Privilege escalation |

### HIGH (6 items — fix before Phase 4)

| # | Issue | File(s) | Risk |
|---|---|---|---|
| **H1** | Cafe `OrderGateway` bypasses protocol layer | `cafe_spec.md` §1.2 | Tight coupling, God object |
| **H2** | Walk-in phone UNIQUE constraint conflicts with `users_identity` | `cafe_spec.md` §7.1 | Duplicate-key errors on registration |
| **H3** | Migration validates per-tenant phone uniqueness, not cross-tenant | `migration_spec.md` §2 | Cross-tenant identity collision |
| **H4** | Dual-read middleware doesn't rewrite writes (only reads) | `migration_spec.md` §4 | Orphaned documents with legacy fields |
| **H5** | Walk-in wallet orphan risk — `user=NULL` → `identity_id=NULL` | `migration_spec.md` §3 | Broken FK, orphaned wallets |
| **H6** | No outbox event schema — events referenced but not defined | All domain specs | Implementation drift |

### MEDIUM (5 items — fix during implementation)

| # | Issue | File(s) | Risk |
|---|---|---|---|
| **M1** | No backup/restore, monitoring, alerting, scaling, DR strategies | All specs | Operational blind spots |
| **M2** | No migration orchestration — M1-M5 not sequenced with dependency locks | `migration_spec.md` | Migration conflicts |
| **M3** | No rate limiting on identity lookup endpoint | `identity_spec.md` §4 | Phone enumeration attacks |
| **M4** | Outbox consumer not defined — no worker, no retry, no DLQ | All domain specs | Stale order metrics |
| **M5** | Custom PC build ID collision — no unique constraint on `KCPB` IDs | `ecommerce_spec.md` §2.2 | Duplicate builds |

---

## What the Council Agrees On

### ✅ Strengths (all 3 reviewers)
- Identity as single source of truth (`users_identity` + extension tables)
- LIVE vs TARGET separation — clear roadmap, no ambiguity
- Tenant isolation baked into every data model (indexes, JSON Schema, TenantCollection)
- Outbox pattern referenced consistently across all domains
- Local-first decisions (UPI QR via `pyqrcode`, no third-party bloat)
- Immutable audit trails (address cloning, wallet transaction log)

### ⚠️ Shared Concerns (all 3 reviewers)
- **MongoDB field naming skew** is the #1 risk — all three flagged it
- **Outbox pattern is referenced but not fully specified** — no event schema, no worker, no DLQ
- **Migration orchestration is missing** — no sequencing, no dependency locks, no CI integration
- **Operational glue is absent** — no backup, monitoring, alerting, DR

---

## Prioritized Action Items

| Priority | Action | Effort | Owner |
|---|---|---|---|
| **P0** | Implement HMAC-SHA256 for Cashfree webhooks | Small | Backend |
| **P0** | Create `event_schema.md` — outbox event payload contracts | Small | Architect |
| **P0** | Fix dual-read middleware to handle writes (not just reads) | Medium | Backend |
| **P1** | Replace JSON role columns with relational tables | Medium | Backend |
| **P1** | Drop `caf_platform_walkins.phone` UNIQUE before M2 | Small | DBA |
| **P1** | Add cross-tenant phone uniqueness check to migration | Small | Backend |
| **P2** | Add operational sections: backup, monitoring, outbox worker | Medium | DevOps |
| **P2** | Add migration orchestration: sequencing, CI integration | Medium | DevOps |
| **P3** | Add rate limiting to identity lookup endpoint | Small | Backend |
| **P3** | Add unique constraint on `custombuilds` collection | Small | Backend |

---

## Implementation Readiness

| Criteria | Status | Notes |
|---|---|---|
| Architecture principles | ✅ Pass | All 9 principles addressed |
| Cross-domain consistency | ✅ Pass | Identity, orders, tenant fields consistent |
| LIVE vs TARGET clarity | ✅ Pass | Clear separation in all specs |
| Security surface | 🔴 Needs work | 4 critical, 6 high findings |
| Operational readiness | 🟡 Partial | No backup, monitoring, DR |
| Migration safety | 🟡 Partial | No orchestration, no CI integration |
| Developer experience | 🟡 Partial | Missing code samples, event schema |

**Overall: Not yet ready for implementation.** Close P0 items first, then P1. Once critical and high findings are resolved, the specs are implementation-ready.

---

## Council Review Archives

| Reviewer | Alias | Archive |
|---|---|---|
| Gemma-4 (arch) | `reviewer-arch` | `~/.council-memory/reviews/deleg-1778975795/` |
| Nemotron-Cascade (logic) | `reviewer-logic` | `~/.council-memory/reviews/deleg-1778975923/` |
| GPT-OSS (diversity) | `reviewer-diversity` | `~/.council-memory/reviews/deleg-1778976066/` |
