---
title: kteam-architecture-audit
created: 2026-04-22
status: active
tags: [audit, architecture, issues, recommendations, backend, frontend, llm-integration]
related:
  - kteam-system-architecture
  - kteam-fe-react
  - kteam-dj-be
  - ADR-004-llm-integration-assessment
---

# kteam-architecture-audit

## Summary

Comprehensive audit of kteam system identifying 97 issues (12 Critical, 24 High, 31 Medium, 30 Low) across kteam-dj-be backend and kteam-fe-chief frontend, plus open-source LLM integration assessment. Top issues: hardcoded credentials (7), Pandas overkill for filtering, no caching/queue layer, 4991-line views file, no code splitting, no React Query, manual Redux caching, 50x duplicated access control blocks. Recommended 20-week phased remediation plan covering security fixes, backend stability, frontend optimization, infrastructure scaling, and LLM integration (chat bot, invoice OCR, automations).

## Details

### Backend Issues (kteam-dj-be): 42 issues
- 7 Critical: hardcoded credentials (settings.py, views.py), DEBUG=True, CORS open, auth commented out on gamers endpoint, traceback exposed to users, no rate limiting, no input validation
- 12 High: 50x duplicated access control blocks, Pandas for simple filtering, MongoClient per request, N+1 queries, no pagination, ThreadPoolExecutor thread safety, no caching, no logging, no tests, inconsistent responses, no MongoDB indexes, tight module coupling
- 14 Medium: 3 PDF libraries, no API versioning, no API docs, no health checks, 4991-line views file, duplicate code across files, hardcoded pricing logic, no background tasks, unmaintained Knox, deprecated boto v2, duplicate PyPDF2/pypdf, Python 3.12 compat, frozen default args, mutable default args
- 9 Low: recursive UUID collision, __str__ bug, inconsistent api_view, missing app configs, missing timezone, missing input validation, missing error handling, missing field projections, no select_related

### Frontend Issues (kteam-fe-chief): 47 issues
- 5 Critical: !== null bug pattern (30+ files), prodData[collection] undefined crashes (25+ locations), auth token in localStorage, missing useEffect cleanup (248/319 hooks), moment.js EOL
- 12 High: no code splitting (27KB routes file), no React Query (manual Redux caching), Redux state bloat, no form validation, no React.memo, no useMemo/useCallback, missing ARIA, inline styles bypassing Tailwind, prop drilling, no TypeScript, missing loading states, missing empty states
- 10 Medium: no request dedup, client-side only pagination, no virtualization, no optimistic updates, no i18n, dark mode bugs, inconsistent responsive design, no browser compatibility config, no PWA, fragmented entity/bg-code storage
- 10 Low: React 19 compat untested, Tailwind v4 migration issues, no build optimization, 89 console.log statements, no tests, 49 unwrapped pages, 13 legacy CSS files, no API docs, no keyboard nav, no analytics

### LLM Integration Assessment
- Chat bot: Qwen3.6-35B-A3B (existing) + RAGFlow + MeiliSearch + Qwen3-Embedding-0.6B
- Invoice OCR: Qwen2.5-VL-7B-Instruct (Q4_K_M, ~14GB VRAM) + PaddleOCR
- Automations: Qwen2.5-7B-Instruct (Q4_K_M, ~5GB VRAM)
- Hardware: RTX 3090 (24GB VRAM) — models must be scheduled (cannot run all simultaneously)
- Implementation: 3 phases over 12 weeks (~127 hours)

### Recommended Architecture Changes
- Auth: Knox → JWT (simplejwt) + httpOnly cookies
- State: Redux for everything → React Query for server state + Redux for UI only
- Access control: 50x duplicated → custom DRF permission class
- Pandas: replace with native ORM
- MongoDB: per-request connections → shared singleton + proper indexes
- Add: Redis caching, Celery background tasks, drf-spectacular docs, pytest-Vitest tests, code splitting, React.memo, loading/empty states, form validation
- Remove: djongo5, boto v2, PyPDF2, moment, pandas

### Phased Execution Plan (20 weeks)
- Phase 0 (Week 1): Security fixes — credentials, auth, traceback, rate limiting, !== null fixes
- Phase 1 (Weeks 2-4): Backend stability — ORM queries, permission class, shared Mongo client, Redis, indexes, logging, response format, code splitting
- Phase 2 (Weeks 5-8): Frontend optimization — React Query, code splitting, React.memo, useMemo, page wrapping, date-fns, loading/empty states, form validation, server-side pagination
- Phase 3 (Weeks 9-12): Infrastructure — Celery, API versioning, API docs, health checks, tests, PDF consolidation, JWT migration, accessibility, PWA
- Phase 4 (Weeks 13-20): LLM integration — chat bot, invoice OCR, automations

### Key Statistics
- Total issues: 97 (12 Critical, 24 High, 31 Medium, 30 Low)
- Estimated effort: ~380 hours (backend 200h, frontend 120h, LLM 60h)
- Libraries to remove: djongo5, boto v2, PyPDF2, moment, pandas
- Libraries to add: python-decouple, simplejwt, drf-spectacular, celery, redis, weasyprint, paddleocr, Qwen2.5 models

## References
- Source: /home/chief/architecture-audit-and-recommendations.md (~47KB, 700+ lines)
- Backend audit: Full inspection of all 5 Django apps (155+ endpoints)
- Frontend audit: Full inspection of 129 pages, all reducers, actions, components
- LLM assessment: ADR-004 in llm-wiki/decisions/
