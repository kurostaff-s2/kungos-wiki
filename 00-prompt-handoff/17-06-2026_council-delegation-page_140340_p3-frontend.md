# Unit 3: Frontend — Delegations List Page

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 3 of 6
**Dependencies:** Unit 1 (API endpoints must be running)
**Estimated effort:** ~30 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Key files for this phase:**
- `src/pages/Council/Delegations.jsx` — new list page (create)
- `src/lib/api.jsx` — reference for fetcher/mutator patterns
- `src/components/common/DataTable.jsx` — reference for table component
- `src/pages/Orders/OrdersList.jsx` — reference for list page pattern

## What This Phase Delivers

React page at `/council/delegations` showing delegation runs in a DataTable. Includes search bar, sort by date (newest first), pagination (20 per page), and actions (View detail, Open MD file).

## Pre-Flight Checklist

- [ ] Unit 1 is complete (API running at `/api/v1/council/delegations`)
- [ ] Read `src/pages/Orders/OrdersList.jsx` for pattern reference
- `src/components/common/DataTable.jsx` for table API
- `src/lib/api.jsx` for fetcher pattern

## Implementation Steps

### Step 1: Create page directory and component

Create `src/pages/Council/Delegations.jsx`:

```jsx
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import DataTable from '@/components/common/DataTable'
import PageHeader from '@/components/common/PageHeader'
import PageSection from '@/components/common/PageSection'
import { Badge, Button, Input } from '@/components/ui'
import { Eye, ExternalLink, Search } from 'lucide-react'
import { fetcher } from '@/lib/api'

const COLUMNS = [
  { key: 'created_at', label: 'Date', sortable: true },
  { key: 'from_model', label: 'From Model' },
  { key: 'to_model', label: 'To Model' },
  { key: 'task_preview', label: 'Task' },
  { key: 'response_length', label: 'Response' },
  { key: 'actions', label: '' },
]

export default function DelegationsList() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [toModel, setToModel] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['delegations', page, search, toModel],
    queryFn: fetcher(`/api/v1/council/delegations?page=${page}&per_page=20${search ? `&search=${encodeURIComponent(search)}` : ''}${toModel ? `&to_model=${encodeURIComponent(toModel)}` : ''}`),
  })

  // Render DataTable with columns
  // Actions: Eye icon → navigate to detail, ExternalLink → open MD in new tab
}
```

**Columns:**
- Date: format `created_at` with dayjs
- From Model: badge (or "unknown" if null)
- To Model: badge with model name
- Task: first 120 chars of task_preview (tooltip for full text)
- Response: `${response_length} chars`
- Actions: View (navigate to detail), Open MD (new tab via raw endpoint)

### Step 2: Style and polish

- Use existing PageHeader, PageSection components
- Empty state when no delegations
- Loading state with Spinner
- Search input with debounce (300ms)

### Step 3: Test

Navigate to `/council/delegations` (once route is registered in Unit 4). Verify:
- Table loads with delegation data
- Search filters by task text
- Pagination works
- Click "View" navigates to detail (Unit 5)
- Click "Open MD" opens raw file in new tab

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/pages/Council/Delegations.jsx` | List page component |
| Create | `src/pages/Council/index.js` | Barrel export (optional) |

## Phase-Specific Tests

1. Page renders without errors
2. Table displays delegation data from API
3. Search input filters results
4. Pagination controls work
5. "Open MD" link opens raw file in new tab

## Completion Gate

- [ ] Component renders with delegation data
- [ ] Search, sort, pagination all work
- [ ] Follows existing page patterns (PageHeader, DataTable)
- [ ] No console errors

## Notes for Next Phase

- Unit 4 registers the route so this page is accessible
- Unit 5 adds the detail view (linked from "View" action)
