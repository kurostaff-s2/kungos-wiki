# Unit 4: Sidebar Navigation + Route Registration

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 4 of 6
**Dependencies:** none (can run in parallel with Unit 3)
**Estimated effort:** ~10 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Key files for this phase:**
- `src/data/sidebar-nav.js` — sidebar config (modify)
- `src/routes/main.jsx` — route registration (modify)

## What This Phase Delivers

"Council" section in sidebar with "Delegation Runs" link. Route `/council/delegations` registered and pointing to the Delegations component.

## Pre-Flight Checklist

- [ ] Read `src/data/sidebar-nav.js` for current sidebar structure
- [ ] Read `src/routes/main.jsx` for current route patterns

## Implementation Steps

### Step 1: Add sidebar section

In `src/data/sidebar-nav.js`, add a new section after "Cafe Platform" (or wherever fits the nav hierarchy):

```js
{
  title: 'Council',
  icon: GitBranch,  // from lucide-react
  key: 'council',
  children: [
    {
      title: 'Delegation Runs',
      key: 'council_delegations',
      path: '/council/delegations',
      icon: GitBranch,
    },
  ],
},
```

Import `GitBranch` from `lucide-react` if not already imported.

### Step 2: Register route

In `src/routes/main.jsx`, add route:

```jsx
import DelegationsList from '@/pages/Council/Delegations'
// ... in routes array ...
{
  path: '/council/delegations',
  element: <DelegationsList />,
},
```

If detail view route is needed (Unit 5):
```jsx
{
  path: '/council/delegations/:chainId',
  element: <DelegationDetail />,
},
```

### Step 3: Test

1. Sidebar shows "Council" section
2. Click "Delegation Runs" → navigates to `/council/delegations`
3. Page loads (Unit 3 component)

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/data/sidebar-nav.js` | Add Council section with Delegation Runs link |
| Modify | `src/routes/main.jsx` | Register `/council/delegations` route |

## Phase-Specific Tests

1. Sidebar renders "Council" section
2. Clicking "Delegation Runs" navigates to correct URL
3. No 404 errors

## Completion Gate

- [ ] Sidebar shows Council → Delegation Runs
- [ ] Navigation works
- [ ] Route registered in main.jsx
- [ ] No console errors

## Notes for Next Phase

- Unit 5 (detail view) needs the `/council/delegations/:chainId` route added here
- If Unit 5 is done after this, add the detail route then
