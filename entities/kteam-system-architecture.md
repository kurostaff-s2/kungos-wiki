---
tags: [architecture, django, react, fullstack, api]
created: 2026-04-22
updated: 2026-04-22
sources: [kteam-dj-be:src/, kteam-fe-chief:src/, kteam-fe-react:wiki/]
related: [[knox-auth]], [[kteam-dj-be]], [[kteam-fe-react]], [[postgres]], [[mongodb]], [[meilisearch]]
status: stable
---

# kteam-system-architecture

## Summary

Full system architecture for the Kuro Gaming ecosystem: **kteam-dj-be** (Django/DRF backend) serves **kteam-fe-chief** (React 19 staff portal) plus other clients. Dual-database design (PostgreSQL for relational, MongoDB for document data), per-business-group multi-tenancy with 45+ granular permission fields. 155+ API endpoints across 5 Django apps, 129+ frontend pages. Auth via Knox tokens, MeiliSearch for full-text search, external integrations with Cashfree (payments) and SMS gateway.

## Details

### Tech Stack

**Frontend (kteam-fe-chief):** React 19, Vite 8, Redux Toolkit 5 + Thunk + Persist, React Router v7, Tailwind CSS v4, Radix UI, shadcn/ui pattern, CVA, Axios, Lucide React, Recharts, react-toastify, react-helmet-async, react-select, react-datepicker. ~129 pages, Phase 3 wrapping ~80/129 done.

**Backend (kteam-dj-be):** Python 3.x, Django, DRF, Knox (token auth), PostgreSQL, MongoDB/PyMongo, MeiliSearch, Django Crontab, Gunicorn + Nginx + Certbot. External: Cashfree, SMS gateway, PDF generation (xhtml2pdf + reportlab + PyPDF2).

### Functional Architecture

**Django Apps (5):**
- `users/` — User management, Knox auth, access levels (45+ permission fields), business groups, phone OTP
- `kuroadmin/` — Admin panel: employees, vendors, inventory, POs, invoices, payments, products, presets, SMS headers, counters, financials, analytics
- `kurostaff/` — Staff-facing: orders, estimates, payments (inward/outward/bulk), purchases, inventory, stock, financials, analytics
- `rebellion/` — E-sports tournament management: teams, players, matches, prize pools (MongoDB-backed)
- `careers/` — Job application management with phone verification

**Frontend Structure:** 129 pages under `src/pages/` organized by domain. Redux actions (`admin/`, `user/`, `products/`) dispatch Axios calls. Shared UI library in `src/components/ui/` (kt-* + shadcn/ui). Vite aliases (@/, @pages, @actions, @components, @hooks, @data).

### Data Flow

Request: Browser → React → Redux Action → Axios → Nginx → Gunicorn → Django Router → DRF View → Knox Auth → Permission Check → PostgreSQL ORM + MongoDB PyMongo → JSON/PDF response.

Three data stores:
- **PostgreSQL:** CustomUser, KuroUser, Accesslevel, BusinessGroup, Switchgroupmodel, PhoneModel, Common_counters, JobApplication
- **MongoDB "kuropurchase":** products, inventory, purchaseorders, vendors, estimates, orders, payments, employees, counters, misc, bgData
- **MongoDB per-BG:** Each BusinessGroup has isolated MongoDB database
- **MeiliSearch:** Indexed products, orders, inventory for full-text search

### Database Manipulations

- **PostgreSQL (Django ORM):** `CustomUser.objects.filter(phone=...)`, `Accesslevel.objects.filter(userid=...)`, bulk updates, JSONField operations on BusinessGroup.entities and Accesslevel.branches
- **MongoDB (PyMongo):** Direct `db[collection].find(filters, fields)`, `.sort()`, `.limit()`, `insert_many()`, `update_one()`, `delete_many()`. Custom `decode_result()` encodes ObjectId→str, datetime→formatted string.
- **Aggregations:** Counter generation (atomic increment), brand management (entity-keyed JSON), PO aggregation (joins PO + vendor data from separate collections).
- **Cross-database:** Every request resolves BusinessGroup from PostgreSQL, uses `db_name` to select MongoDB DB. Accesslevel permissions checked via PostgreSQL, applied to MongoDB queries via entity filtering.

### API Endpoints (155+)

- `/auth/staff` — Password login → Knox token
- `/auth/otp-login` — OTP login
- `/kuro/user` — Current user profile
- `/bggroup` — List business groups
- `/bgSwitch` — Switch BG context
- `/kuroadmin/*` — ~35 admin endpoints (employees, vendors, products, inventory, POs, invoices, payments, SMS, counters, brands, financials, analytics, audit, branches, productfinder, peripherals, portal editor, estimates, TP builds, indent, service)
- `/kurostaff/*` — ~20 staff endpoints (orders, estimates, payments, purchases, inventory, stock, financials, analytics, branches, states, brands)
- `/rebellion/*` — E-sports (tournaments, teams, players, matches, prizepool)
- `/careers/*` — Job applications and phone verification

### Multi-Tenancy

BusinessGroup is the tenant root. Each BG has its own MongoDB database. Accesslevel model provides 45+ granular permission fields (inward_invoices, outward_invoices, purchase_orders, products, inventory, orders, sales, hr, financials, analytics, etc.) with values 0=disabled, 1=view, 2=edit. Pandas DataFrame used for permission filtering. Switchgroupmodel tracks current BG context per session.

### Authentication

Knox token-based (not JWT). Token stored in localStorage + Redux state. Sent via `Authorization: Token {token}` header. No refresh token mechanism.

### Theme System

Dual theme dark/light via `[data-theme]` selectors. ThemeContext centralized. 879 lines of CSS custom properties in `src/index.css`.

## Known Issues & Anti-patterns

- `!== null` doesn't catch `undefined` (use `!= null`)
- `prodData[collection]` can be undefined even when prodData is truthy (use optional chaining `?.filter()`)
- Pandas DataFrame for simple permission filtering (heavy dependency)
- `request.query_params.dict()` used directly as MongoDB query filter (no validation)
- Cashfree API keys hardcoded in views.py
- No rate limiting on auth/SMS endpoints
- No input validation on MongoDB query parameters
- Three PDF libraries (xhtml2pdf + reportlab + PyPDF2)
- All endpoints use `@api_view` functions (not ViewSets)
- No pagination on list endpoints
- No caching layer (no Redis)
- No test coverage

## Recommendations

**P1 Critical:** Move API keys to env vars, fix `prodData[collection]` bug pattern, add input validation for MongoDB queries, add rate limiting.

**P2 High:** Replace pandas with Django ORM filtering, implement Redis caching, add DB indexes on bg_code/entity, add pagination.

**P3 Medium:** Consolidate duplicate utilities (JSONEncoder, decode_result), complete CSS-to-Tailwind migration, complete Phase 3 page wrapping, add drf-spectacular for API docs, set up pytest-django + Vitest.

**P4 Low:** Add Celery for background tasks (SMS, PDF, indexing), add Sentry monitoring, introduce TanStack Query for server state, consolidate PDF libraries, add MeiliSearch management commands.

## References

- [[knox-auth]] — Authentication system
- [[kteam-dj-be]] — Backend wiki page
- [[kteam-fe-react]] — Frontend wiki page
- [[postgres]] — PostgreSQL database
- [[mongodb]] — MongoDB document store
- [[meilisearch]] — Search engine
- [[no-inline-api-keys]] — Anti-pattern: never hardcode credentials
- [[no-unnecessary-deps]] — Anti-pattern: minimize dependencies
