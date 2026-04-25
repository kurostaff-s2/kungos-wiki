<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# design a sidebar for nav for this

Yes — the right nav pattern here is a two-level sidebar: a stable primary rail for the major domains and a contextual secondary panel for the selected domain, so users always see the full system but only interact with the links relevant to the current task.  That matches the report’s core direction of shared page structure across the app, with distinct behavior for Accounts, Orders, Inventory, Products, and HR instead of forcing every page to imitate the dashboard.[^1]

## Sidebar model

The sidebar should be task-first, not route-dump-first: top for global entry, middle for the five major categories, and a secondary layer for the pages inside the selected category.  Since the app already standardizes page headers, breadcrumbs, DataTable-heavy list pages, and category-specific list/detail/create flows, the nav should privilege category entry and frequent list pages rather than exposing every detail/edit route as permanent navigation.[^1]

Detail pages and create/edit pages should stay out of persistent nav and be reached contextually from list pages, row actions, primary CTAs, and breadcrumbs.  That reduces noise, keeps the sidebar short, and supports the “least possible actions” rule you set for the whole redesign.[^1]

## Navigation map

| Zone | Content |
| :-- | :-- |
| Top | Workspace logo/home plus one global action button such as “Create New,” reflecting the shared page-header pattern where pages have a clear primary action. [^1] |
| Primary nav | Dashboard, Accounts, Orders, Inventory, Products, HR. [^1] |
| Context panel | Show only the child pages for the currently selected category, rather than expanding every category at once. |
| Footer | Utility links such as settings/profile/help, plus collapse toggle and theme toggle. |

| Category | Child routes to show in sidebar |
| :-- | :-- |
| Accounts | Invoices, Credit/Debit Notes, Purchase Orders, Payment Vouchers, Vendors, Financials, Analytics, ITC GST. [^1] |
| Orders | Estimates, TP Orders, Offline Orders, Service Requests, Users, Indent/Batches. [^1] |
| Inventory | Stock Register, Audit, TP Builds, Inventory. [^1] |
| Products | Products, Presets, Pre-Builts, Portal Editor. [^1] |
| HR | Employees, Attendance, Salaries, Job Apps, Business Groups, Access Levels. [^1] |

## Interaction rules

Use badges sparingly in the nav: only for actionable counts like pending approvals, low stock, or open job apps, because the report already defines a badge system and emphasizes status-driven workflows across categories.  Active items should use the same token logic as the rest of the app — subtle surface elevation by default, stronger primary tint only for the current route, and muted text for inactive items.[^1]

On desktop, keep the sidebar fixed with a collapsible icon-only rail mode; on mobile, turn the same structure into a slide-over sheet so information-dense pages still have maximum content width. The selected category should persist while moving between its list, detail, and create/edit pages, so the user never feels like they “left” that domain.

## Visual spec

The visual language should echo the report’s established primitives: rounded card-like surfaces, border tokens, muted meta text, and button/badge hierarchy rather than custom ad hoc styles.  The category layer should feel like navigation, not content cards — low contrast at rest, stronger contrast on hover, and a clear active state with icon + label + optional count badge.[^1]

Recommended Tailwind/shadcn treatment:

- Sidebar shell: `w-72 border-r border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80`
- Section label: `px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground`
- Nav item: `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground-muted transition-colors hover:bg-surface-hover hover:text-foreground`
- Active item: `bg-primary/10 text-primary border border-primary/20 shadow-sm`
- Count badge: `ml-auto rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary`
- Collapse rail item: `h-10 w-10 rounded-xl flex items-center justify-center hover:bg-surface-hover`


## Component blueprint

Use one sidebar shell and drive it from config, with category-aware child navigation.  Since the project already leans on shadcn/ui, Radix patterns, Buttons, Badges, Tabs, and shared components, the sidebar should be built from the same primitives rather than a custom isolated system.[^1]

```tsx
<AppLayout>
  <AppSidebar>
    <SidebarHeader>
      <BrandLockup />
      <Button size="sm" className="w-full justify-start gap-2">
        <Plus className="h-4 w-4" />
        Create New
      </Button>
    </SidebarHeader>

    <SidebarPrimaryNav>
      <PrimaryNavItem icon={LayoutGrid} label="Dashboard" to="/" />
      <PrimaryNavItem icon={Receipt} label="Accounts" to="/accounts" active />
      <PrimaryNavItem icon={ShoppingCart} label="Orders" to="/orders" />
      <PrimaryNavItem icon={Boxes} label="Inventory" to="/inventory" />
      <PrimaryNavItem icon={Package} label="Products" to="/products" />
      <PrimaryNavItem icon={Users} label="HR" to="/hr" />
    </SidebarPrimaryNav>

    <SidebarSecondaryNav title="Accounts">
      <SecondaryNavItem label="Invoices" to="/accounts/invoices" badge="12" />
      <SecondaryNavItem label="Credit / Debit Notes" to="/accounts/notes" />
      <SecondaryNavItem label="Purchase Orders" to="/accounts/purchase-orders" />
      <SecondaryNavItem label="Payment Vouchers" to="/accounts/payment-vouchers" />
      <SecondaryNavItem label="Vendors" to="/accounts/vendors" />
      <SecondaryNavItem label="Financials" to="/accounts/financials" />
      <SecondaryNavItem label="Analytics" to="/accounts/analytics" />
      <SecondaryNavItem label="ITC GST" to="/accounts/itc-gst" />
    </SidebarSecondaryNav>

    <SidebarFooter>
      <SidebarUtilityItem icon={PanelLeftClose} label="Collapse" />
      <SidebarUtilityItem icon={SunMoon} label="Theme" />
      <SidebarUtilityItem icon={Settings} label="Settings" />
      <UserMenu />
    </SidebarFooter>
  </AppSidebar>

  <MainShell>
    <Outlet />
  </MainShell>
</AppLayout>
```

A clean implementation split is: `AppSidebar`, `PrimaryNav`, `SecondaryNav`, `NavSectionLabel`, `NavItem`, and `SidebarFooter`, all driven by a route config object. The most important behavior is that the secondary panel changes by selected category, while the primary rail stays stable across the whole app.

<div align="center">⁂</div>

[^1]: DASHBOARD.md

