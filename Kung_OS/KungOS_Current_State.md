# KungOS Current State

> Generated: 2026-05-16
> Purpose: Verified snapshot of live codebase vs. consolidated reference
> Supersedes: None (companion to `KungOS_Consolidated_Reference.md`)

---

## Architecture

| Layer | Status |
|-------|--------|
| **Django project** | Django 5.x, multi-tenant, domain-first, rest_framework_simplejwt, drf_spectacular, meilisearch, channels |
| **Live DB** | PostgreSQL — 49 tables (17 cafe, 5 tenant, 6 RBAC, 11 platform, 10 Django) |
| **MongoDB** | 31 collections, 68,443 docs, 100% tenant-scoped (`bgcode`/`division`/`branch_code`) |
| **Migrations** | **3 cafe_arcade migrations NOT applied** — live DB behind model code |
| **Kuro Gaming** | Separate Django 4.1.13 project (EOL), legacy knox auth, flat apps |

---

## What's Working (Verified ✅)

- Tenant hierarchy (5 tables, cascade-code PKs) — **live & correct**
- RBAC (6 tables, level 0-3, resolution engine) — **live & correct**
- URL routing (all domains wired including `eshop/`) — **live & correct**
- Platform primitives (outbox, events, observability, tenant config, health, shared, RLS) — **live & correct**
- MongoDB tenant field coverage — **100% complete**

---

## Conflicts (Doc vs. Live)

| # | What | Doc Says | Live Reality | Resolution |
|---|------|----------|--------------|------------|
| 1 | **CafeWallet owner** | Polymorphic `walkin`/`user` | `OneToOneField(CustomUser)` only | **Doc wrong** — live is Definition A |
| 2 | **CafeWalkin schema** | `walkin_id`, `secondary_phones (jsonb)`, tenant fields | `phone`, `name`, `created_at`, `last_visit` (5 cols, no tenant fields) | **Doc wrong** — describes future state |
| 3 | **CafeUser schema** | `user_id`, tenant fields, no `wallet_balance` | `user (OneToOne)`, `wallet_balance`, no tenant fields | **Doc wrong** — describes future state |
| 4 | **CafeArcade migrations** | Implied applied | `[ ] 0001`, `[ ] 0002`, `[ ] 0003` — **none applied** | **DB behind code** — `entity` still exists, no `div_code`/`branch_code` |
| 5 | **Tenant table columns** | ~10 cols each | 15-19 cols each (audit fields, extra tax/phone/address) | **Doc incomplete** — missing audit trail, tax, status fields |
| 6 | **MongoDB `entities`** | Not mentioned | Exists (2 docs) | **Doc omission** — legacy, low priority |

---

## Root Cause

The consolidated doc describes **target architecture** (what the Django models intend) but presents it as **current state** (what's in the live DB). The 3 cafe_arcade migrations bridge the gap — they're written but never run.

---

## Immediate Actions

1. **Fix doc errors** (#1-3) — CafeWallet, CafeWalkin, CafeUser conflict resolutions are wrong
2. **Run migrations** — `python manage.py migrate cafe_arcade` (or explain why they're blocked)
3. **Update tenant table details** — add missing columns to doc
4. **Add LIVE vs TARGET column** to all schema tables going forward
