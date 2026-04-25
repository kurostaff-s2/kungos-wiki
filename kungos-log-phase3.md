## [2026-04-23] Navigation & Order Restructure — Phase 3: ConvertToOrderDialog Component

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Phase 3: Build shared `ConvertToOrderDialog` component

**Context:** Phase 2 created separate inline dialogs for converting estimates and SRs to orders. Phase 3 consolidates this into a reusable component that handles both source types with proper linking and status preservation.

### Changes made

#### 1. New ConvertToOrderDialog component
- **Created:** `src/components/common/ConvertToOrderDialog.jsx` — 19.3 KB
- **Features:**
  - Supports two source types: `estimate` and `servicerequest`
  - For estimates: pre-fills order with products, builds, pricing, customer info
  - For SRs: creates order for repair labor + parts (paid repair flow)
  - Links new order to source document (`estimate_no` or `srid` fields)
  - Shows summary of items, customer, and total pricing
  - Order details form: channel, PO/ref, dates
  - Product/build line-item summaries
  - SR-specific repair details (device, issue, labor/parts costs)
  - Uses `kuroadmin/estimates/convert` for estimates
  - Uses `kuroadmin/servicerequest?action=create-order` for SRs
  - Invalidates relevant queries on success
  - Navigates to new order after creation

#### 2. Updated EstimatesDetail.jsx
- **Modified:** `src/pages/Estimates/EstimatesDetail.jsx`
- **Changes:**
  - Replaced inline convert dialog with `<ConvertToOrderDialog>` component
  - Removed duplicate mutation logic (now handled by shared component)
  - Simplified imports (removed Dialog/DialogHeader/DialogFooter imports)
  - Kept accept/reject dialogs (different flow)

#### 3. Updated ServiceRequestsDetail.jsx
- **Modified:** `src/pages/ServiceRequests/ServiceRequestsDetail.jsx`
- **Changes:**
  - Added `ConvertToOrderDialog` import
  - Added `convertDialogOpen` state
  - Added `handleConvertToOrder` function
  - Replaced paid repair decision flow to open ConvertToOrderDialog
  - Kept estimate creation dialog (separate flow for labor/parts entry)

### Files created
- `src/components/common/ConvertToOrderDialog.jsx` — 19.3 KB

### Files modified
- `src/pages/Estimates/EstimatesDetail.jsx` — Simplified, uses shared component
- `src/pages/ServiceRequests/ServiceRequestsDetail.jsx` — Uses shared component

### API Endpoints Used
- **Estimates:** `POST kuroadmin/estimates/convert?estimate_no=X&version=Y`
- **SRs:** `POST kuroadmin/servicerequest?action=create-order&srid=X`

### Impact
- **Code reuse:** Single component handles both estimate and SR conversion
- **Consistent UX:** Same dialog experience regardless of source type
- **Proper linking:** Orders linked back to source documents
- **Query invalidation:** Lists refresh after conversion
- **Cleaner pages:** Detail pages are simpler without inline dialog code

### Next
- **Phase 4:** Navigation restructure — update `navigation.jsx` with new hierarchy
- **Phase 5:** Order consolidation — merge Offline into unified OrdersList
