# System Prompt Injection Audit: Why Are Skills Fully Loaded at Startup?

| Field | Value |
|-------|-------|
| Project ID | `pi-core` |
| Primary entity ID | `21d9bb` |
| Entity type | `session` |
| Short description | Investigate why TDD, Ponytail, and tool schemas are fully injected into the system prompt at startup instead of lazy-loaded on trigger |
| Status | `draft` |
| Source references | Provisional measurements from session 2026-06-24 (see below) |
| Generated | 24-06-2026 |
| Next action / owner | Investigate skill loading config, extension registration, and settings.json for forced full-injection |

## Problem Statement

The pi session starts with ~20K tokens of context before any user input. Investigation reveals that **TDD skill** (5.3K chars) and **Ponytail skill** (6.5K chars) are having their *full* SKILL.md content injected into the system prompt, not just listed in the `<available_skills>` XML block. Tool schemas (27K chars across 36 tools) are also present — this is expected for tool-use LLMs, but the skill full-text injection appears to violate the lazy-load contract.

The `<available_skills>` block instructs: *"Use the read tool to load a skill's file when the task matches its description."* This implies skills should be listed (name + description + location only) and loaded on-demand via `read`. But TDD and Ponytail are bypassing this.

**Question:** Is this intentional (persistent mode skills) or a misconfiguration?

## Provisional Measurements (Needs Audit)

The following data was gathered from file inspection and source code analysis. **All measurements are provisional and need verification** — the extraction methods used heuristic estimates (e.g., 30% of TypeScript blocks = schema size) rather than measuring the actual JSON sent to the LLM.

### Context Breakdown (Provisional)

| Component | Chars | ~Tokens | Confidence |
|---|---|---|---|
| Tool schemas: council-tools (12 tools) | 7,502 | 1,875 | LOW — estimated from TS block sizes |
| Tool schemas: codegraph-mcp (10 tools) | 4,381 | 1,095 | LOW — estimated from TS block sizes |
| Tool schemas: subagent (desc+schema) | 8,178 | 2,044 | MED — desc measured, schema from schemas.ts |
| Tool schemas: built-in (read/bash/edit/write) | 3,772 | 943 | MED — schema vars measured |
| Tool schemas: s2s-mcp | 1,368 | 342 | LOW — estimated |
| Tool schemas: web-search | 1,989 | 497 | LOW — estimated |
| Tool schemas: s2s-test | 77 | 19 | LOW — estimated |
| **Tool schemas subtotal** | **27,267** | **6,816** | **LOW** |
| Tool snippets (one-line per tool) | 1,750 | 437 | GUESS — not measured |
| Tool guidelines | 4,500 | 1,125 | GUESS — not measured |
| AGENTS.md (project instructions) | 3,255 | 813 | HIGH — `wc -c` measured |
| Skills list (XML, 19 skills) | 5,498 | 1,374 | MED — reconstructed from SKILL.md frontmatter |
| **Ponytail skill (FULL text)** | **6,482** | **1,620** | **HIGH — `wc -c` measured** |
| **TDD skill (FULL text)** | **5,252** | **1,313** | **HIGH — `wc -c` measured** |
| Base prompt template | 1,298 | 324 | MED — extracted from JS template literal |
| Pi docs references (paths only) | 800 | 200 | GUESS — not measured |
| Date + working directory | 60 | 15 | HIGH |
| **GRAND TOTAL** | **83,429** | **~20,857** | **LOW** |

### What Was Measured vs Estimated

**Measured from actual files (`wc -c`):**
- AGENTS.md: 3,255 bytes
- Ponytail SKILL.md: 6,482 bytes
- TDD SKILL.md: 5,252 bytes
- All SKILL.md files (for skills list reconstruction)
- SubagentParamsSchema from schemas.ts: 5,357 chars

**Estimated from source code heuristics:**
- Tool schema sizes: extracted TypeScript `registerTool` blocks, estimated 30% = JSON schema portion
- Built-in tool schemas: measured `Type.Object` definitions separately from handler code
- Tool snippets + guidelines: guessed based on typical sizes

**Not measured at all:**
- Actual JSON sent to LLM (no session log captures system prompt)
- Token count from LLM provider (would need API logging)
- Whether TDD/Ponytail are injected by skill config vs extension vs settings

## Key Files to Examine

### Skill Loading

| File | Purpose |
|------|---------|
| `/home/chief/.nvm/.../pi-coding-agent/dist/core/skills.js` | `formatSkillsForPrompt()` — how skills appear in prompt |
| `/home/chief/.nvm/.../pi-coding-agent/dist/core/system-prompt.js` | `buildSystemPrompt()` — how prompt is assembled |
| `/home/chief/.nvm/.../pi-coding-agent/dist/core/agent-session.js` | Tool registration, prompt construction flow |

### Skill Config (What Forces Full Injection?)

| File | Purpose |
|------|---------|
| `/home/chief/.pi/agent/AGENTS.md` | Contains "PONYTAIL MODE ACTIVE" and TDD references — does this trigger full load? |
| `/home/chief/.pi/agent/settings.json` | Check for skill loading preferences |
| Each SKILL.md frontmatter | Check for `alwaysLoad`, `persistent`, `defaultContext` fields |
| `/home/chief/.pi/agent/skills/test-driven-development/SKILL.md` | Frontmatter says "default coding posture" — does this mean always loaded? |
| `/home/chief/.pi/agent/git/.../ponytail/skills/ponytail/SKILL.md` | Contains "ACTIVE EVERY RESPONSE" — is this a directive or just prose? |

### Extension Registration

| File | Purpose |
|------|---------|
| `/home/chief/.pi/agent/extensions/council-tools/index.ts` | 72K file — registers 12 tools |
| `/home/chief/.pi/agent/extensions/codegraph-mcp/index.ts` | 24K file — registers 10 tools |
| `/home/chief/.pi/agent/npm/node_modules/pi-subagents/src/extension/index.ts` | Registers subagent tool |
| `/home/chief/.pi/agent/npm/node_modules/pi-subagents/src/extension/schemas.ts` | SubagentParams schema (5.4K chars) |

## Investigation Phases

### Phase 1: Audit the Provisional Measurements

**What:** Verify or correct the provisional context breakdown. Measure actual data sent to LLM.

**Steps:**
1. Enable API/provider logging to capture the actual system prompt sent to the LLM
2. Parse the captured prompt and measure each component precisely
3. Compare against provisional measurements and flag discrepancies
4. Determine actual token count from the provider (not char/4 estimate)

**Files:** Provider config, API logs, session files
**Tests:** Captured prompt size matches reported ~20K tokens

### Phase 2: Trace Skill Loading Path

**What:** Follow the code path from skill discovery to prompt injection. Determine why TDD and Ponytail get full content.

**Steps:**
1. Read `skills.js` — trace `loadSkills()` → `formatSkillsForPrompt()` → what gets included
2. Read `system-prompt.js` — trace `buildSystemPrompt()` — where does full skill content enter?
3. Check if AGENTS.md content ("PONYTAIL MODE ACTIVE") triggers special loading
4. Check SKILL.md frontmatter for `alwaysLoad`, `persistent`, or similar fields
5. Check `settings.json` for skill loading configuration
6. Determine: is full injection a skill-level setting, extension behavior, or AGENTS.md directive?

**Files:**
- `/home/chief/.nvm/.../pi-coding-agent/dist/core/skills.js` (lines 257+ for formatSkillsForPrompt)
- `/home/chief/.nvm/.../pi-coding-agent/dist/core/system-prompt.js` (buildSystemPrompt function)
- `/home/chief/.nvm/.../pi-coding-agent/dist/core/agent-session.js` (tool/skill integration)
- All SKILL.md frontmatter sections

**Tests:** Code trace shows exact injection point for full skill content

### Phase 3: Review Tool Schema Necessity

**What:** Audit whether all 36 tool schemas are necessary at startup, or if some can be lazy-loaded.

**Steps:**
1. List all 36 tools and categorize: always-needed vs situational
2. Research whether the LLM provider supports dynamic tool registration (tools added mid-session)
3. Identify tools that could be deferred (e.g., s2s-test, review tools if not in use)
4. Estimate token savings from removing deferrable tools

**Files:** All extension index.ts files, pi core tool definitions
**Tests:** List of deferrable tools with estimated savings

### Phase 4: Recommendations

**What:** Based on Phases 1-3, produce actionable options.

**Options to evaluate:**
- A: If skill full-injection is config-driven → change config to lazy-load
- B: If skill full-injection is hardcoded → propose patch
- C: If tool schemas can be dynamic → defer non-essential tools
- D: If current behavior is intentional → document the trade-off and accept

## Caveats & Uncertainty

1. **Provisional data quality:** Tool schema measurements use heuristic estimates (30% of TS blocks). Actual JSON schemas may differ due to TypeBox compilation, nested references, or serialization overhead.
2. **No ground-truth capture:** The actual system prompt sent to the LLM was not captured. All measurements are from source code reconstruction, not from the wire.
3. **Token estimation:** Using chars/4 is approximate. Actual tokenization varies by model (Qwen-27B may differ from the 4:1 ratio).
4. **Skill loading mechanism unknown:** It's unclear whether full skill injection is triggered by frontmatter, AGENTS.md content, settings.json, or extension code. This is the primary unknown.
5. **Ponytail "ACTIVE EVERY RESPONSE" may be intentional:** This could be a design choice (persistent mode) rather than a bug. Needs design intent verification.
6. **TDD "default coding posture" may be intentional:** Same as above — could be by design.

## Success Criteria

- [ ] Actual system prompt captured and measured (replaces provisional data)
- [ ] Exact injection point for TDD + Ponytail full content identified
- [ ] Determined whether full injection is config-driven, hardcoded, or intentional
- [ ] List of deferrable tool schemas with estimated savings
- [ ] Clear recommendation: fix config, patch code, or accept as design

## Constraints

- **Do not modify** any pi core files, extension configs, or settings without explicit approval
- **Do not disable** skills or tools during investigation — only audit
- **Measure, don't assume** — every claim needs file-level evidence
