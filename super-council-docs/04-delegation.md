# Delegation & Active Recall

> Delegation flow with active recall injection, worktree isolation, recall-then-validate, and side-effect rollback.

> **NOTE:** For reviews, use `/v1/council/pipeline` as the primary path. The pipeline's `AGENT_VALIDATE` phase auto-dispatches to the appropriate reviewer with full state machine context management. Direct delegation (`/v1/council/delegate`) is for one-shot tasks outside the pipeline.

## Delegation Flow

```
1. Validate target alias exists in registry
2. Guard: 409 if concurrent delegation, 503 if _system_error
3. Save current slot (chair) BEFORE any swap
4. Truncate task to fit target model's context
5. Active recall: query memsearch for past solutions
6. Recall-then-validate: run tests on recalled code (if test_command provided)
7. ContextRouter: find similar runs for supplementary context
8. Create per-task git worktree (if use_worktree=True)
9. Swap to target model
10. Build system prompt (reviewer prompt with tool policy)
11. Gemma-specific: auto-scope task with anti-hallucination rules
12. Multi-turn tool-use loop (context budget controlled)
13. Swap back to original model (try/finally)
14. Rollback worktree side-effects (created files)
15. Remove worktree
16. Return reviewer response
```

## Active Recall

### Pre-Dispatch Query

```python
recall_query = f"past solutions pitfalls for {task[:200]}"
recalled = self._active_recall(recall_query, phase=phase)
```

Routing: `SlotSupervisor._active_recall()` → `memory_service.indexer.search()` → MemIndex

- MemIndex handles MemSearch lifecycle, config, async execution, graceful degradation
- SlotSupervisor owns domain logic: shell-injection guard, phase filtering, formatting
- Token budget enforced (default 512 tokens = ~2048 chars)
- Shell metacharacter sanitization (rejects `$(`, `` ` ``, `eval(`, `;rm`, `&&rm`)

**Dependency isolation:** `super_council.py` has no direct MemSearch import.
All vector search routes through `memory_service.indexer` (single source of truth).

### Recall-Then-Validate

```python
if test_command:
    wt = self._create_worktree(task_id, repo_path)
    if wt:
        validation = self._recall_then_validate(recalled, test_command, wt)
        if not validation["valid"]:
            # Test now passes → solution stale → drop recall
            recalled = "[RECALL NOTE: Previous solution found but test now passes...]"
```

**Purpose:** Prevents injecting stale solutions that no longer apply.

### ContextRouter Supplementary Context

```python
similar = self.context_router.find_similar_runs(
    query=task[:200],
    project_id=project_id,
    limit=3,
)
```

- Finds similar past runs by task text overlap
- Appends to recalled context as `SIMILAR RUNS:` section

## Per-Task Worktree

### Creation

```python
worktree_path = self._create_worktree(task_id, repo_path)
```

- Creates git worktree at `~/.council-memory/worktrees/{task_id}/`
- Isolated filesystem for subagent changes
- Automatic cleanup on delegation completion

### Side-Effect Rollback

```python
self._rollback_worktree_side_effects(worktree_path, created_files)
```

- Removes files created during delegation (tracked via tool call parsing)
- Preserves git-tracked changes
- Returns `{rolled_back: [...], errors: [...]}`

### Cleanup

```python
self._remove_worktree(worktree_path, repo_path)
```

- Removes worktree directory
- Cleans up git worktree registration

## Multi-Turn Tool-Use Loop

### Context Budget Control

```python
pre_send_threshold = int(ctx_limit * 0.80)  # 80% of context limit
if cumulative_tokens > pre_send_threshold:
    break  # Force final answer
```

- No hard round limit — controlled by context budget
- Pre-send check at 80% threshold (leaves 20% for completion)
- Per-message size diagnostics logged each round

### Tool Filtering

- **Default tools:** `read`, `grep`, `find`, `bash_ro`, `list_dir`, `web_search`
- **Extended tools:** `write`, `delegate_to`, `search_codebase` (when explicitly passed)
- **Filtering:** `_filter_tool_calls()` whitelist enforcement

### Nested Delegation

- `delegate_to` tool allows delegated model to delegate to another model
- 60s timeout for nested delegation
- Context budget tracked across rounds

## Reviewer System Prompts

### Base Prompt

```
You are a reviewer. Tools are available but not mandatory.
Use tools if you need to examine files. Otherwise analyze directly.
```

### Gemma-Specific Enhancements

- Anti-hallucination rules: review ONLY specified lines/files
- "Not visible in this range" instead of inferring
- Channel tag suppression: forbid `<|channel|>` markers
- Auto-scoped task: `_scope_delegation_task()` detects file/line patterns

### Non-Gemma Reviewers

Base prompt without anti-hallucination rules.

## Swap-Back Recovery

```
1. try/finally guarantees swap-back
2. If swap-back fails once → retry one more time
3. If swap-back fails twice → set _system_error + start auto-recovery thread
4. Auto-recovery: 30s interval, 5 attempts max, loads default_alias
```

## Payload Format

```json
{
  "alias": "reviewer-logic",
  "task": "Review the code for issues.",
  "timeout": 300,
  "phase": "build",
  "pipeline_id": "pipe-abc123",
  "project_id": "my-project",
  "repo_path": "/path/to/repo",
  "test_command": "pytest tests/ -v",
  "use_worktree": true,
  "tools": [...]  // optional, defaults to read-only set
}
```

## Response Format

```json
{
  "alias": "reviewer-logic",
  "status": "ok",
  "response": "Reviewer's analysis...",
  "blocked_tool_calls": [...],  // if any tools were filtered
  "worktree_path": "...",       // if worktree was used
  "rollback": {...}             // if side-effects were rolled back
}
```
