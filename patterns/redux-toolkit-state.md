---
tags: [redux, state-management, react, kteam-fe-react]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-fe-react/]
related: [[kteam-fe-react]], [[radix-ui-components]]
status: stable
---

# Redux Toolkit State

## Summary

Redux Toolkit state management patterns used in kteam-fe-react (kg-staff frontend).

## Architecture

- **Redux Toolkit** for state management
- **Redux Thunk** for async actions
- **Redux DevTools Extension** for debugging
- **React Redux** (v9) for React bindings

## Key Patterns

- **Slices**: Each feature domain gets its own slice (auth, orders, products, inventory, hr, analytics)
- **createSlice**: Use RTK's createSlice for reducer + action creators
- **createAsyncThunk**: Use for API calls with pending/fulfilled/rejected states
- **RTK Query**: Not used — project uses manual thunks with Axios
- **Selectors**: Custom selectors for derived state
- **Store setup**: Single store with combineSlices

## API Integration

- Axios instance configured with base URL from env
- Knox tokens attached to requests via interceptors
- Token refresh handled in auth slice

## Anti-Patterns

- No manual action type strings — use createSlice
- No plain Redux reducers — always use RTK
- No Redux in components that don't need it — prefer local state
