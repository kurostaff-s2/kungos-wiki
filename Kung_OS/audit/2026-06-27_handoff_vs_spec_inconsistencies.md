# Handoff vs Spec — Inconsistency Report

**Date:** 2026-06-27
**Purpose:** Identify inconsistencies between handoff document and target state specs
**Scope:** 4 domain specs vs 5 handoff tasks

---

## Critical Inconsistencies

### 1. **EShop Implementation — INCOMPLETE in Handoff**

**Spec (`ecommerce_spec.md`):**
- Models: `Cart`, `Wishlist`, `Addresslist`, `Order` (PostgreSQL)
- **Additional:** `eshop_detail` table (PG) for e-commerce-specific order data
- **Payment:** Cashfree PG integration, UPI QR generation
- **Webhook:** Cashfree webhook with HMAC-SHA256 verification
- **Order Conversion:** `orderconversion` pipeline (MongoDB)
- **Custom PC Builds:** `custombuilds` collection with immutable cloning

**Handoff (Task 2):**
- ✅ Models: `Cart`, `Wishlist`, `Addresslist`
- ❌ **Missing:** `Order` model, `eshop_detail` model
- ❌ **Missing:** Payment integration (Cashfree, UPI)
- ❌ **Missing:** Webhook handler
- ❌ **Missing:** Order conversion pipeline
- ❌ **Missing:** Custom PC build cloning logic

**Impact:** Handoff only implements 30% of EShop spec. Critical payment and order conversion functionality is missing.

**Resolution:** Either:
- **Option A:** Expand handoff to include all EShop components (2-3 days → 5-7 days)
- **Option B:** Phase the implementation (Phase 1: cart/wishlist/addresses, Phase 2: orders, Phase 3: payment)

---

### 2. **Cafe Domain Architecture — MISLEADING in Handoff**

**Spec (`cafe_spec.md`):**
> **Packages:** `domains/cafe_arcade/` (sessions, stations, wallet, pricing) + `domains/cafe_fnb/` (F&B orders, menu)

**Handoff (Task 5):**
> | Domain | Purpose | URL Mount |
> |--------|---------|-----------|
> | `domains/cafe_arcade/` | Arcade stations, hourly/time-based rental, station connections | `/api/v1/cafe/` |
> | `domains/cafe_fnb/` | Food & Beverage orders, menu | `/api/v1/cafe-fnb/` |
> | `domains/cafe/` | Shared cafe functions (billing consolidation, etc.) | `/api/v1/cafe/shared/` (Phase 9) |

**Spec Clarification:**
> **`domains/cafe/`** — Empty shell reserved for Phase 9. Current cafe functionality is split between `cafe_arcade/` and `cafe_fnb/`.

**Issue:** Handoff says `domains/cafe/` is for "shared cafe functions (billing consolidation, etc.)" but spec says it's an **empty shell reserved for Phase 9** with no current functionality.

**Resolution:** Update handoff to match spec:
```markdown
| `domains/cafe/` | **Reserved for Phase 9** (empty shell) | N/A |
```

---

### 3. **Protocol Enforcement — NOT ADDRESSED in Handoff**

**Spec (`cafe_spec.md`):**
> **Protocol chain bypass — ⚠️ CRITICAL:** Domains query DB directly, must enforce protocol usage

**Spec (`tournaments_spec.md`):**
> **Protocol interfaces (`protocols.py`) — ⏳ Planned:** Target pattern, not yet implemented

**Handoff:**
- ❌ **Not mentioned:** Protocol enforcement requirement
- ❌ **Not mentioned:** `ICafeSessionService` interface
- ❌ **Not mentioned:** `TournamentsService` interface

**Impact:** Handoff doesn't address a CRITICAL spec requirement. Current code queries DB directly, which violates the spec.

**Resolution:** Add to handoff:
- Document protocol enforcement requirement
- Create protocol interfaces for cafe and tournaments domains
- Update viewsets to use protocol interfaces instead of direct DB queries

---

### 4. **Identity Migration — NOT ADDRESSED in Handoff**

**Spec (`identity_spec.md`):**
- `users_customer` merges: `reb_users` (1,979) + `misc` (1,979 duplicate) + `orders.user.phone` (727) + `serviceRequest.phone` (1,328)
- `users_player` replaces: `players` collection (MongoDB, 117 docs, 59 unique)
- `users_organization` merges: `teams` (14) + `vendors` (409)

**Handoff (Task 3):**
- ❌ **Not mentioned:** Customer identity migration
- ❌ **Not mentioned:** Player identity migration
- ❌ **Not mentioned:** Organization identity migration

**Impact:** Handoff doesn't address identity domain migration, which is foundational to all other domains.

**Resolution:** Either:
- **Option A:** Add identity migration tasks to handoff (3-5 days)
- **Option B:** Document as out-of-scope for this handoff (defer to Phase 4)

---

### 5. **MongoDB Collections — INCONSISTENT in Handoff**

**Spec (`identity_spec.md`):**
> **`users_customer` — Customer Extension:** Merges `reb_users` (1,979), `misc` (1,979 duplicate), `orders.user.phone` (727 unregistered), `serviceRequest.phone` (1,328 requestors)

**Handoff (Task 5):**
> | Domain | Collections | Rationale |
> |--------|-------------|-----------|
> | `domains/shared/` | `misc` | Legacy counter data |

**Issue:** Spec says `misc` is being **merged into** `users_customer`, but handoff says it's "legacy counter data" still in use.

**Impact:** Conflicting understanding of `misc` collection purpose and fate.

**Resolution:** Clarify in handoff:
```markdown
| `domains/shared/` | `misc` | **DEPRECATED** — Merging into `users_customer` (Phase 4) |
```

---

## High-Priority Inconsistencies

### 6. **Tournaments Endpoints — MISMATCHED in Handoff**

**Spec (`tournaments_spec.md`):**
> ### 6.1 Current Endpoints (Implemented)
> | Method | Endpoint | Description | Auth |
> |---|---|---|---|
> | `GET` | `/api/v1/tournaments/tournaments` | List tournaments | Public |
> | `GET` | `/api/v1/tournaments/players` | List players | JWT |
> | `GET` | `/api/v1/tournaments/teams` | List teams | Public |
> | `POST` | `/api/v1/tournaments/tourneyregister` | Team registration | JWT |

**Handoff (Task 5):**
- ❌ **Not mentioned:** Tournaments domain database usage
- ❌ **Not mentioned:** Current vs target endpoints

**Impact:** Handoff doesn't document tournaments domain, which is partially implemented.

**Resolution:** Add tournaments domain to handoff Task 5 documentation.

---

### 7. **Outbox Pattern — NOT ADDRESSED in Handoff**

**Spec (`cafe_spec.md`):**
> **Session End Flow (Critical):** F&B operational adapter (`OrderGateway`) must publish an outbox event (`order.placed`) using `plat/outbox/` primitive.

**Spec (`ecommerce_spec.md`):**
> **Order Conversion Pipeline:** Integrate `orderconversion` pipeline with `plat/outbox/` system so that order payment triggers a durable outbox event (`order.payment_verified`).

**Handoff:**
- ❌ **Not mentioned:** Outbox pattern
- ❌ **Not mentioned:** `plat/outbox/` integration
- ❌ **Not mentioned:** `order.placed` event
- ❌ **Not mentioned:** `order.payment_verified` event

**Impact:** Handoff doesn't address transaction integrity requirements. Direct MongoDB writes from PostgreSQL views create split-brain risk.

**Resolution:** Add to handoff:
- Document outbox pattern requirement
- Create outbox event handlers for cafe and e-commerce domains
- Update viewsets to use outbox events instead of direct MongoDB writes

---

### 8. **Tenant Isolation — NOT VERIFIED in Handoff**

**Spec (All specs):**
> All queries must include tenant context (`bg_code`, `div_code`)

**Handoff:**
- ❌ **Not mentioned:** Tenant isolation verification
- ❌ **Not mentioned:** `TenantCollection` wrapper usage
- ❌ **Not mentioned:** Cross-tenant data leak prevention

**Impact:** Handoff doesn't verify a fundamental security requirement.

**Resolution:** Add to handoff verification checklist:
- [ ] All MongoDB queries use `TenantCollection` wrapper
- [ ] All PostgreSQL queries include `bg_code` filter
- [ ] No raw PyMongo calls bypass tenant isolation
- [ ] No hardcoded tenant codes

---

## Medium-Priority Inconsistencies

### 9. **Walk-in Management — NOT ADDRESSED in Handoff**

**Spec (`cafe_spec.md`):**
> **Walk-in → Customer Migration Path:** Walk-in creates identity → registers → Identity.user FK set → Identity now has customer_profile extension

**Handoff:**
- ❌ **Not mentioned:** Walk-in management
- ❌ **Not mentioned:** `CafeWalkin` model
- ❌ **Not mentioned:** Walk-in → Customer migration

**Impact:** Handoff doesn't address cafe walk-in customer flow.

**Resolution:** Either:
- **Option A:** Add walk-in management to EShop implementation (Task 2)
- **Option B:** Document as out-of-scope (defer to Phase 5)

---

### 10. **Phone Normalization — NOT ADDRESSED in Handoff**

**Spec (`identity_spec.md`):**
> **Phone Normalization:** All phones must be normalized to E.164 format (+91XXXXXXXXXX)

**Handoff:**
- ❌ **Not mentioned:** Phone normalization
- ❌ **Not mentioned:** E.164 validation
- ❌ **Not mentioned:** `phonenumbers` library

**Impact:** Handoff doesn't address identity lookup requirements.

**Resolution:** Add to handoff:
- Document phone normalization requirement
- Add phone normalization to identity lookup flow
- Add E.164 validation tests

---

## Summary Table

| # | Inconsistency | Severity | Handoff Status | Spec Status |
|---|---------------|----------|----------------|-------------|
| 1 | EShop implementation incomplete | **CRITICAL** | ❌ Missing 70% | ✅ Complete |
| 2 | Cafe domain architecture misleading | HIGH | ❌ Incorrect | ✅ Clear |
| 3 | Protocol enforcement not addressed | HIGH | ❌ Not mentioned | ⚠️ CRITICAL |
| 4 | Identity migration not addressed | HIGH | ❌ Not mentioned | ✅ Complete |
| 5 | `misc` collection purpose inconsistent | MEDIUM | ❌ Incorrect | ✅ Clear |
| 6 | Tournaments endpoints mismatched | MEDIUM | ❌ Not mentioned | ✅ Complete |
| 7 | Outbox pattern not addressed | HIGH | ❌ Not mentioned | ✅ Complete |
| 8 | Tenant isolation not verified | HIGH | ❌ Not mentioned | ✅ Complete |
| 9 | Walk-in management not addressed | MEDIUM | ❌ Not mentioned | ✅ Complete |
| 10 | Phone normalization not addressed | MEDIUM | ❌ Not mentioned | ✅ Complete |

---

## Recommendations

### Immediate (Before Execution)

1. **Expand EShop handoff** to include:
   - `Order` and `eshop_detail` models
   - Payment integration (Cashfree, UPI)
   - Webhook handler
   - Order conversion pipeline

2. **Fix cafe domain documentation** to match spec:
   - `domains/cafe/` is **reserved for Phase 9** (empty shell)
   - Current functionality: `cafe_arcade/` + `cafe_fnb/` only

3. **Add protocol enforcement** to handoff:
   - Document `ICafeSessionService` interface
   - Document `TournamentsService` interface
   - Update viewsets to use protocol interfaces

4. **Clarify `misc` collection status**:
   - Currently: "Legacy counter data"
   - Spec: "Merging into `users_customer` (Phase 4)"
   - Update handoff to match spec

### Short-term (1-2 Weeks)

5. **Add identity migration tasks** (if in scope):
   - Customer identity migration
   - Player identity migration
   - Organization identity migration

6. **Add outbox pattern integration** (if in scope):
   - `order.placed` event handler
   - `order.payment_verified` event handler
   - `fnb.session_billing` event handler

7. **Add tenant isolation verification** to checklist:
   - All MongoDB queries use `TenantCollection`
   - All PostgreSQL queries include `bg_code` filter
   - No raw PyMongo calls bypass isolation

### Long-term (1-2 Months)

8. **Add walk-in management** (Phase 5):
   - `CafeWalkin` model
   - Walk-in → Customer migration flow
   - Phone-only identity creation

9. **Add phone normalization** (Phase 4):
   - E.164 validation
   - Phone normalization utility
   - Identity lookup flow update

---

## Revised Handoff Scope

**Current handoff covers:**
- ✅ Fix `division` → `div_code` in serializers
- ✅ Implement EShop cart/wishlist/addresses (partial)
- ✅ Migrate `teams/kurostaff/` imports
- ✅ Remove 34 dead functions
- ✅ Document domain database usage (partial)

**Missing from handoff (out-of-scope):**
- ❌ EShop orders and payment integration
- ❌ Protocol enforcement
- ❌ Identity migration
- ❌ Outbox pattern integration
- ❌ Tenant isolation verification
- ❌ Walk-in management
- ❌ Phone normalization

**Recommended action:**
- **Option A:** Expand handoff to include all missing items (5-7 days → 10-14 days)
- **Option B:** Keep current scope, document missing items as future phases

---

**Analysis completed:** 2026-06-27
**Next review:** Post-revision of handoff document
