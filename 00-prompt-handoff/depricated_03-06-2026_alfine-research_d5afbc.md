# Task Handoff: AppFlowy AI Alternatives Research & Migration Planning

**Source spec:** Research findings from 03-June-2026 session
**Generated:** 03-06-2026 by research agent
**Goal:** Evaluate self-hosted AI workspace alternatives to AppFlowy, assess migration viability, and prepare execution plan for AFFiNE + Arc integration.

---

## Executive Summary

AppFlowy self-hosted gates AI features behind a paid commercial license. The license validation is closed-source (commercial fork), with no community-reported bypass. The `af_self_host_commercial_license` database table requires a valid signature from AppFlowy PTE LTD.

**Recommendation:** Pivot to AFFiNE self-hosted + direct llama.cpp server integration. AFFiNE accepts OpenAI-compatible endpoints; the existing llama server (`:18095`, granite-4.1-3b) speaks that natively. No LiteLLM proxy needed.

**Status:** 03-June-2026 — AFFiNE instance running on `:3010` has workspace route white screen (DocRendererController serves HTML with zero JS/CSS assets). Clean rebuild required before AI wiring.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:**
- `/home/chief/llm-wiki/super-council-docs/12-appflowy-integration.md`
- `/home/chief/llm-wiki/00-prompt-handoff/03-06-2026_pg-migration-memory-wiring-appflowy-ext_a7f3c2.md`
**Related codebases:**
- AppFlowy-Cloud (vendor): `/home/chief/Coding-Projects/7-council/super_council/vendor/appflowy-cloud/`
- Arc Summarizer: `/home/chief/Coding-Projects/7-council/super_council/arc_summarizer/`
**Key files for this task:**
- Research report (this document)
- Migration plan (to be created)
- AFFiNE docker-compose (to be created)

---

## Current State: AppFlowy AI Integration

### What Works
- [x] Arc server bound to `0.0.0.0:18095`
- [x] Docker networking configured (`host.arc:18095`)
- [x] AppFlowy AI service healthy
- [x] Azure OpenAI provider → Arc server
- [x] Model mapping: `granite-4.1-3b`

### What's Blocked
- [ ] UI AI features gated behind paywall
- [ ] `af_self_host_commercial_license` table empty
- [ ] No self-service license activation
- [ ] License validation is closed-source

### Database Evidence
```sql
-- License table (empty)
SELECT * FROM af_self_host_commercial_license;  -- 0 rows

-- AI provider connection (configured)
SELECT * FROM af_ai_provider_connections;
-- azure_openai | http://host.arc:18095 | enabled=true

-- Subscription plans in code
-- Free=0, Pro=1, Team=2, AiMax=3, AiLocal=4
```

---

## Alternative Frameworks Analysis

### Comparison Matrix

| Framework | AI Support | Local LLM | Self-Hosted | License | Community | Maturity |
|-----------|-----------|-----------|-------------|---------|-----------|----------|
| **AFFiNE** | ✅ Official | ✅ Ollama/LiteLLM | ✅ Full | MIT | Growing | v0.18+ |
| **Logseq** | ✅ Plugins | ✅ Ollama | ✅ Full | AGPL | Strong | v0.10+ |
| **Obsidian** | ✅ Plugins | ✅ Ollama | ⚠️ Local-first | Proprietary | Large | v1.6+ |
| **Anytype** | ✅ MCP | ✅ Local API | ✅ P2P | GPL | Growing | v0.28+ |
| **AppFlowy** | ❌ Paywalled | ❌ No | ⚠️ Open-core | AGPL+Commercial | Large | v0.15+ |

### Deep Dive: AFFiNE

**Strengths:**
- Official self-host AI guide: `https://docs.affine.pro/self-host-affine/administer/ai`
- Supports custom AI providers via LiteLLM proxy
- Open-source (MIT license)
- Active community discussion on local AI support
- Docker Compose deployment with AI modes (local/remote/no-ai)

**Weaknesses:**
- Smaller community than AppFlowy
- AI features still maturing
- Less documentation than AppFlowy

**Self-Host Architecture (Corrected — No LiteLLM):**
```
Internet → AFFiNE:3010
AFFiNE Copilot → http://localhost:18095/v1/chat/completions
Council API    → http://localhost:18095/v1/chat/completions  (future)
Arc Summarizer → http://localhost:18095/v1/chat/completions  (existing)
                          ↓
              llama.cpp server (granite-4.1-3b, Arc A380 GPU)
```

**Why no LiteLLM:** The llama.cpp server on `:18095` already exposes a full OpenAI-compatible API (`/v1/models`, `/v1/chat/completions`). AFFiNE's AI settings accept any OpenAI-compatible base URL via `config.json`. Adding LiteLLM is an unnecessary indirection layer.

**Official config schema** ([docs.affine.pro/self-host-affine/administer/ai](https://docs.affine.pro/self-host-affine/administer/ai)):
```json
{
  "$schema": "https://github.com/toeverything/affine/releases/latest/download/config.schema.json",
  "copilot": {
    "enabled": true,
    "providers.openai": {
      "apiKey": "",
      "baseUrl": "http://localhost:18095"
    }
  }
}
```

**Verified:** `curl http://localhost:18095/v1/chat/completions` returns OpenAI-compatible responses from granite-4.1-3b. No auth required.

### Deep Dive: Logseq

**Strengths:**
- Mature plugin ecosystem
- Ollama integration plugins available
- Strong privacy focus
- Large community

**Weaknesses:**
- Less collaborative (local-first)
- No official self-host cloud
- AI features via plugins (less integrated)

---

## Fork vs Integrate Assessment

### Option A: Fork AppFlowy Commercial
- **Risk:** High (AGPL + commercial license)
- **Effort:** Very High (closed-source validation)
- **Viability:** Low (legal risk, maintenance burden)

### Option B: Fork AFFiNE
- **Risk:** Low (MIT license)
- **Effort:** Medium (if customizations needed)
- **Viability:** High (open-source, active community)

### Option C: Integrate AFFiNE + Direct Llama Server (Recommended)
- **Risk:** Low (standard OpenAI-compatible integration)
- **Effort:** Low (point AFFiNE AI settings at existing llama endpoint)
- **Viability:** High (no proxy, no extra containers, single model server)

**Recommendation: Option C** - Integrate AFFiNE self-hosted + direct llama.cpp server (`:18095`)

---

## AppFlowy Paywall Bypass Assessment

### Community Findings
- Reddit r/selfhosted: "AI features are also locked behind a paid plan (even with your own key)"
- Reddit r/opensource: "Turns out it's limited to 2 users unless you 'upgrade your license'"
- **No successful bypass reported in community**
- GitHub issues: Users report inability to use AI without license

### Technical Assessment
- License validation is **closed-source** (commercial fork)
- `af_self_host_commercial_license` table requires valid signature
- Server-side validation (not client-side)
- No environment variable bypass found
- No database manipulation bypass found

### Bypass Probability: <5%
- **Legal risk:** High (AGPL + commercial license violation)
- **Technical feasibility:** Low (closed-source validation)
- **Community support:** None (no success stories)

---

## Research Tasks for Further Investigation

### Phase 1: AFFiNE Deep Dive

**What:** Evaluate AFFiNE self-hosted AI capabilities in detail.
**Files:** AFFiNE documentation, GitHub discussions, community guides.
**Steps:**
1. Review official self-host AI guide: `https://docs.affine.pro/self-host-affine/administer/ai`
2. Test AFFiNE Docker Compose deployment with AI modes
3. Verify LiteLLM proxy configuration for custom providers
4. Assess AI feature parity with AppFlowy
5. Document migration path from AppFlowy to AFFiNE

**Tests:**
- [ ] AFFiNE deploys successfully with Docker Compose
- [ ] AI Copilot works with local Ollama
- [ ] Custom provider (Arc via LiteLLM) works
- [ ] AI features accessible without license

**Dependencies:** None

---

### Phase 2: Direct Llama Server Wiring

**What:** Point AFFiNE AI settings at the existing llama.cpp server (`:18095`).
**Files:** AFFiNE AI configuration (env vars or admin UI)
**Steps:**
1. Edit AFFiNE `config.json` (Admin console → AI section, or file at `~/.affine/config/config.json`)
2. Set `copilot.providers.openai.baseUrl` to `http://localhost:18095`
3. Set `copilot.providers.openai.apiKey` to `""` (empty, llama.cpp has no auth)
4. Verify model list: `curl http://localhost:18095/v1/models` → should show `granite-4.1-3b`
4. Test AI completion flow: AFFiNE → llama server → granite-4.1-3b
5. Verify responses render correctly in AFFiNE Copilot
6. Test error handling (server down, model not found)

**Tests:**
- [ ] AFFiNE AI requests hit llama server directly
- [ ] granite-4.1-3b responses return correctly
- [ ] Copilot UI shows streaming/completed responses
- [ ] Error handling works (server down, timeout)

**Dependencies:** Phase 1 complete (AFFiNE UI must render first)

---

### Phase 3: Data Migration Planning

**What:** Plan migration of workspace data from AppFlowy to AFFiNE.
**Files:** Migration scripts, data export/import tools
**Steps:**
1. Assess AppFlowy data structure (PostgreSQL)
2. Map AFFiNE data schema
3. Design migration scripts
4. Test data export/import
5. Verify data integrity

**Tests:**
- [ ] AppFlowy data exports successfully
- [ ] AFFiNE imports data correctly
- [ ] Data integrity verified (no loss)
- [ ] Migration is reversible

**Dependencies:** Phase 1 complete

---

### Phase 4: Community Validation

**What:** Validate findings with community and gather best practices.
**Files:** Community forums, GitHub discussions, Reddit
**Steps:**
1. Search AFFiNE community for self-host AI experiences
2. Gather configuration best practices
3. Identify common pitfalls
4. Document community recommendations
5. Assess long-term viability

**Tests:**
- [ ] Community confirms AFFiNE self-host AI works
- [ ] Best practices documented
- [ ] Pitfalls identified and mitigated
- [ ] Long-term viability assessed

**Dependencies:** None (can run in parallel)

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/llm-wiki/00-prompt-handoff/03-06-2026_appflowy-ai-alternatives-research_d5afbc.md` | This research report |
| Create | `/home/chief/llm-wiki/super-council-docs/13-affine-migration-plan.md` | Migration plan (Phase 1 output) |
| Create | `/home/chief/llm-wiki/super-council-docs/13-affine-migration-plan.md` | Migration plan (Phase 1 output) |
| Modify | `/home/chief/llm-wiki/super-council-docs/12-appflowy-integration.md` | Update with findings |
| Modify | This document | Updated architecture (no LiteLLM, direct llama) |

---

## Constraints

- **No AppFlowy license purchase:** Must find open-source alternative
- **Arc server remains:** Keep Granite-4.1-3B on Intel Arc A380
- **Docker networking:** Maintain existing Docker compose patterns
- **Data integrity:** Preserve existing workspace data during migration
- **Legal compliance:** No license bypass attempts (AGPL + commercial risk)

---

## Success Criteria

- [ ] AFFiNE clean rebuild complete (workspace routes serve JS/CSS)
- [ ] AFFiNE self-hosted AI capabilities verified
- [ ] Direct llama server (`:18095`) integration tested
- [ ] Council API routing through llama server planned
- [ ] Migration plan documented with data mapping
- [ ] Community validation complete
- [ ] Legal/compliance risks assessed
- [ ] Execution-ready migration prompt generated
- [ ] All existing Arc functionality preserved
- [ ] No regression in existing services

---

## Caveats & Uncertainty

1. **AFFiNE AI maturity:** AI features may be less mature than AppFlowy
2. **Community support:** Smaller community means fewer resources
3. **Migration complexity:** Data migration may require custom scripts
4. **Timeline:** Migration may take 1-2 weeks for full integration
5. **Feature parity:** Some AppFlowy features may not exist in AFFiNE

---

## Next Steps

1. **Immediate:** Clean rebuild AFFiNE instance (fix workspace white screen)
2. **Immediate:** Execute Phase 1 (AFFiNE deep dive + baseline verify)
3. **Parallel:** Execute Phase 4 (community validation)
4. **Sequential:** Phase 2 (direct llama server wiring) after Phase 1
5. **Sequential:** Phase 3 (data migration) after Phase 1
6. **Future:** Council API routing through llama server
7. **Final:** Generate execution-ready migration prompt

**Estimated timeline:** 1-2 weeks for full migration planning and testing.
