# Wiki Index

## Projects
- [[rebellion-nextjs]] — Next.js 14 App Router landing page for Rebellion Esports gaming cafes (Tailwind CSS, Framer Motion, Lucide React)
- [[kteam-dj-be]] — Django backend API server for Kuro Gaming ecosystem (PostgreSQL, MongoDB, Meilisearch, REST Framework, Knox auth)
- [[kteam-fe-react]] — React 19 + Vite staff portal "kg-staff" (Radix UI, Redux Toolkit, Tailwind CSS v4, React Router v7, Jest)
- [[renderedge-nextjs]] — Next.js project (separate web presence)

## Architecture
- [[kteam-system-architecture]] — Full system architecture: kteam-dj-be (Django/DRF/PostgreSQL/MongoDB/MeiliSearch) + kteam-fe-chief (React 19/Vite 8/Redux 5/Tailwind v4), 155+ API endpoints, 129+ pages, data flow, multi-tenant model, known issues, prioritized recommendations (P1-P4)

## Plans
- [[KungOS_v2]] — Authoritative modernization plan (Project Code: Kungos): Phases 0–3 complete ✅, Phase 4 (testing/CI/CD) pending. Replaces legacy `kungos.md`. See [[kungos-log]] for approved departures.
- [[kungos-deployment]] — Production deployment guide: MongoDB dump restore, entity migration, rollback procedures, and cutover checklist
- [[kungos-cafe-platform]] — GGleap-style gaming cafe management platform: unified identity (phone = universal key), shared wallet, station/session management, post-core expansion (120–180 hours)

## Ops
- [[kungos-log]] — Kungos departure log: approved deviations from the modernization plan with justification and approver
- [[kungos-debug-tools]] — Debugging and audit tooling built during the React render error investigation (errorLogger, ErrorBadge, test_pages.py, test_dynamic_pages.py, TESTING_STRATEGY.md)
- [[kungos-migration-tools]] — Production migration tools: Django management commands for MongoDB dump restore, entity population, and tenant isolation (restore_kuropurchase, backup_kuropurchase, deploy_restore)

## Entities
- [[kteam-architecture-audit]] — Full system audit: 97 issues (12 Critical, 24 High, 31 Medium, 30 Low) across kteam-dj-be + kteam-fe-chief
- [[kteam-system-architecture]] — Full system architecture: kteam-dj-be + kteam-fe-chief, 155+ API endpoints, 129+ pages
- [[local-ai-stack]] — Local LLM inference: endpoints, models, RAG, search
- [[llm-setup-analysis]] — Hardware specs, performance benchmarks, optimization recommendations

## LLM Tools
- **Pi** — Primary coding agent, uses Qwen3.6-27B via port 8001 (OpenAI API)
- **Claude Code** — Uses local proxy at 127.0.0.1:8001
- **OpenCode** — Uses local endpoint at 127.0.0.1:8001

## Infrastructure
- [[Knox Auth]] — Authentication system used in kteam-dj-be
- [[PostgreSQL]] — Primary relational database
- [[MongoDB]] — Document database, daily backups at 22:30
- [[Meilisearch]] — Search engine for kteam-dj-be
- [[MinIO]] — Object storage for RAGFlow

## Decisions
- [[ADR-001-local-llm]] — Use local models instead of cloud APIs for privacy and cost
- [[ADR-002-dual-model]] — Fast model for boilerplate, reasoning model for hard bugs/architecture
- [[ADR-003-llama-cpp]] — Use llama.cpp with CUDA for inference instead of vLLM/Ollama
- [[ADR-004-llm-integration-assessment]] — Open-source LLM integration assessment for kteam (invoice OCR, chat bot, automations, architecture, model recommendations, roadmap)
- [[ADR-005-debug-tools]] — Keep errorLogger, ErrorBadge, and Playwright test scripts as permanent debugging/audit tools (enabled/disabled as needed)

## Lessons
- [[lucide-react-forwardref-typeof-check]] — `typeof` check for React components fails on `forwardRef` components (typeof === 'object'), causing render crashes in React 19

## Patterns
- [[nextjs-dark-theme]] — Dark theme implementation with Tailwind CSS
- [[nextjs-app-router]] — Next.js 14/16 App Router conventions
- [[django-module-structure]] — Django module organization (users, careers, kurostaff, kuroadmin)
- [[redux-toolkit-state]] — Redux Toolkit state management patterns (kteam-fe-react)
- [[radix-ui-components]] — Radix UI headless component patterns (kteam-fe-react)
- [[docker-compose-deploy]] — Docker Compose deployment patterns

## Comparisons
- [[kteam-fe-react-vs-minimal-material-kit]] — Tailwind CSS v4 vs MUI v5 design system comparison, 26 prioritized UI/UX improvements

## Anti-patterns
- [[no-inline-api-keys]] — Never hardcode credentials or API keys
- [[no-cloud-llm-deps]] — Avoid dependency on cloud LLM APIs (local-only)
- [[no-unnecessary-deps]] — Minimize npm/pip dependencies
