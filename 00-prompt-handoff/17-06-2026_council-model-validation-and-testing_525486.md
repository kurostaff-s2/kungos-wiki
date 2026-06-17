# Council Model Validation & Testing — Mellum2 Scout + Nex-N2-Mini Coder

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `525486` |
| Entity type | `handoff` |
| Short description | Validate chat template compatibility for mellum2-12b and nex-n2-mini, test council pipeline with chair gate via actual coding task, measure and fix nex-n2-mini code output quality |
| Status | `draft` |
| Source references | This handoff document |
| Generated | `17-06-2026` |
| Next action / owner | Execute Phase 1 (chat template validation) — any builder agent |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**

| File | Purpose |
|------|---------|
| `/home/chief/llama-swap/config.yaml` | Model server routing, binary groups, model commands |
| `/home/chief/Coding-Projects/7-council/super_council/upstream-config.json` | Council model registry (running process reads this) |
| `/home/chief/Coding-Projects/7-council/super_council/roles.json` | Council role → model alias resolution |
| `/home/chief/Coding-Projects/7-council/super_council/config-subsystem.json` | Subsystem settings (default_alias, roles) |
| `/home/chief/Coding-Projects/7-council/llama-forks/indras-mirror-fork/` | **TO BE DEACTIVATED** — does not support mellum architecture |
| `/home/chief/llama-cpp-latest/` | **ACTIVE binary** — upstream llama.cpp (ggml-org, commit d73cd07), supports mellum |
| `/home/chief/models/Mellum2-12B-A2.5B-Thinking-Q5_K_L.gguf` | Mellum2 scout model (9.4 GB, mellum architecture) |
| `/home/chief/models/nex-agi_Nex-N2-mini-Q4_K_L.gguf` | Nex-N2- Mini coder model (21.7 GB, qwen3_5_moe architecture) |

**Reference URLs:**

- https://huggingface.co/nex-agi/Nex-N2-mini — base model (Qwen3.5 MoE, multimodal)
- https://huggingface.co/prefeitura-rio/Rio-3.5-Open-397B — Rio-3.5 (same arch family, may have fixed chat template)
- https://huggingface.co/bartowski/prefeitura-rio_Rio-3.5-Open-397B-GGUF — Rio-3.5 GGUF (bartowski quant)
- https://huggingface.co/bartowski/nex-agi_Nex-N2-mini-GGUF — Nex-N2- Mini GGUF (bartowski, multimodal)
- https://huggingface.co/sjakek/Nex-N2-mini-GGUF — Nex-N2- Mini GGUF (sjakek, text-only UD variants)

**Related codebases:** `/home/chief/.pi/agent/extensions/council-tools/index.ts` (delegation recording hooks)

---

## Background

Two new models were registered in council roles on 17-06-2026:

| Role | Model | Architecture | Status |
|------|-------|-------------|--------|
| **scout** | `mellum2-12b` | `mellum` (MoE 12B/2.5B active) | NOT TESTED — architecture unsupported by indras-mirror-fork |
| **coder** | `nex-n2-mini` | `qwen3_5_moe` (MoE, multimodal base) | NOT TESTED — chat template may be broken for text-only |
| **builder** | `nex-n2-mini` | same as coder | NOT TESTED |
| **co-chair** | `qwen-160k-UD-fast` | `llama` (MTP) | WORKING — current chair |

**Critical pre-existing issues:**

1. **indras-mirror-fork does NOT support `mellum` architecture** — `llama_model_load: error loading model: unknown model architecture: 'mellum'`. The upstream `llama-cpp-latest` (ggml-org) DOES support it (confirmed in `src/llama-arch.cpp:139`).
2. **Nex-N2-mini is a multimodal model** (Qwen3.5 MoE with vision) — the GGUF chat template may include image/video rendering macros that break text-only chat completion. Rio-3.5 (same arch family) has a known multimodal chat template with `render_content` macros.
3. **VRAM constraint** — RTX 3090 (24GB). Council chair (qwen-160k-UD-fast) uses ~22GB. Mellum2 needs ~9GB, Nex-N2-mini needs ~21GB. Both require council to be stopped or swapped for testing.
4. **llama-swap macro** — `${llama}` resolves to `/home/chief/llama-cpp-latest/build/bin/llama-server`. This is the correct binary for both models.

---

## Execution Order

```
Phase 1 (chat templates) → Phase 2 (council pipeline test) → Phase 3 (quality measurement)
```

All phases are **sequential** — each depends on the previous passing. No parallel execution.

---

## Caveats & Uncertainty

- **VRAM availability:** Testing requires stopping council_main.py (PID varies) or unloading the current model via llama-swap. The executing agent must manage this.
- **Chat template source:** The GGUF files embed tokenizer metadata. The `--jinja` flag in llama-server commands uses the embedded template. If the embedded template is broken, we may need to override with `--chat-template` or patch the GGUF.
- **Rio-3.5 relevance:** Rio-3.5 shares the Qwen3.5 MoE architecture family with Nex-N2-mini. Its chat template (from HuggingFace) may serve as a reference for fixing Nex-N2-mini's template. The GGUF repos (bartowski) may have fixed templates embedded.
- **Mellum tokenizer:** Uses `mellum2` preprocessing type (confirmed in llama.cpp source). May need `--tokenizer-pre-type mellum2` if auto-detection fails.
- **No simulations:** All tests must be real — actual model loads, actual chat completions, actual code generation. No mock responses.

---

### Phase 1: Chat Template Compatibility — Mellum2 + Nex-N2-Mini

**What:** Load both models individually via llama-cpp-latest, verify chat completion works with standard OpenAI-format requests, identify and fix any chat template issues.

**Files:** No files to modify (read-only investigation + potential llama-swap config updates).

**Dependencies:** None (Phase 1 is first).

**Steps:**

1. **Stop council_main.py** to free VRAM:
   ```bash
   # Find and stop council
   pgrep -f council_main.py | xargs kill -TERM
   # Wait for VRAM to free
   sleep 5
   nvidia-smi --query-gpu=memory.free --format=csv,noheader
   ```

2. **Test Mellum2-12B (scout) — basic load + chat:**
   ```bash
   /home/chief/llama-cpp-latest/build/bin/llama-server \
       -m /home/chief/models/Mellum2-12B-A2.5B-Thinking-Q5_K_L.gguf \
       --alias mellum2-12b --port 19998 --host 127.0.0.1 \
       -ngl 99 --ctx-size 32768 \
       --flash-attn on --no-mmap --mlock \
       --threads 16 --threads-batch 16 \
       -ctk q4_0 -ctv q4_0 \
       --temp 0.5 --top-p 0.95 --top-k 40 \
       --jinja \
       2>&1 | tee /tmp/mellum2-load.log &
   sleep 30  # wait for model to load
   ```
   
   **Chat test:**
   ```bash
   curl -s http://127.0.0.1:19998/v1/chat/completions \
       -H "Content-Type: application/json" \
       -d '{
         "model": "mellum2-12b",
         "messages": [
           {"role": "system", "content": "You are a helpful scout agent. Be concise."},
           {"role": "user", "content": "What is the capital of France? Answer in one word."}
         ],
         "max_tokens": 20,
         "temperature": 0.5
       }' | python3 -m json.tool
   ```
   
   **Expected:** Model loads, returns "Paris" or similar. No template errors.
   
   **If fails:** Capture full stderr from `/tmp/mellum2-load.log`. Check for:
   - `unknown model architecture` → wrong binary (must use llama-cpp-latest)
   - `chat template error` / `jinja error` → template issue, proceed to step 4
   - `out of memory` → reduce `-ngl` or `--ctx-size`

3. **Test Nex-N2-Mini (coder) — basic load + chat:**
   ```bash
   # Kill mellum2 first
   pkill -f "mellum2-12b"
   sleep 3
   
   /home/chief/llama-cpp-latest/build/bin/llama-server \
       -m /home/chief/models/nex-agi_Nex-N2-mini-Q4_K_L.gguf \
       --alias nex-n2-mini --port 19999 --host 127.0.0.1 \
       -ngl 99 --ctx-size 32768 \
       --flash-attn on --no-mmap --mlock \
       --cont-batching -b 512 -ub 512 \
       --threads 16 --threads-batch 16 \
       -ctk q8_0 -ctv q8_0 \
       --temp 0.7 --top-p 0.95 --top-k 40 \
       --reasoning on --reasoning-format deepseek --reasoning-budget 8192 \
       --jinja \
       2>&1 | tee /tmp/nex-n2-load.log &
   sleep 45  # 21GB model, slower load
   ```
   
   **Chat test (text-only):**
   ```bash
   curl -s http://127.0.0.1:19999/v1/chat/completions \
       -H "Content-Type: application/json" \
       -d '{
         "model": "nex-n2-mini",
         "messages": [
           {"role": "system", "content": "You are a coding assistant. Write clean, correct code."},
           {"role": "user", "content": "Write a Python function that reverses a string. One line."}
         ],
         "max_tokens": 100,
         "temperature": 0.7
       }' | python3 -m json.tool
   ```
   
   **Expected:** Model loads, returns correct Python code. No template errors.
   
   **If chat template is broken** (e.g., outputs image tokens, jinja errors, or garbled text):
   - The GGUF embeds a multimodal template (Qwen3.5 MoE with vision)
   - **Fix option A:** Try `--chat-template default` or `--chat-template chatml` to override
   - **Fix option B:** Download Rio-3.5's chat template from HuggingFace and use `--chat-template-file /path/to/template.jinja2`
   - **Fix option C:** Check if bartowski's GGUF has a fixed template (download `nex-agi_Nex-N2-mini-Q4_K_L.gguf` from bartowski and compare)

4. **Multi-turn conversation test (both models):**
   ```bash
   # Test multi-turn to verify template handles role switching
   curl -s http://127.0.0.1:19999/v1/chat/completions \
       -H "Content-Type: application/json" \
       -d '{
         "model": "nex-n2-mini",
         "messages": [
           {"role": "user", "content": "What is 2+2?"},
           {"role": "assistant", "content": "4"},
           {"role": "user", "content": "What is 2+3?"}
         ],
         "max_tokens": 20
       }' | python3 -m json.tool
   ```
   
   **Expected:** Returns "5" — not a repeat of "4" or garbled output.

5. **Tool call test (nex-n2-mini only):**
   ```bash
   curl -s http://127.0.0.1:19999/v1/chat/completions \
       -H "Content-Type: application/json" \
       -d '{
         "model": "nex-n2-mini",
         "messages": [
           {"role": "user", "content": "What is the weather in Tokyo?"}
         ],
         "tools": [
           {
             "type": "function",
             "function": {
               "name": "get_weather",
               "description": "Get weather for a city",
               "parameters": {
                 "type": "object",
                 "properties": {"city": {"type": "string"}},
                 "required": ["city"]
               }
             }
           }
         ],
         "tool_choice": "required",
         "max_tokens": 100
       }' | python3 -m json.tool
   ```
   
   **Expected:** Returns a tool_call with `get_weather({"city": "Tokyo"})`.

6. **Save results:** Write a summary to `/tmp/phase1-results.md` with:
   - Load success/fail for each model
   - Chat template status (OK / broken + error)
   - Multi-turn status (OK / broken)
   - Tool call status (OK / broken / N/A)
   - Any fixes applied (template override, GGUF swap, etc.)

7. **Cleanup:** Kill test servers, restart council_main.py:
   ```bash
   pkill -f "llama-server.*1999[89]"
   sleep 3
   # Restart council (use existing systemd or manual command)
   cd /home/chief/Coding-Projects/7-council/super_council/
   python3 council_main.py --listen-port 8090 \
       --upstream-config /home/chief/Coding-Projects/7-council/super_council/upstream-config.json &
   ```

**Tests:**
- [ ] Mellum2 loads without architecture error
- [ ] Mellum2 responds to single-turn chat
- [ ] Nex-N2-mini loads without error
- [ ] Nex-N2-mini responds to single-turn chat
- [ ] Nex-N2-mini handles multi-turn conversation (role switching)
- [ ] Nex-N2-mini handles tool calls (if supported)
- [ ] Results saved to `/tmp/phase1-results.md`

---

### Phase 2: Council Pipeline Test with Chair Gate — Actual Coding Task

**What:** Execute a real coding task through the full council pipeline: chair plans → scout (mellum2) researches → coder (nex-n2-mini) implements → chair gate validates RED→GREEN→REFACTOR.

**Files:** Test project files created during execution.

**Dependencies:** Phase 1 complete (chat templates working).

**Pre-Flight Checklist:**
- [ ] Phase 1 results show both models load and respond correctly
- [ ] council_main.py is running on port 8090
- [ ] llama-swap is running on port 9292
- [ ] roles.json has correct mappings (scout→mellum2-12b, coder→nex-n2-mini)

**Steps:**

1. **Verify council is running:**
   ```bash
   curl -s http://127.0.0.1:8090/health | python3 -m json.tool
   curl -s http://127.0.0.1:9292/health | python3 -m json.tool
   ```

2. **Verify role resolution:**
   ```bash
   # Check that roles resolve correctly
   python3 -c "
   import json
   roles = json.load(open('/home/chief/Coding-Projects/7-council/super_council/roles.json'))
   print('scout:', roles['scout']['primary'])
   print('coder:', roles['coder']['primary'])
   print('builder:', roles['builder']['primary'])
   print('co-chair:', roles['co-chair']['primary'])
   "
   ```

3. **Create test project:**
   ```bash
   mkdir -p /tmp/council-test-project
   cd /tmp/council-test-project
   git init
   cat > README.md << 'EOF'
   # Council Pipeline Test
   
   Task: Implement a Python module for parsing and validating CSV files.
   Requirements:
   - Parse CSV with configurable delimiter
   - Validate column types (int, float, str, date)
   - Report errors with row/column location
   - Handle missing values
   EOF
   ```

4. **Execute council pipeline — POST to pipeline endpoint:**
   ```bash
   # Start pipeline
   curl -s -X POST http://127.0.0.1:8090/v1/council/pipeline \
       -H "Content-Type: application/json" \
       -d '{
         "pipeline_id": "test-csv-parser-001",
         "task": "Implement a Python CSV parser module with type validation. Create csv_parser.py with: (1) CSVParser class that reads files with configurable delimiter, (2) validate_types() method that checks int/float/str/date columns, (3) error reporting with row/col location, (4) handle_missing() for null values. Write tests first (RED), then implement (GREEN).",
         "project_id": "council-test"
       }' | python3 -m json.tool
   ```

5. **Monitor pipeline progress:**
   ```bash
   # Check pipeline state
   curl -s http://127.0.0.1:8090/v1/council/pipeline/test-csv-parser-001 | python3 -m json.tool
   ```

6. **Execute chair gate for RED phase:**
   ```bash
   # After scout/coder complete RED phase, validate with chair gate
   curl -s -X POST http://127.0.0.1:8090/v1/council/chair-gate \
       -H "Content-Type: application/json" \
       -d '{
         "task_id": "test-csv-parser-001",
         "phase": "RED",
         "subagent_log": "$(cat /tmp/council-test-project/scout-log.txt 2>/dev/null || echo 'no log')",
         "worktree_path": "/tmp/council-test-project",
         "test_command": "python3 -m pytest tests/ -v 2>&1",
         "expected_outcome": "FAIL"
       }' | python3 -m json.tool
   ```
   
   **Expected:** Chair gate returns `pass: true` for RED phase (tests should FAIL).

7. **Execute chair gate for GREEN phase:**
   ```bash
   curl -s -X POST http://127.0.0.1:8090/v1/council/chair-gate \
       -H "Content-Type: application/json" \
       -d '{
         "task_id": "test-csv-parser-001",
         "phase": "GREEN",
         "subagent_log": "$(cat /tmp/council-test-project/coder-log.txt 2>/dev/null || echo 'no log')",
         "worktree_path": "/tmp/council-test-project",
         "test_command": "python3 -m pytest tests/ -v 2>&1",
         "expected_outcome": "PASS"
       }' | python3 -m json.tool
   ```
   
   **Expected:** Chair gate returns `pass: true` for GREEN phase (tests should PASS).

8. **Verify delegation recording:**
   ```bash
   # Check delegation_runs table
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('/home/chief/.council-memory/council_core.db')
   cursor = conn.cursor()
   cursor.execute(\"SELECT id, role, model_alias, status, created_at FROM delegation_runs ORDER BY created_at DESC LIMIT 10\")
   for row in cursor.fetchall():
       print(row)
   conn.close()
   "
   ```
   
   **Expected:** Entries for `scout` (mellum2-12b) and `coder` (nex-n2-mini) delegations.

9. **Save results:** Write summary to `/tmp/phase2-results.md` with:
   - Pipeline execution success/fail
   - Chair gate outcomes (RED, GREEN)
   - Delegation recording (count, roles, models)
   - Any errors or unexpected behavior

**Tests:**
- [ ] Council pipeline accepts task and creates pipeline state
- [ ] Scout delegation to mellum2-12b completes
- [ ] Coder delegation to nex-n2-mini completes
- [ ] Chair gate RED phase passes (tests fail as expected)
- [ ] Chair gate GREEN phase passes (tests pass)
- [ ] Delegation entries recorded in council_core.db
- [ ] Results saved to `/tmp/phase2-results.md`

---

### Phase 3: Nex-N2-Mini Code Quality Measurement & Fixes

**What:** Systematically measure nex-n2-mini's code output quality across multiple coding tasks, identify deficiencies, and apply fixes (temperature, system prompt, or template adjustments).

**Files:** Quality measurement scripts, potential config updates.

**Dependencies:** Phase 2 complete (pipeline working).

**Steps:**

1. **Define quality benchmarks** — create a test harness:
   ```bash
   mkdir -p /tmp/nex-quality-tests
   cat > /tmp/nex-quality-tests/benchmarks.json << 'BENCHEOF'
   {
     "tasks": [
       {
         "id": "reverse-string",
         "prompt": "Write a Python function reverse_string(s: str) -> str that reverses a string. Include type hints and docstring.",
         "expected": "def reverse_string(s: str) -> str:",
         "checks": ["has_type_hints", "has_docstring", "correct_signature", "handles_empty_string"]
       },
       {
         "id": "binary-search",
         "prompt": "Write a Python function binary_search(arr: list, target) -> int that returns the index of target or -1. Handle edge cases.",
         "expected": "def binary_search(arr: list, target) -> int:",
         "checks": ["O(log_n)_complexity", "handles_empty_list", "handles_single_element", "returns_negative_not_found"]
       },
       {
         "id": "csv-parser-class",
         "prompt": "Write a Python class CSVParser with __init__(filepath, delimiter=','), read() -> list[dict], and validate_types(schema: dict) -> list[Error].",
         "expected": "class CSVParser:",
         "checks": ["class_definition", "init_method", "read_method", "validate_method", "error_handling"]
       },
       {
         "id": "async-http-client",
         "prompt": "Write an async Python HTTP client using aiohttp with get(url) and post(url, json_data) methods. Include timeout and retry logic.",
         "expected": "import aiohttp",
         "checks": ["async_syntax", "timeout_handling", "retry_logic", "error_handling", "session_management"]
       },
       {
         "id": "sql-injection-safe",
         "prompt": "Write a Python function query_user(db: sqlite3.Connection, user_id: int) that safely queries a users table. Use parameterized queries.",
         "expected": "cursor.execute(",
         "checks": ["parameterized_query", "no_string_formatting", "returns_result", "closes_cursor"]
       }
     ]
   }
   BENCHEOF
   ```

2. **Run benchmarks against nex-n2-mini** — use direct chat completion (bypass council for speed):
   ```bash
   # Load nex-n2-mini on test port (stop council first if needed)
   # Then run each benchmark:
   for task_id in reverse-string binary-search csv-parser-class async-http-client sql-injection-safe; do
       prompt=$(python3 -c "
       import json
       benchmarks = json.load(open('/tmp/nex-quality-tests/benchmarks.json'))
       for t in benchmarks['tasks']:
           if t['id'] == '$task_id':
               print(t['prompt'])
       ")
       
       echo "=== Benchmark: $task_id ==="
       curl -s http://127.0.0.1:19999/v1/chat/completions \
           -H "Content-Type: application/json" \
           -d "{
             \"model\": \"nex-n2-mini\",
             \"messages\": [
               {\"role\": \"system\", \"content\": \"You are an expert Python developer. Write clean, production-ready code with type hints, docstrings, and error handling. Output ONLY the code, no explanation.\"},
               {\"role\": \"user\", \"content\": \"$prompt\"}
             ],
             \"max_tokens\": 1024,
             \"temperature\": 0.7
           }" | python3 -c "
           import sys, json
           resp = json.load(sys.stdin)
           content = resp['choices'][0]['message']['content']
           print(content)
           # Save output
           with open('/tmp/nex-quality-tests/output-$task_id.py', 'w') as f:
               f.write(content)
           " 2>&1
   done
   ```

3. **Evaluate each output** — automated + manual checks:
   ```bash
   # Automated syntax check
   for f in /tmp/nex-quality-tests/output-*.py; do
       echo "=== Syntax check: $(basename $f) ==="
       python3 -c "compile(open('$f').read(), '$f', 'exec')" 2>&1 && echo "PASS" || echo "FAIL: syntax error"
   done
   
   # Automated import check
   for f in /tmp/nex-quality-tests/output-*.py; do
       echo "=== Import check: $(basename $f) ==="
       python3 -c "import importlib.util; importlib.util.spec_from_file_location('test', '$f')" 2>&1 && echo "PASS" || echo "FAIL: import error"
   done
   ```

4. **Score each benchmark** — produce quality report:
   ```bash
   cat > /tmp/nex-quality-tests/quality-report.md << 'REPORTEOF'
   # Nex-N2-Mini Code Quality Report
   
   ## Scoring Criteria
   - **Syntax:** Valid Python (compile check) — pass/fail
   - **Correctness:** Logic matches expected behavior — 0-5 scale
   - **Completeness:** All requested features present — 0-5 scale
   - **Style:** Type hints, docstrings, error handling — 0-5 scale
   - **Security:** No obvious vulnerabilities (SQL injection, etc.) — pass/fail
   
   ## Results
   | Task | Syntax | Correctness | Completeness | Style | Security | Notes |
   |------|--------|-------------|--------------|-------|----------|-------|
   | reverse-string | | | | | | |
   | binary-search | | | | | | |
   | csv-parser-class | | | | | | |
   | async-http-client | | | | | | |
   | sql-injection-safe | | | | | | |
   
   ## Deficiencies Found
   (list specific issues)
   
   ## Recommended Fixes
   (list config/prompt adjustments)
   REPORTEOF
   ```

5. **Apply fixes if deficiencies found:**
   
   **Common fixes and their config changes:**
   
   | Deficiency | Fix | Config Change |
   |------------|-----|---------------|
   | Too verbose (explanation instead of code) | Stronger system prompt | Update `template_kwargs` in upstream-config.json |
   | Missing type hints | Add to system prompt | Same as above |
   | Hallucinated imports | Lower temperature | `temp: 0.7` → `temp: 0.3` in upstream-config.json |
   | Incomplete implementations | Higher max_tokens | `max_tokens: 1024` → `max_tokens: 4096` |
   | Poor error handling | Add to system prompt | Include "always include try/except" in prompt |
   | Chat template garbling | Override template | Add `--chat-template chatml` to llama-swap cmd |

6. **Update upstream-config.json if fixes needed:**
   ```bash
   # Example: adjust temperature for coding tasks
   python3 -c "
   import json
   u = json.load(open('/home/chief/Coding-Projects/7-council/super_council/upstream-config.json'))
   # Find nex-n2-mini and adjust
   for uid, up in u.get('inference-upstream', {}).items():
       if 'nex-n2-mini' in up.get('models', {}):
           m = up['models']['nex-n2-mini']
           # Example fix: lower temperature for code quality
           m['temp'] = 0.3  # was 0.7
           print(f'Updated {uid}/nex-n2-mini temp to {m[\"temp\"]}')
   json.dump(u, open('/home/chief/Coding-Projects/7-council/super_council/upstream-config.json', 'w'), indent=2)
   "
   ```

7. **Re-test with fixed config** — run benchmarks again with adjusted parameters.

8. **Save final results:** Write to `/tmp/phase3-results.md` with:
   - Quality scores per benchmark
   - Deficiencies identified
   - Fixes applied (with before/after config)
   - Re-test results (if fixes were applied)
   - Final recommendation: ready for production / needs more tuning

**Tests:**
- [ ] All 5 benchmarks executed
- [ ] All outputs pass syntax check
- [ ] Quality report completed with scores
- [ ] Deficiencies documented with evidence
- [ ] Fixes applied and re-tested (if needed)
- [ ] Results saved to `/tmp/phase3-results.md`

---

### Phase 4: Deactivate indras-mirror-fork + Production Wiring

**What:** Make indras-mirror-fork inactive in all configurations, verify llama-cpp-latest is the active binary for all models, restart services.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `/home/chief/llama-swap/config.yaml` | Remove `binary_group: llama-flash` references, ensure all models use `${llama}` macro |
| Modify | `/home/chief/Coding-Projects/7-council/super_council/upstream-config.json` | Remove `llama-flash` upstream section or mark inactive |
| Modify | `/home/chief/Coding-Projects/7-council/llama-forks/indras-mirror-fork/super-council-config/config.json` | Mark as inactive (add `"_inactive": true` at top level) |

**Dependencies:** Phases 1-3 complete.

**Steps:**

1. **Update llama-swap config** — ensure no models reference indras-mirror-fork binary:
   ```bash
   # Check current binary_group assignments
   grep "binary_group" /home/chief/llama-swap/config.yaml
   # All should use llama-cpp-latest via ${llama} macro
   # Remove or change binary_group: llama-flash references
   ```

2. **Update upstream-config.json** — remove or mark `llama-flash` upstream as inactive:
   ```bash
   python3 -c "
   import json
   u = json.load(open('/home/chief/Coding-Projects/7-council/super_council/upstream-config.json'))
   # Move llama-flash models to llama-turbo or mark inactive
   flash_models = u.get('inference-upstream', {}).get('llama-flash', {})
   if flash_models:
       print(f'Found {len(flash_models.get(\"models\", {}))} models in llama-flash upstream')
       for alias in flash_models.get('models', {}):
           print(f'  {alias}')
   "
   ```

3. **Restart services:**
   ```bash
   # Restart llama-swap
   systemctl restart llama-swap 2>/dev/null || true
   
   # Restart council
   pgrep -f council_main.py | xargs kill -TERM
   sleep 3
   cd /home/chief/Coding-Projects/7-council/super_council/
   python3 council_main.py --listen-port 8090 \
       --upstream-config /home/chief/Coding-Projects/7-council/super_council/upstream-config.json &
   ```

4. **Verify all models load correctly:**
   ```bash
   # Check each model via llama-swap
   for model in mellum2-12b nex-n2-mini qwen-160k-UD-fast; do
       echo "=== Testing: $model ==="
       curl -s http://127.0.0.1:9292/upstream/$model/ 2>&1 | head -5
       sleep 5
   done
   ```

**Post-Wiring Tests (GATE):**
- [ ] indras-mirror-fork binary is not referenced in any active config
- [ ] llama-cpp-latest is the active binary for all models
- [ ] Mellum2-12B loads via llama-swap
- [ ] Nex-N2-mini loads via llama-swap
- [ ] Council pipeline executes with new models
- [ ] Delegation recording works for both new models
- [ ] All existing models still work (no regression)

---

### Constraints

- **No simulations:** Every test must use actual model inference. No mock responses, no stubbed data.
- **VRAM management:** Only one large model can be loaded at a time. Stop council before loading test models.
- **Binary requirement:** Must use `/home/chief/llama-cpp-latest/build/bin/llama-server` for both mellum2 and nex-n2-mini. indras-mirror-fork binaries are incompatible.
- **Chat template:** If the embedded GGUF template is broken, override with `--chat-template` flag — do NOT modify the GGUF file.
- **Chair gate:** Must use the actual `/v1/council/chair-gate` endpoint with real test output.
- **Quality scoring:** Must be evidence-based. Every deficiency must include the actual output that demonstrates it.

### Success Criteria

- [ ] Mellum2-12B loads and responds to chat completion (Phase 1)
- [ ] Nex-N2-mini loads and responds to chat completion (Phase 1)
- [ ] Chat templates work for single-turn, multi-turn, and tool calls (Phase 1)
- [ ] Council pipeline executes full RED→GREEN cycle with new models (Phase 2)
- [ ] Chair gate validates both phases correctly (Phase 2)
- [ ] Delegation entries recorded in council_core.db for both models (Phase 2)
- [ ] Nex-N2-mini code quality scored across 5 benchmarks (Phase 3)
- [ ] Deficiencies documented with evidence and fixes applied (Phase 3)
- [ ] indras-mirror-fork deactivated in all configs (Phase 4)
- [ ] All models load via llama-cpp-latest binary (Phase 4)
- [ ] No regression in existing model functionality (Phase 4)
