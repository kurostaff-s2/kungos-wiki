a complete memory system combining Agent patterns (curated MEMORY.md, frozen snapshot injection, character caps) with MemSearch (transcript capture, hybrid vector search for recall).

**What you get:** Store (auto-tracking + curated facts + transcript capture), Inject (frozen snapshot at session start, ~3,000 tokens), Recall (tiered retrieval from zero-cost to semantic vector search).

**Assumes nothing.** Every step checks what exists before creating or modifying. Works on a fresh Claude Code project or an existing setup with its own memory instructions.

---

## Step 1: Install MemSearch

Check if memsearch is already installed:

```bash
pip show memsearch 2>/dev/null
```

If not installed:

```bash
pip install memsearch
# First run downloads ONNX bge-m3 model (~558 MB, cached at ~/.cache/memsearch/)
```

## Step 2: Create the folder structure

Check which folders exist, then create only the missing ones:

```bash
test -d context || mkdir -p context
test -d context/memory || mkdir -p context/memory
test -d context/transcripts || mkdir -p context/transcripts
```

These folders will hold:
- `context/memory/{YYYY-MM-DD}.md` â€” daily session logs
- `context/transcripts/{YYYY-MM-DD}.md` â€” transcript summaries from the Stop hook
- `context/MEMORY.md` â€” curated fact scratchpad (created next)

## Step 3: Create context/MEMORY.md

Check if `context/MEMORY.md` already exists. If it does, read it and leave it alone â€” it may contain curated facts from previous sessions. Only create if missing:

```markdown
<!-- Cap: 2,500 chars. Agent maintains via memory-write instructions. -->
# Working Memory

## Active Threads

## Environment Notes

## Pending Decisions
```

## Step 4: Create context/USER.md

Check if `context/USER.md` already exists. If it does, read it and leave it alone â€” it may contain user preferences. Only create if missing:

```markdown
<!-- Cap: 1,375 chars. Updated by the agent when it learns preferences. -->
# User Profile

## About

## Preferences

## Working Style
```

## Step 5: Audit existing memory instructions

Before adding anything, read these files end to end (whichever exist) and search for any existing memory-related instructions:

1. **`CLAUDE.md`** â€” look for memory sections, `MEMORY.md` references, auto-memory rules, `~/.claude/projects/*/memory/` paths, recall/retrieval instructions, memory budget rules, session startup memory loading
2. **`AGENTS.md`** (if it exists) â€” look for memory-related skill entries, memory tool references, memory conventions
3. **`~/.claude/CLAUDE.md`** (if it exists) â€” look for global memory rules, memory management sections, repo memory auto-init, domain knowledge lifecycle rules

For each existing memory instruction you find:
1. List what you found (file, section name, what it does)
2. Determine if it conflicts with this guide's memory system
3. **Remove or update** conflicting instructions â€” this guide defines the single memory system
4. **Keep** instructions that are complementary (e.g., global memory promotion rules can coexist if they reference `context/MEMORY.md` instead of `~/.claude/projects/*/memory/MEMORY.md`)
5. If existing instructions contain project-specific facts worth preserving, migrate them into the appropriate new section

Pay special attention to:
- Any references to `~/.claude/projects/{slug}/memory/MEMORY.md` â€” this is the old path. The new system uses `context/MEMORY.md` in the project repo
- Any auto-memory init rules that create a different `MEMORY.md` format â€” replace with this guide's format
- Any memory retrieval instructions that conflict with the tiered retrieval system below

The goal: after this step, there is exactly one set of memory instructions, not a mix of old and new.

## Step 6: Update CLAUDE.md

Check if `CLAUDE.md` exists at the project root. If it doesn't, create it. If it does, read it first and only add sections that aren't already present (after removing any conflicting memory sections found in Step 5).

**Session startup â€” how to add depends on what exists:**

If CLAUDE.md has a `### Returning Mode` section with numbered steps, find step 3 (reading today's memory file) and add step 3.5 after it:

```
3.5. Read `context/MEMORY.md` (~2.5 KB max, curated working scratchpad). This is a frozen snapshot â€” mid-session writes persist to disk but take effect next session.
```

If CLAUDE.md has no returning mode section, add a full startup block â€” skip if a `## Session Startup` section already exists:

```markdown
## Session Startup (silent â€” do not output anything)

On every session start, read these files silently:
1. Read `context/USER.md` (~1.4 KB max)
2. Read `context/MEMORY.md` (~2.5 KB max, curated working scratchpad)
3. Read `context/memory/{today's date in YYYY-MM-DD}.md` if it exists
4. If today's memory file has no prior sessions, also read yesterday's

These files are your "frozen snapshot" â€” loaded once at session start. Mid-session writes persist to disk but take effect next session. This preserves the prefix cache.

Total injected: ~3,000 tokens. Do not load more than this at startup.
```

**Add a Memory Budget section â€” skip if it already exists:**

```markdown
### Memory Budget

- `context/MEMORY.md`: 2,500 character cap. Before writing, check `wc -c`. If over cap, consolidate existing entries before adding.
- `context/USER.md`: 1,375 character cap. Same rule.
- Mid-session writes to these files persist to disk but only appear in context next session (frozen snapshot pattern â€” preserves prefix cache).
```

**Add a Memory Write section â€” skip if it already exists:**

```markdown
### Memory Write

When the user says "remember this", "note that", "update memory", or "forget about":
1. Read `context/MEMORY.md` in full
2. Check for duplicates (scan for substring match)
3. Check character count: `wc -c < context/MEMORY.md`
4. If under 2,500 chars: append the new fact under the appropriate section
5. If over cap: consolidate â€” merge similar entries, remove stale ones, then add
6. Actions: add (append), replace (find substring + swap), remove (confirm with user first)
7. After writing: "Saved â€” will be active from next session."
```

**Add a Memory Retrieval section â€” skip if it already exists:**

```markdown
### Memory Retrieval

When the user asks about past context, conversations, or decisions:

1. **Tier 0**: Check `context/MEMORY.md` and today's daily log â€” already in context, zero cost
2. **L1**: Run `memsearch search "query" --top-k 5` â€” hybrid vector + keyword search. Finds semantic matches even with different words (e.g. "pricing" finds "monetisation")
3. **L2**: Run `memsearch expand <chunk_hash>` â€” returns full markdown section around the match
4. **L3**: Run `memsearch transcript <session_id>` â€” raw dialogue, last resort
5. **Fallback**: "I don't have a record of that."

Only escalate if the previous tier didn't find the answer.
```

**Add a Daily Log section â€” skip if a daily log or daily memory section already exists:**

```markdown
### Daily Log

Track session activity in `context/memory/{YYYY-MM-DD}.md`. One file per day, numbered session blocks:

#### Session N
**Goal**: [one line, filled when user states their goal]
**Deliverables**: [files created/modified]
**Decisions**: [key decisions and rationale]
**Open threads**: [anything unfinished]

Log these silently as they happen. Never announce "I've logged that."
```

## Step 7: Create the transcript capture hook

Check if `.claude/hooks/` directory exists â€” create it if missing. Check if `transcript-capture.js` already exists â€” skip if it does.

Create `.claude/hooks/transcript-capture.js`:

```javascript
const fs = require('fs');
const path = require('path');

// Stop hook: captures first 500 chars of assistant response to daily transcript file
const input = JSON.parse(fs.readFileSync('/dev/stdin', 'utf8'));

if (input.stop_reason === 'end_turn' && input.response) {
  const today = new Date().toISOString().slice(0, 10);
  const dir = path.join(process.env.CLAUDE_PROJECT_DIR || '.', 'context', 'transcripts');
  const file = path.join(dir, `${today}.md`);

  try {
    fs.mkdirSync(dir, { recursive: true });
    const summary = input.response.slice(0, 500).replace(/\n{3,}/g, '\n\n');
    const timestamp = new Date().toISOString().slice(11, 19);
    const entry = `\n## ${timestamp}\n${summary}\n`;
    fs.appendFileSync(file, entry);
  } catch (e) {
    // Fire and forget â€” don't break the session
  }
}
```

Register it in `.claude/settings.json`. Read the file first:
- If it doesn't exist, create it with the hook config below
- If it exists, check whether a `Stop` hook array already contains `transcript-capture.js` â€” skip if already registered
- If it exists but has no `Stop` hooks, add the entry to the existing structure

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node .claude/hooks/transcript-capture.js"
          }
        ]
      }
    ]
  }
}
```

## Step 8: Integrate with existing project structure (if applicable)

These sub-steps only apply if the project has the corresponding files. Check each one â€” skip any that don't exist.

### 8a: Memory-write skill (if `.claude/skills/` exists)

Check if `.claude/skills/memory-write/` already exists â€” skip if it does.

Create `.claude/skills/memory-write/SKILL.md`:

```markdown
---
name: memory-write
description: >
  Saves durable facts to context/MEMORY.md. Triggers on "remember this",
  "note that", "update memory", "save this", "forget about". Three actions:
  add (append under correct section), replace (substring match + swap),
  remove (confirm with user first). Enforces 2,500 char cap with dedup guard.
---

# Memory Write

## Outcome
- Fact added to, updated in, or removed from `context/MEMORY.md`
- Character cap enforced (2,500 chars)
- Confirmation message: "Saved â€” will be active from next session."

## Steps

1. Read `context/MEMORY.md` in full
2. Determine action: add, replace, or remove
3. **Dedup check**: scan for substring match â€” if the fact already exists, skip or update
4. **Cap check**: run `wc -c < context/MEMORY.md` â€” if over 2,500, consolidate before adding
5. Write the change
6. Confirm: "Saved â€” will be active from next session."

For **remove**: always confirm with the user before deleting.

## Sections in MEMORY.md
- `## Active Threads` â€” current work, open questions
- `## Environment Notes` â€” URLs, API keys (names only), tool versions, project structure
- `## Pending Decisions` â€” decisions that need to be made

## Rules
- Never exceed 2,500 characters
- Always check for duplicates before adding
- Replace is preferred over add when updating existing facts
```

### 8b: AGENTS.md registration (if `AGENTS.md` exists)

Read `AGENTS.md`. Check whether `memory-write` is already in the Skill Registry â€” only add if missing:

```
| `memory-write` | "remember this", "note that", "update memory", "forget about" |
```

Check the Context Matrix for `memory-write` â€” only add if missing:

```
| `memory-write` | â€” | â€” | â€” | â€” | â€” | `## memory-write` |
```

### 8c: Learnings file (if `context/learnings.md` exists)

Read `context/learnings.md`. Check if a `## memory-write` section exists â€” only add if missing:

```
## memory-write
```

### 8d: PreToolUse hook (if `~/.claude/hooks/pre-tool-memory.py` exists)

Read `find_project_memory()` and check if it already checks for `context/MEMORY.md`. Only add if missing â€” prepend before the existing `candidates` list:

```python
# Check in-repo MEMORY.md first
in_repo = os.path.join(cwd, "context", "MEMORY.md")
if os.path.exists(in_repo):
    return in_repo
```

This makes the hook inject the curated in-repo MEMORY.md instead of the empty `~/.claude/projects/` one.

### 8e: Wrap-up skill (if `.claude/skills/meta-wrap-up/SKILL.md` exists)

Read the file. Check whether a `### 3g` step or `Update Working Memory` section already exists â€” only add if missing.

Add step 3g after the last existing sub-step:

```markdown
### 3g: Update Working Memory

Update `context/MEMORY.md` based on the session:
1. Add any new active threads from this session
2. Mark resolved threads (remove or update)
3. Update environment notes if new tools/URLs/configs were discussed
4. Run `wc -c < context/MEMORY.md` and report usage: "{N}/2,500 chars ({percent}%)"
5. If over 2,500 chars, consolidate: merge similar entries, remove stale ones
```

Check the Session Summary template in the same file. Add if not already present:

```
Memory:
- MEMORY.md: {N}/2,500 chars ({percent}%)
```

## Step 9: Configure MemSearch

```bash
memsearch config set paths context/memory,context/transcripts
memsearch index
```

## Step 10: Update .gitignore

Check if `.gitignore` exists â€” create it if missing. Read it first, then only add lines that aren't already present:

```
context/transcripts/
.memsearch/
```

## Step 11: Optional â€” Cron jobs

If `cron/jobs/` directory exists, create these files (skip any that already exist):

**`daily-memory-distill.md`:**
```yaml
---
name: Daily Memory Distillation
time: '23:00'
days: daily
active: 'true'
model: haiku
notify: on_failure
description: 'Extracts durable facts from daily log into MEMORY.md'
timeout: 5m
retry: '0'
---
Read today's `context/memory/{today}.md`. Extract any durable facts (URLs, decisions, preferences, project structure) that aren't already in `context/MEMORY.md`. Add them under the appropriate section. Enforce the 2,500 char cap.
```

**`nightly-memsearch-index.md`:**
```yaml
---
name: Nightly MemSearch Index
time: '02:00'
days: daily
active: 'true'
model: haiku
notify: on_failure
description: 'Re-indexes memory and transcript files for vector search'
timeout: 5m
retry: '1'
---
Run `memsearch index` to update the vector database with any new content from today's memory and transcript files.
```

**`weekly-memory-curator.md`:**
```yaml
---
name: Weekly Memory Curator
time: '09:00'
days: sun
active: 'true'
model: sonnet
notify: on_finish
description: 'Prunes, merges, and consolidates MEMORY.md entries'
timeout: 10m
retry: '0'
---
Read `context/MEMORY.md`. For each entry:
1. Is it still relevant? Remove if stale.
2. Are there duplicates? Merge them.
3. Can entries be consolidated? Combine related facts.
Keep under 2,500 chars. Log what was changed.
```

If `cron/jobs/weekly-activity-digest.md` exists with `active: 'false'`, change to `active: 'true'`.

If `cron/jobs/` doesn't exist, set up these as system cron jobs or scheduled tasks instead:
- **Nightly 02:00**: `memsearch index` â€” re-indexes new content
- **Weekly**: Review MEMORY.md, prune stale entries, merge duplicates

## Step 12: Verify

1. Start a new Claude Code session â€” confirm it reads MEMORY.md and USER.md silently
2. Say "remember that our staging URL is staging.example.com" â€” confirm it writes to MEMORY.md
3. Have a short conversation, then check `context/transcripts/{today}.md` has entries
4. Run `memsearch index` then `memsearch search "staging"` â€” confirm it finds the entry
5. In a new session, ask "what's our staging URL?" â€” confirm Tier 0 finds it in MEMORY.md
6. If cron jobs were created: run `bash scripts/start-crons.sh` â€” confirm new jobs appear

---

## Files Summary

| Action | File |
|--------|------|
| Create (if missing) | `context/MEMORY.md` |
| Create (if missing) | `context/USER.md` |
| Create (if missing) | `context/memory/` (directory) |
| Create (if missing) | `context/transcripts/` (directory) |
| Create (if missing) | `.claude/hooks/transcript-capture.js` |
| Create (if missing) | `.claude/skills/memory-write/SKILL.md` |
| Create or modify | `CLAUDE.md` (add memory sections, skip any that exist) |
| Create or modify | `.claude/settings.json` (register Stop hook if not already registered) |
| Modify (if exists) | `AGENTS.md` (register memory-write if not already listed) |
| Modify (if exists) | `context/learnings.md` (add ## memory-write if missing) |
| Modify (if exists) | `~/.claude/hooks/pre-tool-memory.py` (add in-repo check if missing) |
| Modify (if exists) | `.claude/skills/meta-wrap-up/SKILL.md` (add step 3g if missing) |
| Modify | `.gitignore` (add entries if not already listed) |
| Create (if cron dir exists) | `cron/jobs/daily-memory-distill.md` |
| Create (if cron dir exists) | `cron/jobs/nightly-memsearch-index.md` |
| Create (if cron dir exists) | `cron/jobs/weekly-memory-curator.md` |
| Modify (if exists) | `cron/jobs/weekly-activity-digest.md` (activate if inactive) |
| Install (if missing) | `pip install memsearch` |

**Total: ~30 minutes. Adapts to your project â€” creates what's missing, integrates with what exists, consolidates conflicting memory instructions into one system.**

