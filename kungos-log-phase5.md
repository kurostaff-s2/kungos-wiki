## [2026-04-23] Navigation & Order Restructure — Phase 5: Order Consolidation

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Phase 5: Order Consolidation (Frontend Only)

**Context:** Phase 5 consolidates fragmented order management into unified components. OrdersList handles both TP and KG orders. OrderDetail includes payment, invoice, inventory, and status management. OrderCreate supports "Create from Existing Order" (reorder).

### Changes made

#### 1. OrdersList — Unified TP + KG Orders
- **Modified:** `src/pages/Orders/OrdersList.jsx` — 16.0 KB, 447 lines
- **Features:**
  - Fetches both TP (`kurostaff/tporders`) and KG (`kurostaff/kgorders`) orders
  - Channel filter tabs: All, TP Orders, Offline, Online
  - Status pipeline tabs: New, Products, Authorized, In Process, Shipped, Delivered, Cancelled
  - Table and Kanban views
  - Row actions: View Details, Download Checklist, Cancel (Super users)
  - Bulk cancel action
  - URL-aware: `?channel=tp`, `?channel=offline`, `?stage=new` params
  - React Query with proper cache invalidation
  - Channel badge in table view (blue for TP, green for Offline)

#### 2. OrderDetail — Unified Order Detail
- **Modified:** `src/pages/Orders/OrderDetail.jsx` — 31.7 KB, 748 lines
- **Features:**
  - Tabs: Details, Products, Builds, Payment (non-TP)
  - Payment summary cards: Total, Paid, Due
  - Payment status badge (Paid/Partial/Pending)
  - Payment history table with columns: Date, Mode, Amount, Reference, Recorded By
  - Record Payment dialog (Super users): amount, mode, reference
  - Generate Invoice dialog for offline orders
  - Status update dialog with forward-only navigation
  - Cancel order confirmation dialog
  - Inventory management section (offline orders)
  - Auto-detects order type (TP vs KG) and uses correct API endpoint
  - React Query for order and payment data fetching

#### 3. OrderCreate — Add "Create from Existing Order" (Reorder)
- **Modified:** `src/pages/Orders/OrderCreate.jsx` — 20.3 KB, 587 lines
- **Features:**
  - Reorder section at top: Enter order ID to load existing order
  - Auto-loads order when coming from `/orders/reorder/:orderId` route
  - Pre-fills form with existing order data (customer, addresses, products, builds)
  - Clear button to reset and start fresh
  - Existing order summary display when reorder is active

#### 4. Updated queryKeys.js
- **Modified:** `src/lib/queryKeys.js`
- **Change:** `tpOrders` key changed from `(orderId) => ['tpOrders', { orderId }]` to `() => ['tpOrders']` for list fetching

#### 5. Updated main.jsx
- **Changes:**
  - Added `/orders/reorder/:orderId` route
  - Updated TP orders legacy redirect: `/tporders` → `/orders?channel=tp`
  - Updated Offline orders legacy redirect: `/offlineorders` → `/orders?channel=offline`
  - Total routes: 142, 0 duplicates

#### 6. Updated navigation.jsx
- **Changes:**
  - Added "Payment Vouchers" to Orders section management actions

### Files modified
- `src/pages/Orders/OrdersList.jsx` — 16.0 KB, unified TP + KG orders list
- `src/pages/Orders/OrderDetail.jsx` — 31.7 KB, unified order detail with payment/inventory
- `src/pages/Orders/OrderCreate.jsx` — 20.3 KB, added reorder functionality
- `src/lib/queryKeys.js` — Updated tpOrders key
- `src/routes/main.jsx` — Added reorder route, updated legacy redirects
- `src/data/navigation.jsx` — Added Payment Vouchers to Orders section

### API Endpoints Used
- `GET kurostaff/tporders?limit=500` — Fetch TP orders
- `GET kurostaff/kgorders?limit=500` — Fetch KG/Offline orders
- `GET kurostaff/<type>?orderid=<id>` — Fetch single order
- `GET kuroadmin/inwardpayments/<orderid>` — Fetch payment data
- `POST kurostaff/<type>?orderid=<id>` — Update order status
- `POST kuroadmin/inwardpayments` — Record payment
- `GET kurostaff/check_list?orderid=<id>` — Download checklist
- `GET kurostaff/kgorders?orderid=<id>&generate_invoice=true` — Generate invoice

### Impact
- **Single source of truth:** One OrdersList handles all order types
- **Unified order detail:** All order management in one page with tabs
- **Payment tracking:** Integrated payment recording and history
- **Reorder workflow:** Easy reordering from existing orders
- **Legacy preserved:** All old routes redirect to new unified pages
- **Channel filtering:** URL params for channel and stage filtering

### Next
- **Phase 6:** Products & Procurement reorganization (frontend pages)
- **Phase 7:** Legacy cleanup — remove old page files
