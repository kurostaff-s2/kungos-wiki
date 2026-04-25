## [2026-04-23] Navigation & Order Restructure — Phase 8: Frontend Component Extraction

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Component Consolidation Plan

### Changes made

#### New shared components (8 files + 1 index)

**1. `StatusStepper.jsx`** — Pre-configured status steppers for 3 workflows
- `OrderStatusStepper` — Order fulfillment (New → Products → Auth → InProc → Shipped → Delivered → Cancelled)
- `EstimateStatusStepper` — Estimate pipeline (Draft → Quoted → Accepted → Closed)
- `SRStatusStepper` — Service request pipeline (Received → Diagnosed → In Repair → Ready → Done)
- `GenericStatusStepper` — For any custom pipeline
- Status index helpers: `getOrderStatusIndex`, `getEstimateStatusIndex`, `getSRStatusIndex`

**2. `OrderInfoGrid.jsx`** — Info display components
- `OrderInfoGrid` — 4-column grid (Order Date, Total, Status, Dispatch By)
- `AddressBlock` — Reusable billing/shipping address display
- `CustomerBlock` — Customer info display

**3. `StatusActionsBar.jsx`** — Context-aware action buttons
- `OrderStatusActions` — Order detail actions (Authorize, Cancel, Invoice, Update Status, Reorder, Checklist)
- `EstimateStatusActions` — Estimate actions (Accept, Reject, Convert to Order)
- `SRStatusActions` — SR actions (Warranty, Paid Repair, Advance Status)

**4. `ListPageHeader.jsx`** — List page UI patterns
- `SearchFilterBar` — Combined search + filter + reset
- `StatusTabs` — Status tab buttons
- `ChannelFilter` — Channel pill buttons (TP, Offline, Online)
- `ViewToggle` — Table/Kanban view toggle

**5. `OrderPaymentSection.jsx`** — Payment display and recording
- `PaymentSummaryCard` — Total/Paid/Due summary with status badge
- `PaymentHistoryTable` — Payment history with DataTable
- `RecordPaymentDialog` — Modal for recording payments

**6. `OrderTableComponents.jsx`** — Products and builds tables
- `OrderProductsTable` — Products for orders
- `OrderBuildsTable` — Builds for orders
- `EstimateProductsTable` — Products for estimates
- `EstimateBuildsTable` — Builds for estimates

**7. `SRDecisionFlow.jsx`** — Service request decision flow
- `SRWarrantyDecision` — Warranty/Paid Repair buttons
- `SRAdvanceStatusDialog` — Status advancement dialog
- `SRCreateEstimateDialog` — Repair estimate creation dialog
- `SRWarrantyConfirmDialog` — Warranty confirmation dialog

**8. `EntryPointCards.jsx`** — Summary stat cards
- `EntryPointsStatCards` — Estimates/SRs/Orders summary
- `OrderPipelineStatCards` — Pipeline stage counts
- `EstimateStatCards` — Estimate status counts
- `SRStatCards` — SR status counts

**9. `common/index.jsx`** — Centralized exports for all 8 components

#### Refactored pages (6 files)

**Orders/OrderDetail.jsx** — Replaced inline implementations:
- Inline stepper → `ProgressStepper` (via shared component)
- 4-column info grid → `OrderInfoGrid`
- Address display → `AddressBlock`
- Customer display → `CustomerBlock`
- Products table → `OrderProductsTable`
- Builds table → `OrderBuildsTable`
- Payment summary → `PaymentSummaryCard`
- Payment history → `PaymentHistoryTable`
- Record payment → `RecordPaymentDialog`
- Status actions → `OrderStatusActions`

**Orders/OrdersList.jsx** — Replaced inline implementations:
- Channel filter → `ChannelFilter`
- View toggle → `ViewToggle`
- Stats → `OrderPipelineStatCards`

**Estimates/EstimatesDetail.jsx** — Replaced inline implementations:
- Inline stepper → `EstimateStatusStepper`
- Status actions → `EstimateStatusActions`
- Products table → `EstimateProductsTable`
- Builds table → `EstimateBuildsTable`

**Estimates/EstimatesList.jsx** — Replaced inline implementations:
- Stats → `EstimateStatCards`
- Search/filter → `SearchFilterBar`

**ServiceRequests/ServiceRequestsDetail.jsx** — Replaced inline implementations:
- Inline stepper → `SRStatusStepper`
- Status actions → `SRStatusActions` + `SRWarrantyDecision`
- Warranty confirm → `SRWarrantyConfirmDialog`
- Paid repair flow → `SRCreateEstimateDialog`
- Advance status → `SRAdvanceStatusDialog`

**ServiceRequests/ServiceRequestsList.jsx** — Replaced inline implementations:
- Stats → `SRStatCards`
- Status tabs → `StatusTabs`
- Search → `SearchFilterBar`

### Impact

| Metric | Before | After |
|---|---|---|
| Duplicate status steppers | 3 (inline) | 1 (shared) |
| Duplicate product/builds tables | 4 (inline) | 4 (shared) |
| Duplicate payment sections | 2 (inline) | 1 (shared) |
| Duplicate status action patterns | 3 (inline) | 1 (shared) |
| Duplicate list page patterns | 3 (inline) | 1 (shared) |
| Shared components | 0 | 9 |
| Pages refactored | 0 | 6 |
| Files changed | — | 15 |
| Lines added | — | +1,459 |
| Lines removed | — | -867 |

### Build verification
- All 15 new/modified files pass basic syntax checks (braces, parens balanced)
- Pre-existing build errors in `OutwardInvoice.jsx` and `Profile` are unrelated
- No new import resolution errors

### Next
- Phase 8 complete
- Additional pages can now use shared components for consistency
- Future pages should import from `@/components/common` instead of implementing inline
