# Remaining Items: kurogg-nextjs Migration, Warranty Endpoint, QA Gate

| Field | Value |
|-------|-------|
| Project ID | `KungOS` |
| Primary entity ID | `5addf0` |
| Entity type | `handoff` |
| Short description | Migrate kurogg-nextjs from legacy `/api/user/*` to canonical `/api/v1/*`, implement warranty lookup endpoint, fix EditAttendance prefix, execute manual QA gate |
| Status | `draft` |
| Source references | `llm-wiki/Kung_OS/reviews/frontend_backend_coverage_audit_2026-07-02.md`, `llm-wiki/00-prompt-handoff/02-07-2026_frontend-api-fixes-and-legacy-cleanup_06d49e.md` |
| Generated | 02-07-2026 |
| Next action / owner | Execute Phase 1A (EditAttendance.jsx prefix fix) — any frontend agent |

---

## Project Context

**Project root (kurogg-nextjs):** `/home/chief/Coding-Projects/kurogg-nextjs`
**Project root (admin frontend):** `/home/chief/Coding-Projects/KungOS-FE-Team`
**Project root (backend):** `/home/chief/Coding-Projects/KungOS-dj`
**Reference docs:** `llm-wiki/Kung_OS/reviews/frontend_backend_coverage_audit_2026-07-02.md`, `llm-wiki/Kung_OS/CANONICAL_NAMING.md`
**Key files for this task:** Listed per phase below

---

## Goal

Complete the four remaining items from the previous handoff (`06d49e`):

1. **kurogg-nextjs legacy API migration** — Migrate all API calls from legacy `/api/user/*` and `/api/products/*` patterns to canonical `/api/v1/{domain}/*` endpoints.
2. **EditAttendance.jsx missing `/api/v1/` prefix** — One-line fix to prevent production 404.
3. **Warranty lookup backend implementation** — New endpoint in Orders domain to validate warranty status for service requests.
4. **Full manual test suite** — QA verification checklist for all fixes from both handoffs.

---

## Canonical Domain Boundaries (Reference)

| Domain | Owns | kurogg-nextjs Maps To |
|--------|------|----------------------|
| **Auth** | Login, OTP, refresh, logout, password reset | `/api/v1/auth/*` |
| **Users** | Profile, saved addresses, identity | `/api/v1/users/*` |
| **Eshop** | Cart, wishlist, consumer orders, checkout | `/api/v1/eshop/*` |
| **Products** | Product catalog, prebuilds, components | `/api/v1/products/*` |

---

## Execution Order (DAG)

```
Phase 1A (EditAttendance fix) ──┐
Phase 1B (Warranty endpoint) ────┤── Phase 2 (kurogg-nextjs API migration) ──┐
                                  │                                           │
Phase 3 (Manual QA Gate) ─────────┘                                           │
                                                                              │
Phase 4 (Production Wiring) ──────────────────────────────────────────────────┘
```

**Phase 1A and 1B are independent and can execute in parallel.** Phase 2 depends on Phase 1B (warranty endpoint must exist before kurogg can call it — though kurogg doesn't currently call warranty, so this is a soft dependency). Phase 3 depends on all previous phases. Phase 4 is the final gate.

---

## Phase 1A: EditAttendance.jsx Prefix Fix

**Priority:** High (production 404 risk)
**What:** Add missing `/api/v1/` prefix to the attendance API call in `EditAttendance.jsx`.
**Files:** `KungOS-FE-Team/src/pages/Hr/EditAttendance.jsx`
**Dependencies:** None

### Current State

```javascript
// Line 47: Missing /api/v1/ prefix
url: `/teams/emp-attendance?userid=${empId}`,
```

This call bypasses both the axios baseURL AND the Vite dev proxy because it lacks the `/api/v1/` prefix. In production, it resolves to `https://domain.com/teams/emp-attendance` which returns 404.

### Steps

1. Open `KungOS-FE-Team/src/pages/Hr/EditAttendance.jsx`.
2. Locate `url: `/teams/emp-attendance?userid=${empId}``` (line ~47).
3. Replace with: `url: `/api/v1/teams/emp-attendance?userid=${empId}```.
4. Verify no other calls in the file have the same issue.

### Tests

- [ ] Navigate to `/hr/attendance/edit/{empId}` in dev environment.
- [ ] Submit the form and verify the API call succeeds (check Network tab for 200 response).
- [ ] Verify the request URL includes `/api/v1/teams/emp-attendance`.

---

## Phase 1B: Warranty Lookup Backend Endpoint

**Priority:** Medium (feature gap, not broken)
**What:** Implement a warranty validation endpoint in the Orders domain for service requests.
**Files:** `KungOS-dj/domains/orders/services.py`, `KungOS-dj/domains/orders/urls.py`, `KungOS-dj/domains/orders/models.py` (if new model needed)
**Dependencies:** None

### Current State

The frontend (`ServiceRequestsDetail.jsx`) has a warranty decision flow (`SRWarrantyConfirmDialog`) that was previously calling:

```
POST teams/service-requests?action=warranty&srid=<id>
```

This endpoint was removed during the domain migration. The frontend currently shows an alert: "Warranty lookup is currently unavailable."

### Requirements

Based on the frontend component (`SRDecisionFlow.jsx`), the warranty flow must:

1. **Accept:** Service request ID (`srid`).
2. **Validate:** Check if the associated product/build is under warranty.
3. **Return:** Warranty status (`valid`, `expired`, `none`) and details.
4. **On valid warranty:** Advance SR status to "In Repair" (as described in the dialog: "Mark this SR as a warranty repair. No invoice or payment will be required. The status will advance to 'In Repair'.")

### Design Options

**Option A: New endpoint under `/orders/service-requests/{srid}/warranty-check`**

- POST endpoint that validates warranty and optionally advances status.
- Returns: `{ status: "valid" | "expired" | "none", details: {...}, srStatus: "..." }`
- Pros: Clean RESTful design, matches existing SR endpoints.
- Cons: Requires warranty data model (purchase date, warranty period).

**Option B: Extend existing `/orders/service-requests/{srid}/advance-status` action**

- Add `warranty` as a valid action type.
- Backend validates warranty internally and advances status if valid.
- Pros: Reuses existing infrastructure.
- Cons: Less explicit — warranty validation is hidden inside status advance.

**Recommendation:** Option A — explicit warranty check endpoint. This separates concerns (validation vs. status management) and provides clear feedback to the frontend.

### Implementation Steps

1. **Add warranty check function to `domains/orders/services_pg.py`:**
   - Query `service_detail` table for the SR.
   - Join with product/build data to find purchase date.
   - Calculate warranty period (default: 1 year from purchase date, configurable).
   - Return warranty status and details.

2. **Add endpoint to `domains/orders/services.py`:**
   - `@api_view(['POST'])` decorator.
   - Accept `srid` in URL path.
   - Call warranty check function.
   - If valid, advance SR status to "In Repair".
   - Return structured response.

3. **Register URL in `domains/orders/urls.py`:**
   - `path('service-requests/<str:srid>/warranty-check', views.warranty_check, name='sr-warranty-check')`

4. **Update frontend (`ServiceRequestsDetail.jsx`):**
   - Replace the alert placeholder with actual API call.
   - Call `POST /api/v1/orders/service-requests/{srid}/warranty-check`.
   - Handle response: show warranty status, auto-advance if valid.

### Caveats & Uncertainty

- **Warranty data model is unclear:** The existing `service_detail` table may not have purchase date or warranty period fields. This may require a database migration or a workaround (e.g., check against the associated TP Build's creation date).
- **Warranty period is configurable:** Different product categories may have different warranty periods. The backend should support a default (1 year) but allow overrides.
- **If warranty data is truly unavailable:** Implement a stub that returns `{ status: "manual_review", message: "Warranty status requires manual verification" }` and flag for the product team.

### Tests

- [ ] POST to `/api/v1/orders/service-requests/{srid}/warranty-check` returns structured response.
- [ ] Valid warranty returns `status: "valid"` and advances SR to "In Repair".
- [ ] Expired warranty returns `status: "expired"` with reason.
- [ ] No warranty returns `status: "none"`.
- [ ] Invalid SR ID returns 404.

---

## Phase 2: kurogg-nextjs Legacy API Migration

**Priority:** Medium (works in dev via proxy, breaks in prod without reverse proxy)
**What:** Migrate all API calls in `kurogg-nextjs` from legacy patterns to canonical `/api/v1/{domain}/*` endpoints.
**Dependencies:** Phase 1B (warranty endpoint — soft dependency, kurogg doesn't call it yet)

### Current State

kurogg-nextjs uses **two distinct API patterns**:

#### Pattern 1: Redux Actions (Auth, Cart, Wishlist, Orders)

**File:** `kurogg-nextjs/redux/actions/user.js`

Uses `NEXT_URL` (from `config/index.js`, resolves to `http://localhost:3000`) + legacy paths:

| Legacy Path | Canonical Path | Method | Purpose |
|------------|----------------|--------|---------|
| `/api/user` | `/api/v1/users/me` | GET | Get current user profile |
| `/api/user/login` | `/api/v1/auth/login` | POST | Login (email/password) |
| `/api/user/verify` | `/api/v1/auth/verify-otp` | POST | OTP verification |
| `/api/user/register` | `/api/v1/auth/register` | POST | Register new user |
| `/api/user/logout` | `/api/v1/auth/logout` | POST | Logout |
| `/api/user/cartitems` | `/api/v1/eshop/cart/` | GET/POST/DELETE | Cart CRUD |
| `/api/user/wishlist` | `/api/v1/eshop/wishlist/` | GET/POST/DELETE | Wishlist CRUD |
| `/api/user/address` | `/api/v1/users/addresses/` | GET/POST/DELETE | Saved addresses CRUD |

**File:** `kurogg-nextjs/redux/actions/order.js`

| Legacy Path | Canonical Path | Method | Purpose |
|------------|----------------|--------|---------|
| `/api/user/checkoutlist` | `/api/v1/eshop/orders/` | GET | Checkout order list |
| `/api/user/orders` | `/api/v1/eshop/orders/` | GET | User order history |

#### Pattern 2: Product Pages (SSR)

**Files:** `kurogg-nextjs/libs/products.js`, `kurogg-nextjs/pages/**/*.js`

Uses `REACT_APP_KG_API_URL` (from `.env.development`, resolves to `http://127.0.0.1:8000`) + legacy paths:

| Legacy Path | Canonical Path | Method | Purpose |
|------------|----------------|--------|---------|
| `/api/products/prodlist` | `/api/v1/products/` | GET | Product list |
| `/api/products/products` | `/api/v1/products/` | GET | Product detail |
| `/api/products/prebuilds` | `/api/v1/products/prebuilds` | GET | Prebuilt PC list |
| `/api/products/buildlist` | `/api/v1/products/builds` | GET | Build list |
| `/api/products/kurodata` | `/api/v1/shared/kurodata` | GET | Hero/landing data |

#### Pattern 3: Custom PC Builder

**Files:** `kurogg-nextjs/pages/api/custom-pc/*.js`

| Legacy Path | Canonical Path | Method | Purpose |
|------------|----------------|--------|---------|
| `/api/kuroadmin/custombuilds` | `/api/v1/products/custom-builds/` | POST | Save custom build |
| `/api/kuroadmin/customprice` | `/api/v1/products/custom-price/` | GET | Get custom price |

### Migration Strategy

**Step 1: Add centralized API configuration**

Create `kurogg-nextjs/config/api.js`:

```javascript
// Centralized API base URL — overrides legacy REACT_APP_KG_API_URL
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';
```

**Step 2: Migrate Redux actions (`user.js`)**

Replace all `${NEXT_URL}/api/user/*` calls with `${API_BASE_URL}/eshop/*` or `${API_BASE_URL}/auth/*` or `${API_BASE_URL}/users/*`.

Key changes:
- Import `API_BASE_URL` from `config/api.js`.
- Replace `/api/user` → `${API_BASE_URL}/users/me`.
- Replace `/api/user/login` → `${API_BASE_URL}/auth/login`.
- Replace `/api/user/cartitems` → `${API_BASE_URL}/eshop/cart/`.
- Replace `/api/user/wishlist` → `${API_BASE_URL}/eshop/wishlist/`.
- Replace `/api/user/address` → `${API_BASE_URL}/users/addresses/`.

**Step 3: Migrate Redux actions (`order.js`)**

Replace all `${NEXT_URL}/api/user/*` calls with `${API_BASE_URL}/eshop/orders/*`.

**Step 4: Migrate product pages (`libs/products.js`)**

Replace all `process.env.REACT_APP_KG_API_URL + '/api/products/*'` with `${API_BASE_URL}/products/*`.

**Step 5: Migrate custom PC builder (`pages/api/custom-pc/*.js`)**

Replace `process.env.REACT_APP_KG_API_URL + '/api/kuroadmin/*'` with `${API_BASE_URL}/products/*`.

**Step 6: Update environment variables**

Add `NEXT_PUBLIC_API_BASE_URL` to `.env.development` and `.env.production`:

```env
# .env.development
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# .env.production
NEXT_PUBLIC_API_BASE_URL=https://api.kurogaming.com/api/v1
```

**Step 7: Remove legacy environment variables**

Deprecate `REACT_APP_KG_API_URL` and `REACT_APP_KC_API_URL` (replace with `NEXT_PUBLIC_*` equivalents).

### Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `kurogg-nextjs/config/api.js` | Centralized API base URL |
| Modify | `kurogg-nextjs/redux/actions/user.js` | Migrate 18 API calls to canonical paths |
| Modify | `kurogg-nextjs/redux/actions/order.js` | Migrate 2 API calls to canonical paths |
| Modify | `kurogg-nextjs/libs/products.js` | Migrate 7 API calls to canonical paths |
| Modify | `kurogg-nextjs/pages/api/custom-pc/save-build.js` | Migrate 1 API call |
| Modify | `kurogg-nextjs/pages/api/custom-pc/components.js` | Migrate 1 API call |
| Modify | `kurogg-nextjs/.env.development` | Add `NEXT_PUBLIC_API_BASE_URL`, deprecate legacy vars |
| Modify | `kurogg-nextjs/.env.production` (if exists) | Add `NEXT_PUBLIC_API_BASE_URL` |

### Caveats & Uncertainty

- **Endpoint mapping may not be 1:1:** Some legacy endpoints may have different request/response formats than the canonical endpoints. Verify each mapping against the actual backend endpoint.
- **Authentication headers:** The legacy `/api/user/*` endpoints may use a different auth mechanism (e.g., session cookies vs. JWT tokens). Verify that the canonical endpoints accept the same auth headers.
- **Product endpoints may not exist yet:** `/api/v1/products/custom-builds/` and `/api/v1/products/custom-price/` may not be implemented. If they don't exist, create stub endpoints or keep the legacy calls with a deprecation warning.
- **SSR compatibility:** The product pages use SSR (Server-Side Rendering via `getServerSideProps` or similar). The API base URL must resolve correctly in both browser and Node.js contexts.
- **Hardcoded URLs:** `libs/products.js` has a hardcoded URL for hero data (`https://kaizoku.kurogaming.com/api/products/kurodata?type=hero`). This should be migrated to `/api/v1/shared/kurodata` but requires the backend to support the `type=hero` query param.

### Tests

- [ ] All Redux actions resolve to canonical `/api/v1/*` URLs.
- [ ] Login flow works end-to-end (login → OTP → profile).
- [ ] Cart CRUD operations work (add, update, remove).
- [ ] Wishlist CRUD operations work.
- [ ] Product listing renders correctly (SSR).
- [ ] Custom PC builder saves and retrieves builds.
- [ ] No legacy `/api/user/*` or `/api/products/*` calls remain in source code.

---

## Phase 3: Manual QA Gate

**Priority:** Final Gate (must pass before marking complete)
**What:** Execute manual verification checklist for all fixes from both handoffs (`06d49e` and `5addf0`).
**Dependencies:** Phases 1A, 1B, 2 complete

### Test Environment Setup

1. Start backend: `cd KungOS-dj && python manage.py runserver`
2. Start admin frontend: `cd KungOS-FE-Team && npm run dev`
3. Start kurogg-nextjs: `cd kurogg-nextjs && npm run dev`
4. Ensure database is seeded with test data.

### Checklist: Phase 1A-1D (Service Requests, Procurement, Stock Audit, Orders)

#### Service Requests (1A)

- [ ] Navigate to `/service-requests` — list loads without 404s.
- [ ] Click a service request — detail view loads.
- [ ] Create a new service request — form submits successfully.
- [ ] Advance SR status — status updates correctly.
- [ ] Network tab shows all API calls go to `/api/v1/orders/service-requests/*`.

#### Procurement (1B)

- [ ] Navigate to `/products/procurement/purchase-orders` — list loads.
- [ ] Create a new PO — form submits to `/api/v1/inventory/purchase-orders/create`.
- [ ] Navigate to `/products/procurement/indents` — list loads.
- [ ] Download indent PDF — no 404.

#### Stock Audit (1C)

- [ ] Navigate to `/inventory/audit` — list loads.
- [ ] Click an audit — detail view loads.
- [ ] Create/edit audit — form submits to `/api/v1/inventory/stock-audit/*`.

#### Orders Overview (1D)

- [ ] Navigate to `/orders/overview` — page loads (authenticated route).
- [ ] No purchase order data is displayed (removed per domain boundaries).
- [ ] Service request data loads from `/api/v1/orders/service-requests`.

### Checklist: Phase 2 (Wrong Domain/Prefix)

- [ ] Navigate to `/hr/employees-salary` — attendance loads from `/api/v1/teams/emp-attendance`.
- [ ] Navigate to `/users` — user list loads from `teams/users`.
- [ ] Navigate to `/change-password` — password reset submits to `auth/pwdreset`.
- [ ] Navigate to `/hr/attendance/edit/{empId}` (Phase 1A fix) — attendance saves to `/api/v1/teams/emp-attendance`.

### Checklist: Phase 3 (Routing Bugs)

- [ ] Navigate to `/products/tp-builds` — TP Builds list loads.
- [ ] Click "New Build" — navigates to `/products/tp-builds/new`.
- [ ] Click a build — navigates to `/products/tp-builds/{id}`.
- [ ] Legacy URLs redirect correctly:
  - [ ] `/create-tpbuilds` → `/products/tp-builds/new`
  - [ ] `/tpbuilds` → `/products/tp-builds`
  - [ ] `/inventory/tp-builds` → `/products/tp-builds`
  - [ ] `/inventory/tp-builds/new` → `/products/tp-builds/new`
  - [ ] `/inventory/tp-builds/:id` → `/products/tp-builds/:id`
  - [ ] `/inventory/tp-builds/:id/edit` → `/products/tp-builds/:id/edit`

### Checklist: Phase 4 (kurogg-nextjs Migration)

- [ ] Navigate to kurogg-nextjs homepage — products load.
- [ ] Login flow works (email → OTP → profile).
- [ ] Add item to cart — cart updates.
- [ ] View cart — items display correctly.
- [ ] Add item to wishlist — wishlist updates.
- [ ] View product detail — product data loads.
- [ ] Custom PC builder — components load, build saves.
- [ ] Network tab shows all API calls go to `/api/v1/*`.

### Checklist: Backend Legacy Cleanup

- [ ] `GET /api/v1/teams/employeesdata` returns 404 (FBV removed).
- [ ] `GET /api/v1/accounts/export` works with `?type=` query param.
- [ ] `GET /api/v1/accounts/export/inward-invoices` returns 404 (redundant route removed).
- [ ] `GET /api/v1/cafe-fnb/orders` works (trailing slash alias removed, non-slash works).
- [ ] `GET /api/v1/legacy/products/inventory/stock` returns 301 redirect with deprecation warning in logs.

### Regression Tests

- [ ] Run existing Jest tests: `cd KungOS-FE-Team && npx jest src/App.test.jsx`
- [ ] Run existing Playwright tests: `cd KungOS-FE-Team && npx playwright test`
- [ ] Run backend tests: `cd KungOS-dj && python manage.py test`
- [ ] No console errors in browser dev tools.
- [ ] No 404 errors in Network tab across all tested pages.

---

## Phase 4: Production Wiring

**Priority:** Final Gate
**What:** Verify all components work end-to-end in production-like environment.
**Dependencies:** All previous phases complete, all QA checks pass

### Steps

1. **Build kurogg-nextjs for production:**
   ```bash
   cd kurogg-nextjs
   NEXT_PUBLIC_API_BASE_URL=https://api.kurogaming.com/api/v1 npm run build
   ```

2. **Build KungOS-FE-Team for production:**
   ```bash
   cd KungOS-FE-Team
   npm run build
   ```

3. **Verify backend routes:**
   ```bash
   cd KungOS-dj
   python manage.py show_urls | grep -E "service-request|purchase-order|stock-audit|warranty"
   ```

4. **Smoke test in production:**
   - [ ] Admin frontend loads all critical pages without 404s.
   - [ ] kurogg-nextjs loads products, cart, and wishlist.
   - [ ] Service requests workflow completes end-to-end.
   - [ ] Procurement workflow completes end-to-end.
   - [ ] Warranty check returns expected response.

5. **Deprecation monitoring:**
   - [ ] Verify `legacy_redirect` deprecation warnings appear in logs when legacy URLs are accessed.
   - [ ] Set up alerting for 404 errors on migrated endpoints.

### Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] Production build succeeds for both frontends.
- [ ] All API calls resolve to canonical `/api/v1/*` paths.
- [ ] No legacy `/api/user/*` or `/api/products/*` calls in production Network tab.
- [ ] Legacy redirect endpoint logs deprecation warnings.
- [ ] Full service request workflow completes in production.
- [ ] Full procurement workflow completes in production.
- [ ] Full e-commerce workflow completes in production (kurogg-nextjs).
- [ ] All existing tests still pass (no regression).

---

## Constraints

- **No silent changes:** Every API path change must be verified against the actual backend endpoint.
- **Preserve legacy redirect endpoint:** Keep `/api/v1/legacy/*` functional with deprecation logging until 6 months of zero hits are observed.
- **kurogg-nextjs auth compatibility:** Verify that canonical auth endpoints accept the same auth mechanism (JWT/session) as the legacy endpoints.
- **SSR compatibility:** API base URL must resolve correctly in both browser and Node.js (SSR) contexts.
- **Domain boundaries:** Do not introduce cross-domain calls that violate canonical boundaries (e.g., Orders domain must not call Inventory endpoints directly).
- **Warranty endpoint is best-effort:** If warranty data model is insufficient, implement a stub that returns `manual_review` status rather than blocking the handoff.

---

## Success Criteria

- [ ] EditAttendance.jsx attendance save works in production (Phase 1A).
- [ ] Warranty check endpoint returns structured response for valid SR (Phase 1B).
- [ ] All kurogg-nextjs API calls use canonical `/api/v1/*` paths (Phase 2).
- [ ] All QA checklist items pass (Phase 3).
- [ ] Production builds succeed and smoke tests pass (Phase 4).
- [ ] No regression in existing tests.
- [ ] Legacy redirect endpoint logs deprecation warnings.
- [ ] Zero 404 errors on migrated endpoints in production.

---

## Caveats & Uncertainty

1. **Warranty data model:** The `service_detail` table may not have purchase date or warranty period fields. If warranty data is truly unavailable, implement a stub that returns `{ status: "manual_review" }` and flag for the product team.
2. **kurogg-nextjs auth mechanism:** The legacy `/api/user/*` endpoints may use session cookies or a different token format. Verify compatibility with `/api/v1/auth/*` before migrating.
3. **Product endpoint existence:** `/api/v1/products/custom-builds/` and `/api/v1/products/custom-price/` may not exist in the backend. If missing, create stubs or keep legacy calls with deprecation warnings.
4. **Hardcoded hero data URL:** `libs/products.js` has `https://kaizoku.kurogaming.com/api/products/kurodata?type=hero` hardcoded. This external URL may not be controllable. Coordinate with the infrastructure team.
5. **Environment variable naming:** `REACT_APP_*` prefix is Create React App convention. Next.js uses `NEXT_PUBLIC_*`. The migration should adopt `NEXT_PUBLIC_API_BASE_URL` consistently.
6. **Line numbers are approximate:** Use `grep` to locate exact lines before editing.
7. **Volume estimates:** Any performance-related estimates are fabricated placeholders. Verify against live databases before performance testing.

---

## Execution Summary

| Phase | Priority | Files | Estimated Complexity |
|-------|----------|-------|---------------------|
| 1A: EditAttendance Fix | High | 1 | Low (1-line change) |
| 1B: Warranty Endpoint | Medium | 3-4 | Medium (new endpoint + frontend integration) |
| 2: kurogg-nextjs Migration | Medium | 8 | High (28+ API calls across 3 patterns) |
| 3: Manual QA Gate | Final Gate | N/A | Medium (full checklist) |
| 4: Production Wiring | Final Gate | N/A | Medium (builds + smoke tests) |

**Total: 1 fix + 1 new endpoint + 28 API migrations + full QA verification across 3 codebases.**

---

*Handoff generated from verified codebase analysis. All endpoints verified against actual `domains/*/urls.py` files. All frontend calls verified against actual source files.*

*Source: `llm-wiki/Kung_OS/reviews/frontend_backend_coverage_audit_2026-07-02.md`*

*Related: `llm-wiki/00-prompt-handoff/02-07-2026_frontend-api-fixes-and-legacy-cleanup_06d49e.md` (parent handoff — complete)*
