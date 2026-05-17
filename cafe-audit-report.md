---
tags: [cafe, audit, F&B, rebellion, kungos, architecture]
created: 2026-05-13
sources: [rebellion/cafe/, CAFE_PLATFORM.md, kungos-cafe-platform.md, legacy_views.py]
related: [[kungos-cafe-platform]], [[KungOS_v2]], [[kungos-log]]
status: locked
locked: 2026-05-13
locked_by: council-review (Gemma, Nemo, GPT-OSS)
---

# Cafe Platform Audit Report

**Date:** 2026-05-13  
**Scope:** `rebellion/cafe/` codebase, F&B handling, domain split proposal  
**Purpose:** Ground-truth audit of what exists vs. what's planned

---

## 1. `rebellion/cafe/` Is Generic Logic Wearing a Brand Name

**Finding:** Zero Rebellion-specific logic exists in the entire `rebellion/cafe/` app. Every model, view, and serializer is brand-agnostic cafe platform code.

| Evidence | Detail |
|----------|--------|
| `grep -rn "rebellion\|REBELLION\|reb_"` | **No matches** in `rebellion/cafe/` |
| Tenant isolation | Handled via `bg_code`/`div_code`/`branch_code` filtering — generic multi-tenant |
| Models | `Cafe`, `Station`, `Session`, `PricePlan`, `CafeWallet` — all brand-agnostic |
| Views | 24 endpoints, all filter by `get_tenant_context(request.user)` |

The backend should be abstract. Brand names in Django app structure imply brand-specific logic that doesn't exist. The only brand differentiation is **which `bg_code` data they see**, handled by `plat/tenant/`.

**Recommendation:** Move `rebellion/cafe/` → `domains/cafe/` (merge with existing empty shell). Same for `rebellion/esports/` → `domains/esports/`. The `brands/` directory stays for genuinely brand-specific implementations — currently nothing.

---

## 2. F&B Reality: Half-Implemented in Legacy MongoDB, Zero in PostgreSQL

### Current State

| Layer | F&B Status | Evidence |
|-------|------------|----------|
| PostgreSQL models | ❌ Only pass-through | `Session.food_charges` — single `DecimalField`, never populated |
| PostgreSQL views | ❌ No F&B endpoints | 24 cafe endpoints — none for orders, menu, products |
| Legacy MongoDB | ✅ Full system | `kgorders` collection with `food[]` items, `productid`, `quantity`, `unit` |
| Legacy views | ✅ Full CRUD | `reborders()` — create, read, update, close orders with inventory deduction |
| Frontend | ⚠️ Referenced, not wired | `FoodOrderModal` in CAFE_PLATFORM.md — defined, no backend |

### Legacy MongoDB Data Model (from `legacy_views.py`)

```json
{
    "orderid": "KG00000001",
    "food": [
        { "productid": "PROD001", "quantity": 2, "unit": "pcs", "price": 150, "totalprice": 300 }
    ],
    "totalprice": 300,
    "status": "Open",
    "division": "REB0001_001",
    "branch": "BR001",
    "user": { "phone": "...", "name": "..." }
}
```

The legacy system handles: order creation/modification, inventory deduction, order totals (service vs food, monthly/daily breakdowns), payment merging, user creation from order data. **None of this exists in the new PostgreSQL cafe platform.**

### What the Plans Say

| Document | F&B Coverage |
|----------|-------------|
| `KUNGOS_INTEGRATION_PLAN.md` | `domains/products/` and `domains/orders/` — only for **e-commerce** (PC sales), not cafe F&B |
| `KungOS_v2.md` (repo) | `inventory/ — Products, stock register, presets` — no cafe F&B spec |
| `KungOS_v2.md` (llm-wiki) | `food-orders/ — Cafe food orders` — listed in tree, **zero implementation detail** |
| `CAFE_PLATFORM.md` | `FoodOrderModal` component referenced — no backend implementation |

---

## 3. kungos-cafe-platform.md: Session-Attached F&B, Not Separate Domain

The plan treats F&B as a **pass-through to sessions**, not a standalone domain.

### Planned Endpoint

```
POST /cafe/sessions/<id>/food  →  "Add food to session"
```

That's it. **One endpoint.** No `cafe-fnb/` app, no `FnbOrder`, no `FnbProduct`, no `FnbMenu`.

### How It Works

```
Legacy MongoDB (kgorders)
     ↓ food order placed
Session.food_charges += order.total  (PostgreSQL)
     ↓
session_end: total_charges = session_charge + food_charges
     ↓
Wallet deduction (PostgreSQL)
```

The bridge is `Session.food_charges` — a one-way accumulation. F&B doesn't need to know about sessions; sessions just accumulate F&B charges.

### Legacy MongoDB F&B Stays Untouched

| Collection | Planned Enhancement | Status |
|------------|-------------------|--------|
| `kgorders` | `order_type: cafe` | ❌ **Not enhanced** — cafe orders use PG sessions |
| `stock_register` | `product_type: food` | ❌ **Not enhanced** — cafe food orders separate |

**Rationale:** Cafe F&B is fundamentally an add-on to sessions. The legacy MongoDB system already handles full F&B complexity (products, inventory, payments). The cafe platform only needs the charge amount.

---

## 4. Proposed Split vs. Plan

| Domain | Your Proposal | kungos-cafe-platform Plan | Alignment |
|--------|--------------|--------------------------|-----------|
| `arcade-station/` | Sessions, stations, leases, commands, events | ✅ Core cafe platform (14 PG tables) | ✅ Matches |
| `cafe-fnb/` | Products, orders, menu, presets, inventory | ❌ Session-attached, single endpoint | ⚠️ Diverges |
| `tournaments/` | Players, tournaments, registrations | ✅ Esports integration (Phase 3) | ✅ Matches |

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Session-attached** (plan) | Simple, no new domain, leverages legacy MongoDB | No cafe-specific product catalog, no F&B analytics |
| **Separate domain** (`cafe-fnb/`) | Full F&B domain, cafe-specific products, presets, analytics | More complexity, duplicates legacy MongoDB functionality |

---

## 5. Implementation Gaps

### What's Built (PostgreSQL — 14 tables, all implemented)

| Table | Purpose | Status |
|-------|---------|--------|
| `caf_platform_cafes` | Cafe registry | ✅ |
| `caf_platform_stations` | Station inventory | ✅ |
| `caf_platform_sessions` | Session tracking + `food_charges` | ✅ |
| `caf_platform_session_leases` | Lease versioning | ✅ |
| `caf_platform_station_commands` | Remote control | ✅ |
| `caf_platform_station_events` | Event log | ✅ |
| `caf_platform_wallets` | Shared wallet | ✅ |
| `caf_platform_wallet_transactions` | Transaction audit | ✅ |
| `caf_platform_price_plans` | Zone-based pricing | ✅ |
| `caf_platform_member_plans` | Edge/Titan/S tiers | ✅ |
| `caf_platform_games` | Game catalog | ✅ |
| `caf_platform_users` | Cafe user profiles | ✅ |
| `caf_platform_walkins` | Walk-in tracking | ✅ |
| `caf_platform_auth_tokens` | QR/login tokens | ✅ |

### What's Built (API — 24 endpoints, all implemented)

| Category | Endpoints | Status |
|----------|-----------|--------|
| Customer | register, lookup, profile | ✅ |
| Wallet | balance, recharge, transactions | ✅ |
| Stations | list, detail, status | ✅ |
| Sessions | start, pause, resume, end, extend, active | ✅ |
| Pricing | rules, calculate | ✅ |
| Games | library | ✅ |
| Members | plans, upgrade | ✅ |
| Dashboard | overview, revenue, utilization | ✅ |
| Payments | history, record | ✅ |
| **Sessions/food** | `POST /cafe/sessions/<id>/food` | ❌ **Planned, not built** |

### Critical Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| `POST /cafe/sessions/<id>/food` | High | Planned endpoint, zero implementation |
| `Session.food_charges` population | High | Field exists, never set |
| `FoodOrderModal` backend | Medium | Frontend component defined, no API |
| Accesslevel cafe permissions | Medium | 7 permission fields planned, not in schema |
| Django Channels WebSocket | Critical | Required for station platform, partially wired |
| Celery Beat scheduler | Medium | Expired sessions cleanup, not configured |
| Cashfree payment wiring | Medium | Wallet recharge has no payment provider |

---

## 6. Recommendations

### A. Rename `rebellion/cafe/` → `domains/cafe/`

**Action:** Move the generic cafe app to the domains namespace. The code is brand-agnostic — the name should reflect that.

**Risk:** Low — single directory rename, update imports in `rebellion/urls.py` and `INSTALLED_APPS`.

### B. Close the F&B Gap — Session-Attached Approach

**Action:** Implement `POST /cafe/sessions/<id>/food` endpoint that:
1. Accepts food items (productid, quantity, price)
2. Validates against legacy MongoDB `kgorders` product catalog
3. Accumulates charges on `Session.food_charges`
4. Creates a legacy `kgorders` document for inventory/accounting

**Why session-attached:** Keeps the cafe platform simple. F&B is an add-on to sessions, not a standalone business. Legacy MongoDB already handles full F&B complexity.

### C. Keep Legacy MongoDB for F&B Operations

**Action:** Don't migrate `kgorders`, `stock_register`, or F&B inventory to PostgreSQL. The legacy system works. The cafe platform only needs `food_charges` accumulation.

**Bridge:** `POST /cafe/sessions/<id>/food` writes to both:
- PostgreSQL: `Session.food_charges += total`
- MongoDB: `kgorders` document for inventory deduction and accounting

### D. Defer `cafe-fnb/` Separate Domain

**Action:** If F&B needs to become a separate domain (cafe-specific products, presets, analytics), do it **after** the core platform is wired. Not now.

**Signal to watch:** If multiple brands need different cafe F&B logic (different menus, different pricing rules), that's the trigger for a separate domain.

### E. Wire the Protocol Chain

**Action:** Connect `core/` → `brands/` → `domains/` so the existing architecture is functional:
- `core/cafe/` protocols (`ICafeSessionService`, `IWalletService`) — already defined
- `brands/` implementations — currently stubs returning `{"status": "created"}`
- `domains/cafe/` viewsets — currently query PostgreSQL directly, bypassing protocols

**Why:** The protocol chain exists but isn't wired. Making it functional is the work, not redesigning it.

---

## 7. Summary

| Question | Answer |
|----------|--------|
| Is `rebellion/cafe/` brand-specific? | **No** — generic cafe logic wearing a brand name |
| How is F&B handled now? | Legacy MongoDB only (`kgorders`), zero PostgreSQL implementation |
| How is F&B proposed in plans? | Session-attached: single endpoint, `Session.food_charges` accumulation |
| Is the food endpoint built? | **No** — planned, not implemented |
| Should F&B be a separate domain? | **Yes** — council-locked lightweight `cafe-fnb/` domain |
| What's the real work? | Wire the existing protocol chain, close the F&B gap, rename `rebellion/cafe/` → `domains/cafe/` |

---

## 8. Locked Decision (2026-05-13)

**Council Review:** Gemma-arch, Nemo-logic, GPT-OSS-diversity
**Verdict:** Lightweight `cafe-fnb/` domain, no event layer, `Session.last_order_id` reference

| Decision | Status |
|----------|--------|
| Separate `cafe-fnb/` domain | ✅ **LOCKED** — lightweight, no models, `OrderGateway` adapter |
| Event/orchestration layer | ❌ **DEFERRED** — add when >5 locations or franchise model |
| `Session.last_order_id` | ✅ **LOCKED** — replaces `food_charges` |
| Legacy MongoDB `kgorders` | ✅ **LOCKED** — stays in MongoDB, no migration |
| Protocol chain enforcement | ✅ **LOCKED** — domains → services → repositories |
| Rename `rebellion/cafe/` | ⚠️ **DEFERRED** — Phase 9 after integration tests stable |

**Implementation:** Phase 2B in `KUNGOS_INTEGRATION_PLAN.md`
**Council report:** `~/llm-wiki/cafe-council-review.md`
