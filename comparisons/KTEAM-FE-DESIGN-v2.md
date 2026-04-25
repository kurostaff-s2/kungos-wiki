# KTEAM-FE-DESIGN-v2
## Comprehensive Design Language & Implementation Blueprint

**Tech Stack**: React 19 + Vite + Tailwind CSS v4 + shadcn/ui + Radix UI + Redux Toolkit + React Router v7  
**Theme**: System preference by default, manual light/dark toggle  
**Principle**: Intuitive data representation with the least possible actions for the end user, seamless functionality  
**Revision Focus**: Tightened hierarchy, reduced variant sprawl, role-aware permissions, simplified rollout plan

---

# PART A: SIDEBAR & NAVIGATION REDESIGN

## A.1 Goals

The sidebar must do four jobs well:

1. Make the product structure obvious in under 2 seconds.
2. Reduce route noise by hiding detail/create/edit pages from persistent nav.
3. Keep users inside a domain while moving between list, detail, and edit flows.
4. Reflect permissions, so users only see what they can access or act on.

## A.2 Navigation Model

Use a **two-level sidebar**:

- **Primary rail**: stable domain switches.
- **Secondary panel**: contextual pages for the currently selected domain.
- **Hidden routes**: detail, create, edit, and workflow substeps are never permanent nav items.

### Hierarchy rule

Every primary domain must follow one of these patterns consistently:

- **Pattern A — Section switcher**: clicking the primary item selects the domain and opens the secondary panel; the first secondary item is always `Overview`.
- **Pattern B — Landing page**: clicking the primary item opens a true domain landing page; the secondary panel contains the landing page plus child pages.

**Recommendation**: use **Pattern A** across all 5 domains for consistency.

That means the secondary panel for each domain always starts with an `Overview` item.

## A.3 Information Architecture

### Primary Nav

| Item | Purpose | Route |
|------|---------|-------|
| Dashboard | Cross-domain summary | `/` |
| Accounts | Finance and compliance workflows | `/accounts/overview` |
| Orders | Order lifecycle and fulfillment | `/orders/overview` |
| Inventory | Stock, audits, builds | `/inventory/overview` |
| Products | Catalog and configuration | `/products/overview` |
| HR | People, attendance, payroll, hiring | `/hr/overview` |

### Secondary Nav

#### Accounts
- Overview
- Invoices
- Credit & Debit Notes
- Purchase Orders
- Payment Vouchers
- Vendors
- Financials
- Analytics
- ITC GST

#### Orders
- Overview
- Estimates
- TP Orders
- Offline Orders
- Online Orders
- Service Requests
- Indent & Batches

#### Inventory
- Overview
- Stock Register
- Inventory
- Audit
- TP Builds

#### Products
- Overview
- Products
- Presets
- Pre-Builts
- Portal Editor

#### HR
- Overview
- Employees
- Attendance
- Salaries
- Job Apps
- Business Groups
- Access Levels

## A.4 Route Naming Rules

Normalize all routes and keys.

### Route rules
- Use lowercase kebab-case only.
- Use plural nouns for collections.
- Use `/overview` as the first child route for every domain.
- Avoid legacy fragments like `bg_group`, `employee_accesslevel`, `service-request` mixed with plural patterns.

### Key rules
- Use readable domain-prefixed keys.
- Format: `<domain>.<feature>`.

Examples:
- `accounts.invoices`
- `orders.tp-orders`
- `inventory.stock-register`
- `products.portal-editor`
- `hr.access-levels`

## A.5 Permission Rules

Permissions must shape both navigation and page actions.

### Permission model
Use capability-based permissions instead of route-only checks.

Each domain should expose permissions such as:
- `view`
- `create`
- `edit`
- `approve`
- `delete`
- `export`
- `manage`

Examples:
- `accounts.invoices.view`
- `accounts.invoices.approve`
- `orders.tp-orders.create`
- `inventory.audit.manage`
- `products.catalog.edit`
- `hr.salaries.export`

### Sidebar rules
- Hide nav items the user cannot `view`.
- Hide count badges if the user cannot act on the underlying items.
- Hide the global `Create New` entry entirely if the user has no `create` permission anywhere.
- Do not show disabled links in persistent navigation unless there is a strong compliance reason.

### Action rules
- Row actions, bulk actions, and primary CTAs must be permission-gated separately from route access.
- Example: a user may `view` invoices but not `approve` or `delete` them.
- Primary actions should collapse gracefully: `Approve Invoice` becomes read-only metadata if permission is absent.

## A.6 Badge Rules

Reduce badge noise.

Use navigation badges only when all three are true:
- the value is actionable,
- the count matters right now,
- the user has permission to resolve it.

### Allowed nav badge types
- Pending approvals
- Overdue items
- Low stock alerts
- Attendance anomalies
- Open job applications

### Do not use nav badges for
- total counts,
- vanity metrics,
- static record counts,
- duplicated signals already visible in the selected page header.

### Single-signal rule
Never show the same alert count on both the primary item and its child item unless the primary badge is an aggregate and the child badge is omitted after entering the domain.

## A.7 Global Create Pattern

Replace the generic global button with a **Create Menu**.

### Behavior
- Trigger opens a popover or command-style sheet.
- Show only high-frequency create actions.
- Filter by user permissions.
- Group by domain.
- On mobile, open full-screen sheet.

### Example items
- New Invoice
- New Order
- New Audit
- New Product
- Add Employee

Do not include low-frequency admin setup flows in this menu.

## A.8 Visual Rules

```txt
Sidebar shell:        w-72 border-r border-border bg-surface/95 backdrop-blur
Primary item:         flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm
Primary active:       bg-primary/10 text-primary border border-primary/20 shadow-sm
Secondary item:       flex items-center gap-2 rounded-lg px-3 py-2 text-sm
Secondary active:     bg-accent text-foreground font-medium
Section label:        px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground
Utility item:         h-10 w-10 rounded-xl flex items-center justify-center hover:bg-surface-hover
Count badge:          ml-auto rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary
```

### Density rule
- Primary rail is visually stronger than secondary panel.
- Secondary panel is denser than the main content area.
- Footer utilities are visually quiet.

## A.9 Mobile Rules

- Sidebar becomes a sheet.
- Hamburger lives in the top bar, not inside the sidebar.
- Secondary panel remains in the same sheet below the primary selection.
- Default open view is the current domain context.
- Close on route change for detail/create pages.

## A.10 Route Config Shape

```ts
export const sidebarConfig = {
  primary: [
    {
      label: 'Dashboard',
      icon: LayoutGrid,
      to: '/',
      key: 'dashboard',
      permission: 'dashboard.view'
    },
    {
      label: 'Accounts',
      icon: Receipt,
      to: '/accounts/overview',
      key: 'accounts',
      permission: 'accounts.view',
      children: [
        { label: 'Overview', to: '/accounts/overview', key: 'accounts.overview', permission: 'accounts.view' },
        { label: 'Invoices', to: '/accounts/invoices', key: 'accounts.invoices', permission: 'accounts.invoices.view', badge: 'pendingInvoices' },
        { label: 'Credit & Debit Notes', to: '/accounts/notes', key: 'accounts.notes', permission: 'accounts.notes.view' },
        { label: 'Purchase Orders', to: '/accounts/purchase-orders', key: 'accounts.purchase-orders', permission: 'accounts.purchase-orders.view' },
        { label: 'Payment Vouchers', to: '/accounts/payment-vouchers', key: 'accounts.payment-vouchers', permission: 'accounts.payment-vouchers.view' },
        { label: 'Vendors', to: '/accounts/vendors', key: 'accounts.vendors', permission: 'accounts.vendors.view' },
        { label: 'Financials', to: '/accounts/financials', key: 'accounts.financials', permission: 'accounts.financials.view' },
        { label: 'Analytics', to: '/accounts/analytics', key: 'accounts.analytics', permission: 'accounts.analytics.view' },
        { label: 'ITC GST', to: '/accounts/itc-gst', key: 'accounts.itc-gst', permission: 'accounts.itc-gst.view' }
      ]
    }
  ]
}
```

## A.11 Sidebar Component Rules

Build these components only:
- `AppSidebar`
- `SidebarPrimaryNav`
- `SidebarSecondaryNav`
- `NavItem`
- `SidebarCreateMenu`
- `SidebarFooter`
- `PermissionGate`

Do not create separate `PrimaryNavItem` and `SecondaryNavItem` unless behavior truly diverges. One shared `NavItem` with variants is simpler and reduces component sprawl.

---

# PART B: GLOBAL PAGE STRUCTURE

## B.1 App Shell

```tsx
<AppLayout>
  <AppSidebar />
  <MainShell className="space-y-6 p-6">
    <TopBar />
    <Outlet />
  </MainShell>
</AppLayout>
```

## B.2 Global Page Skeleton

```tsx
<div className="space-y-6">
  <PageBreadcrumb items={...} />
  <PageHeader title="" description="" action={...} />
  {showStats && (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard />
      <StatCard />
      <StatCard />
      <StatCard />
    </div>
  )}
  <Card className="rounded-xl border border-border bg-surface shadow-sm">
    <CardHeader />
    <CardContent />
  </Card>
</div>
```

## B.3 Shared Tailwind Rules

| Element | Class |
|---------|-------|
| Page root | `space-y-6` |
| Header row | `flex items-center justify-between` |
| Stat grid | `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4` |
| Cards | `rounded-xl border border-border bg-surface shadow-sm` |
| Page titles | `text-2xl font-bold tracking-tight text-foreground` |
| Body text | `text-sm text-foreground` |
| Meta text | `text-xs text-muted-foreground` |
| Amounts/codes | `font-mono font-medium` |

## B.4 Shared Component Layer

| Component | Purpose |
|-----------|---------|
| `PageHeader` | Title + description + primary action |
| `PageBreadcrumb` | Hierarchical navigation trail |
| `StatCard` | KPI metric with trend |
| `FormField` | Label + input + help text + error |
| `EmptyState` | Friendly empty state with CTA |
| `PageFilters` | Filter bar with search + selects |
| `PageSection` | Collapsible card section for forms |
| `DetailHero` | Top summary row for detail pages |
| `StickyActionBar` | Floating action bar for long forms |
| `DataTable` | Reusable data table with core features |

---

# PART C: PER-CATEGORY DESIGN LANGUAGES

## C.1 Accounts

**Purpose**: Financial record-keeping with speed, clarity, and minimal navigation hops.

**List pages**: ledger-like tables, strong date/status/amount hierarchy, KPI strip where helpful.  
**Detail pages**: verification-first summaries, line items, tax breakdown, audit trail.  
**Create/edit pages**: sectioned forms with sticky totals and inline vendor creation.  
**Analytics pages**: comparison cards, time selectors, charts, daily breakdown tables.

## C.2 Orders

**Purpose**: Manage the order lifecycle from estimate to fulfillment.

**List pages**: list-first, optional Kanban for workflow-heavy teams.  
**Detail pages**: progress stepper, fulfillment timeline, next-step CTA.  
**Create/edit pages**: step-based when process order matters.

## C.3 Inventory

**Purpose**: Provide live stock visibility, quick correction, and clear auditability.

**List pages**: dense tables, stock bars, anomaly-first signals.  
**Audit pages**: review/variance workflow.  
**TP Build pages**: grouped component cards plus pricing table.

## C.4 Products

**Purpose**: Manage catalog objects, presets, and pre-built configurations.

**List pages**: grid/list toggle, images and pricing visible, status readable.  
**Detail pages**: specs, pricing, media, related configs.  
**Create/edit pages**: tabbed editor for non-linear content editing.

## C.5 HR

**Purpose**: Manage employees, attendance, payroll, and hiring.

**Directory pages**: identity-first list/grid views.  
**Attendance**: sticky matrix, quick-edit cells, strong legends.  
**Payroll**: grouped pay/deduction/net tables.  
**Hiring**: pipeline-based candidate flow.

---

# PART D: GLOBAL DESIGN SYSTEM

## D.1 Design System Goals

The design system must be:
- small enough to learn quickly,
- expressive enough for five domains,
- strict enough to avoid drift.

This version reduces token and variant sprawl.

## D.2 Component Variant Policy

### Rule
Every shared component must have **three levels** of variants:

1. **Core semantic variants** — always available.
2. **Size variants** — only where truly needed.
3. **Domain-specific mapping** — handled by helpers, not by adding more component variants.

Do not create a new visual variant when a semantic mapping function can solve it.

## D.3 Button System

Use only these shared button variants:

| Variant | Use |
|---------|-----|
| `primary` | Main page or form action |
| `secondary` | Supporting action |
| `ghost` | Low-emphasis action or icon button |
| `danger` | Destructive action |

### Button sizes
- `sm`
- `md`
- `lg`
- `icon`

Remove redundant overlap between `secondary` and `outline`. Use **one** secondary pattern only.

## D.4 Badge System

Reduce the badge system to **five semantic variants**.

| Variant | Meaning | Common uses |
|---------|---------|-------------|
| `success` | Completed / healthy | Paid, Active, In Stock, Delivered |
| `warning` | Needs attention | Pending, Low Stock, On Hold |
| `danger` | Problem / failed | Overdue, Cancelled, Out of Stock, Absent |
| `neutral` | Draft / inactive / default | Draft, Inactive, Unassigned |
| `info` | Informational in-progress state | Confirmed, Processing, Review |

### Mapping rule
Pipeline-specific colors like purple or indigo belong in:
- progress steppers,
- Kanban headers,
- charts,
- timeline markers.

They do **not** need to exist as global badge variants.

## D.5 Typography Scale

Keep a compact scale.

| Token | Use |
|-------|-----|
| `text-xs` | Badges, helper text, metadata |
| `text-sm` | Table text, labels, buttons |
| `text-base` | Body text, inputs |
| `text-lg` | Section headers, card titles |
| `text-xl` | Sub-page headings, tabs |
| `text-2xl` | Page titles |

Do not add larger application typography except on Dashboard or marketing-like surfaces.

## D.6 Color Semantics

Use semantic tokens only.

- `background`
- `surface`
- `border`
- `foreground`
- `muted-foreground`
- `primary`
- `success`
- `warning`
- `danger`
- `info`

Do not hardcode workflow colors directly in page code.

## D.7 Form Pattern Rules

Choose form structure by task shape.

### Use sectioned single-page forms when
- users need to scan everything before submit,
- the form is document-like,
- cross-field review matters.

Examples: invoices, vendor records, employee records.

### Use stepper forms when
- the sequence matters,
- later fields depend on earlier fields,
- the user benefits from progressive disclosure.

Examples: new orders, audits, TP builds.

### Use tabbed editors when
- the object has multiple independent content modes,
- users return to edit specific slices over time.

Examples: products, portal editor.

## D.8 Shared Component Inventory

Only standardize these shared components in the first design-system layer:
- `PageHeader`
- `PageBreadcrumb`
- `StatCard`
- `StatusBadge`
- `PageFilters`
- `EmptyState`
- `FormField`
- `PageSection`
- `StickyActionBar`
- `DetailHero`
- `DataTable`

Advanced domain widgets remain domain-owned until they stabilize:
- `AttendanceCell`
- `StockLevelBar`
- `ProgressStepper`

This prevents the shared layer from becoming a dumping ground.

## D.9 URL State Rules

All list pages should sync these to the URL when applicable:
- search query,
- filters,
- sort,
- page,
- page size,
- view mode.

This improves refresh continuity, shareability, and user trust.

## D.10 Accessibility Rules

- Every icon-only action needs an accessible label.
- Tables must support keyboard focus for row actions.
- Status cannot rely on color alone.
- Sticky headers and sticky columns must preserve readable contrast.
- Command menus and sheets must trap focus correctly.

---

# PART E: IMPLEMENTATION EXECUTION PLAN

## E.1 Rollout Principles

This rollout is intentionally simplified.

### Principles
- Build the shell before redesigning pages.
- Build only the shared primitives needed by at least two domains.
- Delay advanced interactions until the page that truly requires them.
- Migrate high-ROI pages first.
- Keep legacy pages functional while replacing them incrementally.

## E.2 Phase 0 — Decision Lock

Before implementation starts, lock these decisions:
- route naming conventions,
- permission model,
- button and badge variants,
- page templates,
- URL state strategy.

Deliverables:
- `sidebarConfig` approved
- permission capability list approved
- `StatusBadge` mapping approved
- page template matrix approved

## E.3 Phase 1 — Shell & Core Primitives

### Build
- `AppSidebar`
- `NavItem`
- `SidebarCreateMenu`
- `SidebarFooter`
- `PageHeader`
- `PageBreadcrumb`
- `EmptyState`
- `FormField`
- `StatusBadge`
- `PageFilters`
- `DataTable` (core only)

### DataTable v1 scope
- sorting
- filtering
- pagination
- row actions
- loading state
- empty state
- responsive overflow

### Do not build yet
- drag and drop
- virtualization
- column pinning
- mobile card transformation
- advanced grouped headers

## E.4 Phase 2 — High-ROI Migration

### Accounts
- Invoices list
- Invoice detail
- New invoice
- Vendors list

### Products
- Products list
- Product detail
- New product

Reason: these pages prove the list/detail/create system quickly and expose the most obvious raw UI issues.

## E.5 Phase 3 — Workflow Pages

### Orders
- Orders list
- Order detail
- New order
- Estimate flows

### Inventory
- Inventory list
- Stock register
- Audit flow
- TP build list/detail

In this phase, add only the advanced components you now actually need:
- `ProgressStepper`
- `StockLevelBar`

## E.6 Phase 4 — Complex HR & Advanced Table Features

### HR
- Employees list/detail/new
- Attendance
- Salaries
- Job Apps

### Add only after real need is proven
- virtualization for large tables,
- `AttendanceCell` optimization,
- Kanban drag and drop,
- column pinning,
- grouped salary headers.

## E.7 Phase 5 — Polish & Hardening

- empty states everywhere
- skeletons everywhere
- toast notifications
- keyboard shortcuts
- accessibility audit
- responsive QA
- permission audit
- performance audit
- route cleanup

## E.8 Deliverable Checklist Per Page

A page is complete only when it has:
- correct page template,
- permission-gated actions,
- loading state,
- empty state,
- responsive behavior,
- URL-synced filter state if list-based,
- keyboard-accessible actions,
- no raw legacy controls.

## E.9 Simplified Migration Order

| Order | Area | Goal |
|------|------|------|
| 1 | Shell | New sidebar, permissions, shared nav |
| 2 | Shared | Header, breadcrumb, badge, form field, filters, DataTable v1 |
| 3 | Accounts | Prove document-heavy workflows |
| 4 | Products | Prove grid/list + editor patterns |
| 5 | Orders | Add workflow sequencing and stepper |
| 6 | Inventory | Add stock-specific visualization |
| 7 | HR | Add matrix-heavy attendance and payroll |
| 8 | Polish | QA, accessibility, performance |

---

# PART F: ROUTE MIGRATION ORDER

| Phase | Category | Routes | Why |
|-------|----------|--------|-----|
| 1 | Sidebar + Shared | App shell, nav, page primitives | Foundation for all pages |
| 2 | Accounts | Invoices, Vendors | Highest clarity ROI |
| 2 | Products | Products list/detail/new | Proves catalog patterns |
| 3 | Orders | Order flows | Introduces workflow patterns |
| 3 | Inventory | Stock, audit, TP builds | Adds stock-specific UX |
| 4 | HR | Employees, attendance, salaries, job apps | Most complex data shapes |

---

# PART G: REUSABLE COMPONENT SPECIFICATIONS

## G.1 DataTable

```txt
Props:
- columns
- data
- searchKey?
- filterColumns?
- pagination?
- sorting?
- loading?
- emptyText?
- onRowClick?
- actions?

Features in v1:
- Sorting
- Global search
- Column-level filters
- Pagination
- Per-row action dropdown
- Sticky header
- Skeleton loading state
- Empty state
```

## G.2 StatusBadge

```txt
Props:
- status
- variant: success | warning | danger | neutral | info
- size: sm | md | lg

Features:
- semantic mapping
- text + color accessibility
- consistent sizing
```

## G.3 StatCard

```txt
Props:
- title
- value
- trend?
- icon?

Features:
- card metric display
- trend indicator
- responsive layout
```

---

# PART H: ANTI-PATTERNS TO AVOID

1. Raw HTML tables on structured data pages.
2. Inline styles for production UI.
3. Hardcoded workflow colors in page code.
4. Too many badge variants.
5. Too many shared components too early.
6. Showing detail/create/edit routes in persistent nav.
7. Permission-blind nav and actions.
8. Forms that mix tabs, steppers, and sections without a reason.
9. Filters that reset on refresh.
10. Badge counts that are not actionable.

---

# PART I: DEFINITION OF DONE

- Sidebar follows two-level hierarchy with domain `Overview` routes.
- Nav items and page actions are permission-aware.
- Badge system uses only five semantic variants.
- Button system uses only four shared variants.
- Shared component layer stays intentionally small.
- DataTable v1 is implemented before advanced table features.
- No detail/create/edit routes appear in persistent nav.
- Every migrated page uses the correct template type.
- List pages preserve state through URL params where appropriate.
- No raw legacy controls remain on migrated pages.

---

*This v2 document keeps the original product direction, but makes the system stricter, smaller, and easier to execute without design or engineering drift.*
