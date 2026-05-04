# Sidebar Navigation Optimisation

> **Date**: 2026-05-04
> **Scope**: `src/data/sidebar-nav.js` + `src/components/layout/AppSidebar.jsx`
> **Goal**: Reduce sidebar clutter from ~80 nav items to ~40 while keeping all pages reachable

---

## Problem Statement

The current sidebar has **~80+ nav items** across 10 top-level sections. Key pain points:

| Section | Items | Problem |
|---|---|---|
| **Orders** | ~25+ | 4 sub-groups with deep nesting (Entry Points → sub-items, Pipeline → 7 stages, Channels → 3) |
| **Products & Procurement** | ~22 | 3-level nesting (Procurement → sub-items), legacy "Create TP Build" duplicate |
| **Accounts** | ~20 | Documents has 13 children, Payments duplicates items already in Orders |
| **Cafe Platform** | ~11 | "New Session" duplicates "Active Sessions" key; "Games" reuses dashboard key |

### Root Causes

1. **3-level nesting is overwhelming** — `Orders → Fulfillment Pipeline → 7 stages` and `Orders → Estimates → 2 sub-items` means users click through 2-3 levels to reach anything. The sidebar becomes a scroll fest.

2. **Duplicate/overlapping items** — `Inward Payments` and `Bulk Payments` exist in **both** Orders and Accounts. `Analytics` appears as top-level AND under Accounts → Financials. `Create TP Build` exists twice.

3. **Dynamic routes shouldn't be nav items** — Items like `Product Detail`, `Invoice Detail`, `Stock Detail`, `User Detail`, `TP Build Detail`, `Outward Invoice Detail`, `Edit Attendance`, `Change Password` are detail views reached from list pages, never from the sidebar.

4. **Fulfillment Pipeline shouldn't be sidebar links** — The 7 pipeline stages (`New Orders`, `Products Added`, `Pending Auth`, etc.) are query-param filters on the same page (`/orders?stage=...`). These should be **horizontal tabs/pills on the Orders page itself**, not individual sidebar entries.

5. **Tools section is a waste of space** — A single "Search" item deserves its own section when the Command Palette (⌘K) already exists.

---

## Optimisations

### Quick wins (low effort, high impact)

**A. Remove detail-view nav items** — Prune ~15 items only reachable from list pages:

```
Product Detail, Invoice Detail, Stock Detail, User Detail,
TP Build Detail, TP Build Edit, Outward Invoice Detail,
Edit Attendance, Change Password, Inward Payment Detail,
Payment Link (dynamic)
```

**B. Collapse Fulfillment Pipeline into the page** — Move the 7 stages from sidebar → horizontal status tabs on the Orders page. Replace with a single "Orders" link.

**C. Deduplicate cross-section items** — Pick one home for `Inward Payments` and `Bulk Payments` (Accounts makes more sense). Remove from Orders sidebar.

**D. Remove Analytics duplication** — Keep it under Accounts → Financials. Remove the top-level Analytics entry.

**E. Remove legacy items** — `Create TP Build (legacy)` at `/create-tpbuilds` duplicates the Inventory entry.

**F. Merge Tools into header** — Remove the Tools section entirely. Search lives in the Command Palette (⌘K).

### Medium effort (UX improvements)

**G. Frequent actions bar** — Instead of sidebar entries for "New Estimate", "New SR", "Create Order", put quick-action buttons in the Orders overview page (as the navigation restructure plan already designs).

**H. Collapsed-by-default sub-sections** — Only expand the section relevant to the current route. Auto-collapse others on navigation.

**I. Smart visibility** — Hide empty/unused sections entirely. If a user has zero access to Cafe Platform items, don't show the section at all.

---

## Target Sidebar Structure

```
┌─ KTEAM ─────────────────────┐
│ [+ Order]  [+ Invoice]       │
│                              │
│ 📊 Dashboard                 │
│ 🛒 Orders                    │
│    ├─ Estimates              │
│    ├─ Service Requests       │
│    ├─ Create Order           │
│    └─ Invoices               │
│ 📦 Products & Procurement    │
│    ├─ Products               │
│    ├─ Presets                │
│    ├─ Pre-Builts             │
│    ├─ Stock                  │
│    ├─ Stock Register         │
│    ├─ TP Builds              │
│    ├─ Purchase Orders        │
│    ├─ Indents                │
│    └─ Audit                  │
│ 🧾 Accounts                  │
│    ├─ Invoices               │
│    ├─ Credit/Debit Notes     │
│    ├─ Payment Vouchers       │
│    ├─ Inward Payments        │
│    ├─ Bulk Payments          │
│    ├─ Vendors                │
│    ├─ Financials             │
│    └─ ITC GST                │
│ 👥 HR                        │
│    ├─ Employees              │
│    ├─ Attendance             │
│    ├─ Salaries               │
│    └─ Job Applications       │
│ 👤 Users                     │
│ ⚙️  Settings                 │
│    ├─ Business Groups        │
│    ├─ Brands & Divisions     │
│    ├─ Branches               │
│    ├─ Roles                  │
│    └─ User Access            │
│                              │
│ ☕ Cafe Platform             │
│    ├─ Dashboard              │
│    ├─ Stations               │
│    ├─ Sessions               │
│    ├─ Wallets                │
│    ├─ Pricing                │
│    └─ Members                │
│                              │
│ ───────────────────────────  │
│ ◀ Collapse                   │
│ 🌙 Theme                     │
│ ⚙️  Settings                 │
│ ⌘ Command Palette            │
│ ───────────────────────────  │
│ [JD] John Doe                │
│    Super Admin               │
└──────────────────────────────┘
```

**From ~80 items → ~40 items** (50% reduction) while keeping all reachable pages accessible.

---

## Implementation Plan

### Phase 1: Prune (A + B + C + D + E + F)

**File**: `src/data/sidebar-nav.js`

- Remove all `isDynamic: true` entries (detail views, edit views)
- Replace Fulfillment Pipeline sub-group with single `Orders` link
- Remove `Inward Payments` and `Bulk Payments` from Orders (keep in Accounts)
- Remove top-level `Analytics` entry (keep under Accounts → Financials)
- Remove `Create TP Build (legacy)` entry
- Remove entire `Tools` section
- Flatten Orders: keep Estimates, Service Requests, Create Order, Invoices as direct children (no sub-groups)
- Flatten Products & Procurement: remove Catalog/Inventory/Procurement sub-group wrappers, list items directly
- Flatten Accounts: reduce Documents sub-group, merge Payments items directly

### Phase 2: Pipeline as page tabs (B continued)

**File**: `src/pages/Orders/OrdersList.jsx` (or equivalent)

- Add horizontal status tabs/pills: `New | Products | Auth | In Process | Shipped | Delivered | Cancelled`
- Each tab sets `?stage=...` query param (no route change needed)
- Active tab highlighted; counts shown as badges (requires API or client-side computation)

### Phase 3: UX polish (G + H + I)

**File**: `src/components/layout/AppSidebar.jsx`

- Auto-collapse non-active sections on navigation
- Hide sections where user has zero child access (already partially done via `visiblePrimaryNav`)
- Consider lazy-expand: show only first 3 children with "Show more" for long lists

---

## Files to Modify

| File | Change |
|---|---|
| `src/data/sidebar-nav.js` | Prune items, flatten hierarchy, remove duplicates |
| `src/components/layout/AppSidebar.jsx` | Auto-collapse logic, section hiding |
| `src/pages/Orders/OrdersList.jsx` | Add horizontal status pipeline tabs |
| `src/hooks/useNavAccess.jsx` | No changes needed (already supports child filtering) |

---

## Risks & Considerations

- **Bookmark preservation**: Old URLs with `?stage=...` or `?channel=...` still work since they target the same page. No 404 risk.
- **RBAC**: The `useNavAccess` hook already filters by child access. Removing nav items doesn't remove permissions — users can still access URLs directly.
- **Cafe Platform**: Deferred per Phase plan. Keep as-is for now, optimise when Cafe Platform activates.
- **Navigation restructure plan**: This aligns with `2026-04-23-navigation-structure-restructure.md` Phase 4 (navigation restructure). This sidebar optimisation is a precursor that can ship independently.

---

## [2026-05-04] Nomenclature Cleanup (Phase 10)

### Completed

- **TenantSelector**: Full rewrite — shows labels to users, uses codes for filtering. Trigger shows `Division Label · Branch` (clean).
- **Component renames**: `EntityFilters` → `ListFilters`, `EntitySelector` → `DivisionSelector`
- **Variable renames**: `accessibleEntities` → `accessibleDivs`, `filterByEntity` → `filterByDiv` (24 pages)
- **UI labels**: All `"Entity"` → `"Division"` in table headers, form fields, dropdowns
- **Backend**: JWT token `entity` → `division` (bug fix — was reading non-existent `ctx.entity`), `resolve_permission` param, viewset responses
- **TDZ fixes**: 8 files had `useBranchQuery` before `activeDivision` declaration — all fixed

### Remaining sidebar work (Phase 11)

Quick-wins A-F from this doc still apply:
- A: Prune detail routes (Product Detail, Invoice Detail, etc.)
- B: Collapse Fulfillment Pipeline → horizontal tabs on Orders page
- C: Deduplicate cross-section items (Inward Payments, Analytics)
- D: Remove legacy "Create TP Build" duplicate
- E: Remove Tools section → Command Palette only
- F: Remove "Change Password" from sidebar (profile settings)
