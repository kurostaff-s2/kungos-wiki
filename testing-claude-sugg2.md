<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# What's right:

- Tournaments 500 root cause ✅ (missing @api_view decorator)
- Gamers no-auth root cause ✅ (missing auth decorators)
- E2E coverage gaps correctly identified (cafe lifecycle, WebSocket, gaming)
- Priority ordering makes sense
- CI/CD pipeline structure is good

What's wrong (must fix before execution):

- Model fields are wrong — AccessLevel (capital L) doesn't exist; actual model is Accesslevel (lowercase L) with completely different fields (orders, products,
inventory — no kungosadmin)
- File paths are wrong — InvoicesList.jsx is at src/pages/Accounts/, Sidebar.jsx is AppSidebar.jsx
- Auth fix approach is wrong — proposes browser cookie extraction but failing tests use Playwright's request fixture (HTTP client, not browser)

does this align with the kungos v2 spec?

Your three corrections are **accurate and spec-aligned**. Here is a precise breakdown of what the spec actually says vs. what was previously generated wrong, and the exact corrected approach for each.

***

## Correction 1 — `Accesslevel` Model (Spec Alignment: ✅ Confirmed)

The spec **confirms your correction** but from two different angles that need to be separated:

**Current state (what exists today):** `Accesslevel` (lowercase L) is the existing permission model with business operation fields — `orders`, `products`, `inventory`, etc. This is the model used in the current running codebase.[^1]

**Spec target (what Phase 3/CAFE_PLATFORM requires adding to it):** The fields `kungosadmin`, `cafedashboard`, `stationmanagement`, `walletmanagement`, etc. are **new fields that must be ADDED** via migration — they do not exist yet. The spec states them as planned additions, not current state.[^2]

The previous instructions treated `kungosadmin` as an existing field you could query against. That was wrong. The corrected `seed_test_users` command must:

```python
# WRONG — field doesn't exist yet:
AccessLevel.objects.update_or_create(user=user, defaults={'kungosadmin': 1})

# CORRECT — use only existing fields until migration adds the new ones:
# Step 1: Check what fields actually exist right now:
python manage.py shell -c "
from users.models import Accesslevel
print([f.name for f in Accesslevel._meta.get_fields()])
"

# Step 2: seed_test_users must use ONLY confirmed existing fields.
# Example using the actual business permission fields:
Accesslevel.objects.update_or_create(
    user=user,
    defaults={
        'orders': 2,        # ← use whatever the actual field names are
        'products': 2,
        'inventory': 2,
        # DO NOT reference kungosadmin — it doesn't exist until Phase 3 migration
    }
)
```

**The real fix for A-5 (TASK seed_test_users):** The 403 on sys-admin endpoints is NOT a missing `kungosadmin` value — it's that `E2EADM01` has no `Accesslevel` row at all, or the entity is empty. Fix the entity first:

```python
# The actual blocking issue per the E2E report — entity is empty:
UserTenantContext.objects.update_or_create(
    user=user, bg_code='BG0001',
    defaults={'entity': 'kurogaming', 'branches': ['main'], 'scope_type': 'entity'}
)
# THEN seed Accesslevel with whatever fields currently exist on the model
```

**Phase gate:** `kungosadmin`, `cafedashboard`, `stationmanagement`, etc. need a **Django migration** as their first step. Add this to your TODO before `seed_test_users` can reference them:

```python
# users/migrations/XXXX_add_cafe_permissions_to_accesslevel.py
operations = [
    migrations.AddField('Accesslevel', 'kungosadmin',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'cafedashboard',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'stationmanagement',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'walletmanagement',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'cafesessions',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'walletrecharge',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'pricingmanagement',
        models.IntegerField(default=0)),
    migrations.AddField('Accesslevel', 'cafepayments',
        models.IntegerField(default=0)),
]
```

This migration must **run before** `seed_test_users` references those fields.[^2]

***

## Correction 2 — File Paths (Spec Alignment: ✅ Confirmed, Spec Silent on Paths)

The spec lists page names in its progress log and navigation structure but **never specifies exact filesystem paths** within `kteam-fe-chief`. Your corrections are:


| Previous (Wrong) | Correct |
| :-- | :-- |
| `src/pages/InvoicesList.jsx` | `src/pages/Accounts/InvoicesList.jsx` |
| `src/components/layout/Sidebar.jsx` | `src/components/AppSidebar.jsx` (or wherever `AppSidebar` lives) |

**Before executing any frontend task, run this first to build a ground-truth path map:**

```bash
# One-time: generate exact paths for all remaining useEffect pages
cd /home/chief/Coding-Projects/kteam-fe-chief

grep -rn "useEffect\|import axios" src/pages/ \
  --include="*.jsx" \
  -l | sort > /tmp/remaining_useeffect_pages.txt

cat /tmp/remaining_useeffect_pages.txt
# This gives you the real paths — use these in ALL subsequent tasks
```

```bash
# Find the actual sidebar component:
find src/ -name "*Sidebar*" -o -name "*sidebar*" | grep -v node_modules
# Expected output: src/components/AppSidebar.jsx (or similar)

# Find InvoicesList specifically:
find src/ -name "InvoicesList*"
# Expected: src/pages/Accounts/InvoicesList.jsx
```

For TASK A-6 (navigation selectors), the `data-testid` must be added to the **actual** component:

```bash
# Find the real component before patching:
grep -rn "sidebar\|nav-section" src/components/ --include="*.jsx" -l
# Open the file this returns — THAT is your target, not "Sidebar.jsx"
```


***

## Correction 3 — Auth Fix Approach (Spec Alignment: ✅ Confirmed)

Your correction is technically precise. The spec mandates `CookieJWTAuthentication` as the auth mechanism, but the previously suggested fix — extracting JWT from browser cookies — only works with Playwright's `page` fixture (a real browser). Tests using the `request` fixture use Playwright's isolated HTTP client, which has its own cookie jar separate from any browser session.[^1]

**The correct approach depends on which fixture the failing test uses:**

```js
// Pattern A — tests using `page` fixture (browser):
// Cookie IS automatically shared if you navigate to /login first.
// The previous suggestion was correct here — but only for page-based tests.
test('...', async ({ page }) => {
  await page.goto('/login')
  await page.fill('#userid', process.env.E2E_ADMIN_USER)
  await page.fill('#pwd', process.env.E2E_ADMIN_PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('/dashboard')
  // All subsequent page.request.get() calls automatically carry the cookie ✅
})

// Pattern B — tests using `request` fixture (HTTP client, NOT browser):
// The request fixture has its OWN cookie jar. You must log in via HTTP,
// not via browser navigation. The cookie is then auto-stored in the
// request context's jar and sent on all subsequent calls automatically.
test('...', async ({ request }) => {
  // Step 1: Authenticate via HTTP — cookie is stored in request's jar
  const loginRes = await request.post('http://localhost:8000/api/v1/auth/login/', {
    data: {
      userid: process.env.E2E_ADMIN_USER,
      password: process.env.E2E_ADMIN_PASSWORD,
    },
  })
  expect(loginRes.ok()).toBeTruthy()
  // ✅ No manual cookie extraction needed — Playwright stores it automatically
  // All subsequent request.get() / request.post() calls carry jwt_token cookie

  // Step 2: Use the authenticated request directly
  const res = await request.get('http://localhost:8000/api/v1/sys/templates/')
  expect(res.status()).toBe(200)
})
```

**The actual root cause of the 8 outbox failures** is therefore simpler than the previous fix suggested — no `getAuthHeader()` helper is needed at all. The fix is:

```js
// e2e/06-outbox-events.spec.js
// REMOVE: any manual Authorization header construction
// ADD: a login call at the top of beforeAll/beforeEach using the request fixture

test.describe('Outbox Events', () => {
  test.beforeAll(async ({ request }) => {
    const res = await request.post('http://localhost:8000/api/v1/auth/login/', {
      data: {
        userid: process.env.E2E_ADMIN_USER,
        password: process.env.E2E_ADMIN_PASSWORD,
      },
    })
    if (!res.ok()) {
      throw new Error(
        `E2E login failed: ${res.status()} — is seed_test_users run? Is server up?`
      )
    }
    // Cookie is now in the request fixture's jar — no further action needed
  })

  test('outbox event is published', async ({ request }) => {
    // request automatically carries the jwt_token cookie from beforeAll
    const res = await request.get('http://localhost:8000/api/v1/outbox/events/')
    expect(res.status()).toBe(200)
  })
})
```

**One important caveat from the spec:** The spec states `CookieJWTAuthentication` as the target auth class. Verify this is actually active on the outbox endpoints — if those views still use Knox (`TokenAuthentication`), the cookie won't be accepted regardless of the fix above:[^1]

```bash
grep -n "authentication_classes\|CookieJWT\|TokenAuthentication" \
  /home/chief/Coding-Projects/kteam-dj-chief/plat/outbox/views.py
```


***

## Corrected Task Priority After These Fixes

| ID | Was | Now |
| :-- | :-- | :-- |
| A-5 | Seed `E2EADM01` with `kungosadmin=1` | First run `entity` fix, then create Accesslevel migration, then seed cafe fields |
| A-3 | Create `getAuthHeader()` cookie extractor | Delete `getAuthHeader()` entirely — use `request.post('/auth/login/')` in `beforeAll` |
| A-6 | Patch `Sidebar.jsx` | Run `find src/ -name "*Sidebar*"` first, then patch the real file |
| G-02 | Migrate `src/pages/InvoicesList.jsx` | Target `src/pages/Accounts/InvoicesList.jsx` |
| **NEW** | — | Add `users/migrations/XXXX_add_cafe_permissions.py` before any seed command references those fields |

<div align="center">⁂</div>

[^1]: KungOS_v2.md

[^2]: CAFE_PLATFORM.md

