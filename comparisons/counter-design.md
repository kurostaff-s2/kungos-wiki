<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>


For comparison — here is a developer-facing implementation blueprint that turns the category-level design language into concrete route templates, reusable component shells, Tailwind/shadcn structure, and an execution todo list.  The blueprint keeps one shared interaction system across the app while giving Accounts, Orders, Inventory, Products, and HR their own default page architecture based on the category purpose already defined in the report.[^1]

## Shell

The report already establishes the common UI contract: page header with primary action, stat cards where useful, card-wrapped content, Badge for statuses, DataTable for list views, grid-based forms, breadcrumbs on detail views, and consistent empty/loading states.  It also identifies the reusable base components that should be created first: `PageHeader`, `StatCard`, `FormField`, `EmptyState`, and `PageBreadcrumb`, with shadcn primitives like `Card`, `Button`, `Tabs`, `Dialog`, and `Select` as the main building blocks.[^1]

**App shell component tree**[^1]

```tsx
<AppLayout>
  <SidebarNav />
  <MainShell className="space-y-6 p-6">
    <TopBar />
    <Outlet />
  </MainShell>
</AppLayout>
```

**Global page skeleton**[^1]

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

**Shared file structure**[^1]

```txt
src/
  components/
    common/
      PageHeader.tsx
      PageBreadcrumb.tsx
      StatCard.tsx
      FormField.tsx
      EmptyState.tsx
      PageFilters.tsx
      PageSection.tsx
      DetailHero.tsx
      StickyActionBar.tsx
    domain/
      accounts/
      orders/
      inventory/
      products/
      hr/
    ui/
      ...shadcn
  pages/
    accounts/
    orders/
    inventory/
    products/
    hr/
  routes/
    accounts.tsx
    orders.tsx
    inventory.tsx
    products.tsx
    hr.tsx
```

**Shared Tailwind rules**[^1]

- Page root: `space-y-6`.[^1]
- Header row: `flex items-center justify-between`.[^1]
- Stat grid: `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4`.[^1]
- Cards: `rounded-xl border border-border bg-surface shadow-sm`.[^1]
- Titles: `text-2xl font-bold tracking-tight text-foreground`.[^1]
- Body text: `text-sm text-foreground`; meta text: `text-xs text-muted-foreground`; amounts/codes: `font-mono font-medium`.[^1]


## Accounts

The report defines Accounts as financial record-keeping with speed, clarity, DataTable, badges, summary cards, card-wrapped forms, and card-based detail sections for invoices, notes, purchase orders, vouchers, vendors, financials, analytics, and GST views.  That means the route blueprint should default to ledger-like list pages, verification-oriented detail pages, and structured document forms with sticky totals and minimal navigation hops.[^1]

### Proposed routes

| Route | Template | Component tree | Tailwind/shadcn structure |
| :-- | :-- | :-- | :-- |
| `/accounts/invoices` | List | `AccountsInvoiceListPage > PageHeader > StatCardGrid > InvoiceFilterBar > Card > Tabs > DataTable` [^1] | Page root `space-y-6`; filters `flex flex-wrap gap-3`; table inside `CardContent`; status uses `Badge`; primary CTA uses `Button`. [^1] |
| `/accounts/invoices/:id` | Detail | `AccountsInvoiceDetailPage > PageBreadcrumb > DetailHero > SummaryCards3Up > InvoiceInfoCard > LineItemsCard > PaymentCard > AuditTrailCard` [^1] | Top summary grid `grid grid-cols-1 gap-6 lg:grid-cols-3`; line items in `Card`; action cluster `flex items-center gap-2`. [^1] |
| `/accounts/invoices/new` | Create/Edit | `AccountsInvoiceFormPage > PageBreadcrumb > PageHeader > Card(Form) > Section(DocumentInfo) > Section(Vendor) > Section(LineItems) > StickyTotalsCard > StickyActionBar` [^1] | Form grid `grid grid-cols-1 gap-4 md:grid-cols-2`; footer `flex items-center gap-3`; use `Input`, `Select`, `Textarea`, `DatePicker`, `Button`. [^1] |
| `/accounts/financials` | Summary/list hybrid | `FinancialOverviewPage > PageHeader > StatCardGrid > Card > Tabs > DataTable` [^1] | Reuse dashboard-like stat grid; tabbed financial buckets in `TabsList`; detail rows in `DataTable`. [^1] |
| `/accounts/analytics` | Analytics/list hybrid | `PaymentAnalyticsPage > PageHeader > ComparisonCards > Card > DataTable` [^1] | Two-up comparison cards `grid grid-cols-1 gap-4 lg:grid-cols-2`; daily breakdown in `CardContent`. [^1] |

### Accounts list template

```tsx
<div className="space-y-6">
  <PageHeader title="Inward Invoices" description="Track, verify, and act on financial documents." action={<CreateInvoiceButton />} />
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard />
    <StatCard />
    <StatCard />
    <StatCard />
  </div>
  <Card>
    <CardHeader className="space-y-4">
      <Tabs defaultValue="pending">
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap gap-3">
        <Input className="w-full md:w-72" />
        <Select />
        <Select />
        <DateRangePicker />
      </div>
    </CardHeader>
    <CardContent>
      <DataTable />
    </CardContent>
  </Card>
</div>
```


### Accounts detail template

- Use a top hero row with document number, status badge, created/due metadata, and right-aligned actions for Edit, Download, Approve, Reject, or Mark Paid.[^1]
- Place Vendor, Invoice Details, and Payment in a 3-card summary row before deeper sections so the current financial truth is visible without scrolling the whole page.[^1]
- Keep Line Items and Tax Breakdown as separate cards, and add Audit Trail beneath them instead of mixing metadata into the main content.[^1]


### Accounts create/edit template

- Break the form into cards for Document Info, Counterparty, Line Items, Tax, and Notes instead of a raw table layout.[^1]
- Use `FormField` with `Input`, `Select`, `Textarea`, and `DatePicker`, and replace every hardcoded-width field with `w-full` inside a responsive grid.[^1]
- Footer actions must always be `Cancel`, `Save Draft`, and `Submit`, and add inline vendor creation through a drawer so users do not leave the invoice workflow.[^1]


## Orders and Inventory

The report defines Orders around lifecycle flow — create, track, fulfill, invoice — with stage tabs, custom row renderers, dropdown row actions, and card-based detail sections.  It defines Inventory as read-heavy and already closest to refined, with DataTable as the backbone, card-wrapped filters, styled selects, buttonized add/remove actions, and TP Build as the main exception needing structural cleanup.[^1]

### Orders routes

| Route | Template | Component tree | Tailwind/shadcn structure |
| :-- | :-- | :-- | :-- |
| `/orders` | List | `OrdersListPage > PageHeader > StatCardGrid > StageTabs > OrderFilterBar > Card > DataTable` [^1] | Stage tabs in `TabsList`; customer cell uses `Avatar + text`; row actions use `DropdownMenu`. [^1] |
| `/orders/:id` | Detail | `OrderDetailPage > PageBreadcrumb > DetailHero > CustomerCard > ShippingCard > LineItemsCard > TotalsCard > TimelineCard` [^1] | Body uses `space-y-6`; top info cards use `grid grid-cols-1 gap-6 lg:grid-cols-3`. [^1] |
| `/orders/new` | Create/Edit | `OrderFormPage > PageBreadcrumb > MultiStepShell > StepCustomer > StepItems > StepShipping > StepBilling > StepReview > StickyActionBar` [^1] | Steps can be `Tabs` or explicit wizard state; section content uses `Card`; two-column form grid at `md+`. [^1] |

**Orders list template**[^1]

```tsx
<div className="space-y-6">
  <PageHeader title="Orders" description="Create, track, fulfill, and invoice customer orders." action={<NewOrderButton />} />
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
    <StatCard />
    <StatCard />
    <StatCard />
    <StatCard />
    <StatCard />
  </div>
  <Card>
    <CardHeader className="space-y-4">
      <Tabs defaultValue="new">
        <TabsList>
          <TabsTrigger value="new">New</TabsTrigger>
          <TabsTrigger value="pending">Pending Auth</TabsTrigger>
          <TabsTrigger value="packed">Packed</TabsTrigger>
          <TabsTrigger value="delivered">Delivered</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap gap-3">
        <Input className="w-full md:w-72" />
        <Select />
        <Select />
        <DateRangePicker />
      </div>
    </CardHeader>
    <CardContent>
      <DataTable />
    </CardContent>
  </Card>
</div>
```

**Orders detail rules**[^1]

- The dominant CTA should reflect the next operational step, such as Approve, Pack, Dispatch, or Invoice, instead of presenting all actions with equal weight.[^1]
- Keep Customer, Billing, Shipping, Line Items, and Totals in separate cards, and add a fulfillment timeline or status history card below the commercial sections.[^1]
- Use a `DropdownMenu` for duplicate, delete, and low-frequency actions so the top bar stays focused.[^1]

**Orders create/edit rules**[^1]

- Convert the raw table-style form into a multi-step, card-wrapped workflow with responsive fields and no `w-[300px]` widths.[^1]
- Add searchable line-item selection, inline customer/address creation, and a sticky review/totals summary before submission.[^1]
- Primary footer CTA: `Submit Order`; secondary CTAs: `Save Draft`, `Cancel`.[^1]


### Inventory routes

| Route | Template | Component tree | Tailwind/shadcn structure |
| :-- | :-- | :-- | :-- |
| `/inventory/stock-register` | List | `StockRegisterPage > PageHeader > FilterTabs > InventoryFilterBar > Card > DataTable` [^1] | Dense filter row, styled `Select`, table-first layout, no oversized cards. [^1] |
| `/inventory/audit` | List/detail hybrid | `AuditPage > PageHeader > StatCardGrid(optional) > FilterBar > Card > DataTable > AuditDrawer` [^1] | Keep list dense; corrections open in drawer for minimal navigation. [^1] |
| `/inventory/tp-builds` | List | `TPBuildListPage > PageHeader > FilterBar > Card > DataTable` [^1] | List uses same DataTable system as inventory/product pages. [^1] |
| `/inventory/tp-builds/:id` | Detail/Edit | `TPBuildDetailPage > PageBreadcrumb > DetailHero > CoreComponentsCard > StorageCard > PeripheralsCard > PricingCard > StickyActionBar` [^1] | Each component family gets its own `Card`; dynamic rows use icon buttons, not `[+]`/`[-]`. [^1] |
| `/inventory/tp-builds/new` | Create/Edit | `TPBuildFormPage > PageBreadcrumb > PageHeader > CardsByComponentGroup > PricingTable > StickyActionBar` [^1] | Form groups in `space-y-6`; fields `grid grid-cols-1 gap-4 md:grid-cols-2`; pricing in `Card + DataTable`. [^1] |

**Inventory list rules**[^1]

- Preserve DataTable as the main canvas, because the report identifies inventory as already the most refined category through that component.[^1]
- Move all entity, brand, category, and date filters into one card header row using styled shadcn `Select` components.[^1]
- Make low stock, mismatch, and adjustment-needed rows visually obvious through badges and row emphasis rather than separate pages.[^1]

**TP Build detail/edit rules**[^1]

- Split the form into Core Components, Storage, Peripherals, and Pricing cards exactly as the report outlines, rather than one monolithic form.[^1]
- Replace text spans for add/remove with `Button variant="ghost" size="icon"` and use a pricing DataTable for cost, margin, and selling price.[^1]
- Keep `Cancel` and `Submit` in a sticky action region so long technical forms remain actionable.[^1]


## Products and HR

The report defines Products as catalog management with DataTable-backed lists, card-wrapped detail sections, inline pricing controls, image/media blocks, config grids, and tabbed portal editing.  It defines HR as people management with employee DataTable views, avatars, badges, card-wrapped forms, attendance grids, salary tables, business-group management, and a reusable `AttendanceCell` replacing large inline class logic.[^1]

### Products routes

| Route | Template | Component tree | Tailwind/shadcn structure |
| :-- | :-- | :-- | :-- |
| `/products` | List | `ProductsListPage > PageHeader > StatCardGrid > Tabs > ProductFilterBar > Card > DataTable` [^1] | Tabs for Products, Presets, Pre-Builts, Portal; thumbnail column uses image container block. [^1] |
| `/products/:id` | Detail | `ProductDetailPage > PageBreadcrumb > DetailHero > ProductDetailsCard > SpecsCard > PricingCard > ImagesCard > RelatedConfigsCard` [^1] | Cards stacked with `space-y-6`; media strip inside `flex gap-3 flex-wrap`. [^1] |
| `/products/new` | Create/Edit | `ProductFormPage > PageBreadcrumb > PageHeader > Tabs/Steps(Basic, Specs, Pricing, Images, Portal) > StickyActionBar` [^1] | Tabbed editor in `Card`; inputs `w-full`; compact price editors `w-24 text-right font-mono`. [^1] |
| `/products/portal-editor` | Editor | `PortalEditorPage > PageHeader > Tabs > EditorCard > PreviewCard` [^1] | Use tabbed editing rather than ad hoc buttons. [^1] |

**Products list template**[^1]

```tsx
<div className="space-y-6">
  <PageHeader title="Products" description="Manage catalog items, presets, and portal-ready content." action={<NewProductButton />} />
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard />
    <StatCard />
    <StatCard />
    <StatCard />
  </div>
  <Card>
    <CardHeader className="space-y-4">
      <Tabs defaultValue="products">
        <TabsList>
          <TabsTrigger value="products">Products</TabsTrigger>
          <TabsTrigger value="presets">Presets</TabsTrigger>
          <TabsTrigger value="prebuilts">Pre-Builts</TabsTrigger>
          <TabsTrigger value="portal">Portal</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex flex-wrap gap-3">
        <Input className="w-full md:w-72" />
        <Select />
        <Select />
      </div>
    </CardHeader>
    <CardContent>
      <DataTable />
    </CardContent>
  </Card>
</div>
```

**Products detail/edit rules**[^1]

- Keep Details, Specs, Pricing, and Images as separate cards because the report explicitly recommends card-wrapped sections for these concerns.[^1]
- Use the image container pattern from the report for product thumbnails and media blocks rather than raw image tags dropped into tables.[^1]
- Split save actions into `Save Draft`, `Save All`, and `Publish/Approve` so catalog preparation and publication are not collapsed into one action.[^1]


### HR routes

| Route | Template | Component tree | Tailwind/shadcn structure |
| :-- | :-- | :-- | :-- |
| `/hr/employees` | List | `EmployeesListPage > PageHeader > StatCardGrid > Tabs > EmployeeFilterBar > Card > DataTable` [^1] | Employee column uses `Avatar`; role and status use `Badge`; primary CTA is Add Employee. [^1] |
| `/hr/employees/:id` | Detail | `EmployeeDetailPage > PageBreadcrumb > DetailHero(Employee) > ProfileCard > EmploymentCard > AttendanceSummaryCard > CompensationCard > AccessCard` [^1] | Use 2- or 3-column summary grids depending on content density. [^1] |
| `/hr/employees/new` | Create/Edit | `EmployeeFormPage > PageBreadcrumb > PageHeader > Card(Form) > PersonalInfoSection > EmploymentSection > CompensationSection > AccessSection > DocumentsSection > StickyActionBar` [^1] | Responsive form grid with `grid grid-cols-1 gap-4 md:grid-cols-2`. [^1] |
| `/hr/attendance` | Grid/list hybrid | `AttendancePage > PageHeader > MonthYearControls > LegendBar > Card > AttendanceGrid > StickyActionBar` [^1] | Grid uses `grid grid-cols-7` pattern and reusable `AttendanceCell`. [^1] |
| `/hr/salaries` | Table | `SalaryPage > PageHeader > FilterBar > Card > DataTable` [^1] | Group columns into pay, deductions, and net; keep export/payroll actions in header. [^1] |

**HR detail/edit rules**[^1]

- Surface identity first with employee name, avatar, role, and status badge before attendance, salary, or access details.[^1]
- Replace raw table-based employee forms with card-wrapped sections and standardized `FormField` usage.[^1]
- Treat attendance as a dedicated grid experience with a reusable `AttendanceCell` component instead of a giant inline-class table.[^1]

**Attendance component tree**[^1]

```tsx
<AttendancePage>
  <PageHeader />
  <Card>
    <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <MonthYearControls />
      <LegendBar />
    </CardHeader>
    <CardContent>
      <AttendanceGrid>
        <AttendanceRow>
          <AttendanceCell status="present" />
          <AttendanceCell status="absent" />
          <AttendanceCell status="holiday" />
        </AttendanceRow>
      </AttendanceGrid>
    </CardContent>
    <CardFooter className="flex items-center gap-3">
      <Button variant="outline">Cancel</Button>
      <Button variant="default">Submit</Button>
    </CardFooter>
  </Card>
</AttendancePage>
```


## Todo plan

The report already gives a four-phase implementation order with an estimated total of about 72 hours, moving from foundation fixes to card structure, DataTable migration, and final polish.  The most efficient way to execute this blueprint is to convert that priority list into an engineering todo plan tied directly to the reusable components and route families above.[^1]

### Phase 1 — foundation

- Replace all browser-default or legacy page titles with the shared title pattern `text-2xl font-bold text-foreground tracking-tight`.[^1]
- Add `PageHeader` to every route and standardize the title-left, action-right structure.[^1]
- Replace all raw `<button>` usage with shadcn `Button` variants and remove `[+]`/`[-]` spans in favor of icon buttons.[^1]

```
- Replace raw `<input>`, `<select>`, and `<textarea>` with `Input`, `Select`, `Textarea`, or existing `kt-input` wrappers.[^1]
```

- Replace custom tab implementations with shadcn `Tabs`.[^1]
- Replace plain text status values with `Badge`.[^1]

```
- Remove `<p>&nbsp;</p>`, `<br />`, legacy `txt-light-grey`, and hardcoded width hacks.[^1]
```


### Phase 2 — shared components

- Build `PageHeader`, `PageBreadcrumb`, `StatCard`, `FormField`, and `EmptyState` exactly as the report recommends.[^1]
- Add `PageFilters`, `DetailHero`, `StickyActionBar`, and category-specific section cards as thin wrappers around shadcn primitives to reduce repeated layout code.[^1]
- Add common loading shells: stat-card skeleton grid, table skeleton, and detail-page skeleton.[^1]
- Add toast notifications for success, error, and save-draft flows instead of `alert()`.[^1]


### Phase 3 — route migration

| Category | Routes to do first | Why |
| :-- | :-- | :-- |
| Accounts | `/accounts/invoices`, `/accounts/invoices/:id`, `/accounts/invoices/new`, `/accounts/financials`, `/accounts/analytics` | The report marks these pages as raw and a high-value target for DataTable, badges, cards, and financial summary patterns. [^1] |
| Orders | `/orders`, `/orders/:id`, `/orders/new` | This category needs lifecycle clarity and currently depends on custom tabs, raw buttons, and raw forms. [^1] |
| Inventory | `/inventory/stock-register`, `/inventory/audit`, `/inventory/tp-builds/:id`, `/inventory/tp-builds/new` | Inventory is already closest to refined, so the main win is cleanup and TP Build restructuring. [^1] |
| Products | `/products`, `/products/:id`, `/products/new`, `/products/portal-editor` | The report already identifies DataTable, config grids, image handling, and card-wrapped detail sections as the correct destination. [^1] |
| HR | `/hr/employees`, `/hr/employees/:id`, `/hr/employees/new`, `/hr/attendance`, `/hr/salaries` | HR has some of the rawest structures, especially attendance and large salary tables, and benefits strongly from reusable patterns. [^1] |

### Phase 4 — polish and QA

- Add breadcrumbs to all detail pages.[^1]
- Add empty states to every DataTable and every empty list/detail state.[^1]
- Add loading skeletons that visually match the final content structure.[^1]
- Fix invalid Tailwind classes like `bg-#87858e`, `mb-10px`, and `x-w-[300px]`.[^1]
- Verify responsive behavior by replacing hardcoded widths with grid-based `w-full` inputs and testing list/detail/form layouts at mobile and desktop widths.[^1]


### Definition of done

- No raw tables remain on pages that should be using `DataTable`, except deliberately simple semantic tables wrapped in the design system.[^1]
- No raw buttons, raw inputs, custom tab hacks, or spacing hacks remain.[^1]
- Every route has a clear page header, consistent action hierarchy, loading state, empty state, and responsive layout.[^1]
- Every detail view uses breadcrumbs plus card-wrapped sections, and every create/edit view uses structured form sections with cancel and submit actions.[^1]

Next step: implement the shared component layer first, then migrate routes in this order — Accounts, Orders, Inventory TP Builds, Products, and HR.[^1]

<div align="center">⁂</div>

[^1]: DASHBOARD.md

