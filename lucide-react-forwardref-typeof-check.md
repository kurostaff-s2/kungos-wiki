# Lucide React forwardRef typeof Check Pitfall

> **Date**: 2026-04-25
> **Source**: Root cause of persistent React 19 render crash on Home page

## The Bug

`EmptyState.jsx` used `typeof Icon === 'function'` to check if `Icon` is a React component. When no `icon` prop is passed, `Icon` defaults to `FileSearch` from `lucide-react`. The check returned `false`, causing the `forwardRef` component object to be rendered directly as a React child, triggering:

```
Objects are not valid as a React child (found: object with keys {$$typeof, render})
```

## Why It Happens

**`lucide-react` icons are `React.forwardRef` components.** In JavaScript:

```js
import { FileSearch } from 'lucide-react'

typeof FileSearch  // 'object' — NOT 'function'!
```

A `forwardRef` component is an object with two keys:
- `$$typeof` — `Symbol(react.forward_ref)`
- `render` — the actual component function

**The code path that failed:**
1. `typeof Icon === 'function'` → `false` (because `Icon` is a `forwardRef` object)
2. Code takes the `else` branch: `<>{Icon}</>`
3. This renders the `forwardRef` component **object** directly as a React child, not as a component type
4. React 19's `throwOnInvalidObjectTypeImpl` detects the object with `$$typeof` and `render` keys
5. Error: `Objects are not valid as a React child (found: object with keys {$$typeof, render})`

## The Fix

```diff
- const isComponent = typeof Icon === 'function'
+ const isComponent = typeof Icon === 'function' || (typeof Icon === 'object' && Icon && Icon.render)
```

This correctly identifies `forwardRef` components (which have a `render` property) as components, so they're rendered via `React.createElement(Icon, ...)` instead of being passed directly as children.

## General Rule

When checking if a value is a React component:

| Component Type | `typeof X` | Detection |
|---|---|---|
| Function component | `'function'` | `typeof X === 'function'` |
| `React.forwardRef` | `'object'` | `X.render` or `X.$$typeof === Symbol(react.forward_ref)` |
| Class component | `'function'` | `typeof X === 'function'` |
| String/element | `'string'` / `'object'` | `typeof X === 'string'` or `React.isValidElement(X)` |

**`typeof X === 'function'` is NOT sufficient.** Always check for `forwardRef` objects when accepting component props.

## Affected Libraries

This pattern affects **any** library that uses `React.forwardRef` for its components:
- `lucide-react` — all icons
- `@radix-ui/*` — many components
- `shadcn/ui` — all components (wraps Radix with forwardRef)
- `recharts` — some components
- Any custom `React.forwardRef` component

## In This Codebase

**File**: `src/components/common/EmptyState.jsx`
**Fixed in**: commit `3395aed`
**Context**: This was the root cause of the persistent React render error that took extensive debugging to isolate (see [[kungos-log]] for the full investigation log).
