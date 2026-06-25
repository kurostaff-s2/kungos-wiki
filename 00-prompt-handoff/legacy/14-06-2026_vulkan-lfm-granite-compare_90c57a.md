# Vulkan Backend Comparison: LFM2.5-8B vs Granite-4.1-3B

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `90c57a` |
| Entity type | `handoff` |
| Short description | Fresh Vulkan backend quality comparison: LFM2.5-8B Q4_K_XL vs Granite-4.1-3B Q4_K_M on Arc A380 using consolidation v3 daily prompt |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/00-prompt-handoff/vulkan-intel-arc-research.md`, `/home/chief/llm-wiki/00-prompt-handoff/vulkan-a380-execution-plan.md` |
| Generated | `14-06-2026` |
| Next action / owner | Execute test phases sequentially on Arc A380 with no other GPU consumers |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/vulkan-intel-arc-research.md`
**Key files for this task:**
- Vulkan binary: `/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-vulkan/bin/llama-server`
- LFM model: `/home/chief/models/LFM2.5-8B-A1B-UD-Q4_K_XL.gguf` (5.0 GB)
- Granite model: `/home/chief/models/granite-4.1-3b-Q4_K_M.gguf` (2.0 GB)
- Trace file: `/home/chief/.council-memory/canonical-raw-session-data/trace-85a9cdb8.md` (77 KB)
- Prompt builder: `/home/chief/Coding-Projects/7-council/super_council/memory_service/consolidate/prompts.py`
- Historical SYCL baseline: `/home/chief/llm_test_lfm_arc_q4_trace85a.json`

## Goal

Run both LFM2.5-8B and Granite-4.1-3B on the Vulkan backend with the same consolidation v3 daily tier prompt, save outputs, and compare quality, consistency, and speed.

## Pre-Flight Checklist

- [ ] No other processes consuming Arc A380 VRAM (check `ps aux | grep llama-server`)
- [ ] Qwen3.6-27B server on RTX 3090 (port 8091) can stay running — it does NOT use the Arc
- [ ] Any leftover Vulkan/SYCL servers on Arc A380 must be stopped
- [ ] Ports 18100 and 18101 are free (`ss -tlnp | grep -E "1810[0-9]"`)
- [ ] Vulkan binary exists and is executable
- [ ] Both model files exist and are readable

## Phase 1: Build Consolidation V3 Prompt

**What:** Build the daily tier consolidation prompt from the trace file.

**Steps:**
1. Run the prompt builder:
```bash
python3 -c "
import sys
sys.path.insert(0, '/home/chief/Coding-Projects/7-council/super_council')
from memory_service.consolidate.prompts import SYSTEM_CONSOLIDATION, build_tier_consolidation_prompt
trace = open('/home/chief/.council-memory/canonical-raw-session-data/trace-85a9cdb8.md').read()
prompt = build_tier_consolidation_prompt(trace, 'daily')
import json
json.dump({'system': SYSTEM_CONSOLIDATION, 'user': prompt}, open('/tmp/consolidation-prompt-v3.json','w'))
print(f'V3 prompt built: {len(prompt)} chars')
"
```

**Expected output:** `V3 prompt built: 82391 chars` (approximately)
**Artifact:** `/tmp/consolidation-prompt-v3.json`

## Phase 2: LFM2.5-8B Vulkan Test

**What:** Run LFM2.5-8B Q4_K_XL on Vulkan backend with consolidation v3 prompt.

**Steps:**
1. Start the server:
```bash
GGML_VK_VISIBLE_DEVICES=2 /home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-vulkan/bin/llama-server \
    -m /home/chief/models/LFM2.5-8B-A1B-UD-Q4_K_XL.gguf \
    --alias lfm2.5-8b \
    -ngl 99 \
    -c 32768 \
    -t 8 \
    -ctk q8_0 \
    -ctv q8_0 \
    --host 127.0.0.1 \
    --port 18100 \
    --flash-attn on \
    --no-mmap \
    --cont-batching \
    -b 512 \
    -ub 512 \
    -lv 1 \
    > /tmp/lfm-vulkan-server.log 2>&1 &
echo $! > /tmp/lfm-vulkan-pid.txt
```

2. Wait for full load (model loaded + health OK):
```bash
for i in $(seq 1 150); do
    if grep -q "model loaded" /tmp/lfm-vulkan-server.log 2>/dev/null; then
        if curl -s "http://127.0.0.1:18100/health" > /dev/null 2>&1; then
            echo "LFM server fully loaded after ${i}s"
            break
        fi
    fi
    sleep 2
done
# Extra safety margin
sleep 5
```

3. Send the request:
```bash
START=$(date +%s%3N)
curl -s -X POST "http://127.0.0.1:18100/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
prompt = json.load(open('/tmp/consolidation-prompt-v3.json'))
req = {
    'model': 'lfm2.5-8b',
    'messages': [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user']}
    ],
    'max_tokens': 4096,
    'temperature': 0.3,
}
json.dumps(req)
")" \
    -o /tmp/lfm-vulkan-response.json \
    -w "%{http_code}" > /tmp/lfm-vulkan-http-status.txt 2>&1
END=$(date +%s%3N)
ELAPSED=$(( (END - START) ))
echo "LFM request completed in ${ELAPSED}ms ($(( ELAPSED / 1000 ))s)"
echo "HTTP status: $(cat /tmp/lfm-vulkan-http-status.txt)"
```

4. Parse and save results:
```bash
python3 -c "
import json
elapsed_ms = ${ELAPSED}
try:
    resp = json.load(open('/tmp/lfm-vulkan-response.json'))
    if 'error' in resp:
        print(f'ERROR: {resp[\"error\"]}')
        result = {'name': 'lfm-vulkan', 'status': 'error', 'error': str(resp['error'])}
    else:
        usage = resp.get('usage', {})
        tokens = usage.get('completion_tokens', 0)
        ptokens = usage.get('prompt_tokens', 0)
        tps = tokens / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0
        content = resp['choices'][0]['message']['content']
        result = {
            'name': 'lfm-vulkan',
            'time_ms': elapsed_ms,
            'prompt_tokens': ptokens,
            'output_tokens': tokens,
            'tps': round(tps, 2),
            'status': 'ok',
            'content_length': len(content),
            'has_summary': '## Summary' in content,
            'has_decisions': '## Decisions' in content,
            'has_work_completed': '## Work Completed' in content,
            'has_open_items': '## Open Items' in content,
            'has_blockers': '## Blockers' in content,
            'has_carried_forward': '## Carried Forward' in content,
            'has_deviations': '## Deviations' in content,
            'section_count': len([l for l in content.split(chr(10)) if l.startswith('## ')]),
        }
        with open('/tmp/lfm-vulkan-output.txt', 'w') as f:
            f.write(content)
except Exception as e:
    result = {'name': 'lfm-vulkan', 'status': 'error', 'error': str(e)}
    print(f'ERROR: {e}')
json.dump(result, open('/tmp/lfm-vulkan-result.json', 'w'), indent=2)
print(json.dumps(result, indent=2))
"
```

5. Stop the server:
```bash
kill $(cat /tmp/lfm-vulkan-pid.txt) 2>/dev/null || true
sleep 2
```

**Artifacts:**
- `/tmp/lfm-vulkan-server.log` — server startup log
- `/tmp/lfm-vulkan-response.json` — full API response
- `/tmp/lfm-vulkan-output.txt` — raw model output text
- `/tmp/lfm-vulkan-result.json` — parsed metrics

## Phase 3: Granite-4.1-3B Vulkan Test

**What:** Run Granite-4.1-3B Q4_K_M on Vulkan backend with the same consolidation v3 prompt.

**Steps:** Same as Phase 2, but with:
- Model: `/home/chief/models/granite-4.1-3b-Q4_K_M.gguf`
- Alias: `granite-4.1-3b`
- Port: `18101`
- All output files prefixed with `granite-vulkan` instead of `lfm-vulkan`

**Commands:**
```bash
# Start server
GGML_VK_VISIBLE_DEVICES=2 /home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-vulkan/bin/llama-server \
    -m /home/chief/models/granite-4.1-3b-Q4_K_M.gguf \
    --alias granite-4.1-3b \
    -ngl 99 \
    -c 32768 \
    -t 8 \
    -ctk q8_0 \
    -ctv q8_0 \
    --host 127.0.0.1 \
    --port 18101 \
    --flash-attn on \
    --no-mmap \
    --cont-batching \
    -b 512 \
    -ub 512 \
    -lv 1 \
    > /tmp/granite-vulkan-server.log 2>&1 &
echo $! > /tmp/granite-vulkan-pid.txt

# Wait for load
for i in $(seq 1 60); do
    if grep -q "model loaded" /tmp/granite-vulkan-server.log 2>/dev/null; then
        if curl -s "http://127.0.0.1:18101/health" > /dev/null 2>&1; then
            echo "Granite server fully loaded after ${i}s"
            break
        fi
    fi
    sleep 2
done
sleep 5

# Send request
START=$(date +%s%3N)
curl -s -X POST "http://127.0.0.1:18101/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
prompt = json.load(open('/tmp/consolidation-prompt-v3.json'))
req = {
    'model': 'granite-4.1-3b',
    'messages': [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user']}
    ],
    'max_tokens': 4096,
    'temperature': 0.3,
}
json.dumps(req)
")" \
    -o /tmp/granite-vulkan-response.json \
    -w "%{http_code}" > /tmp/granite-vulkan-http-status.txt 2>&1
END=$(date +%s%3N)
ELAPSED=$(( (END - START) ))
echo "Granite request completed in ${ELAPSED}ms ($(( ELAPSED / 1000 ))s)"

# Parse results (same Python as Phase 2, replace 'lfm' with 'granite')
# ... [same parsing script as Phase 2] ...

# Stop server
kill $(cat /tmp/granite-vulkan-pid.txt) 2>/dev/null || true
sleep 2
```

**Artifacts:**
- `/tmp/granite-vulkan-server.log`
- `/tmp/granite-vulkan-response.json`
- `/tmp/granite-vulkan-output.txt`
- `/tmp/granite-vulkan-result.json`

## Phase 4: Compare and Analyze

**What:** Produce side-by-side comparison of both outputs.

**Steps:**
1. Display metrics table:
```bash
python3 -c "
import json
lfm = json.load(open('/tmp/lfm-vulkan-result.json'))
granite = json.load(open('/tmp/granite-vulkan-result.json'))

print(f\"{'Model':<15} {'Time(s)':<10} {'Prompt Tok':<12} {'Output Tok':<12} {'t/s':<8} {'Sections':<10} {'Summary':<8} {'Status'}\")
print('-'*95)
for r in [lfm, granite]:
    t = r.get('time_ms', 0) / 1000.0
    print(f\"{r['name']:<15} {t:<10.2f} {r.get('prompt_tokens',0):<12} {r.get('output_tokens',0):<12} {r.get('tps',0):<8.2f} {r.get('section_count',0):<10} {'YES' if r.get('has_summary') else 'NO':<8} {r['status']}\")
"
```

2. Read and review both output files:
```bash
echo "=== LFM OUTPUT ==="
cat /tmp/lfm-vulkan-output.txt
echo ""
echo "=== GRANITE OUTPUT ==="
cat /tmp/granite-vulkan-output.txt
```

3. Save combined results:
```bash
python3 -c "
import json
lfm = json.load(open('/tmp/lfm-vulkan-result.json'))
granite = json.load(open('/tmp/granite-vulkan-result.json'))
combined = {
    'prompt_source': 'trace-85a9cdb8.md (consolidation v3 daily tier)',
    'backend': 'Vulkan (Mesa ANV)',
    'gpu': 'Intel Arc A380 (6GB VRAM)',
    'kv_cache': 'q8_0/q8_0',
    'context_size': 32768,
    'max_tokens': 4096,
    'temperature': 0.3,
    'lfm': lfm,
    'granite': granite
}
json.dump(combined, open('/tmp/vulkan-compare-final.json', 'w'), indent=2)
print('Saved to /tmp/vulkan-compare-final.json')
"
```

4. Quality analysis checklist:
```
For each model output, evaluate:

STRUCTURE:
- [ ] All 7 sections present (Summary, Decisions, Work Completed, Open Items, Blockers, Carried Forward, Deviations)
- [ ] Summary is 1500-3000+ characters (rich narrative, not brief)
- [ ] Output is Markdown with ## headers (no YAML, no code fences)

CONTENT QUALITY:
- [ ] Summary includes specific file names, function names, error messages
- [ ] Decisions include user_intention field
- [ ] Work Completed items cite specific files/functions
- [ ] No hallucinations (all claims traceable to source material)
- [ ] No fabricated details or invented file paths

CONSISTENCY:
- [ ] Output matches the source material (trace-85a9cdb8.md content)
- [ ] No contradictions within the output
- [ ] Carried Forward items track continuity properly

COMPARE TO HISTORICAL SYCL BASELINE:
- [ ] Compare against /home/chief/llm_test_lfm_arc_q4_trace85a.json (SYCL, 3 runs)
- [ ] Historical SYCL speeds: 5.9 t/s, 13.7 t/s, 13.6 t/s
- [ ] Historical SYCL output: ~2658-3231 tokens, ~4128-5122 chars content
```

## Constraints

- **One model at a time:** Only one model loaded on Arc A380 at a time (6GB VRAM limit)
- **Wait for full load:** Must see "model loaded" in server log AND health endpoint responding before sending request
- **Same prompt:** Both models must receive the exact same prompt (from `/tmp/consolidation-prompt-v3.json`)
- **Same parameters:** Both tests use identical settings (q8_0 KV cache, 32K context, 4096 max tokens, temp 0.3)
- **Kill servers between tests:** Stop LFM server completely before starting Granite server

## Caveats & Uncertainty

- **Previous loading failure:** The Vulkan server failed to load LFM in the earlier test session (empty server log, process died). This may have been due to port conflict or VRAM contention. Verify the server log shows successful startup.
- **Model loading time:** LFM (5GB) takes ~2 minutes to load on Vulkan. Granite (2GB) takes ~30 seconds.
- **Thinking tokens:** LFM2.5 outputs `[Start thinking]` / `[End thinking]` markers. The thinking content is included in the output but shouldn't count toward structured output quality.
- **Section schema:** The daily tier prompt expects 7 sections. Granite may produce fewer sections if it doesn't follow instructions as well.

## Success Criteria

- [ ] Both servers start and load models successfully on Vulkan
- [ ] Both models produce valid JSON responses (no errors)
- [ ] Both outputs saved to `/tmp/{model}-vulkan-output.txt`
- [ ] Both outputs parsed with metrics in `/tmp/{model}-vulkan-result.json`
- [ ] Combined results saved to `/tmp/vulkan-compare-final.json`
- [ ] Quality analysis completed for both outputs
- [ ] Comparison against historical SYCL baseline documented

## Expected Timeline

- Phase 1: 30 seconds (prompt building)
- Phase 2: ~3 minutes (LFM load ~2min + request ~1min)
- Phase 3: ~2 minutes (Granite load ~30s + request ~1min)
- Phase 4: ~5 minutes (analysis)
- **Total: ~10-12 minutes**
