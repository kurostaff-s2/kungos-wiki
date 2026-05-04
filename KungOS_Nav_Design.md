**KungOS Navigation Design - Locked Spec**
***Status:*** * Final - ready for implementation*
 *
 * ***Last updated:*** * 2026-05-04*
 *
 * ***Scope:*** * Sidebar navigation + Header bar for KungOS / K-Team admin platform*
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANklEQVR4nO3OMQ2AABAAsSNBCkLfFR7wwIgHRiywEZJWQZeZ2ao9AAD+4lyruzq+ngAA8Nr1AOIEBeX8aGZPAAAAAElFTkSuQmCC)
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANklEQVR4nO3OMQ2AABAAsSNBCkLfFR7wwIgHRiywEZJWQZeZ2ao9AAD+4lyruzq+ngAA8Nr1AOIEBeX8aGZPAAAAAElFTkSuQmCC)
**Rules**
| | |
|-|-|
| **UI/UX Stack** | All UI components and styling must be built with **Tailwind CSS + Radix UI + shadcn/ui**. No custom CSS frameworks. Use shadcn primitives as the foundation, extend with Tailwind utilities, and rely on Radix for unstyled accessible behavior. |
| **Responsive Design** | All UI/UX must be **mobile-first**, then optimised for **tablet** and **desktop**. Every component, layout, and navigation pattern must work seamlessly across all three breakpoints. Use Tailwind responsive utilities (`sm:`, `md:`, `lg:`, `xl:`) to adapt layouts progressively. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANElEQVR4nO3OQQmAABRAsSdYxKa/jL0MIR7FCt5E2BJsmZmt2gMA4C+Otbqr8+sJAACvXQ85SAYUQNBTfQAAAABJRU5ErkJggg==)
**Architecture Principle**
**Sidebar = Navigation** (where to go) ·  **Header = Actions** (what to do)
The sidebar is purely for browsing the information architecture. Global actions - search, creation, notifications - live in the header. This keeps cognitive load low: users scan the sidebar to find their work, and use the header to act on it.
![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANElEQVR4nO3OQQmAABRAsSdYxKa/jL0MIR7FCt5E2BJsmZmt2gMA4C+Otbqr8+sJAACvXQ85SAYUQNBTfQAAAABJRU5ErkJggg==)
**Header Bar**
┌──────────────────────────────────────────────────────────────────────┐
 │  KungOS  K-Team          [ 🔍  Search / Cmd+K ]      [+ Create]  🔔  👤  │
 └──────────────────────────────────────────────────────────────────────┘

| | |
|-|-|
| **Element** | **Purpose** |
| **KungOS K-Team** | Brand lockup. Static. Reinforces product identity on every screen. |
| **Search / Cmd+K** | Command Palette trigger. App-wide search across pages, records, and actions. Keyboard shortcut Cmd+K / Ctrl+K opens instantly. Surfaces: navigate to any page, search orders/products/customers, quick actions (switch tenant, toggle theme, logout), recently visited items. |
| **[+ Create]** | Primary quick-action button. Dropdown surfaces all creatable entities: New Order, New Estimate, New Service Request, New Invoice, New Purchase Order, New Payment Voucher, New Employee. Context-aware - prioritizes items relevant to the current section. |
| **🔔 Notifications** | System alerts: order status changes, payment confirmations, low-stock warnings, approval requests. |
| **👤 User Avatar** | Opens User Menu (Profile, Preferences, Logout). Also shows current user name and role badge. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANklEQVR4nO3OMQ2AABAAsSNBACPykMH4NpGACyywEZJWQZeZ2aszAAD+4l6rrTo+jgAA8N71AL/CBEiG5xPoAAAAAElFTkSuQmCC)
**Sidebar Navigation**
**1. Dashboard**
**Purpose:** Executive landing page. The first screen users see after login. High-level metrics across the entire business - no drilling, just the pulse of the operation.
| | |
|-|-|
| **Page** | **Purpose** |
| **Overview** | Key metrics at a glance: today's orders, revenue, pending approvals, low-stock alerts. The "cockpit" view. |
| **Order Analytics** | Charts and trends for order volume, fulfillment speed, channel breakdown (online/offline/TP). |
| **Finance Analytics** | Revenue trends, receivables aging, cash flow summary, expenditure patterns. |
| **Team Performance** | Employee productivity metrics, order handling per person, attendance summary, payroll snapshot. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AUBBAsUeCE4yeIiT9CRVMWGAjJK2CbjNzVGcAAPzF2qu7Wl9PAAB47XoA/vcF8exqpY4AAAAASUVORK5CYII=)
**2. Orders**
**Purpose:** The operational heart of the platform. Every transaction that generates revenue lives here - from initial quote to fulfilled delivery.
| | |
|-|-|
| **Page** | **Purpose** |
| **Quick Overview** | At-a-glance order health: three pre-configured views showing orders that need attention right now. The first thing users see when entering Orders. |
| ↳ Payment Due | Orders with outstanding payments past due date. |
| ↳ High Value | Orders above a configurable threshold (e.g., ₹50,000+). |
| ↳ Delayed Orders | Orders past expected delivery date. |
| **Overview** | Order pipeline summary: counts by status (new, processing, shipped, delivered, cancelled), today's targets vs. actuals. |
| **All Orders** | Unified order list with filtering by status, date, channel, customer. The primary working screen for order management. |
| **Estimates** | Sales quotes - pre-order pricing documents. Can be converted to orders. Tracks won/lost/pending. |
| **Service Requests** | Repair and service intake. Warranty vs. paid decision flows into order creation. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AABAAsSNhwgJe0PYTKpnRgQU2QtIq6DIze3UGAMBf3Gu1VcfXEwAAXrseaIEEMYtKmi4AAAAASUVORK5CYII=)
**3. Inventory**
**Purpose:** Everything related to physical goods - what you sell, what you build, what you buy, and what you have in stock.
| | |
|-|-|
| **Page** | **Purpose** |
| **Stock Overview** | Summary of current stock levels across branches. Low-stock alerts, fast-moving items, dead stock. |
| **Products** | Master product catalog. Individual SKUs with pricing, descriptions, images, and stock status. |
| **Presets** | Pre-configured product bundles (e.g., standard PC configurations). Reusable templates for quick order assembly. |
| **Pre-Builts** | Ready-to-sell assembled systems. Finished goods with their own SKUs and stock levels. |
| **TP Builds** | Third-party build orders. Custom builds managed through TP (third-party) channels. |
| **Purchase Orders** | Outgoing orders to vendors/suppliers. Tracks what's been ordered, what's received, what's pending. |
| **Indents** | Internal stock requests between branches or from warehouse to counter. Requisition workflow. |
| **Real-Time Inventory** | Live stock movement log. Every stock-in, stock-out, transfer, and adjustment in chronological order. The audit trail for physical goods. |
| **Audit** | Historical audit records for inventory discrepancies, stock adjustments, and reconciliation entries. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AABAAsSPBCUZfE2IYmVDBhAU2QtIq6DIzW7UHAMBfnGt1V8fXEwAAXrse/xcF7U7sx4wAAAAASUVORK5CYII=)
**4. Accounts**
**Purpose:** Financial operations. Money in, money out, tax compliance, and financial reporting.
| | |
|-|-|
| **Page** | **Purpose** |
| **Financials Overview** | Top-level financial summary: P&L snapshot, balance summary, cash position. The first stop for any financial review. |
| **Receivables & Payables** | All cash-flow transactions grouped by direction - what's coming in and what's going out. |
| ↳ Sales Invoices (Revenue) | Invoices issued to customers. The primary revenue document. Links to orders and payments. |
| ↳ Purchase Invoices (Expenditure) | Invoices received from vendors. The primary expenditure document. Links to purchase orders and payment vouchers. |
| ↳ Inward Payments | Money received from customers. Cash, bank transfer, cheque - all payment receipts. |
| ↳ Payment Vouchers | Money paid to vendors and suppliers. Outgoing payment records with approval workflow. |
| ↳ Bulk Payments | Batch payment processing - paying multiple invoices or receiving multiple payments in one operation. |
| ↳ Vendors | Vendor master records managed in the context of payables. Contact info, payment terms, outstanding balances. |
| **Tax Panel** | Tax documentation and compliance. |
| ↳ Credit / Debit Notes | Adjustments to invoices - credits for returns/refunds, debits for additional charges. Can apply to both sales and purchase invoices. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AABAAsSNhwgJuUPYDMpnRgQU2QtIq6DIze3UGAMBf3Gu1VcfXEwAAXrseaHEEM+cJoFcAAAAASUVORK5CYII=)
**5. Teams**
**Purpose:** People management. Everything about who works for the business - their records, time, compensation, and system access.
| | |
|-|-|
| **Page** | **Purpose** |
| **Members** | Unified person directory. Merges employee HR records and system user accounts into one profile. Name, role, branch, contact, hire date, and access status in a single view. |
| **Timesheets** | Attendance and time tracking. Daily check-in/out, leave requests, overtime, and monthly attendance summaries. |
| **Payroll** | Salary management. Pay slips, deductions, bonuses, payroll runs, and payment history. |
| **Job Applications** | Recruitment pipeline. Incoming applications, interview scheduling, offer letters, and onboarding status. |
| **Roles & Access** | Permission management. Define roles (Manager, Sales, Inventory, Admin) and assign access levels to members. Controls what each user can see and do in the platform. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OQQmAABRAsSdYxZ4/mJjEsxE8W8GbCFuCLTOzVXsAAPzFuVZ3dXw9AQDgtesBxPEF3bv7x0IAAAAASUVORK5CYII=)
**6. Cafe Platform**
**Purpose:** Dedicated module for cafe/restaurant operations. Separate from the core K-Team ERP because it serves a different operational model - table service, station management, and member wallets.
| | |
|-|-|
| **Page** | **Purpose** |
| **Dashboard** | Cafe-specific metrics: active sessions, table occupancy, wallet balances, today's cafe revenue. |
| **Stations** | POS station management. Configure terminals, assign to counters, track station status (active/idle/offline). |
| **Sessions** | Active dining sessions. Table assignments, order timelines, session duration, and checkout. |
| **Wallets** | Member prepaid wallets. Balance tracking, top-up history, redemption logs. |
| **Pricing** | Cafe menu pricing. Item prices, combo deals, happy hour pricing, and price overrides. |
| **Members** | Cafe loyalty members. Membership tiers, points balance, visit history, and preferences. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAAM0lEQVR4nO3OMQ0AIAwAwZKQ6kBqjSAOJywYYCIkd9OP36pqRMQMAAB+sfqJfLoBAMCN3NYoAzBA+QG0AAAAAElFTkSuQmCC)
**Bottom Rail**
Elements below the main navigation, visually separated by dividers.
**⚙ Settings**
**Purpose:** Administrative configuration. Items users visit infrequently - setup, structure, and system preferences. Tucked away from the main nav to reduce daily cognitive load.
| | |
|-|-|
| **Page** | **Purpose** |
| **Counters** | Counter master configuration. Define POS counters, assign locations, set opening/cash float. |
| **Business Groups** | Business group management (mirrors Organization). Create, edit, and configure top-level tenant entities. |
| **Brands** | Brand configuration. Logo, colors, tax IDs, default pricing rules. |
| **Divisions** | Division setup. Name, scope, and associated branches. |
| **Branches** | Branch management. Address, contact, operating hours, and tenant context assignment. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AABAAsSNhZscaUpheJwqQgQU2QtIq6DIze3UGAMBf3Gu1VcfXEwAAXrseopcEQ2uoYnwAAAAASUVORK5CYII=)
**👤 User Menu**
**Purpose:** Personal account controls. Pinned to the absolute bottom of the sidebar - the last resort before leaving the app.
| | |
|-|-|
| **Item** | **Purpose** |
| **Profile** | View and edit personal information: name, email, phone, photo, default branch. |
| **Preferences** | App preferences: theme (light/dark), language, notification settings, date/time format. |
| **Logout** | End session. Clears JWT cookies and returns to login screen. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANUlEQVR4nO3OMQ2AABAAsSPBCj7fFwtCmJHAjAU2QtIq6DIzW7UHAMBfnGt1V8fHEQAA3rsexOkF3va0dq8AAAAASUVORK5CYII=)
**Navigation Metrics**
| | |
|-|-|
| **Metric** | **Value** |
| **Main sections** | 6 (Dashboard, Orders, Inventory, Accounts, Teams, Cafe Platform) |
| **Settings items** | 5 (Counters, Business Groups, Brands, Divisions, Branches) |
| **User menu items** | 3 (Profile, Preferences, Logout) |
| **Total leaf pages** | ~45 |
| **Max nesting depth** | 3 levels (Accounts → Receivables & Payables → Sales Invoices) |
| **Settings + User** | Bottom rail, visually separated |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAANElEQVR4nO3OQQmAABRAsSdYxKY/jbnMIJ7FCt5E2BJsmZmt2gMA4C+Otbqr8+sJAACvXQ85TgYRMv3/cwAAAABJRU5ErkJggg==)
| | |
|-|-|
| **Counters in Settings, not Accounts** | Counters are structural configuration (define POS locations, cash float, assign branches) - not a financial transaction. Belongs alongside Business Groups, Brands, Divisions, Branches as admin setup. |

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAnEAAAACCAYAAAA3pIp+AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAAM0lEQVR4nO3OMQ0AIAwAwdIgBKl1gjacsGCAiZDcTT9+q6oRETMAAPjF6ify6QYAADdyA9Y0AypN+bdfAAAAAElFTkSuQmCC)
**Interaction Pattern — Slide-Out Panels**
Every expandable group in the sidebar uses the same interaction: **click → panel slides out to the right.**

| | |
|-|-
| **Trigger** | Click any section label, Settings, or User Menu row |
| **Panel** | Radix `Popover` with `side="right" sideOffset={8}` — renders via Portal to the right of the sidebar |
| **Close** | Click a nav item (navigates + closes), click outside, or press Escape |
| **Depth** | Nested groups inside the panel use the same Popover pattern (panel-within-panel) |
| **No inline expansion** | Sidebar height never changes — children live in the overlay panel |
| **Active state** | Open panel highlights the active item with `bg-primary/10 text-primary` |

**Why Popover over DropdownMenu:** Popover gives explicit `open` state control, supports multi-depth nesting without z-index stacking wars, and the panel can be wider than a typical dropdown. DropdownMenu Portal fights the sidebar's `z-[200]` stacking context.

**Implementation Notes**
- **Lazy loading:** All section routes should be code-split. Sidebar renders instantly; page content loads on navigation.
- **Active state:** Current section and current page should both be visually indicated (section highlight + page bold).
- **Collapsible sections:** Each section should collapse to its icon + label to save vertical space.
- **Tenant-aware:** All pages respect the current tenant context (BG → Brand → Division → Branch). Data is scoped automatically.
- **Command Palette:**Cmd+K / Ctrl+K global shortcut. Fuzzy search across all nav items, recent pages, and key records.
- **Responsive:** On mobile, sidebar becomes a slide-out drawer. Header remains sticky.
- **UI/UX Stack:** All sidebar components built with **Tailwind CSS + Radix UI Popover + shadcn/ui**. No custom CSS. Sidebar `aside` uses `overflow-x-hidden` (not `overflow-hidden`) so Popover Portals render unclipped.
