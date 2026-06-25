# Unit 5: Frontend — Delegation Detail View

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 5 of 6
**Dependencies:** Unit 3 (list page must exist), Unit 1 (API detail endpoint)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Key files for this phase:**
- `src/pages/Council/DelegationDetail.jsx` — new detail page (create)
- `src/routes/main.jsx` — add detail route (modify)

## What This Phase Delivers

Detail view at `/council/delegations/:chainId` showing full task text, full response text (collapsible), metadata (chain_id, role, from/to model, batch, retry, timestamp), and "Open Full MD" button.

## Pre-Flight Checklist

- [ ] Unit 3 is complete (list page exists)
- [ ] Unit 1 is complete (GET `/v1/council/delegations/{chain_id}` endpoint exists)
- [ ] Read one delegation detail API response to verify data shape

## Implementation Steps

### Step 1: Create detail component

Create `src/pages/Council/DelegationDetail.jsx`:

```jsx
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import PageHeader from '@/components/common/PageHeader'
import PageSection from '@/components/common/PageSection'
import { Badge, Button, Card, CardContent } from '@/components/ui'
import { Spinner } from '@/components/ui/Spinner'
import { ArrowLeft, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react'
import { fetcher } from '@/lib/api'

export default function DelegationDetail() {
  const { chainId } = useParams()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['delegation', chainId],
    queryFn: fetcher(`/api/v1/council/delegations/${chainId}`),
  })

  if (isLoading) return <Spinner />
  if (!data) return <div>Not found</div>

  return (
    <>
      <PageHeader
        title="Delegation Detail"
        onBack={() => navigate('/council/delegations')}
      />
      <PageSection>
        {/* Metadata cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent>From: {data.from_model || 'unknown'}</CardContent></Card>
          <Card><CardContent>To: {data.to_model}</CardContent></Card>
          <Card><CardContent>Role: {data.role}</CardContent></Card>
          <Card><CardContent>Batch: {data.batch} / Retry: {data.retry}</CardContent></Card>
        </div>

        {/* Task */}
        <Card>
          <CardContent>
            <h3>Task</h3>
            <pre className="whitespace-pre-wrap">{data.task}</pre>
          </CardContent>
        </Card>

        {/* Response (collapsible) */}
        <Card>
          <CardContent>
            <div className="flex justify-between">
              <h3>Response ({data.response_length} chars)</h3>
              <Button onClick={() => setExpanded(!expanded)}>
                {expanded ? <ChevronUp /> : <ChevronDown />}
              </Button>
            </div>
            {expanded || data.response_length < 500 ? (
              <pre className="whitespace-pre-wrap">{data.response}</pre>
            ) : (
              <pre className="whitespace-pre-wrap">{data.response?.slice(0, 500)}...</pre>
            )}
          </CardContent>
        </Card>

        {/* Open MD button */}
        <Button asChild>
          <a href={`/api/v1/council/delegations/${chainId}/raw`} target="_blank" rel="noopener noreferrer">
            <ExternalLink /> Open Full MD
          </a>
        </Button>
      </PageSection>
    </>
  )
}
```

### Step 2: Add detail route

In `src/routes/main.jsx`, add:
```jsx
{
  path: '/council/delegations/:chainId',
  element: <DelegationDetail />,
},
```

### Step 3: Wire list → detail navigation

In `Delegations.jsx` (Unit 3), make the "View" action navigate to `/council/delegations/{chain_id}`.

### Step 4: Test

1. Click delegation row → navigates to detail view
2. Detail shows full task + response
3. Response collapses/expands
4. "Open Full MD" opens raw file in new tab

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/pages/Council/DelegationDetail.jsx` | Detail page component |
| Modify | `src/routes/main.jsx` | Add `/council/delegations/:chainId` route |
| Modify | `src/pages/Council/Delegations.jsx` | Wire "View" action to navigate to detail |

## Phase-Specific Tests

1. Detail page loads with delegation data
2. Metadata displays correctly
3. Task text renders fully
4. Response collapses/expands (500 char preview default)
5. "Open Full MD" opens raw file in new tab
6. Back button returns to list

## Completion Gate

- [ ] Detail view renders all fields
- [ ] Response collapsible works
- [ ] "Open Full MD" link works
- [ ] Navigation between list and detail works
- [ ] No console errors

## Notes for Next Phase

This is the final implementation unit. After completion, run full verification:
1. Trigger a new delegation → verify it appears in DB and frontend
2. Search/filter in list view
3. Navigate to detail → verify all fields
4. Open MD file → verify raw content matches
