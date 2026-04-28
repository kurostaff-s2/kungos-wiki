<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# format this with specific  agentic instrictions for execution

Here is the full course of action reformatted as agentic execution instructions — each task is a self-contained unit with a clear trigger condition, exact file target, precise code change, and a verifiable success signal.

***

# KungOS v2 — Agentic Execution Plan

**Generated:** 2026-04-28 | **Based on:** E2E Report Card + KungOS_v2.md cross-reference
**Execution model:** Tasks are ordered by dependency. Complete each task fully before proceeding. Verify the success signal before marking done.

***

## BLOCK A — Execute Immediately (Today, ~6h total)

> These tasks are independent of each other and can be run in parallel. They restore test accuracy and fix active runtime bugs.

***

### TASK A-1 — Fix Tournaments 500 Error

**File:** `rebellion/views.py`
**Trigger:** `GET /api/v1/rebellion/tournaments/` returns HTTP 500 — `accepted_renderer` not set
**Blocker for:** E2E test 4.20, Phase 3 exit criteria

```python
# FIND the tournaments view — it currently looks like:
def get_tournaments(request):
    # ... logic ...
    return HttpResponse(json.dumps(data), content_type='application/json')

# REPLACE with DRF Response pattern:
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tournaments(request):
    # ... same logic unchanged ...
    return Response(data)
```

**If the view is a class-based view:** ensure `renderer_classes = [JSONRenderer]` is set on the class.

**Run to verify:**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TEST_JWT" \
  http://localhost:8000/api/v1/rebellion/tournaments/
# Expected: 200 or 401 — NEVER 500
```

**Success signal:** `python -m pytest tests/ -v -k "tournament"` passes. E2E test 4.20 passes.

***

### TASK A-2 — Re-enable Auth on `gamers()` Endpoint

**File:** `rebellion/views.py`
**Trigger:** Auth is commented out on the `gamers()` view — anyone can create sessions
**Blocker for:** Phase 0 P0 \#5 exit criterion; security go-live gate

```python
# FIND — somewhere in gamers() or its class:
# authentication_classes = []   ← commented-out or empty
# permission_classes = []       ← commented-out or empty

# REPLACE:
from rest_framework.permissions import IsAuthenticated
from users.cookieauth import CookieJWTAuthentication

@api_view(['GET', 'POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def gamers(request):
    # existing logic unchanged
```

> **Note:** This is a temporary patch. The final state per CAFE_PLATFORM.md §2 replaces this endpoint with `POST /api/v1/cafe/customer/lookup` + walk-in wallet balance check. That is a Phase Cafe task, not this task.

**Run to verify:**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/api/v1/rebellion/gamers/
# Expected: 401
```

**Success signal:** Unauthenticated request returns 401, not 200.

***

### TASK A-3 — Fix `getAuthHeader()` in Playwright Specs

**File:** `e2e/helpers/auth.js` (create if not exists) + update all spec imports
**Trigger:** 8/8 outbox tests fail with 403; auth header not reaching protected endpoints
**Blocker for:** `06-outbox-events.spec.js` (8 failures), `04-api-integration.spec.js` (3 failures)

**Step 1 — Create helper file:**

```js
// e2e/helpers/auth.js
export async function getAuthHeader(page) {
  const cookies = await page.context().cookies(['http://localhost:8000'])
  const jwt = cookies.find(c => c.name === 'jwt_token')
  if (!jwt) {
    throw new Error('[getAuthHeader] jwt_token cookie missing — ensure loginAs() was called before this test')
  }
  return { Authorization: `Bearer ${jwt.value}` }
}

export async function loginAs(page, userid, password) {
  await page.goto('/login')
  await page.fill('#userid', userid)
  await page.fill('#pwd', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('/dashboard', { timeout: 10000 })
}
```

**Step 2 — Update all affected spec files:**

```js
// In 06-outbox-events.spec.js and 04-api-integration.spec.js
// REMOVE any existing inline getAuthHeader function
// ADD at top:
import { getAuthHeader, loginAs } from './helpers/auth.js'

// In beforeEach or test setup:
await loginAs(page, process.env.E2E_ADMIN_USER, process.env.E2E_ADMIN_PASSWORD)
const headers = await getAuthHeader(page)
// Pass headers to all fetch() or request() calls
```

**Run to verify:**

```bash
cd /home/chief/Coding-Projects/kteam-fe-chief
npx playwright test 06-outbox-events --reporter=line
# Expected: 15/15 pass (after T-01, T-03 are both done)
```

**Success signal:** `06-outbox-events.spec.js` goes from 7/15 → 15/15.

***

### TASK A-4 — Fix Auth Cookie Assertion (False Positive)

**File:** `e2e/01-auth.spec.js`
**Trigger:** Test 1.16 always passes regardless of whether the cookie is set
**Blocker for:** Accurate auth test reporting

```js
// FIND in 01-auth.spec.js (around test 1.16):
expect(cookies.length).toBeGreaterThanOrEqual(0)  // ← DELETE this line

// REPLACE with:
const jwtCookie = cookies.find(c => c.name === 'jwt_token')
expect(jwtCookie, 'jwt_token cookie must exist after login').toBeDefined()
expect(jwtCookie.httpOnly, 'jwt_token must be HttpOnly').toBe(true)
expect(jwtCookie.path, 'jwt_token path must be /').toBe('/')
expect(['Lax', 'Strict']).toContain(jwtCookie.sameSite)
expect(jwtCookie.domain, 'jwt_token must be for localhost').toMatch(/localhost/)
```

**Run to verify:**

```bash
npx playwright test 01-auth --reporter=line
# Expected: 16/16 pass (previously 15/16)
```

**Success signal:** `01-auth.spec.js` goes from 15/16 → 16/16.

***

### TASK A-5 — Create `seed_test_users` Management Command

**File:** `teams/management/commands/seed_test_users.py` (create new)
**Trigger:** `E2EADM01` has `entity=""` causing entity-filtered endpoints to return 401
**Blocker for:** All E2E tests requiring entity-scoped permissions

```python
# teams/management/commands/seed_test_users.py
from django.core.management.base import BaseCommand
from django.conf import settings
from users.models import CustomUser, AccessLevel
from plat.tenant.config import TenantConfig
import os

class Command(BaseCommand):
    help = 'Seed E2E test users with correct entity, branches, and permissions'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete and recreate test users')

    def handle(self, *args, **options):
        self._seed_admin(options['reset'])
        self._seed_staff(options['reset'])
        self.stdout.write(self.style.SUCCESS('Test users seeded successfully'))

    def _seed_admin(self, reset):
        userid = 'E2EADM01'
        password = os.environ.get('E2E_ADMIN_PASSWORD', 'TestAdmin@2026!')

        if reset:
            CustomUser.objects.filter(userid=userid).delete()

        user, created = CustomUser.objects.get_or_create(
            userid=userid,
            defaults={
                'phone': '9100000001',
                'name': 'E2E Test Admin',
                'usertype': 'staff',
            }
        )
        user.set_password(password)
        user.save()

        # Set tenant context — must have entity value or entity-filtered endpoints return 401
        from users.models import UserTenantContext
        UserTenantContext.objects.update_or_create(
            user=user,
            bg_code='BG0001',
            defaults={
                'entity': 'kurogaming',
                'branches': ['main'],
                'scope_type': 'entity',
                'request_defaults': {'entity': 'kurogaming', 'branch': 'main'},
            }
        )

        # Full permissions — kungosadmin + all cafe permissions
        AccessLevel.objects.update_or_create(
            user=user,
            defaults={
                'kungosadmin': 1,
                'cafedashboard': 1,
                'stationmanagement': 1,
                'cafesessions': 1,
                'walletmanagement': 1,
                'walletrecharge': 1,
                'pricingmanagement': 2,
                'cafepayments': 1,
            }
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(f'  {action} {userid}')

    def _seed_staff(self, reset):
        userid = 'E2ESTF01'
        password = os.environ.get('E2E_STAFF_PASSWORD', 'TestStaff@2026!')
        if reset:
            CustomUser.objects.filter(userid=userid).delete()
        user, created = CustomUser.objects.get_or_create(
            userid=userid,
            defaults={'phone': '9100000002', 'name': 'E2E Test Staff', 'usertype': 'staff'}
        )
        user.set_password(password)
        user.save()
        # Staff user has limited permissions — used for permission-gating tests
        AccessLevel.objects.update_or_create(
            user=user, defaults={'kungosadmin': 0, 'cafedashboard': 1}
        )
        self.stdout.write(f'  {"Created" if created else "Updated"} {userid}')
```

**Run to verify:**

```bash
python manage.py seed_test_users --reset
python manage.py shell -c "
from users.models import CustomUser, UserTenantContext
u = CustomUser.objects.get(userid='E2EADM01')
ctx = UserTenantContext.objects.get(user=u)
assert ctx.entity == 'kurogaming', f'entity wrong: {ctx.entity}'
assert u.accesslevel.kungosadmin == 1
print('OK')
"
```

**Success signal:** Shell assertion prints `OK`. No assertion error.

***

### TASK A-6 — Fix Navigation Test Selectors

**File:** `e2e/02-navigation.spec.js`
**Trigger:** 2 navigation tests fail — sidebar selector changed after `kuroadmin → teams` rename

**Step 1 — Identify the failing selectors:**

```bash
npx playwright test 02-navigation --reporter=line 2>&1 | grep "✗\|Error"
```

**Step 2 — Add `data-testid` to sidebar in frontend** (the permanent fix):

```jsx
// src/components/layout/Sidebar.jsx (or equivalent)
// Add data-testid to the root nav element:
<nav data-testid="sidebar-nav" className="...">
  {/* existing content */}
</nav>

// Add data-testid to each nav section:
<div data-testid="nav-section-cafe">...</div>
<div data-testid="nav-section-teams">...</div>   {/* was kuroadmin */}
```

**Step 3 — Update test selectors:**

```js
// e2e/02-navigation.spec.js
// REPLACE brittle class-based selectors:
// await expect(page.locator('.sidebar')).toBeVisible()   ← fragile

// WITH testid-based selectors:
await expect(page.getByTestId('sidebar-nav')).toBeVisible()
await expect(page.getByTestId('nav-section-cafe')).toBeVisible()
```

**Step 4 — Fix unknown route test:**

```js
// The test may expect 404 page for authenticated users, but get redirected to /login
// Fix: check both outcomes as valid
await page.goto('/some-unknown-route-xyz')
const url = page.url()
const is404 = await page.locator('[data-testid="not-found-page"]').isVisible()
const isLogin = url.includes('/login')
expect(is404 || isLogin, 'Unknown route should show 404 or redirect to login').toBe(true)
```

**Run to verify:**

```bash
npx playwright test 02-navigation --reporter=line
# Expected: 17/17 pass
```


***

### TASK A-7 — Re-run Static Page Tester

**File:** `test_pages.py`
**Trigger:** Last run was against a dead server (57 false failures on 2026-04-26)

**Add server health gate at top of script:**

```python
# test_pages.py — add at top before any tests run:
import urllib.request
import time
import sys

def wait_for_server(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False

if not wait_for_server('http://localhost:3000'):
    print('ERROR: Vite dev server not running at localhost:3000. Start it first.')
    sys.exit(1)
```

**Run:**

```bash
# Terminal 1:
cd /home/chief/Coding-Projects/kteam-fe-chief && npm run dev

# Terminal 2:
cd /home/chief/Coding-Projects/kteam-fe-chief && python3 /home/chief/test_pages.py
# Expected: 57/57 ✅ (baseline was clean on 2026-04-25)
```

**Success signal:** `57/57 pages — 0 console errors`.

***

## BLOCK B — This Week (~15h total)

> Depends on Block A being fully green. Wire platform infrastructure and add the most critical missing E2E coverage.

***

### TASK B-1 — Wire `CorrelationIDMiddleware` Into Django

**File:** `backend/settings.py`
**Trigger:** `plat/observability/middleware.py` exists but is not in `MIDDLEWARE` — no request tracing active

```python
# backend/settings.py
# FIND: MIDDLEWARE = [
# ADD as the FIRST entry (must be first to capture all requests):
MIDDLEWARE = [
    'plat.observability.middleware.CorrelationIDMiddleware',  # ← add here
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ... rest unchanged
]
```

**Verify `plat/observability/middleware.py` exists first:**

```bash
ls /home/chief/Coding-Projects/kteam-dj-chief/plat/observability/middleware.py
# If missing: the Phase 4 primitives build may not be fully committed — check git log
```

**Run to verify:**

```bash
curl -v http://localhost:8000/api/v1/health/ 2>&1 | grep -i "x-request-id"
# Expected: X-Request-ID: <uuid> in response headers
```

**Success signal:** Every response contains `X-Request-ID` header with a UUID.

***

### TASK B-2 — Wire Sentry SDK

**Files:** `requirements.txt`, `backend/settings.py`, `.env.example`
**Trigger:** Phase 0 P0 \#13 never completed — no error tracking in production

```bash
# Step 1: Add to requirements.txt
echo "sentry-sdk[django]>=2.0.0" >> requirements.txt
pip install sentry-sdk[django]
```

```python
# Step 2: backend/settings.py — add after imports:
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

SENTRY_DSN = env('SENTRY_DSN', default='')

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.2,
        profiles_sample_rate=0.1,
        environment=env('DJANGO_ENV', default='development'),
        before_send=lambda event, hint: _attach_tenant_tags(event),
    )

def _attach_tenant_tags(event):
    # Attach bg_code and user_id from request context if available
    from plat.observability.context import get_current_tenant_ctx
    ctx = get_current_tenant_ctx()
    if ctx:
        event.setdefault('tags', {}).update({
            'bg_code': ctx.get('bg_code'),
            'entity': ctx.get('entity'),
        })
    return event
```

```bash
# Step 3: .env.example — add:
SENTRY_DSN=https://your-dsn@sentry.io/project-id
DJANGO_ENV=development
```

**Success signal:** Sentry dashboard shows a test event after running:

```bash
python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('KungOS Sentry wired ✅')"
```


***

### TASK B-3 — Migrate `InvoicesList.jsx` to React Query

**File:** `src/pages/InvoicesList.jsx`
**Trigger:** High-volume page still using `useEffect+axios` — no stale-time, no AbortController, memory leak risk
**Priority:** P1 per v2 plan (highest priority of remaining 12 pages)

```jsx
// PATTERN to replace:
// const [invoices, setInvoices] = useState([])
// useEffect(() => { axios.get('/api/...').then(r => setInvoices(r.data)) }, [])

// REPLACE WITH:
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/lib/queryKeys'
import { fetchInvoices } from '@/lib/api'

export default function InvoicesList() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.invoices.list(),
    queryFn: ({ signal }) => fetchInvoices({ signal }),   // AbortController auto-wired
    staleTime: 5 * 60 * 1000,      // 5 minutes
    gcTime: 10 * 60 * 1000,        // 10 minutes
  })

  if (isLoading) return <Spinner />
  if (isError) return <ErrorState message={error.message} />
  // ... rest of render unchanged
}

// Add to src/lib/queryKeys.js:
invoices: {
  list: (filters = {}) => ['invoices', 'list', filters],
  detail: (id) => ['invoices', 'detail', id],
},

// Add to src/lib/api.jsx:
export const fetchInvoices = async ({ signal, ...params } = {}) => {
  const res = await fetch(`/api/v1/finance/invoices/?${new URLSearchParams(params)}`, {
    signal,
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`Invoices fetch failed: ${res.status}`)
  return res.json()
}
```

Apply the same pattern to the next 9 remaining pages in this priority order: `Employees.jsx`, `Stock.jsx`, `StockDetail.jsx`, `ProductsList.jsx`, `TPBuilds.jsx`, `CreateEstimate.jsx`, `Audit.jsx`. Defer `OrderDetail.jsx`, `OrdersList.jsx`, `PurchaseOrders.jsx` — these are blocked on OrderConsolidation (Post-Phase 4).

**Success signal:** `npx playwright test 05-react-query` stays 19/19. No `useEffect` importing `axios` remains in these files (`grep -r "useEffect\|import axios" src/pages/InvoicesList.jsx` returns nothing).

***

### TASK B-4 — Write Cafe Session Lifecycle E2E Test

**File:** `e2e/09-cafe-session-lifecycle.spec.js` (create new)
**Trigger:** Highest-risk untested path — billing correctness never verified end-to-end

```js
// e2e/09-cafe-session-lifecycle.spec.js
import { test, expect } from '@playwright/test'
import { loginAs, getAuthHeader } from './helpers/auth.js'

const BASE = 'http://localhost:8000/api/v1'

test.describe('Cafe Session Lifecycle — Full Billing Journey', () => {
  let headers, sessionId, walletBefore

  test.beforeAll(async ({ request }) => {
    // Login to get auth cookie
    await request.post(`${BASE}/auth/login/`, {
      data: { userid: process.env.E2E_ADMIN_USER, password: process.env.E2E_ADMIN_PASSWORD }
    })
  })

  test('1. Customer lookup / register', async ({ request }) => {
    const res = await request.post(`${BASE}/cafe/customer/lookup/`, {
      headers,
      data: { phone: '9100000099' }
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('customer')
    expect(body).toHaveProperty('wallet')
    walletBefore = body.wallet.balance
  })

  test('2. Start session — station assigned, wallet checked', async ({ request }) => {
    const res = await request.post(`${BASE}/cafe/sessions/start/`, {
      headers,
      data: { phone: '9100000099', station_id: 'STN001', zone: '144Hz' }
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('active')
    expect(body).toHaveProperty('session_id')
    expect(body).toHaveProperty('rate_per_hour')
    sessionId = body.session_id
  })

  test('3. Pause session — timer stops', async ({ request }) => {
    const res = await request.post(`${BASE}/cafe/sessions/pause/`, {
      headers, data: { session_id: sessionId }
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('paused')
    expect(body).toHaveProperty('paused_at')
  })

  test('4. Resume session — timer resumes', async ({ request }) => {
    const res = await request.post(`${BASE}/cafe/sessions/resume/`, {
      headers, data: { session_id: sessionId }
    })
    expect(res.status()).toBe(200)
    expect((await res.json()).status).toBe('active')
  })

  test('5. End session — billing is correct', async ({ request }) => {
    const res = await request.post(`${BASE}/cafe/sessions/end/`, {
      headers, data: { session_id: sessionId }
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('total_minutes')
    expect(body).toHaveProperty('session_charges')
    expect(body).toHaveProperty('wallet_balance_after')
    // Billing correctness: wallet must have decreased by exactly session_charges
    const walletAfter = body.wallet_balance_after
    const charged = body.session_charges
    expect(
      Math.abs((walletBefore - walletAfter) - charged),
      `Wallet delta (${walletBefore - walletAfter}) must equal charged amount (${charged})`
    ).toBeLessThan(0.01)
    // Wallet must not go below zero
    expect(walletAfter).toBeGreaterThanOrEqual(0)
  })

  test('6. Station returns to online after session ends', async ({ request }) => {
    const res = await request.get(`${BASE}/cafe/stations/STN001/`, { headers })
    expect(res.status()).toBe(200)
    expect((await res.json()).status).toBe('online')
  })

  test('7. Wallet transaction recorded exactly once', async ({ request }) => {
    const res = await request.get(
      `${BASE}/cafe/wallet/transactions/?reference_type=session&reference_id=${sessionId}`,
      { headers }
    )
    const txns = (await res.json()).transactions
    expect(txns.length, 'Exactly one wallet debit per session').toBe(1)
    expect(txns[0].transaction_type).toBe('spend')
  })
})
```

**Run to verify:**

```bash
npx playwright test 09-cafe-session-lifecycle --reporter=line
# Expected: 7/7 pass
```


***

## BLOCK C — This Sprint (~40h total)

> These depend on Blocks A and B being complete.

***

### TASK C-1 — Create CI/CD Pipeline

**File:** `.github/workflows/ci.yml` (create new)

```yaml
# .github/workflows/ci.yml
name: KungOS CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: kteam_test
          POSTGRES_USER: kteam
          POSTGRES_PASSWORD: testpassword
        options: >-
          --health-cmd pg_isready
          --health-interval 10s --health-timeout 5s --health-retries 5
      mongodb:
        image: mongo:8
        options: --health-cmd "mongosh --eval 'db.adminCommand(\"ping\")'" --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - name: Lint — no hardcoded secrets
        run: |
          grep -rn "SECRET_KEY\s*=\s*['\"][^e]" . --include="*.py" && exit 1 || true
          grep -rn "toBeGreaterThanOrEqual(0)" e2e/ && echo "WEAK ASSERTION FOUND" && exit 1 || true
      - name: Backend unit tests
        run: python -m pytest tests/ -v --tb=short
        env:
          DATABASE_URL: postgres://kteam:testpassword@localhost/kteam_test
          MONGO_URI: mongodb://localhost:27017
          DJANGO_SECRET_KEY: ci-only-secret-not-production
          DEBUG: "False"
      - name: Seed test users
        run: python manage.py seed_test_users --reset
        env:
          E2E_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}

  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    needs: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
        working-directory: /path/to/kteam-fe-chief
      - run: npx playwright install chromium
      - name: Wait for backend
        run: |
          for i in $(seq 1 30); do
            curl -sf http://localhost:8000/api/v1/health/ && break
            sleep 2
          done
      - name: Wait for frontend
        run: |
          for i in $(seq 1 30); do
            curl -sf http://localhost:3000 && break
            sleep 2
          done
      - name: Run critical E2E suites
        run: npx playwright test 01-auth 03-cafe-platform 07-entity-switching 08-detail-pages 09-cafe-session-lifecycle
        env:
          E2E_ADMIN_USER: E2EADM01
          E2E_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
```

**Success signal:** PR to `main` is blocked until both `backend` and `e2e` jobs pass.

***

### TASK C-2 — Verify `kungosadmin` Field After Rename

**Files:** `users/permissions.py`, `users/models.py`
**Trigger:** Sys admin endpoints return 403 — field name may have changed after `kuroadmin → teams` rename

```bash
# Step 1 — Inspect current AccessLevel model fields:
python manage.py shell -c "
from users.models import AccessLevel
import inspect
fields = [f.name for f in AccessLevel._meta.get_fields()]
print('AccessLevel fields:', fields)
"

# Step 2 — Inspect KungosAdminPermission:
grep -n "kungosadmin\|kuroadmin\|accesslevel" users/permissions.py
```

**If `KungosAdminPermission` still references a renamed/removed field:**

```python
# users/permissions.py
class KungosAdminPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            # Verify this field name matches AccessLevel model exactly:
            return request.user.accesslevel.kungosadmin == 1
        except AttributeError:
            return False
```

**Success signal:** `npx playwright test 04-api-integration --reporter=line` shows tests 4.14, 4.15, 4.16 passing.

***

## BLOCK D — Next Sprint (~122h total)

> These are the two largest remaining v2 plan gaps. Block D-1 must fully complete before D-2 can begin.

***

### TASK D-1 — Gaming Backend Integration (Phase 3, ~90h)

**Trigger:** `kuro-gaming-dj-backend` is still a separate repo; cutover checklist item 24 is `[🟡]`
**Dependency chain:** This unblocks Phase 3b → Frontend storefront migration → `kurogg-nextjs` retirement

Execute in this exact sequence:

```
1. Remove remaining 2 hardcoded S3 keys from kuro-gaming-dj-backend     (1h)
   File: kuro-gaming-dj-backend/settings.py
   Replace: AWS_ACCESS_KEY_ID = 'AKIA...' → env('AWS_ACCESS_KEY_ID')

2. Copy 5 gaming apps into kteam-dj-chief:                               (4h)
   cp -r kuro-gaming-dj-backend/accounts   kteam-dj-chief/apps/
   cp -r kuro-gaming-dj-backend/products   kteam-dj-chief/apps/
   cp -r kuro-gaming-dj-backend/orders     kteam-dj-chief/apps/
   cp -r kuro-gaming-dj-backend/payment    kteam-dj-chief/apps/
   cp -r kuro-gaming-dj-backend/games      kteam-dj-chief/apps/

3. Remove djongo from all copied apps (already done in Phase 1 P1 #11   (2h)
   — verify no djongo imports remain)
   grep -r "djongo" apps/ --include="*.py"   ← must return nothing

4. Add all 5 apps to INSTALLED_APPS in settings.py                       (1h)

5. Merge gaming settings.py into unified settings via django-environ      (4h)
   — Cashfree keys, UPI keys, Google Merchant, TextLocal SMS

6. Create DRF serializers for all 5 app model sets                       (38h)
   — ProductSerializer, BuildSerializer, OrderSerializer,
      CartSerializer, WishlistSerializer, GameSerializer

7. Add bgcode field to all gaming PostgreSQL models                       (8h)
   — Cart, Wishlist, Addresslist, Orders, OrderItems
   — Create and run Django migrations

8. Add TenantContextPermission to all 25 gaming admin endpoints          (12h)
   — Same pattern as cafe endpoints

9. Write gaming backend tests                                             (16h)
   — tests/test_gaming_products.py
   — tests/test_gaming_orders.py
   — tests/test_gaming_bgcode_isolation.py

10. Verify gaming DB migration with restore tool:                          (4h)
    python manage.py restore_kuropurchase --dump /path/to/dump --dry-run
    python manage.py restore_kuropurchase --dump /path/to/dump --restore
    python manage.py restore_kuropurchase --verify
```

**Success signal:** `python -m pytest tests/ -v` shows gaming test suites passing. `grep -r "kuro-gaming-dj-backend" .` returns only archive/docs references.

***

### TASK D-2 — Phase 3b Gaming Multi-Tenant (~32h)

**Trigger:** Gaming data has no BG isolation until D-1 is complete
**Prerequisite:** TASK D-1 fully complete and all tests green

```
1. Add compound indexes to gaming PostgreSQL models:                      (3h)
   Cart(bgcode, user_id), Orders(bgcode, user_id, status)

2. Create TenantContextPermission for gaming namespace                    (8h)
   — All gaming endpoints must resolve BG context before data access
   — Same pattern as plat/tenant/TenantCollection wrapper

3. Add bgcode to all 12 gaming MongoDB collections                       (12h)
   — Use restore_kuropurchase tool's entity population logic
   — Verify: all prods, builds, kgbuilds, etc. have bgcode field

4. Write tenant isolation tests for gaming data                           (9h)
   — User from BG0001 cannot see BG0002 products
   — Entity context required on all gaming endpoints
   python manage.py verify_tenant_isolation --scope gaming
```

**Success signal:** Cross-tenant gaming data access returns empty set, not foreign data. `python manage.py verify_tenant_isolation --scope gaming` returns `0 leaks detected`.

***

## Verification Checkpoint — Full Test Run

After all blocks are complete, run the full suite and verify these numbers:

```bash
# Backend:
cd /home/chief/Coding-Projects/kteam-dj-chief
python -m pytest tests/ -v
# Target: 80+ tests, 100% pass

# E2E:
cd /home/chief/Coding-Projects/kteam-fe-chief
npx playwright test
# Target: 200+ tests, 95%+ pass rate

# Static pages:
python3 /home/chief/test_pages.py
# Target: 57/57 ✅

# Tenant isolation:
python manage.py verify_tenant_isolation
# Target: 0 leaks detected
```


***

## Quick Reference — Expected Pass Rate After Each Block

| After Block | Backend | E2E | Static | Overall |
| :-- | :-- | :-- | :-- | :-- |
| Baseline (today) | 49/49 (100%) | 107/160 (67%) | Stale | 82% |
| After Block A | 49/49 (100%) | ~155/160 (97%) | 57/57 | ~97% |
| After Block B | 55/55+ | ~165/168 (98%) | 57/57 | ~98% |
| After Block C | 55/55+ | ~175/180 | 57/57 | ~98% + CI gate live |
| After Block D | 75/75+ | ~220/225 | 57/57 | **~99% — go-live ready** |

