---
tags: [cafe, council, review, architecture, F&B, kungos]
created: 2026-05-13
reviewers: [reviewer-arch (Gemma), reviewer-logic (Nemo), reviewer-diversity (GPT-OSS)]
related: [[cafe-audit-report]], [[kungos-cafe-platform]], [[KungOS_v2]]
status: locked
locked: 2026-05-13
locked_path: lightweight (no event layer)
---

# Cafe Platform — Council Review

**Date:** 2026-05-13  
**Reviewers:** Gemma-4-26B (arch), Nemotron-Cascade-30B (logic), GPT-OSS-20B (diversity)  
**Context:** Pre-lock architecture review — changes still possible

---

## Consensus (All Three Agree)

| Finding | All Three Say |
|---------|--------------|
| **Session-attached F&B** | ❌ **REJECT** — lifecycle mismatch, inventory integrity risk, God object |
| **Separate cafe-fnb/ domain** | ✅ **ADOPT** — clean bounded context, independent scaling |
| **Protocol chain bypass** | ⚠️ **CRITICAL** — domains query DB directly, must enforce protocol usage |
| **Rename rebellion/cafe/** | ✅ **RENAME** — brand name on generic code is misleading |
| **Session should reference F&B, not embed it** | ✅ **AGREE** — thin FK or order_id reference, not food_charges accumulation |

---

## Gemma (Architecture Reviewer) — DO NOT LOCK

**Key arguments:**
- F&B has different lifecycle than arcade sessions (food orders exist outside sessions)
- Session model already handles leases, stations, commands — adding F&B creates God object
- Inventory requires strict transactional integrity — can't be buried in session service
- Need **event/orchestration layer** for domain communication

**Implementation strategy:**
1. Create `cafe-fnb/` domain
2. Implement `LegacyKgOrdersAdapter` within `cafe-fnb/` that implements `ICafeFnbService`
3. Adapter reads from legacy MongoDB `kgorders` but exposes clean domain format
4. Session holds reference (`fnb_order_ids: List[UUID]`) or cached `total_fnb_charges`

**Endpoint change:** `POST /cafe/sessions/<id>/food` → `POST /cafe-fnb/orders/` (payload includes `session_id`)

---

## Nemo (Logic Reviewer) — DO NOT LOCK

**Key arguments:**
- Session is temporary construct — embedding mutable domain data (price totals, inventory, tax) makes data **non-canonical**
- No domain invariant enforced on server side — malicious client could bypass UI and corrupt inventory
- Session-scoped caching (Redis) loses cart on expiry, but order must survive for accounting
- Mixing session cache with durable order storage forces eventual consistency — risks double-spending inventory

**What "reject" means:**
- Keep session **only** for UI state (selected items, flags)
- Introduce dedicated `FoodOrder` aggregate created on "Place Order"
- Order lifecycle: `Cart → OrderCreated → PaymentInitiated → InventoryReserved → OrderCompleted/Failed`
- Session holds reference (`orderId`) after placement, authoritative data in separate table/collection

**Protocol bypass consequences:**
| Failure Mode | Explanation |
|-------------|-------------|
| Invariant violation | Direct DB call skips service that coordinates multiple invariants (order → payment → inventory) |
| No audit trail | Changes bypass IWalletService that logs transactions and emits domain events |
| Hard to replace persistence | Direct DB imports defeat the protocol contract |
| Fragile testing | Unit tests need real DB connection instead of in-memory fakes |

---

## GPT-OSS (Diversity Reviewer) — PARTIALLY AGREES, FLAGS OVER-ENGINEERING

**Agrees with consensus on:**
- Separate `cafe-fnb/` domain (namespace separation, clean boundaries)
- Protocol chain enforcement (cheap at 3-cafe scale, protects against schema drift)
- Session should reference F&B orders, not embed logic
- Rename `rebellion/cafe/` (but flags high risk of breaking integration tests)

**Flags over-engineering:**
| Point | Why Unnecessary for 3 Cafes |
|-------|---------------------------|
| Full event/orchestration layer | Hard to test for handful of daily orders |
| Separate PostgreSQL + MongoDB instruction sets | Two databases for same purpose is maintenance burden |
| Ignoring `Session.food_charges` field | Unused decimal column is harmless friction — could drop entirely |
| Non-implemented endpoint stub | Source of confusion — remove or add "feature not enabled" response |

**Simpler pragmatic path:**
| Level | Approach |
|-------|----------|
| Database | Move all F&B data into existing `kgorders` collection. Session stores `order_id` reference. |
| Domain | **Lightweight** `cafe-fnb/` with only gateway to Mongo (`OrderGateway.get_by_order_id`). No event bus. |
| Protocol | Thin adapter layer exposing F&B via existing `ICafeSessionService` contract |
| Session model | Delete `food_charges`; add `last_order_id` (nullable). GUI shows real amount via single Mongo lookup. |
| Endpoint | Remove all food-order endpoints not yet implemented. Keep FoodOrderModal on hold. |

---

## Synthesis: Where They Agree, Where They Diverge

| Topic | Gemma | Nemo | GPT-OSS | Consensus |
|-------|-------|------|---------|-----------|
| Separate cafe-fnb/ domain | ✅ Yes | ✅ Yes | ✅ Yes (lightweight) | ✅ **ADOPT** |
| Full event/orchestration layer | ✅ Yes | ✅ Yes | ❌ Over-engineering | ⚠️ **Defer** |
| Session references F&B | ✅ order_ids list | ✅ orderId FK | ✅ last_order_id | ✅ **ADOPT** |
| Protocol chain enforcement | ✅ Critical | ✅ Critical | ✅ Yes (thin adapter) | ✅ **ADOPT** |
| Rename rebellion/cafe/ | ✅ core/cafe/ | ✅ platform/cafe/ | ⚠️ High test risk | ⚠️ **Defer** |
| Legacy MongoDB adapter | ✅ LegacyKgOrdersAdapter | ✅ Service layer | ✅ OrderGateway | ✅ **ADOPT** |

---

## Recommended Path (Council Synthesis)

### Phase 1: Lightweight Domain Split (Now)

1. **Create `cafe-fnb/` domain** — lightweight, no event bus
2. **Implement `OrderGateway`** — reads/writes legacy MongoDB `kgorders`
3. **Add `Session.last_order_id`** — nullable FK reference
4. **Remove `Session.food_charges`** — unused, misleading
5. **Enforce protocol chain** — domains call services, services call repositories
6. **Remove non-implemented food endpoint** — or return "feature not enabled"

### Phase 2: Event Layer (When Business Demands)

- Add event bus when: multiple brands need different F&B logic, or real-time inventory syncing across locations
- Signal: >5 locations, or franchise model requiring centralized menu management

### What NOT to Do Yet

- ❌ Full event/orchestration layer (GPT-OSS: over-engineering for 3 cafes)
- ❌ Parallel PostgreSQL F&B tables (GPT-OSS: maintenance burden)
- ❌ Rename `rebellion/cafe/` until integration tests are stable (GPT-OSS: high break risk)

---

## Key Quote from Nemo

> "The logic of the system is currently tangled: session and cafe share the same namespace, and domain actions bypass the very contracts that give us safety and replaceability. By untangling those knots now, we set the stage for predictable scaling, robust security, and maintainable code."

## Key Quote from GPT-OSS

> "The current consensus is safe and sound for a 3-brand café. It may appear over-engineered at first glance, but it is well-within the span of normal service-based design practice. The suggested simplification cuts incidental maintenance cost while preserving all necessary safety nets."

---

## Decision Required

**Lock the lightweight path (Phase 1) or wait for Phase 2 scope?**

The council agrees on the direction (separate domain, protocol enforcement, session reference). They disagree on the scope (lightweight vs. full event layer). The pragmatic answer: **lock Phase 1 now, defer Phase 2 until business demand justifies it.**

---

## Locked Decision (2026-05-13)

**RESOLVED — Lightweight path locked. Events deferred until business demands.**

### Implementation Path

| Component | Decision | Phase |
|-----------|----------|-------|
| `domains/cafe-fnb/` | Lightweight domain, `OrderGateway` adapter, no models | Phase 2B |
| `Session.last_order_id` | Replaces `food_charges` | Phase 2A |
| Legacy MongoDB `kgorders` | Stays in MongoDB, no migration | Phase 2B |
| Protocol chain | Enforce: domains → services → repositories | Phase 2B |
| Event/orchestration layer | ❌ Deferred — trigger: >5 locations or franchise model | Future |
| Rename `rebellion/cafe/` | ⚠️ Deferred — Phase 9 after integration tests stable | Phase 9 |

### Trigger Conditions for Event Layer

| Condition | Action |
|-----------|--------|
| >5 cafe locations | Add event bus for real-time inventory sync |
| Franchise model | Add centralized menu management with brand overrides |
| Multiple payment providers | Add async webhook reconciliation |
| Real-time analytics pipeline | Add revenue streaming, inventory forecasting |

**When triggered:** Replace direct calls in `cafe-fnb/views.py` with `event_bus.publish()`. Add event handlers in each domain. Wire `plat/outbox/` for durable event logging. No data migration needed.
