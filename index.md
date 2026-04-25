# Wiki Index

## Projects
- [[rebellion-nextjs]] — Next.js 14 App Router landing page for Rebellion Esports gaming cafes (Tailwind CSS, Framer Motion, Lucide React)
- [[kteam-dj-be]] — Django backend API server for Kuro Gaming ecosystem (PostgreSQL, MongoDB, Meilisearch, REST Framework, Knox auth)
- [[kteam-fe-react]] — React 19 + Vite staff portal "kg-staff" (Radix UI, Redux Toolkit, Tailwind CSS v4, React Router v7, Jest)
- [[renderedge-nextjs]] — Next.js project (separate web presence)

## Architecture
- [[kteam-system-architecture]] — Full system architecture: kteam-dj-be (Django/DRF/PostgreSQL/MongoDB/MeiliSearch) + kteam-fe-chief (React 19/Vite 8/Redux 5/Tailwind v4), 155+ API endpoints, 129+ pages, data flow, multi-tenant model, known issues, prioritized recommendations (P1-P4)

## Plans
- [[kungos]] — Master modernization plan (Project Code: Kungos): phased remediation of 97 audit issues + gaming integration, ~340–520 hours (likely 420h), single deployment at program end, 6 phases with P0/P1/P2 prioritization

## Ops
- [[kungos-log]] — Kungos departure log: approved deviations from the modernization plan with justification and approver
- [[kungos-debug-tools]] — Debugging and audit tooling built during the React render error investigation (errorLogger, ErrorBadge, test_pages.py, test_dynamic_pages.py, TESTING_STRATEGY.md)

## Entities
- [[kteam-architecture-audit]] — Full system audit: 97 issues (12 Critical, 24 High, 31 Medium, 30 Low) across kteam-dj-be + kteam-fe-chief, LLM integration assessment for chat bot/OCR/automations, 20-week remediation plan
- [[kteam-system-architecture]] — Full system architecture: kteam-dj-be (Django/DRF/PostgreSQL/MongoDB/MeiliSearch) + kteam-fe-chief (React 19/Vite 8/Redux 5/Tailwind v4), 155+ API endpoints, 129+ pages, data flow, multi-tenant model, known issues, prioritized recommendations (P1-P4)
- [[Qwen3.5-35B-A3B]] — Secondary fast model, also served via llama.cpp
- [[DeepSeek-R1-Distill-Qwen-32B]] — Reasoning model with speculative decoding (Qwen2.5-1.5B draft), served on port 11435
- [[RTX 3090]] — Hardware: 24GB VRAM, primary GPU for local inference
- [[96GB DDR5 RAM]] — System memory
- [[llama.cpp]] — Local LLM inference engine with CUDA 12.8 support
- [[RAGFlow]] — Self-hosted RAG knowledge base (Elasticsearch, MinIO, Redis, MySQL, Qwen3-Embedding-0.6B)
- [[SearXNG]] — Self-hosted metasearch engine
- [[CUDA 12.8]] — GPU compute toolkit

## LLM Tools
- [[Claude Code]] — Uses qwen3.6-35b-a3b via local proxy at 127.0.0.1:8001
- [[OpenCode]] — Uses Anthropic-compatible local endpoint at 127.0.0.1:8001
- [[Codex CLI]] — OpenAI-compatible with skills (imagegen, plugin-creator, skill-creator)
- [[Cursor]] — Configured with skills (canvas, create-skill, create-rule, subagents)
- [[OpenClaw]] — Gateway with Telegram bot, local model provider, 16K context, 4096 max tokens

## Infrastructure
- [[Local AI Stack]] — Full setup: llama.cpp services, model downloads, systemd services, OpenClaw config
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
