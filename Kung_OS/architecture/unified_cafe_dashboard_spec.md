# KungOS — Unified Cafe Dashboard Specification

**Date:** 2026-06-28  
**Status:** ❌ NOT IMPLEMENTED  
**Priority:** P0 — Core Supervisor Workflow

---

## Executive Summary

The KungOS cafe platform is **missing a unified supervisor dashboard** that tracks all walk-in customer activities in one place. The current frontend has separate pages for:
- Sessions (arcade gaming)
- F&B orders (will be implemented)
- Wallet top-ups
- Payments

But there is **no single view** for the store incharge/branch supervisor to:
1. See all active sessions with their F&B orders
2. Add F&B items to a session
3. Process wallet top-ups
4. Record payments
5. Close sessions with unified checkout

This is a **critical gap** for the cafe operations workflow.

---

## 📊 Current State vs. Required State

### Current State (Fragmented)

```
Cafe Platform
├── Dashboard (Arcade stats only)
├── Stations (Station list)
├── Sessions
│   ├── Start (SessionStart)
│   ├── Active (SessionActive — sessions only)
│   └── End (SessionEnd — session charges only)
├── Wallets
│   ├── Balance (WalletBalance)
│   └── Recharge (WalletRecharge)
├── Menu (Not implemented)
├── Orders (Not implemented)
└── Refunds (Not implemented)
```

**Problem:** Supervisor must jump between 6+ pages to serve a single walk-in customer.

### Required State (Unified)

```
Cafe Platform
├── Dashboard (Unified overview)
├── Customer Tracker (NEW — unified walk-in view)
│   ├── Active Sessions (with F&B orders)
│   ├── Add F&B Order
│   ├── Wallet Top-up
│   └── Close Session (unified checkout)
├── Stations (Station list)
├── Wallets
│   ├── Balance (WalletBalance)
│   └── Recharge (WalletRecharge)
├── Menu (Menu management)
├── Orders (Order history)
└── Refunds (Refund history)
```

**Solution:** Single "Customer Tracker" page for supervisor workflow.

---

## 🎯 Unified Customer Tracker — Wireframe

```
┌─────────────────────────────────────────────────────────────────┐
│  Cafe Platform > Customer Tracker                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [All Active] [F&B Orders] [Wallet Top-ups] [Payments]          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Station: ST-001  |  Customer: John Doe (9876543210)      │   │
│  │ Game: GTA V  |  Started: 14:30  |  Duration: 45 min      │   │
│  │ Price Plan: ₹120/hr  |  Session Charge: ₹60.00          │   │
│  │                                                                  │
│  │  F&B Orders:                              [Add Order]       │   │
│  │  ├─ Burger x2     ₹200.00                                      │   │
│  │  ├─ Coffee x1     ₹80.00                                       │   │
│  │  └─ Subtotal: ₹280.00                                          │   │
│  │                                                                  │
│  │  Wallet: ₹500.00  |  Top-up: [₹] [Top Up]                     │   │
│  │                                                                  │
│  │  TOTAL DUE: ₹340.00                                             │   │
│  │  [Pay & Close Session]                                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Station: ST-002  |  Customer: Jane Smith (9876543211)    │   │
│  │ Game: Fortnite  |  Started: 15:00  |  Duration: 15 min    │   │
│  │ Price Plan: ₹100/hr  |  Session Charge: ₹25.00          │   │
│  │                                                                  │
│  │  F&B Orders:                              [Add Order]       │   │
│  │  (No orders)                                                   │   │
│  │                                                                  │
│  │  Wallet: ₹200.00  |  Top-up: [₹] [Top Up]                  │   │
│  │                                                                  │
│  │  TOTAL DUE: ₹25.00                                            │   │
│  │  [Pay & Close Session]                                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Required Features

### 1. Active Sessions List
- Show all active sessions with:
  - Station code/name
  - Customer name/phone
  - Game selected
  - Start time
  - Duration (live)
  - Session charge (calculated)
  - F&B orders count and subtotal
  - Wallet balance
  - Total due (session + F&B)

### 2. Add F&B Order to Session
- Modal or inline form to add F&B items to a session
- Select from menu items
- Specify quantity
- Calculate item total
- Add to session's F&B orders

### 3. Wallet Top-up
- Input amount
- Process payment (cash/UPI/wallet)
- Update wallet balance
- Record transaction

### 4. Close Session (Unified Checkout)
- Calculate final charges:
  - Session time charge
  - F&B orders subtotal
  - Total due
- Process payment:
  - Wallet deduction (if sufficient balance)
  - Cash/UPI payment (if wallet insufficient)
- Generate receipt
- Release station

---

## 🔧 Backend API Requirements

### New Endpoints Needed

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/cafe/tracker/active` | GET | List all active sessions with F&B orders |
| `/api/v1/cafe/tracker/sessions/:id/fnb/orders` | GET | Get F&B orders for a session |
| `/api/v1/cafe/tracker/sessions/:id/fnb/orders` | POST | Add F&B order to session |
| `/api/v1/cafe/tracker/sessions/:id/wallet/topup` | POST | Top up wallet for session |
| `/api/v1/cafe/tracker/sessions/:id/close` | POST | Close session with unified checkout |

### Enhanced Endpoints

| Endpoint | Method | Enhancement |
|----------|--------|-------------|
| `/api/v1/cafe/sessions/active` | GET | Include F&B orders count and subtotal |
| `/api/v1/cafe/dashboard/overview` | GET | Include F&B revenue in today's revenue |

---

## 📊 Data Model Relationships

```
Session (caf_platform_sessions)
├── station (FK → Station)
├── game (FK → Game)
├── price_plan (FK → PricePlan)
├── identity (FK → users_identity)
├── wallet (FK → CafeWallet)
└── fnb_orders (1:N → CafeFnbDetail)
    └── order (FK → CafeFnbOrder)
        └── items (1:N → CafeFnbOrderItem)
            └── menu_item (FK → CafeMenuItem)
```

**Current State:** `Session.fnb_orders` is a reverse relation (not a field).  
**Required:** Query `CafeFnbDetail.objects.filter(session=session)` to get F&B orders.

---

## 🎯 Implementation Plan

### Phase 1: Backend API (2 days)

- [ ] Create `domains/cafe_arcade/views_tracker.py`
- [ ] Implement `GET /cafe/tracker/active` — list active sessions with F&B
- [ ] Implement `GET /cafe/tracker/sessions/:id/fnb/orders` — session F&B orders
- [ ] Implement `POST /cafe/tracker/sessions/:id/fnb/orders` — add F&B order
- [ ] Implement `POST /cafe/tracker/sessions/:id/wallet/topup` — wallet top-up
- [ ] Implement `POST /cafe/tracker/sessions/:id/close` — close session
- [ ] Update `GET /cafe/sessions/active` to include F&B counts
- [ ] Update `GET /cafe/dashboard/overview` to include F&B revenue

### Phase 2: Frontend Pages (3 days)

- [ ] Create `src/pages/cafe/CustomerTracker.jsx` — unified supervisor view
- [ ] Create `src/pages/cafe/components/SessionCard.jsx` — session card component
- [ ] Create `src/pages/cafe/components/AddFnbOrderModal.jsx` — add F&B order modal
- [ ] Create `src/pages/cafe/components/WalletTopupModal.jsx` — wallet top-up modal
- [ ] Create `src/pages/cafe/components/CloseSessionModal.jsx` — close session modal
- [ ] Update `src/lib/cafeApi.js` — add tracker API methods
- [ ] Update `src/data/navigation.jsx` — add Customer Tracker to navigation

### Phase 3: Integration (1 day)

- [ ] Test unified workflow end-to-end
- [ ] Verify F&B orders appear in session
- [ ] Verify wallet top-up updates balance
- [ ] Verify close session calculates total correctly
- [ ] Verify receipt generation

---

## 📋 Estimated Timeline

| Phase | Duration |
|-------|----------|
| Backend API | 2 days |
| Frontend Pages | 3 days |
| Integration | 1 day |
| **Total** | **6 days** |

---

## 🎯 Recommendation

**Implement the Unified Customer Tracker as a P0 priority.**

This is the **core supervisor workflow** for cafe operations. Without it, the supervisor must jump between 6+ pages to serve a single customer, which is inefficient and error-prone.

**The legacy docs do not explicitly specify this unified view**, but the backend architecture (Session → F&B orders relationship) supports it. The frontend should be implemented to match the current backend state.

---

## 📚 References

| Document | Path |
|----------|------|
| Cafe Platform Spec | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_spec.md` |
| Cafe Council Review | `/home/chief/llm-wiki/cafe-council-review.md` |
| Integration Plan | `/home/chief/llm-wiki/legacy/KUNGOS_INTEGRATION_PLAN.md` |
| **This Spec** | `/home/chief/llm-wiki/Kung_OS/architecture/unified_cafe_dashboard_spec.md` |

---

*Specification generated: 2026-06-28*  
*Unified Customer Tracker: NOT IMPLEMENTED*  
*Priority: P0 — Core Supervisor Workflow*
