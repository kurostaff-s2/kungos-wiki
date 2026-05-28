# arc_summarizer — Open Gaps (2026-05-28)

> **MIGRATION COMPLETE (2026-05-28):** Arc summarizer is now canonical.
> - Old consolidation methods stripped from `super_council.py` (597 lines removed)
> - `self._arc.consolidate()` is the active path
> - Health gate added before consolidation thread
> - `self.store` → `self.relational_store` wiring bug fixed
> - `last_output_path` property added for memsearch indexing
> See [arc-summarizer-status.md](./arc-summarizer-status.md) for full audit.
>
> **Server status:** ✅ RUNNING — PID 78875, granite-4.1-3b on 127.0.0.1:18095

## P0: Race condition — HTTP server starts before Tier 1 is ready

**Problem:** `serve_forever()` launches consolidation thread, then immediately starts HTTP server. First N requests arrive before `_tier1_knowledge_card` is populated → zero Tier 1 injection.

**Fix:** Add `threading.Event` gate in serve_forever():
```python
self._tier1_ready = threading.Event()
# ... in _run_startup_consolidation():
self._tier1_ready.set()
# ... in serve_forever():
self._tier1_ready.wait(timeout=30)  # wait up to 30s for Tier 1
```

**Risk:** Low — fallback consolidation still works, just delayed.

---

## P1: ~~DUAL SYSTEM — old methods active, Arc module dormant~~ ✅ FIXED

> **RESOLVED:** Old methods stripped, Arc is now canonical. `self._arc.consolidate()` is the active path.

**Problem:** ~700 lines of old consolidation methods in `super_council.py` are **actively called**
from `_run_startup_consolidation()` (line 8800, thread target at line 9636). Meanwhile,
`self._arc` (ArcSummarizer) is loaded at line 9590 but **never used for consolidation**.

The old methods are NOT dead code — they are the current execution path. The new `arc_summarizer`
module is the intended canonical path but is not wired in.

**Active old methods (all called from `_run_startup_consolidation`):**
- `_do_startup_consolidation()` — gathers input, builds prompt, calls model, parses output
- `_build_consolidation_prompt()` — builds system+user prompt
- `_call_consolidation_model()` — HTTP call with retry
- `_parse_consolidation_output()` / `_parse_yaml_fallback()` — YAML parsing
- `_render_consolidation_yaml()` — markdown rendering
- `_write_consolidation_to_cache()` — DB write
- `_activate_latest_consolidation()` — exit probation
- `_inject_tier1_startup_context()` — Tier 1 knowledge card

**Truly dead old methods (no callers):**
- `_call_session_summarizer()` — should delegate to `self._arc.summarize_session()`
- `_call_knowledge_extraction()` — should delegate to `self._arc.extract_knowledge()`
- `_call_summarizer()` — legacy alias

**Fix:** Replace thread target with `self._arc.start_consolidation_thread()`,
strip old methods, keep `_inject_tier1_into_payload()` (used by handler).

**Files:** `super_council/super_council.py` lines ~8800–9500

---

## P2: systemd port conflict — manual server holds 18095

**Problem:** Manual llama-server test instance holds port 18095. systemd service can't bind → fails with exit-code 1.

**Fix:** Stop manual server before starting systemd service. Or change port in `arc_summarizer/start.sh` and `config-subsystem.json` to avoid conflicts.

---

## P3: ~~No health gate before consolidation thread~~ ✅ FIXED

> **RESOLVED:** Health gate added — `self._arc.health_check()` called before launching thread.
> Skips consolidation with warning if Arc server is unhealthy.

---

## P4: systemd service — ExecStartPre group error (cosmetic)

**Problem:** `ExecStartPre=/bin/bash -c 'source /opt/intel/oneapi/setvars.sh'` fails with "Failed to determine supplementary groups: Operation not permitted" in user-level systemd.

**Status:** Worked around by moving oneAPI sourcing into `start.sh` script.

**Fix:** Remove `ExecStartPre` line from `~/.config/systemd/user/arc-summarizer.service`.

---

## P5: Journal retention — user-level journald config may not apply

**Problem:** `~/.config/systemd/journald.conf.d/arc-summarizer.conf` sets 7-day retention, but user-level journald may not honour `MaxRetentionSec` without root.

**Fix:** Verify with `journalctl --user --disk-usage`. If not working, add cleanup cron:
```bash
# ~/.cron.d/arc-summarizer-cleanup
0 3 * * * journalctl --user -u arc-summarizer.service --vacuum-time=7d 2>/dev/null
```

---

## P6: Model file path — hardcoded in start.sh

**Problem:** `start.sh` hardcodes model path to `/home/chief/Coding-Projects/chief-s2s/models/`. If models are reorganized, service breaks.

**Fix:** Read model path from `config-subsystem.json` or use symlink in canonical location (`/home/chief/models/arc/`).

---

## P7: No graceful shutdown handler

**Problem:** systemd sends SIGTERM on stop. llama-server may not save slot state before exiting.

**Fix:** Add `ExecStop=/bin/bash -c 'curl -s http://127.0.0.1:18095/v1/council/supervisor-restart'` or signal handler in start.sh.
