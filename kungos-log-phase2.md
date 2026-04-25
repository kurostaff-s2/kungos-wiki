## [2026-04-23] Navigation & Order Restructure — Phase 2: Estimate & Service Request Consolidation (Frontend)

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Phase 2: consolidate Estimates and Service Requests into unified list/detail views

**Context:** Estimates and Service Requests were scattered across the navigation with inconsistent UX. Estimates used useEffect+axios, Service Requests used React Query but were mixed into the same page. Both needed unified list and detail views with proper status pipelines and order conversion capability.

### Changes made

#### 1. New AlertDialog component
- **Created:** `src/components/ui/AlertDialog.jsx` — Radix UI AlertDialog wrapper
- **Exports:** AlertDialog, AlertDialogPortal, AlertDialogOverlay, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader, AlertDialogFooter, AlertDialogTitle, AlertDialogDescription, AlertDialogAction, AlertDialogCancel
- **Added to:** `src/components/ui/index.jsx`

#### 2. EstimatesList.jsx — Unified estimate list (React Query-migrated)
- **Created:** `src/pages/Estimates/EstimatesList.jsx`
- **Migrated from:** `src/pages/Estimates.jsx` (useEffect+axios → React Query)
- **Features:**
  - React Query with `queryKeys.estimates()` for consistent caching
  - Search by estimate no, customer name, phone
  - Status filter (all/draft/quoted/accepted/rejected)
  - Stats cards: Total, Draft, Quoted, Accepted, Rejected
  - DataTable with columns: Estimate No, Customer, Entity, Total, Status, Date, Actions
  - Row click navigates to detail view
  - Duplicate action preserved from original
  - Entity filtering via TenantContext
  - Access control via `accesslevels.estimates`

#### 3. EstimatesDetail.jsx — Unified estimate detail
- **Created:** `src/pages/Estimates/EstimatesDetail.jsx`
- **Migrated from:** `src/pages/EstimateOrder.jsx`
- **Features:**
  - React Query for estimate data fetching
  - Status stepper: Draft → Quoted → Accepted → Closed
  - Info cards: Total Quote, Customer, Entity
  - Customer details section (name, phone, address, city/state)
  - Dates section (estimated, dispatch by, status)
  - Products table (with maker, category, qty, price, total)
  - Builds table (custom builds)
  - Notes/description section
  - **Actions:** Accept, Reject, Convert to Order
  - Accept/Reject dialogs with confirmation
  - Convert to Order dialog — creates order from estimate data
  - Status-based action gating (accept/reject disabled if already done)

#### 4. ServiceRequestsList.jsx — Unified SR list (React Query-migrated)
- **Created:** `src/pages/ServiceRequests/ServiceRequestsList.jsx`
- **Migrated from:** `src/pages/Service.jsx` (already React Query, but consolidated)
- **Features:**
  - React Query with `queryKeys.serviceRequests()` for consistent caching
  - Status tabs: All, Received, Diagnosed, In Repair, Ready, Done
  - Search by SR ID, customer, device, issue
  - Stats cards: Total, Received, Diagnosed, In Repair, Ready, Done
  - DataTable with columns: SR ID, Customer, Device, Issue, Type, Assigned, Status, Date, Actions
  - Employee assignment lookup
  - Entity filtering via TenantContext
  - Access control via `accesslevels.service_request`

#### 5. ServiceRequestsDetail.jsx — Unified SR detail with warranty/paid decision
- **Created:** `src/pages/ServiceRequests/ServiceRequestsDetail.jsx`
- **Migrated from:** `src/pages/ServiceRequest.jsx`
- **Features:**
  - React Query for SR data fetching
  - Status stepper: Received → Diagnosed → In Repair → Ready → Done
  - Info cards: Customer, Device, Assigned To
  - Issue description (editable)
  - Repair logs with timestamps and assignments
  - **Warranty/Paid Repair Decision Flow** (key new feature):
    - When status is "Diagnosed", shows Warranty and Paid Repair buttons
    - Warranty: marks as warranty repair (no invoice needed)
    - Paid Repair: opens estimate creation dialog
    - Estimate creation: labor cost, parts cost, description → creates estimate → navigates to Estimates
  - Status advancement dialog
  - Field editing for issue description
  - Entity filtering via TenantContext

#### 6. Route updates in `src/routes/main.jsx`
- **Added imports:** EstimatesList, EstimatesDetail, ServiceRequestsList, ServiceRequestsDetail
- **New routes:**
  - `/orders/estimates` → EstimatesList
  - `/orders/estimates/new` → CreateEstimate (existing)
  - `/orders/estimates/:estimate_no` → EstimatesDetail
  - `/orders/service-request` → ServiceRequestsList
  - `/orders/service-request/new` → Service (existing create form)
  - `/orders/service-request/:srid` → ServiceRequestsDetail
- **Legacy redirects:**
  - `/estimates` → `/orders/estimates`
  - `/estimates/:estimate_no` → `/orders/estimates/:estimate_no`
  - `/nps/estimates/:estimate_no` → `/orders/estimates/:estimate_no`
  - `/create-estimate` → `/orders/estimates/new`
  - `/service-request` → `/orders/service-request`
  - `/servicerequest/:srid` → `/orders/service-request/:srid`

### Files created
- `src/pages/Estimates/EstimatesList.jsx` — 13.4 KB
- `src/pages/Estimates/EstimatesDetail.jsx` — 20.8 KB
- `src/pages/ServiceRequests/ServiceRequestsList.jsx` — 14.2 KB
- `src/pages/ServiceRequests/ServiceRequestsDetail.jsx` — 24.9 KB
- `src/components/ui/AlertDialog.jsx` — 3.5 KB

### Files modified
- `src/components/ui/index.jsx` — Added AlertDialog exports
- `src/routes/main.jsx` — Added imports, new routes, legacy redirects

### Impact
- **Estimates:** Now under unified `/orders/estimates` path with proper list/detail views
- **Service Requests:** Now under unified `/orders/service-request` path with warranty/paid decision flow
- **Order conversion:** Estimates can be converted to orders; SR paid repairs create estimates → orders
- **Consistent UX:** Both use React Query, DataTable, StatusBadge, StatCard patterns
- **Legacy preserved:** All old routes redirect to new paths (bookmarks work)
- **Tenant-aware:** Both use TenantContext for entity filtering
- **Access controlled:** Both check proper access levels

### Next
- **Phase 3:** Build `ConvertToOrderDialog` component (shared between Estimate/SR detail)
- **Phase 4:** Navigation restructure — update `navigation.jsx` with new hierarchy
- **Phase 5:** Order consolidation — merge Offline into unified OrdersList
