# Kungos Debug & Audit Tools

> **Date**: 2026-04-25
> **Context**: Built during the systematic investigation of the React 19 render crash (`Objects are not valid as a React child (found: object with keys {$$typeof, render})`).

## Overview

Five debugging/audit tools were built during the crash investigation. They are **kept** in the codebase for ongoing use — not removed as testing artifacts.

| Tool | File | Status | Purpose |
|------|------|--------|---------|
| Error Logger | `src/lib/errorLogger.js` | ⏸️ Disabled in App.jsx | Runtime error capture |
| Error Badge | `src/components/common/ErrorBadge.jsx` | ⏸️ Disabled in App.jsx | Visual error indicator |
| Static Tester | `test_pages.py` | ✅ Active | Regression testing |
| Dynamic Tester | `test_dynamic_pages.py` | ✅ Active | Dynamic route testing |
| Test Strategy | `TESTING_STRATEGY.md` | ✅ Active | Test plan & matrix |

---

## 1. `errorLogger.js` — Global Error Logger

**Path**: `src/lib/errorLogger.js`

**What it does**: Captures all uncaught errors in the application:
- `window.onerror` — uncaught exceptions with filename, line, column
- `window.unhandledrejection` — unhandled promise rejections
- `console.error` override — intercepts React errors, type errors, reference errors, etc.

**API**:
```js
import { initErrorLogger, getErrorLog, downloadErrorLog, clearErrorLog } from '@/lib/errorLogger'

initErrorLogger('app')        // Start capturing (call once)
const log = getErrorLog()     // Get all captured errors as string
downloadErrorLog()            // Download as runtime-errors.log
clearErrorLog()               // Clear all captured errors
```

**Current state**: Imported in `App.jsx` but **disabled** (`initErrorLogger` call commented out). Keep disabled in production; enable when debugging.

---

## 2. `ErrorBadge.jsx` — Floating Error Badge

**Path**: `src/components/common/ErrorBadge.jsx`

**What it does**: A floating badge that appears in the bottom-right corner when errors are detected. Clicking it opens a panel showing:
- Error count badge (pulsing red)
- Full error log in a scrollable panel
- Download button (downloads `runtime-errors.log`)
- Clear button (resets all captured errors)

**Current state**: Imported in `App.jsx` but **disabled** (rendered inside `/* <ErrorBadge /> */`). Keep disabled in production; enable when debugging.

---

## 3. `test_pages.py` — Static Page Tester

**Path**: `test_pages.py`

**What it does**: Systematically tests every static route in the app:
- Extracts all routes from `src/routes/main.jsx`
- Logs in via Django API to get CSRF token and session
- Navigates to each page
- Captures `pageerror` events (console errors)
- Reports pass/fail per page
- Appends results to `test-results.md`

**Usage**: `python3 test_pages.py`

**Current state**: **Active** — run after every major change to catch regressions. 57/57 static pages tested.

---

## 4. `test_dynamic_pages.py` — Dynamic Page Tester

**Path**: `test_dynamic_pages.py`

**What it does**: Tests dynamic routes with real IDs:
- Extracts routes with `:param` placeholders from `main.jsx`
- Logs in via Playwright (handles HttpOnly JWT cookies)
- Uses known IDs from backend API or fetches live IDs
- Tests routes like `/orders/:orderId`, `/inward-debitnotes/:debitnoteid`
- Reports pass/fail per page
- Appends results to `test-results.md`

**Usage**: `python3 test_dynamic_pages.py`

**Current state**: **Active** — run after every major change. 4/4 testable dynamic pages pass, 46 skipped (no API mapping).

---

## 5. `TESTING_STRATEGY.md` — Test Plan & Page Matrix

**Path**: `TESTING_STRATEGY.md`

**What it contains**:
- Phase alignment audit (what the plan says vs. what the code does)
- Page-by-page test matrix (4 tests per page: load, entity filter, navigation, ⌘K)
- Fix order priority list
- Known issues to address

**Current state**: **Active** — reference document for system testing.

---

## How to Enable Debugging Tools

To temporarily enable the error logger and badge for debugging:

1. In `src/App.jsx`, uncomment:
   ```js
   import { initErrorLogger } from './lib/errorLogger'
   // ...
   initErrorLogger('App')
   // ...
   <ErrorBadge />
   ```
2. Reload the page — errors will appear in the console AND in the floating badge
3. Click the badge to view/download the error log
4. When done, comment them back out and commit
