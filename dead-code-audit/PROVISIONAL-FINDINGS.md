# Dead Code Audit — Provisional Findings

**Project:** kteam-dj-chief  
**Date:** 2026-06-25  
**Method:** Graph-based CALLS edge analysis (codegraph)  
**Scope:** 430 non-test, non-management-command Python/TS functions  

---

## Executive Summary

- **430 total functions** (excl. tests, management commands, migrations)
- **210 functions** have at least one incoming `CALLS` edge
- **220 functions** have zero incoming `CALLS` edges (raw candidates)
- **~160 of 220 are FALSE POSITIVES** — invoked via URL routing, DRF ViewSet actions, Celery tasks, template tags, middleware, or event bus registration (not captured by static CALLS edges)
- **~60 functions remain as true candidates** after filtering route handlers — requires manual verification

---

## Why 220 Looks Worse Than It Is

The graph analyzer only tracks **direct function calls** (`foo()` in Python). It cannot see:

| Invocation Mechanism | Example | Why Graph Misses It |
|---|---|---|
| **Django URL routing** | `path('health/', health_check)` | `health_check` is a string-to-function mapping at runtime |
| **DRF `@action` decorators** | `@action(detail=False)` on ViewSet methods | Router generates URL → method mapping dynamically |
| **DRF `DefaultRouter`** | `router.register('auth', AuthViewSet)` | Standard `list`, `create`, `retrieve` etc. auto-generated |
| **Celery tasks** | `@shared_task` decorated functions | Invoked via message queue, not direct calls |
| **Template tags/filters** | `@register.simple_tag` | Invoked by Django template engine at render time |
| **Middleware** | `get_tenant_context` in middleware | Called by Django middleware pipeline |
| **Event bus registration** | `bus.on('event', handler)` | Handlers registered via string names or callbacks |
| **Shell scripts** | `start()`, `stop()` in `run_dev.sh` | Invoked as shell functions, not Python calls |
| **`if __name__ == '__main__'`** | `main()` in scripts | Entry point, not called by other code |
| **TypeScript event handlers** | `onSelect`, `toggleModal` | Bound to DOM events, not called imperatively |

---

## False Positives (Route Handlers & Dynamic Invocation)

### HTTP Route Handlers (Django URL routing) — ~95 functions

These are mapped in `urls.py` files and invoked by HTTP requests, not function calls:

**teams/products.py** (20/20 are route handlers):
- `accounts`, `addproduct`, `adminportal`, `analytics`, `bulk_payments`, `createproduct`, `doc_generator`, `indent`, `kuroServiceRequest`, `kurodata`, `presets`, `products`, `serviceRequest`, `store_data`, `tempproducts`, `tpbuilds`, `userdetails`, `copy_sundry_balances_to_new_financial_year`, `build_daywise_totals`, `daywise_totals_pipeline`

**teams/financial.py** (17/17 are route handlers):
- `bulk_payments`, `estimates`, `financials`, `indent`, `itc_gst`, `kuroServiceRequest`, `payment`, `paymentvouchers`, `purchaseorders`, `purchases`, `sales`, `serviceRequest`, `settlements`, `updatestatement`, `uploadinvoices`, `link_callback`, `fetch_resources`

**teams/kurostaff/views.py** (20/21 are route handlers):
- `brands`, `check_list`, `counters`, `emp_attendance`, `emp_dashboard`, `indent`, `invCalculations`, `inventory`, `inwardcreditnotes`, `inwarddebitnotes`, `inwardinvoices`, `kgorders`, `orderconversion`, `outward`, `states`, `stock`, `tporders`, `updateorder`, `vendors`, `fetch_resources`
- `_parse_invoice_date` — **may be truly dead** (internal helper, not a route)

**domains/cafe_arcade/views.py** (22/22 are route handlers):
- All 22: `cafe_payments`, `cafe_payments_record`, `customer_lookup`, `customer_profile`, `customer_register`, `dashboard_overview`, `dashboard_revenue`, `dashboard_utilization`, `game_library`, `member_plans`, `member_upgrade`, `pricing_calculate`, `pricing_rules`, `session_active`, `session_end`, `session_extend`, `session_pause`, `session_resume`, `session_start`, `wallet_balance`, `wallet_recharge`, `wallet_transactions`

**kungos_admin/views.py** (9/9 are route handlers):
- `api_key_detail`, `api_keys`, `bootstrap_tenant`, `domain_configs`, `get_tenant_status`, `resume_tenant`, `suspend_tenant`, `tenant_template_detail`, `tenant_templates`

**careers/views.py** (3/3 are route handlers):
- `jobadmin`, `jobapp`, `verifyphone`

**domains/cafe_fnb/views.py** (4/4 are route handlers):
- `create_order`, `get_order`, `list_orders`, `menu`

**users/views.py** (10/10 are route handlers or ViewSet actions):
- `accesslevel`, `bgSwitch`, `emp_acc`, `employees_data`, `empprofile`, `getCounters`, `kuroloaduser`, `rebloaduser`, `update_user`, `verifyUserid`
- Note: Many of these are now served by ViewSet actions in `users/api/viewsets.py` but kept as legacy routes

**domains/tournaments/views.py** (4/4 are route handlers):
- `players`, `teams`, `tournaments`, `tourneyregister`

**teams/outward_invoices.py** (3/3 are route handlers):
- `outwardcreditnotes`, `outwarddebitnotes`, `outwardinvoices`

**teams/inward_invoices.py** (10/10 are route handlers):
- `exportinwardinvoices`, `exportinwardpayments`, `exportoutwardinvoices`, `invoices`, `inwardpayments`, `outwardpayments`, `purchases`, `sales`, `updatestatement`, `uploadinvoices`

**domains/cafe_arcade/legacy_views.py** (6/8 are route handlers):
- `rbpackages`, `reb_users`, `reborders`, `sending_rebuserdata`, `getamount`, `update_endtime`
- `order_totalsGetMethod_legacy`, `to_camel_case2` — **may be truly dead**

**backend/views.py** (1/1 is route handler):
- `health_check`

**plat/health/views.py** (2/2 are route handlers):
- `health_live`, `health_ready`

**teams/employees.py** (2/6 are route handlers):
- `employees`, `empupdate` — confirmed route handlers
- `createcollection`, `getcollection`, `send_sms_wrapper`, `smsheadersapi` — need verification

**teams/estimates.py** (1/2 is route handler):
- `estimates` — confirmed
- `smsheadersapi` — need verification

**teams/service_requests.py** (3/3 are route handlers):
- `indent`, `kuroServiceRequest`, `serviceRequest`

**teams/export_utils.py** (9/9 need verification — some may be called from views):
- `export_inwardcreditnote`, `export_inwardinvoice`, `exporttopdf`, `format_creditnote`, `format_debitnote`, `format_inwarddebitnote`, `format_outwardinvoice`, `link_callback`, `num2words`

**teams/millie.py** (4/4 are route handlers):
- `delete_document`, `millieindex`, `search_documents`, `update_document`

**teams/analytics.py** (4/4 are route handlers):
- `analytics`, `build_daywise_totals`, `daywise_totals_pipeline`, `doc_generator`

### Backend Invocation (non-HTTP)

**Celery tasks** (2 functions):
- `check_expired_sessions` (domains/cafe_arcade/tasks.py) — Celery periodic task
- `process_outbox_batch` (plat/outbox/worker.py) — Celery task

**Event bus** (1 function):
- `on` (plat/events/bus.py) — method used to *register* handlers, not called directly in test scope

**Django template tags** (1 function):
- `get_item` (teams/templatetags/extras.py) — invoked by template engine

**Middleware** (1 function):
- `get_tenant_context` (plat/observability/middleware.py) — called by Django middleware pipeline

**Scripts / Entry Points** (3 functions):
- `run_server` (run_server.py) — `if __name__ == '__main__'` entry point
- `my_mongo_backup`, `my_sql_backup` (backend/cron.py) — cron-scheduled, not called in code

**Outbox worker** (1 function):
- `retry_failed_events` (plat/outbox/service.py) — likely called by worker/scheduler

**Observability** (1 function):
- `setup_structured_logging` (plat/observability/logging.py) — called at startup, possibly via ` AppConfig.ready()`

### TypeScript Event Handlers (10 functions)

**assets/src/entry.ts** (10/10 are DOM event handlers or React callbacks):
- `calculateItemTotal`, `getCalendar`, `onSelect`, `renderNetPayablesChart`, `renderNetReceivablesChart`, `renderPnLChart`, `showModal`, `submitForm`, `toggleDropdown`, `toggleModal`
- All bound to UI events or lifecycle hooks — not called imperatively in code

---

## True Dead Code Candidates (~20-30 functions)

These have NO obvious invocation path. Require manual verification:

### High Confidence (likely dead)

| Function | File | Reason |
|---|---|---|
| `order_totalsGetMethod_legacy` | domains/cafe_arcade/legacy_views.py | "legacy" suffix, no URL mapping, no callers |
| `to_camel_case2` | domains/cafe_arcade/legacy_views.py | Numbered variant — superseded by `to_camel_case` |
| `update_endtime` | domains/cafe_arcade/legacy_views.py | No URL mapping, no callers |
| `getamount` | domains/cafe_arcade/legacy_views.py | No URL mapping, no callers |
| `_parse_invoice_date` | teams/kurostaff/views.py | Internal helper, no callers found |
| `extract_block` | teams/split_views.py | No callers, no URL mapping |
| `_retry_with_backoff` | domains/cafe_fnb/gateways.py | Internal helper, no callers |
| `check_division_access` | backend/auth_utils.py | May be superseded by `check_division_write_access` |
| `resolve_user` | backend/auth_utils.py | May be superseded by `resolve_user_with_bg` |
| `unauthorized_response` | backend/response_utils.py | `error_response` exists — may be unused variant |
| `close_mongo_client` | backend/utils.py | Cleanup function, may never be called |
| `get_branch_fallback` | backend/utils.py | No callers in our scope (called in auth_utils which is in scope) |

### Medium Confidence (need investigation)

| Function | File | Reason |
|---|---|---|
| `get_cached_permissions` | users/permissions.py | May be called by RBAC middleware |
| `invalidate_role_permissions` | users/permissions.py | May be called on role changes |
| `get_tenant_from_token` | users/tenant_tokens.py | May be called by auth middleware |
| `send_otp_sms` | users/otp_utils.py | May be called by ViewSet actions |
| `get_user_brand_code` | users/otp_utils.py | May be called by auth flow |
| `resolve_brand_code_from_request` | users/otp_utils.py | May be called by auth flow |
| `send_sms_wrapper` | teams/employees.py | May be called dynamically |
| `smsheadersapi` | teams/employees.py | Duplicate of teams/products.py? |
| `createcollection` | teams/employees.py | Duplicate of teams/infrastructure.py? |
| `getcollection` | teams/employees.py | Duplicate of teams/infrastructure.py? |

### Utility Functions (may be imported but not called in our scope)

These are helper/utility functions that may be imported by files outside our analysis scope (tests, management commands, or other modules):

**plat/shared/helpers.py** (5 functions):
- `deep_merge`, `flatten_dict`, `paginate`, `to_camel_case`, `to_snake_case`
- `to_camel_case` IS called in legacy_views.py (confirmed in called set)
- Others may be used in templates, serializers, or views outside our scope

**plat/shared/encoding.py** (5 functions):
- `decode_base64`, `encode_base64`, `encode_hex`, `generate_token`, `hash_sha256`
- May be used by auth, tokens, or crypto operations

**plat/shared/validation.py** (4 functions):
- `is_valid_email`, `is_valid_phone`, `is_valid_uuid`, `sanitize_string`
- May be used by serializers or forms

**domains/products/depreciation.py** (3 functions):
- `calculate_monthly_depreciation`, `compute_depreciation_run`, `get_depreciation_defaults`
- May be called by management commands or scheduled tasks

**backend/views_diagnostic.py** (3 functions):
- `api_cors_debug`, `api_health`, `api_routes`
- Diagnostic/debug endpoints — may not be in production URLs

---

## What's Missing From This Analysis

1. **ViewSet methods not indexed as functions** — DRF ViewSet actions (e.g., `login`, `verify`, `profile`) are methods, not standalone functions. They may or may not appear in the graph depending on indexing.
2. **Cross-file imports not followed** — If `teams/employees.py` imports `smsheadersapi` from `teams/products.py`, the graph should show a CALLS edge. If it doesn't, the function may truly be dead in one file (duplicate).
3. **Dynamic dispatch** — `getattr()`, `importlib`, or string-based function resolution won't show in CALLS edges.
4. **Signals and receivers** — Django signals (`@receiver(post_save)`) are not captured.
5. **Domains with DRF routers** — `domains/accounts/`, `domains/orders/`, `domains/products/`, `domains/vendors/`, `domains/teams/` use ViewSet-based routing. Their functions may not be in our 430-function scope if they're methods.

---

## Next Steps

1. **Verify high-confidence dead code** — Read source of top 12 candidates to confirm no hidden invocation paths.
2. **Check medium-confidence candidates** — Trace imports and middleware to see if they're called indirectly.
3. **Investigate utility functions** — Grep for actual usage in serializers, forms, or templates.
4. **Check for duplicate functions** — `smsheadersapi`, `createcollection`, `getcollection` appear in multiple files.
5. **Produce final report** — After verification, produce a clean "safe to delete" list.

---

## Methodology Notes

- **Graph backend:** SQLite + FTS5 (codegraph tools)
- **Cypher limitations:** `NOT ()-[:CALLS]-()`, `size()`, `IS NULL` are unsupported — forced two-query approach (all functions vs called functions) + in-memory diff
- **Exclusions:** Test files, `management/commands/`, migration files, `venv/`, `__pycache__/`
- **False positive rate:** ~73% (160/220) — expected for Django projects with heavy URL routing
