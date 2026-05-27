#!/usr/bin/env python3
"""slot-supervisor.py — llama-server wrapper for persistent slot state management.

Merged design:
  - Proxy architecture (OP): stable frontend port, upstream llama-server on separate port.
    Clients never see swap churn. Upstream restarts on --upstream-port, frontend stays on --listen-port.
  - Per-model slot namespace (ours): <alias>/<config_hash>/ prevents cross-model KV corruption.
  - Binary hash tracker (ours): purges all slots on llama-server binary change.
  - Slot metadata + retries (OP): .json sidecar validates model signature before restore.
  - Frozen ModelConfig (ours): immutable runtime config, SHA-256 hash for namespace isolation.

CRITICAL CONSTRAINT: KV cache is model-specific. Slot bins are stored in per-model,
per-config namespaces. Cross-model KV restoration is impossible by design.

Slot directory layout:
  /home/chief/tmp/llama-slots/
  ├── chair/
  │   └── <config_hash>/
  │       ├── slot-0.bin
  │       ├── slot-0.bin.checkpoints
  │       └── slot-0.json          ← metadata: model_alias, model_signature, timestamp
  ├── builder/
  │   └── <config_hash>/
  │       └── ...
  └── .llama_server_binary_hash

Config hash is computed from: model_path, ctx_size, ngl, ctk, ctv, flash_attention, pipeline.
Any change → invalidation → full prefill.

Pi Agent adaptation:
  - No volatile token normalization (Pi doesn't inject <TS>/<DATE>/<EPOCH>)
  - Single slot (id_slot=0) — all models serialize through one GPU
  - NVMe slot storage with Linux page cache as implicit RAM tier

Usage:
  python3 slot-supervisor.py --listen-port 8080 --upstream-port 8081 \
      --config /home/chief/tmp/llama-swap/config.json \
      --slot-dir /home/chief/tmp/llama-slots

Author: Merged from OP's Reddit post (r/LocalLLM, May 2026) + our safety-critical additions
Date: 2026-05-06
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8080
DEFAULT_UPSTREAM_HOST = "127.0.0.1"
DEFAULT_UPSTREAM_PORT = 8081
DEFAULT_SLOT_DIR = "/home/chief/tmp/llama-slots"
DEFAULT_CONFIG = "/home/chief/tmp/llama-swap/config.json"
DEFAULT_LLAMA_BIN = "/home/chief/Coding-Projects/7-council/llama-cpp-turboquant/build/bin/llama-server"

DEFAULT_TIMEOUT_READ = 5
DEFAULT_TIMEOUT_CHAT = 600
DEFAULT_METRICS_POLL = 5
DEFAULT_POLL_HEALTH = 1
DEFAULT_RESTORE_RETRIES = 2
DEFAULT_RESTORE_BACKOFF = 0.4

# Crash diagnostics
MAX_CRASH_LINES = 50

# Per-alias backoff (seconds)
BACKOFF_MIN = 2.0
BACKOFF_MAX = 30.0
BACKOFF_MULTIPLIER = 1.5
BACKOFF_JITTER = 0.3  # ±30% jitter

CUDA_CLEANUP_DELAY = 2.0  # seconds — initial wait before VRAM polling begins
CUDA_VRAM_POLL_INTERVAL = 0.2  # seconds between nvidia-smi polls
CUDA_VRAM_POLL_TIMEOUT = 30.0  # seconds — max time to wait for VRAM to free
CUDA_VRAM_HEADROOM = 1024  # MiB — minimum free VRAM required before starting new model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("slot-supervisor")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_json_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def http_request(
    method: str,
    url: str,
    *,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT_READ,
) -> Tuple[int, bytes, Dict[str, str]]:
    """Send HTTP request to upstream llama-server.

    Catches connection errors, broken pipes, and decode failures from crashed
    upstream processes — returns (502, error_json, {}) instead of raising.
    """
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, body, hdrs
    except urllib.error.HTTPError as e:
        # Upstream returned an HTTP error (4xx/5xx) — pass status code through
        err_body = e.read() if hasattr(e, 'read') else b""
        log.warning("UPSTREAM HTTP %d [%s %s]: %s", e.code, method, url, err_body[:200])
        return e.code, err_body, {}
    except (urllib.error.URLError, OSError, UnicodeDecodeError, ValueError) as e:
        # Upstream crashed, OOM, broken pipe, or returned garbage
        err_msg = str(e).split("\n")[0]  # first line only
        log.warning("UPSTREAM HTTP ERROR [%s %s]: %s", method, url, err_msg)
        return 502, json.dumps({"error": f"Upstream unavailable: {err_msg}"}).encode("utf-8"), {}


# ─── Council Memory (Tier 1 — structured logging, no model) ──────────────────

class CouncilMemory:
    """Tier 1 structured logging — no model, no swap, instant writes.

    Writes structured markdown table rows to ~/.council-memory/daily/YYYY-MM-DD.md.
    Append-only, thread-safe. Zero latency impact on request path.

    Events logged: chat completions, delegations, model swaps, compactions.
    """

    TABLE_HEADER = (
        "| Time | Event | Model | Detail | Status | Duration |\n"
        "|------|-------|-------|--------|--------|----------|\n"
    )

    def __init__(self, base_dir: str = os.path.expanduser("~/.council-memory")):
        self.base_dir = Path(base_dir)
        self.daily_dir = self.base_dir / "daily"
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_tokens: Dict[str, int] = {}

    def _daily_path(self) -> Path:
        return self.daily_dir / time.strftime("%Y-%m-%d.md")

    def _append(self, line: str) -> None:
        with self._lock:
            path = self._daily_path()
            is_new = not path.exists()
            with path.open("a", encoding="utf-8") as f:
                if is_new:
                    f.write(f"# Council Log — {time.strftime('%Y-%m-%d')}\n\n")
                    f.write(self.TABLE_HEADER)
                f.write(line)

    def log_request(self, *, alias: str, tokens_before: int, tokens_after: int,
                    duration_ms: float, status: int) -> None:
        """Log a chat completion request."""
        ts = time.strftime("%H:%M:%S")
        delta = tokens_after - tokens_before if tokens_before > 0 else tokens_after
        cache = "HIT" if tokens_before > 0 else "COLD"
        self._append(
            f"| {ts} | chat | {alias} | {tokens_before:,}→{tokens_after:,} (+{delta:,}) "
            f"[{cache}] | {status} | {duration_ms:.0f}ms |\n"
        )
        # Compaction detection: token count dropped >30%
        prev = self._last_tokens.get(alias, 0)
        if prev > 0 and tokens_after < prev * 0.7:
            reduction = (1 - tokens_after / prev) * 100
            self._append(
                f"| {ts} | ⚠️ COMPACT | {alias} | {prev:,}→{tokens_after:,} "
                f"(-{reduction:.0f}%) | — | — |\n"
            )
        if tokens_after > 0:
            self._last_tokens[alias] = tokens_after

    def log_delegation(self, *, from_alias: str, to_alias: str, task_len: int,
                       result_status: int, duration_ms: float,
                       swap_back_ok: bool) -> None:
        """Log a delegation event."""
        ts = time.strftime("%H:%M:%S")
        icon = "✅" if swap_back_ok else "❌"
        self._append(
            f"| {ts} | deleg | {from_alias}→{to_alias} | task:{task_len:,}ch "
            f"{icon} | {result_status} | {duration_ms:.0f}ms |\n"
        )

    def log_swap(self, *, alias: str, tokens_restored: int, restore_ms: float,
                 cold_start: bool) -> None:
        """Log a model swap event."""
        ts = time.strftime("%H:%M:%S")
        if cold_start:
            self._append(f"| {ts} | cold-start | {alias} | 0 tokens | — | — |\n")
        else:
            self._append(
                f"| {ts} | restore | {alias} | {tokens_restored:,} tokens "
                f"| HIT | {restore_ms:.0f}ms |\n"
            )

    def log_event(self, event: str, detail: str = "") -> None:
        """Log a generic event (startup, shutdown, error)."""
        ts = time.strftime("%H:%M:%S")
        self._append(f"| {ts} | {event} | — | {detail} | — | — |\n")

    def save_delegation_response(self, *, chain_id: str, role: str,
                                  alias: str, batch: int, retry: int,
                                  content: str, task: str = "") -> str:
        """Save a delegation response to ~/.council-memory/reviews/{chain_id}/.

        Creates one markdown file per delegation call. Chain delegations share
        a folder by chain_id. Standalone delegations get a timestamp folder.

        Returns the saved file path.
        """
        reviews_dir = self.base_dir / "reviews" / chain_id
        reviews_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = f"{role}-{alias}-{batch}-{retry}-{ts}.md"
        path = reviews_dir / fname
        with self._lock:
            with path.open("w", encoding="utf-8") as f:
                f.write(f"# Delegation Response\n\n")
                f.write(f"- **Chain:** `{chain_id}`\n")
                f.write(f"- **Role:** {role}\n")
                f.write(f"- **Alias:** {alias}\n")
                f.write(f"- **Batch:** {batch}\n")
                f.write(f"- **Retry:** {retry}\n")
                f.write(f"- **Time:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"- **Content:** {len(content)} chars\n")
                if task:
                    f.write(f"\n## Task\n\n{task}\n\n")
                f.write(f"## Response\n\n{content}\n")
        return str(path)

    def save_chat_summary(self, *, summary: str, alias: str,
                           message_count: int) -> str:
        """Save a chat session summary to ~/.council-memory/chat-summaries/.

        One markdown file per summary, timestamped.

        Returns the saved file path.
        """
        summaries_dir = self.base_dir / "chat-summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = f"{ts}-{alias}.md"
        path = summaries_dir / fname
        with self._lock:
            with path.open("w", encoding="utf-8") as f:
                f.write(f"# Chat Session Summary\n\n")
                f.write(f"- **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"- **Model:** {alias}\n")
                f.write(f"- **Messages summarized:** {message_count}\n")
                f.write(f"- **Summary length:** {len(summary)} chars\n")
                f.write(f"\n{summary}\n")
        return str(path)

    def _auto_index_file(self, path: str) -> None:
        """Fire-and-forget: index a file into memsearch for vector recall.

        Uses fcntl.flock() — released automatically on process death (no stale locks).
        Doesn't block the calling pipeline — failures are logged at debug level.
        """
        # P0: guard against None/invalid paths
        if not path:
            log.debug("memsearch index skipped: no path provided")
            return
        try:
            path_str = str(path)
        except Exception:
            log.debug("memsearch index skipped: invalid path type %r", path)
            return

        if not os.path.isfile(path_str):
            log.debug("memsearch index skipped: file not found %s", path_str)
            return

        _lock_path = self.base_dir / ".memsearch.lock"
        try:
            # Ensure lock file exists (may be from prior run — that's fine)
            _lock_path.touch(exist_ok=True)
            fd = open(str(_lock_path), "w")
            try:
                # Non-blocking exclusive lock — auto-released on process death
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                log.debug("memsearch index skipped: lock held")
                fd.close()
                return

            # Use direct Python API instead of CLI subprocess.
            # CLI's `memsearch index <file>` triggers cross-file cleanup deletion
            # (MemSearch.index() deletes ALL sources not in active_sources).
            # MemSearch.index_file() only deletes stale chunks within the same file.
            ms = None
            try:
                ms = MemSearch(
                    embedding_provider="onnx",
                    embedding_model="gpahal/bge-m3-onnx-int8",
                    milvus_uri=os.path.expanduser("~/.memsearch/milvus.db"),
                    collection="memsearch_chunks",
                )
                asyncio.run(ms.index_file(path_str))
            except Exception as e:
                log.debug("memsearch index failed for %s: %s", path_str, e)
            finally:
                # Release milvus-lite server process to free the db file lock.
                if ms is not None:
                    try:
                        ms.close()
                    except Exception:
                        pass
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
            except Exception:
                pass


# ─── Model Config (frozen, ours) ─────────────────────────────────────────────

@dataclass(frozen=True)
class ModelConfig:
    """Immutable runtime configuration for a model.

    Any change to these parameters invalidates existing slot bins.
    """
    model_path: str
    ctx_size: int
    ngl: int
    ctk: str = ""
    ctv: str = ""
    flash_attention: bool = True
    pipeline: int = 1
    server_flags: Dict[str, Any] = field(default_factory=dict)

    def config_hash(self) -> str:
        """SHA-256 of runtime parameters → namespaces slot directories."""
        config_str = (
            f"{self.model_path}\n"
            f"ctx_size={self.ctx_size}\n"
            f"ngl={self.ngl}\n"
            f"ctk={self.ctk}\n"
            f"ctv={self.ctv}\n"
            f"fa={'1' if self.flash_attention else '0'}\n"
            f"np={self.pipeline}\n"
        )
        return sha256_hex(config_str.encode("utf-8"))[:16]

    def slot_dir(self, base_slot_dir: Path) -> Path:
        """Per-model, per-config slot directory."""
        alias = Path(self.model_path).stem
        return base_slot_dir / alias / self.config_hash()


@dataclass
class ModelInfo:
    """Model metadata from config.json (OP's pattern)."""
    alias: str
    model_path: str
    ctx_size: int = 32768
    ngl: Optional[int] = None
    group: str = "default"
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        """Stable identifier for this model definition."""
        payload = {
            "model_path": self.model_path,
            "ctx_size": self.ctx_size,
            "ngl": self.ngl,
            "group": self.group,
            "extra": self.extra,
        }
        return sha256_hex(stable_json(payload).encode("utf-8"))


# ─── Model Registry ───────────────────────────────────────────────────────────

class ModelRegistry:
    """Maps model aliases to GGUF paths, context sizes, and runtime configs."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.models: Dict[str, ModelInfo] = {}
        self.configs: Dict[str, ModelConfig] = {}
        self._raw: dict = {}
        self.load()

    def load(self) -> None:
        self._raw = read_json_file(self.config_path)
        models: Dict[str, ModelInfo] = {}
        configs: Dict[str, ModelConfig] = {}
        groups = self._raw.get("groups", [])
        if not isinstance(groups, list):
            raise ValueError("config.groups must be a list")
        for group in groups:
            group_name = group.get("name", "default")
            group_defaults = group.get("group_defaults", {})
            group_server_flags = group_defaults.get("server_flags", {})
            group_chat_defaults = group_defaults.get("chat_defaults", {})
            for model_def in group.get("models", []):
                alias = model_def.get("alias") or model_def.get("name", "")
                model_path = model_def.get("model") or model_def.get("path", "")
                if not alias or not model_path:
                    continue
                # Merge group_defaults into model-specific values
                merged_server_flags = {**group_server_flags, **model_def.get("server_flags", {})}
                merged_chat_defaults = {
                    **group_chat_defaults,
                    **model_def.get("chat_defaults", {})
                }
                models[alias] = ModelInfo(
                    alias=alias,
                    model_path=model_path,
                    ctx_size=int(model_def.get("ctx_size", 32768)),
                    ngl=int(model_def["ngl"]) if "ngl" in model_def else None,
                    group=group_name,
                    extra={k: v for k, v in model_def.items()
                           if k not in {"alias", "name", "model", "path", "ctx_size", "ngl"}},
                )
                # Override extra.chat_defaults with merged version
                models[alias].extra["chat_defaults"] = merged_chat_defaults
                kv_cache = model_def.get("kv_cache", {})
                configs[alias] = ModelConfig(
                    model_path=model_path,
                    ctx_size=models[alias].ctx_size,
                    ngl=models[alias].ngl,
                    ctk=kv_cache.get("ctk", ""),
                    ctv=kv_cache.get("ctv", ""),
                    flash_attention=True,
                    pipeline=1,
                    server_flags=merged_server_flags,
                )
        self.models = models
        self.configs = configs
        log.info("Loaded %d models from %s", len(self.models), self.config_path)

    def get(self, alias: str) -> Optional[ModelInfo]:
        return self.models.get(alias)

    def get_config(self, alias: str) -> Optional[ModelConfig]:
        return self.configs.get(alias)

    def known_aliases(self) -> List[str]:
        return sorted(self.models.keys())


# ─── Slot Store ───────────────────────────────────────────────────────────────

class SlotStore:
    """Per-model, per-config slot storage with metadata sidecars.

    Merges our namespace isolation with OP's .json metadata pattern.
    """

    def __init__(self, slot_dir: str):
        self.slot_dir = Path(slot_dir)
        self.slot_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _slot_base(self, config: ModelConfig, slot_id: int) -> Path:
        """Base path for a slot: <alias>/<config_hash>/slot-{id}."""
        return config.slot_dir(self.slot_dir) / f"slot-{slot_id}"

    def slot_files(self, config: ModelConfig, slot_id: int) -> Dict[str, Path]:
        """Get paths for all slot artifacts."""
        base = self._slot_base(config, slot_id)
        return {
            "bin": base.with_suffix(".bin"),
            "ckpt": Path(str(base) + ".bin.checkpoints"),
            "meta": base.with_suffix(".json"),
        }

    def write_meta(self, config: ModelConfig, slot_id: int, meta: dict) -> None:
        """Write metadata sidecar for a slot."""
        files = self.slot_files(config, slot_id)
        files["bin"].parent.mkdir(parents=True, exist_ok=True)
        write_json_file(files["meta"], meta)

    def read_meta(self, config: ModelConfig, slot_id: int) -> Optional[dict]:
        """Read metadata sidecar for a slot."""
        meta = self.slot_files(config, slot_id)["meta"]
        if not meta.exists():
            return None
        try:
            return read_json_file(meta)
        except Exception:
            return None

    def bin_exists(self, config: ModelConfig, slot_id: int) -> bool:
        """Check if slot bin exists for a config."""
        return self.slot_files(config, slot_id)["bin"].exists()

    def bin_path(self, config: ModelConfig, slot_id: int) -> Path:
        """Return path to slot bin file."""
        return self.slot_files(config, slot_id)["bin"]

    def meta_path(self, config: ModelConfig, slot_id: int) -> Path:
        """Return path to slot metadata sidecar."""
        return self.slot_files(config, slot_id)["meta"]

    def cleanup_duplicate_artifacts(self, config: ModelConfig, slot_id: int) -> int:
        """Remove llama-server's duplicate model-stem artifacts.

        llama-server writes both slot-{id}.bin AND <model_stem> (no extension)
        as exact duplicates. Remove the stem-named copy since it's not required.
        Returns number of files removed.
        """
        removed = 0
        slot_path = config.slot_dir(self.slot_dir)
        if not slot_path.is_dir():
            return 0
        model_stem = Path(config.model_path).stem
        canonical_name = f"slot-{slot_id}.bin"
        duplicate = slot_path / model_stem
        if duplicate.is_file() and duplicate.name != canonical_name:
            # Only remove if it's a duplicate of the canonical slot bin
            canonical = self.slot_files(config, slot_id)["bin"]
            if canonical.exists() and duplicate.stat().st_size == canonical.stat().st_size:
                size_mb = duplicate.stat().st_size / (1024 * 1024)
                duplicate.unlink()
                log.info(
                    "[ARTIFACT NORMALIZE] pruned duplicate '%s' (%.1f MiB) — "
                    "canonical '%s' retained. llama-server writes both; only slot-{id}.bin is required.",
                    duplicate.name, size_mb, canonical_name,
                )
                removed += 1
        return removed

    def cleanup(self, known_aliases: Optional[set] = None) -> Dict[str, int]:
        """Purge orphaned artifacts and unknown model directories."""
        known_aliases = known_aliases or set()
        removed = {"orphan_ckpt": 0, "orphan_meta": 0, "unknown_bin": 0, "unknown_dir": 0}
        with self.lock:
            # Orphan .checkpoints without matching .bin
            for ckpt in self.slot_dir.rglob("*.bin.checkpoints"):
                bin_path = Path(str(ckpt)[:-len(".checkpoints")])
                if not bin_path.exists():
                    ckpt.unlink(missing_ok=True)
                    removed["orphan_ckpt"] += 1
            # Orphan .json without matching .bin
            for meta in self.slot_dir.rglob("*.json"):
                bin_path = Path(str(meta)[:-5] + ".bin")
                if not bin_path.exists():
                    meta.unlink(missing_ok=True)
                    removed["orphan_meta"] += 1
            # Orphan .bin without matching .json
            for b in self.slot_dir.rglob("*.bin"):
                meta = Path(str(b)[:-4] + ".json")
                if not meta.exists():
                    b.unlink(missing_ok=True)
                    removed["unknown_bin"] += 1
            # Unknown model directories
            for item in self.slot_dir.iterdir():
                if item.is_dir() and item.name not in known_aliases and not item.name.startswith("."):
                    shutil.rmtree(item)
                    removed["unknown_dir"] += 1
        return removed


# ─── Binary Hash Tracker (ours) ──────────────────────────────────────────────

class BinaryHashTracker:
    """Tracks llama-server binary hash. Purges all slots on binary change."""

    HASH_FILE = ".llama_server_binary_hash"

    def __init__(self, binary_path: str, slot_dir: str):
        self.binary_path = binary_path
        self.slot_dir = Path(slot_dir)
        self.hash_file = self.slot_dir / self.HASH_FILE

    def _compute_hash(self) -> str:
        h = hashlib.sha256()
        with open(self.binary_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def check_and_invalidate(self) -> bool:
        """Check if binary changed since last run. Returns True if invalidated."""
        current_hash = self._compute_hash()
        if self.hash_file.exists():
            stored_hash = self.hash_file.read_text().strip()
            if stored_hash != current_hash:
                log.warning("llama-server binary changed! Purging all slots.")
                for item in self.slot_dir.iterdir():
                    if item.name != self.HASH_FILE:
                        shutil.rmtree(item)
                        log.info("  Purged: %s", item.name)
                self.hash_file.write_text(current_hash)
                return True
        self.hash_file.write_text(current_hash)
        return False


# ─── Upstream Process ────────────────────────────────────────────────────────

class UpstreamProcess:
    """Manages llama-server child process lifecycle."""

    def __init__(self, bin_path: str, port: int, host: str = DEFAULT_UPSTREAM_HOST,
                 env: Optional[Dict[str, str]] = None):
        self.bin_path = bin_path
        self.port = port
        self.host = host
        self.proc: Optional[subprocess.Popen] = None
        self.current_config: Optional[ModelConfig] = None
        self.extra_args: List[str] = []
        self._last_args: List[str] = []
        self._env = env or {}  # extra env vars to pass to llama-server subprocess
        # Background stdout tailer for request-time checkpoint logging
        self._stdout_thread: Optional[threading.Thread] = None
        self._stdout_stop_event: Optional[threading.Event] = None

    def build_args(self, config: ModelConfig, slot_dir: Path) -> List[str]:
        """Build llama-server command-line arguments."""
        slot_path = config.slot_dir(slot_dir)
        slot_path.mkdir(parents=True, exist_ok=True)
        args = [
            self.bin_path,
            "-m", config.model_path,
            "--ctx-size", str(config.ctx_size),
        ]
        if config.ngl is not None:
            args.extend(["-ngl", str(config.ngl)])
        args += [
            "--host", self.host,
            "--port", str(self.port),
            "--slot-save-path", str(slot_path),
            "-np", str(config.pipeline),
        ]
        # KV cache types (from config or defaults)
        if config.ctk:
            args.extend(["-ctk", config.ctk])
        if config.ctv:
            args.extend(["-ctv", config.ctv])

        # Server flags from config (per-model overrides)
        flags = config.server_flags
        if flags:
            fa = flags.get("flash_attn")
            if fa:
                args.extend(["-fa", str(fa)])
            elif config.flash_attention:
                args.extend(["-fa", "on"])

            fit = flags.get("fit")
            if fit:
                args.extend(["-fit", str(fit)])
            else:
                args.extend(["-fit", "on"])  # default

            fit_target = flags.get("fit_target")
            if fit_target:
                args.extend(["-fitt", str(fit_target)])

            if flags.get("no_mmap"):
                args.append("--no-mmap")
            if flags.get("mlock"):
                args.append("--mlock")
            if flags.get("cont_batching"):
                args.append("--cont-batching")

            batch = flags.get("batch")
            if batch:
                args.extend(["-b", str(batch)])
            ubatch = flags.get("ubatch")
            if ubatch:
                args.extend(["-ub", str(ubatch)])

            threads = flags.get("threads")
            if threads:
                args.extend(["--threads", str(threads)])
            threads_batch = flags.get("threads_batch")
            if threads_batch:
                args.extend(["--threads-batch", str(threads_batch)])

            ctx_checkpoints = flags.get("ctx_checkpoints")
            if ctx_checkpoints is not None:
                args.extend(["--ctx-checkpoints", str(ctx_checkpoints)])
            checkpoint_every = flags.get("checkpoint_every_n_tokens")
            if checkpoint_every is not None:
                args.extend(["--checkpoint-every-n-tokens", str(checkpoint_every)])
            cache_reuse = flags.get("cache_reuse")
            if cache_reuse is not None:
                args.extend(["--cache-reuse", str(cache_reuse)])

            temp = flags.get("temp")
            if temp is not None:
                args.extend(["--temp", str(temp)])
            top_p = flags.get("top_p")
            if top_p is not None:
                args.extend(["--top-p", str(top_p)])
            top_k = flags.get("top_k")
            if top_k is not None:
                args.extend(["--top-k", str(top_k)])
            min_p = flags.get("min_p")
            if min_p is not None:
                args.extend(["--min-p", str(min_p)])

            presence = flags.get("presence_penalty")
            if presence is not None:
                args.extend(["--presence-penalty", str(presence)])
            repeat = flags.get("repeat_penalty")
            if repeat is not None:
                args.extend(["--repeat-penalty", str(repeat)])

            reasoning = flags.get("reasoning")
            if reasoning:
                args.extend(["--reasoning", str(reasoning)])
            reasoning_budget = flags.get("reasoning_budget")
            if reasoning_budget:
                args.extend(["--reasoning-budget", str(reasoning_budget)])
            reasoning_format = flags.get("reasoning_format")
            if reasoning_format:
                args.extend(["--reasoning-format", str(reasoning_format)])

            max_predict = flags.get("max_predict")
            if max_predict is not None:
                args.extend(["-n", str(max_predict)])

            jinja = flags.get("jinja")
            if jinja is True:
                args.append("--jinja")
            # jinja=False → omit; default is already no-jinja

            chat_template = flags.get("chat_template")
            if chat_template:
                # llama.cpp --chat-template only accepts built-in names
                # (qwen2, gemma, llama3, chatml, …) unless --jinja is set.
                # Detect custom Jinja strings by presence of {{ or {%
                ct = str(chat_template)
                if "{{" in ct or "{%" in ct:
                    # Custom Jinja string — use override-kv
                    args.extend(["--override-kv", f"tokenizer.chat_template=str:{ct}"])
                else:
                    # Built-in template name
                    args.extend(["--chat-template", ct])

            chat_template_file = flags.get("chat_template_file")
            if chat_template_file:
                # --chat-template-file implicitly enables --jinja
                args.extend(["--chat-template-file", str(chat_template_file)])

        args.extend(self.extra_args)
        return args

    def start(self, config: ModelConfig, slot_dir: Path, timeout: int = 120) -> None:
        """Start llama-server with the given model config."""
        self.stop()
        args = self.build_args(config, slot_dir)
        self._last_args = list(args)
        log.info("Starting upstream: %s", " ".join(args))

        # Build subprocess env: inherit current env + apply overrides from config
        proc_env = os.environ.copy()
        proc_env.update(self._env)
        if self._env:
            log.info("Server env overrides: %s", self._env)

        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout — single stream
            env=proc_env,
            # No encoding — raw bytes so os.read() in _drain_upstream_startup_output
            # can access the full pipe without a TextIOWrapper buffer stealing data
        )
        self.current_config = config
        crash_output = self.wait_ready(timeout=timeout)
        if crash_output is None:
            # Server is up — drain the startup output and log key info
            self._drain_upstream_startup_output()
            # Launch background tailer for request-time checkpoint/logging output
            self._start_stdout_tailer()
        if crash_output is not None:
            # Process exited unexpectedly — crash_output is the drained stream
            returncode = self.proc.returncode
            self._log_crash(crash_output, returncode)
            self.proc = None
            self.current_config = None
            raise RuntimeError(
                f"Upstream exited (rc={returncode}) on port {self.port} — "
                f"see crash output above"
            )

    def wait_ready(self, timeout: int = 120) -> Optional[str]:
        """Wait for llama-server to respond to /v1/health.

        Returns None if ready, or the drained output if the process exited.
        """
        deadline = time.time() + timeout
        health_url = f"http://{self.host}:{self.port}/v1/health"
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                # Process exited — drain the pipe to avoid deadlock, return output
                try:
                    raw, _ = self.proc.communicate(timeout=3)
                    output = raw.decode("utf-8", errors="replace") if raw else ""
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    raw, _ = self.proc.communicate(timeout=2)
                    output = raw.decode("utf-8", errors="replace") if raw else ""
                return output  # caller will log it via _log_crash
            try:
                status, _, _ = http_request("GET", health_url, timeout=DEFAULT_POLL_HEALTH)
                if status == 200:
                    return None  # ready
            except urllib.error.URLError:
                continue
            except KeyboardInterrupt:
                raise
            except Exception:
                continue
            time.sleep(1)
        # Timeout — drain whatever output exists
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        try:
            raw, _ = self.proc.communicate(timeout=3)
            output = raw.decode("utf-8", errors="replace") if raw else ""
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raw, _ = self.proc.communicate(timeout=2)
            output = raw.decode("utf-8", errors="replace") if raw else ""
        return output

    def _drain_upstream_startup_output(self) -> None:
        """Drain the upstream's stdout pipe after startup and log key diagnostics.

        llama-server prints layer offload, VRAM usage, and other startup info to stdout.
        The supervisor captures stdout via PIPE but never reads it on success —
        this drains what's buffered so we can log it.

        Uses non-blocking os.read() on the raw fd to bypass the TextIOWrapper's
        internal buffer which would otherwise hide data from select()/os.read().
        """
        import fcntl
        import os
        if not self.proc or self.proc.stdout is None:
            return
        try:
            fd = self.proc.stdout.fileno()
            # Make fd non-blocking so os.read() returns immediately with whatever is buffered
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            try:
                chunks = []
                while True:
                    try:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    except OSError:
                        # EAGAIN/EWOULDBLOCK — no more data right now
                        break
                raw_output = b"".join(chunks)
            finally:
                # Restore original flags
                fcntl.fcntl(fd, fcntl.F_SETFL, flags)

            if raw_output:
                output = raw_output.decode("utf-8", errors="replace")
                alias = Path(self.current_config.model_path).name if self.current_config else "unknown"
                lines = output.rstrip("\n").split("\n")
                # Log all lines (they're startup diagnostics)
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Key patterns to highlight
                    if any(kw in stripped.lower() for kw in ["offload", "layer", "gpu", "vram", "memory", "tensor", "split", "backend", "kv-cache", "cache", "checkpoint"]):
                        log.info("UPSTREAM [%s]: %s", alias, stripped)
                    elif any(kw in stripped.lower() for kw in ["warn", "error", "fail", "cannot"]):
                        log.warning("UPSTREAM [%s]: %s", alias, stripped)
                    else:
                        log.debug("UPSTREAM [%s]: %s", alias, stripped)
        except Exception as e:
            log.debug("Startup output drain failed (non-critical): %s", e)

    def _start_stdout_tailer(self) -> None:
        """Launch a background thread to tail llama-server's stdout.

        Captures request-time messages (checkpoint reuse, SWA state, etc.)
        that the one-time startup drain misses.

        Uses select() with a 1-second poll interval so the thread can
        respond to the stop event without blocking.
        """
        if not self.proc or self.proc.stdout is None:
            return
        self._stdout_stop_event = threading.Event()
        self._stdout_thread = threading.Thread(
            target=self._tail_stdout_loop,
            name="upstream-tailer",
            daemon=True,
        )
        self._stdout_thread.start()

    def _tail_stdout_loop(self) -> None:
        """Background loop: read stdout lines, filter, log.

        Reads up to 64KB chunks, buffers partial lines, splits on newlines.
        Filters same keywords as startup drain — checkpoint, cache, offload, etc.
        Exits on stop event, pipe EOF, or process exit.
        """
        import select
        stop = self._stdout_stop_event
        alias = Path(self.current_config.model_path).name if self.current_config else "unknown"
        buf = b""
        try:
            while not stop.is_set():
                if self.proc is None or self.proc.poll() is not None:
                    # Process exited
                    break
                # Non-blocking select: 1s timeout lets us check stop event
                try:
                    ready, _, _ = select.select([self.proc.stdout], [], [], 1.0)
                except (ValueError, OSError):
                    # Pipe closed or invalid fd
                    break
                if not ready:
                    continue
                try:
                    chunk = self.proc.stdout.read(65536)
                except (OSError, ValueError):
                    break
                if not chunk:
                    # EOF
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    stripped = line.decode("utf-8", errors="replace").strip()
                    if not stripped:
                        continue
                    low = stripped.lower()
                    if any(kw in low for kw in ["checkpoint", "cache", "offload", "layer", "gpu", "vram", "memory", "tensor", "split", "backend", "kv-cache"]):
                        log.info("UPSTREAM-LIVE [%s]: %s", alias, stripped)
                    elif any(kw in low for kw in ["warn", "error", "fail", "cannot"]):
                        log.warning("UPSTREAM-LIVE [%s]: %s", alias, stripped)
                    else:
                        log.debug("UPSTREAM-LIVE [%s]: %s", alias, stripped)
        except Exception as e:
            log.debug("Stdout tailer exited: %s", e)

    def _log_crash(self, output: str, returncode: int) -> None:
        """Log crash diagnostics: alias, command, return code, last N output lines."""
        alias = Path(self.current_config.model_path).name if self.current_config else "unknown"
        lines = output.rstrip("\n").split("\n") if output else ["(no output captured)"]
        tail = lines[-MAX_CRASH_LINES:] if len(lines) > MAX_CRASH_LINES else lines
        log.error("="*60)
        log.error("UPSTREAM CRASH — model: %s", alias)
        log.error("command: %s", " ".join(self._last_args))
        log.error("return code: %s", returncode)
        log.error("output (last %d lines):", len(tail))
        for line in tail:
            log.error("  %s", line)
        log.error("="*60)

    def stop(self) -> None:
        if not self.proc:
            return
        # Signal background stdout tailer to stop
        if self._stdout_stop_event is not None:
            self._stdout_stop_event.set()
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
            # Always drain pipes to avoid blocking the child's write buffers
            try:
                self.proc.communicate(timeout=2)
            except (subprocess.TimeoutExpired, UnicodeDecodeError):
                pass
        finally:
            self.proc = None
            self.current_config = None
        # Wait for tailer thread to finish (with timeout)
        if self._stdout_thread is not None and self._stdout_thread.is_alive():
            self._stdout_thread.join(timeout=3)
            self._stdout_thread = None
            self._stdout_stop_event = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


# ─── Slot Client ──────────────────────────────────────────────────────────────

class SlotClient:
    """HTTP client for llama-server slot endpoints."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, timeout: int = DEFAULT_TIMEOUT_READ) -> Tuple[int, bytes]:
        status, body, _ = http_request("GET", self.base_url + path, timeout=timeout)
        return status, body

    def post_json(self, path: str, payload: dict, timeout: int = DEFAULT_TIMEOUT_CHAT) -> Tuple[int, bytes]:
        body = json.dumps(payload).encode("utf-8")
        status, resp, _ = http_request(
            "POST",
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        return status, resp

    def health(self) -> bool:
        try:
            status, _ = self.get("/v1/health", timeout=DEFAULT_POLL_HEALTH)
            return status == 200
        except Exception:
            return False

    def metrics(self) -> dict:
        try:
            status, body = self.get("/metrics", timeout=DEFAULT_TIMEOUT_READ)
            if status != 200:
                return {}
            return json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def _parse_upstream_json(self, body: bytes, context: str = "") -> Optional[dict]:
        """Safely parse upstream JSON response, logging raw bytes on decode failure."""
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            # Log safely: hex preview of first 128 bytes + length
            preview = body[:128].hex(" ")
            log.warning(
                "UPSTREAM RAW [%s]: status=2xx, len=%d, decode_error=%s, hex_preview=%s",
                context, len(body), e, preview,
            )
            # Fallback: try replace-mode decode
            try:
                return json.loads(body.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                log.warning("UPSTREAM RAW [%s]: fallback decode also failed", context)
                return None

    def save_slot(self, slot_id: int = 0, filename: str = "slot-0.bin", timeout: int = DEFAULT_TIMEOUT_READ) -> Optional[dict]:
        """Save slot state. POST /slots/{id}?action=save with {filename}.
        Returns response dict with id_slot, filename, n_saved, n_written, timings."""
        try:
            status, body = self.post_json(
                f"/slots/{slot_id}?action=save",
                {"filename": filename},
                timeout=timeout
            )
            if 200 <= status < 300:
                return self._parse_upstream_json(body, context=f"save_slot-{slot_id}")
            return None
        except Exception:
            return None

    def restore_slot(self, slot_id: int = 0, filename: str = "slot-0.bin", timeout: int = DEFAULT_TIMEOUT_READ) -> Optional[dict]:
        """Restore slot with retries and backoff.
        POST /slots/{id}?action=restore with {filename}.
        Returns response dict with id_slot, filename, n_restored, n_read, timings."""
        for attempt in range(DEFAULT_RESTORE_RETRIES + 1):
            try:
                status, body = self.post_json(
                    f"/slots/{slot_id}?action=restore",
                    {"filename": filename},
                    timeout=timeout
                )
                if 200 <= status < 300:
                    return self._parse_upstream_json(body, context=f"restore_slot-{slot_id}")
            except Exception:
                pass
            if attempt < DEFAULT_RESTORE_RETRIES:
                time.sleep(DEFAULT_RESTORE_BACKOFF * (attempt + 1))
        return None

    def reset_slot(self, slot_id: int = 0) -> bool:
        try:
            status, _ = self.get(f"/slots/{slot_id}?action=reset", timeout=DEFAULT_TIMEOUT_READ)
            return 200 <= status < 300
        except Exception:
            return False


# ─── Slot Supervisor ─────────────────────────────────────────────────────────

class SlotSupervisor:
    """Main supervisor: proxy frontend + upstream management + slot persistence.

    Architecture:
      Client → [listen_port:8080] ←proxy→ [upstream_port:8081:llama-server]

    Slot storage: per-model, per-config namespaces with .json metadata sidecars.
    """

    def __init__(
        self,
        *,
        listen_host: str,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
        config_path: str,
        slot_dir: str,
        upstream_bin: str,
        id_slot: int = 0,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.config_path = config_path
        self.slot_dir = Path(slot_dir)
        self.upstream_bin = upstream_bin
        self.id_slot = id_slot

        self.registry = ModelRegistry(config_path)
        self.store = SlotStore(slot_dir)
        self.client = SlotClient(f"http://{upstream_host}:{upstream_port}")

        # Read server-level env overrides from config.json
        _raw = read_json_file(Path(config_path))
        self._server_env: Dict[str, str] = _raw.get("server_env", {})

        self.upstream = UpstreamProcess(
            upstream_bin, upstream_port, upstream_host, env=self._server_env
        )

        self.current_alias: Optional[str] = None
        self.current_signature: Optional[str] = None
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.httpd = None
        self._failures: Dict[str, int] = {}  # alias -> failure_count

        # Fanout / swap coordination flags
        self.fanout_in_progress = False
        self._swapping = False
        self._swap_lock = threading.Lock()  # serialize swap operations
        self._swap_event = threading.Event()  # signaled when swap completes
        self._swap_event.set()  # initially not swapping
        self._delegating = False  # guard against concurrent delegation
        self._system_error = False  # set if swap-back fails (Gemma fix)
        self._error_lock = threading.Lock()  # protect _system_error reads/writes
        self._restarting = False  # set during upstream restart
        self._recovery_thread: Optional[threading.Thread] = None
        self._recovery_stop_event = threading.Event()
        self._restart_log: List[dict] = []  # restart progress messages
        self._last_n_saved: int = 0  # last save token count for memory logging
        self.memory = CouncilMemory()

        # Thread-safety locks
        self._delegation_lock = threading.Lock()  # atomic check-and-set for _delegating
        self._slot_lock = threading.Lock()  # serialize slot writes
        self._restart_lock = threading.Lock()  # serialize restart operations

        # Tool-use: allowed tools (supervisor-side filter)
        self._allowed_tools = {
            "read_file", "grep", "find", "list_dir", "bash_ro",
            "delegate_to", "search_codebase", "read",
            "web_search", "write",  # added for tool-use battery testing
        }

        self.stats = {
            "start_time": time.time(),
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "swaps": 0,
            "restores": 0,
            "saves": 0,
            "errors": 0,
        }
        self._stats_lock = threading.Lock()
        self.metrics_cache: Dict[str, Any] = {}
        self.metrics_cache_ts = 0.0
        self.council_manager: Optional[TinyCouncilManager] = None

    def _inc_stat(self, key: str, amount: int = 1) -> None:
        """Atomically increment a stats counter — pure operation, no side effects."""
        with self._stats_lock:
            self.stats[key] = self.stats.get(key, 0) + amount

    def _init_council_manager(self) -> None:
        """Initialize TinyCouncilManager once at startup."""
        try:
            _raw = read_json_file(Path(self.config_path))
            fanout_cfg = _raw.get("fanout", {})
            if fanout_cfg:
                group_name = fanout_cfg.get("council_group", "tiny_council")
                council_aliases, council_configs = self._resolve_council_group(group_name, _raw)
                if council_aliases:
                    self.council_manager = TinyCouncilManager(
                        self, fanout_cfg, council_aliases, council_configs
                    )
                else:
                    log.warning("No council models found for group '%s'", group_name)
                    self.council_manager = None
            else:
                self.council_manager = None
        except Exception as e:
            log.warning("Failed to init council manager: %s", e)
            self.council_manager = None

    def _resolve_council_group(self, group_name: str, raw_config: dict) -> Tuple[List[str], Dict[str, ModelConfig]]:
        """Resolve council group aliases and configs from raw config.

        Returns (aliases, configs) tuple. Empty lists if group not found.
        """
        aliases: List[str] = []
        configs: Dict[str, ModelConfig] = {}
        for group in raw_config.get("groups", []):
            if group.get("name") == group_name:
                for model_def in group.get("models", []):
                    alias = model_def.get("alias") or model_def.get("name", "")
                    if alias:
                        aliases.append(alias)
                        config = self.registry.get_config(alias)
                        if config:
                            configs[alias] = config
                break
        return aliases, configs

    # ── Swap Logic ─────────────────────────────────────────────────────────

    def _backoff_delay(self, alias: str) -> float:
        """Compute exponential backoff with jitter for a failing alias."""
        count = self._failures.get(alias, 0)
        if count == 0:
            return 0.0
        delay = min(BACKOFF_MIN * (BACKOFF_MULTIPLIER ** (count - 1)), BACKOFF_MAX)
        # Add jitter ±BACKOFF_JITTER
        delay = delay * (1 + random.uniform(-BACKOFF_JITTER, BACKOFF_JITTER))
        return delay

    def _record_failure(self, alias: str) -> None:
        self._failures[alias] = self._failures.get(alias, 0) + 1

    def _clear_failure(self, alias: str) -> None:
        self._failures.pop(alias, None)

    def _get_free_vram(self) -> Optional[int]:
        """Query nvidia-smi for free VRAM in MiB. Returns None on failure."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Parse first GPU's free memory
                return int(result.stdout.strip().split('\n')[0].strip())
        except Exception as e:
            log.warning("nvidia-smi query failed: %s", e)
        return None

    def _wait_for_vram(self) -> bool:
        """Wait for CUDA to free VRAM using adaptive polling.

        1. Initial sleep (CUDA_CLEANUP_DELAY) for fast path
        2. Poll nvidia-smi every CUDA_VRAM_POLL_INTERVAL until free > HEADROOM
        3. Timeout after CUDA_VRAM_POLL_TIMEOUT

        Returns True if VRAM freed, False on timeout.
        """
        # Fast path: initial delay covers most cases
        time.sleep(CUDA_CLEANUP_DELAY)

        free = self._get_free_vram()
        if free is not None and free >= CUDA_VRAM_HEADROOM:
            log.info("VRAM free after %.1fs: %d MiB available", CUDA_CLEANUP_DELAY, free)
            return True

        # Polling path: check every 0.2s until VRAM is free
        deadline = time.time() + CUDA_VRAM_POLL_TIMEOUT
        poll_count = 0
        while time.time() < deadline:
            time.sleep(CUDA_VRAM_POLL_INTERVAL)
            free = self._get_free_vram()
            if free is not None:
                poll_count += 1
                if free >= CUDA_VRAM_HEADROOM:
                    elapsed = time.time() - deadline + CUDA_VRAM_POLL_TIMEOUT
                    log.info("VRAM free after %.1fs (%d polls): %d MiB available",
                             elapsed, poll_count, free)
                    return True
                # Log progress every 10 polls (~2 seconds)
                if poll_count % 10 == 0:
                    log.info("Waiting for VRAM: %d MiB free (need %d)",
                             free, CUDA_VRAM_HEADROOM)

        # Timeout
        log.warning("VRAM wait timed out after %.1fs: %d MiB free (need %d)",
                    CUDA_VRAM_POLL_TIMEOUT, free or 0, CUDA_VRAM_HEADROOM)
        return False

    def _swap_to(self, alias: str) -> None:
        """Swap upstream to the target model alias.

        1. Check backoff for this alias
        2. Save current slot (if running)
        3. Stop upstream
        4. Start upstream with new model + per-config slot path
        5. Attempt restore (validates signature from metadata)
        """
        model = self.registry.get(alias)
        config = self.registry.get_config(alias)
        if not model or not config:
            raise KeyError(f"Unknown model alias: {alias}")

        if self.current_alias == alias and self.upstream.running():
            return

        # ── Swap guard: queue requests during active swap ──
        # Wait for any in-progress swap to complete (max 30s timeout)
        if not self._swap_event.wait(timeout=30):
            raise TimeoutError(f"Swap to '{alias}' timed out waiting for prior swap to complete")

        # Acquire exclusive swap lock
        if not self._swap_lock.acquire(timeout=1):
            raise RuntimeError(f"Swap to '{alias}' blocked: could not acquire swap lock")
        self._swapping = True
        self._swap_event.clear()  # signal that swap is in progress
        try:
            with self.lock:
                # Guard fanout check inside the lock to prevent race conditions
                if self.fanout_in_progress:
                    raise RuntimeError(
                        f"Swap to '{alias}' blocked: fanout operation in progress"
                    )

                # Re-check after acquiring lock — another thread may have swapped already
                if self.current_alias == alias and self.upstream.running():
                    self._clear_failure(alias)
                    return

                # Check backoff
                delay = self._backoff_delay(alias)
                if delay > 0:
                    log.warning(
                        "BACKOFF [%s]: retrying in %.1fs (%d prior failure(s))",
                        alias, delay, self._failures.get(alias, 0),
                    )
                    # Release lock during sleep so other requests aren't blocked
                    self.lock.release()
                    try:
                        time.sleep(delay)
                    finally:
                        self.lock.acquire()

                    # Re-check again after backoff
                    if self.current_alias == alias and self.upstream.running():
                        self._clear_failure(alias)
                        return

                # Save current slot before swap
                if self.upstream.running() and self.current_alias is not None:
                    self._save_current_slot()
                    # Clean up duplicate artifacts after save — async writes may have completed
                    cur_config = self.registry.get_config(self.current_alias)
                    if cur_config:
                        self.store.cleanup_duplicate_artifacts(cur_config, self.id_slot)
                    self.upstream.stop()
                    # ── Option D: Overlap VRAM wait + model load ──
                    # Start two threads:
                    #   1. VRAM wait — polls nvidia-smi until free >= headroom
                    #   2. Model load — starts llama-server (blocks on GPU alloc until VRAM free)
                    # The CUDA driver serializes GPU allocation, but host-side model copy
                    # can stream from NVMe in parallel. Saves ~3s per swap.
                    log.info("Overlapping VRAM wait + model load for %s…", alias)
                    self.lock.release()
                    try:
                        start_time = time.time()
                        vram_ready = threading.Event()
                        load_exc: Optional[Exception] = None

                        def _wait_thread():
                            self._wait_for_vram()
                            vram_ready.set()

                        def _load_thread():
                            nonlocal load_exc
                            try:
                                self.upstream.start(config, self.slot_dir)
                            except Exception as e:
                                load_exc = e

                        t_wait = threading.Thread(target=_wait_thread, daemon=True)
                        t_load = threading.Thread(target=_load_thread, daemon=True)
                        t_wait.start()
                        t_load.start()
                        t_load.join(timeout=120)  # model load timeout
                        t_wait.join(timeout=30)   # VRAM wait timeout

                        elapsed = time.time() - start_time
                        if load_exc:
                            # Model load failed — record failure AFTER lock re-acquired (see finally below)
                            log.error("SWAP FAILED [%s]: %s (overlap took %.1fs)", alias, load_exc, elapsed)
                        elif not vram_ready.is_set():
                            # VRAM wait timed out — but load may have succeeded
                            log.warning("VRAM wait timed out but model load may have proceeded (%.1fs)", elapsed)
                        else:
                            log.info("Overlap swap complete (%.1fs): VRAM=ok, load=ok",
                                    elapsed)
                    finally:
                        self.lock.acquire()
                    # Record failure and re-raise only after lock is re-held
                    if load_exc:
                        self._record_failure(alias)
                        raise load_exc

            # ── Post-swap: only runs if try block succeeded ──
            # Start upstream with new model (if not already started via overlap).
            # Must be done under self.lock to prevent concurrent alias reads.
            with self.lock:
                if not self.upstream.running():
                    try:
                        self.upstream.start(config, self.slot_dir)
                    except RuntimeError as e:
                        self._record_failure(alias)
                        count = self._failures.get(alias, 1)
                        retry_in = min(BACKOFF_MIN * (BACKOFF_MULTIPLIER ** (count - 1)), BACKOFF_MAX)
                        log.error("SWAP FAILED [%s]: %s (next retry ~%.1fs)", alias, e, retry_in)
                        raise

            self.current_alias = alias
            self.current_signature = model.signature
            self._clear_failure(alias)  # success — reset backoff
            self._inc_stat("swaps")

            # Attempt restore — validates signature from metadata
            restore_result = self._restore_current_slot(prefer_signature=model.signature)
            # Log slot state after restore
            config = self.registry.get_config(self.current_alias)
            if config:
                meta = self.store.read_meta(config, self.id_slot)
                if meta and meta.get("slot_tokens"):
                    log.info("SWAP: slot restored with %d tokens (meta)", meta["slot_tokens"])
        except Exception:
            # Swap failed — clear current_alias so swap-back doesn't short-circuit.
            # If the overlap swap killed the upstream but never set current_alias,
            # the caller's swap-back needs to know the upstream is dead and restart it.
            if self.current_alias == alias:
                self.current_alias = None
                self.current_signature = None
            raise
        finally:
            self._swapping = False
            self._swap_lock.release()
            self._swap_event.set()  # signal waiting requests to retry

    def _slot_meta(self) -> dict:
        return {
            "model_alias": self.current_alias,
            "model_signature": self.current_signature,
            "saved_at": time.time(),
            "timestamp": time.time(),
        }

    def _get_slot_timeout(self) -> int:
        """Read slot_timeout from current model's server_flags, or use default."""
        config = self.registry.get_config(self.current_alias)
        if config and config.server_flags:
            raw = config.server_flags.get("slot_timeout", DEFAULT_TIMEOUT_READ)
            try:
                timeout = int(float(raw))
                if timeout < 1 or timeout > 300:
                    log.warning("slot_timeout=%d out of range [1,300], clamping", timeout)
                    timeout = max(1, min(300, timeout))
                return timeout
            except (ValueError, TypeError):
                log.warning("Invalid slot_timeout=%r, using default %ds", raw, DEFAULT_TIMEOUT_READ)
        return DEFAULT_TIMEOUT_READ

    def _start_recovery(self) -> None:
        """Spawn a background thread that retries loading the default model.
        Clears _system_error on success so traffic resumes automatically."""
        if self._recovery_thread and self._recovery_thread.is_alive():
            return  # already recovering
        self._recovery_stop_event.clear()
        self._recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
        self._recovery_thread.start()
        log.info("Auto-recovery thread started")

    def _recovery_loop(self) -> None:
        """Retry loading the default model every 30s, up to 5 attempts."""
        target = self._get_default_alias() or self.current_alias
        if not target:
            log.warning("Recovery aborted: no target alias available")
            return
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            if self._recovery_stop_event.is_set():
                log.info("Recovery stopped (signal received)")
                return
            with self._error_lock:
                if not self._system_error:
                    log.info("Recovery stopped: _system_error cleared externally")
                    return
            log.info("Recovery attempt %d/%d: trying to load %s", attempt, max_attempts, target)
            try:
                self._swap_to(target)
                with self._error_lock:
                    self._system_error = False
                log.info("Recovery succeeded: loaded %s, clearing _system_error", target)
                return
            except Exception as e:
                log.warning("Recovery attempt %d failed: %s", attempt, e)
            # Wait 30s or until stopped
            if self._recovery_stop_event.wait(timeout=30):
                log.info("Recovery stopped (signal received)")
                return
        log.error("Recovery exhausted %d attempts — system remains unstable", max_attempts)

    def _save_current_slot(self) -> bool:
        config = self.registry.get_config(self.current_alias)
        if not config:
            return False
        filename = f"slot-{self.id_slot}.bin"
        timeout = self._get_slot_timeout()
        result = self.client.save_slot(self.id_slot, filename, timeout=timeout)
        if result is not None:
            self._inc_stat("saves")
            meta = self._slot_meta()
            # Compute SHA-256 checksum of saved bin for corruption detection
            bin_path = self.store.bin_path(config, self.id_slot)
            if bin_path.exists():
                checksum = sha256_hex(bin_path.read_bytes())
                meta["slot_checksum"] = checksum
                meta["slot_tokens"] = result.get("n_saved", 0)
                self._last_n_saved = meta["slot_tokens"]
            self.store.write_meta(config, self.id_slot, meta)
            # DIAGNOSTIC: log checkpoint file size alongside slot bin
            ckpt_path = self.store.slot_files(config, self.id_slot)["ckpt"]
            ckpt_total = 0
            ckpt_files = []
            if ckpt_path.exists() and ckpt_path.is_file():
                # PCLL format: single companion file (e.g. slot-0.bin.checkpoints)
                ckpt_total = ckpt_path.stat().st_size
                ckpt_files.append(f"{ckpt_path.name}:{ckpt_total/(1024*1024):.1f}MB")
            elif ckpt_path.exists() and ckpt_path.is_dir():
                # Future-proof: directory with multiple checkpoint files
                for f in ckpt_path.rglob("*"):
                    if f.is_file():
                        sz = f.stat().st_size
                        ckpt_total += sz
                        ckpt_files.append(f"{f.name}:{sz/(1024*1024):.1f}MB")
            bin_size = bin_path.stat().st_size / (1024*1024) if bin_path.exists() else 0
            log.info("Saved slot %d: %d tokens, bin=%.1fMiB, checkpoints=%.1fMiB(%d files: %s) (%.1fms)",
                     self.id_slot, result.get("n_saved", 0),
                     bin_size, ckpt_total/(1024*1024), len(ckpt_files),
                     ",".join(ckpt_files[:5]),
                     result.get("timings", {}).get("save_ms", 0))
        return result is not None

    def _restore_current_slot(self, prefer_signature: Optional[str] = None) -> bool:
        """Restore slot, validating model signature + checksum from metadata."""
        config = self.registry.get_config(self.current_alias)
        if not config:
            return False

        # Check signature compatibility via metadata
        meta = self.store.read_meta(config, self.id_slot)
        if prefer_signature and meta and meta.get("model_signature") != prefer_signature:
            log.info("Restore skipped: signature mismatch for %s", self.current_alias)
            return False

        # Check bin exists
        if not self.store.bin_exists(config, self.id_slot):
            log.info("COLD START [%s] — no slot bin", self.current_alias)
            try:
                self.memory.log_swap(alias=self.current_alias, tokens_restored=0, restore_ms=0, cold_start=True)
            except Exception:
                pass
            return False

        # Validate checksum if available (detects binary corruption)
        if meta and meta.get("slot_checksum"):
            bin_path = self.store.bin_path(config, self.id_slot)
            if bin_path.exists():
                current_checksum = sha256_hex(bin_path.read_bytes())
                if current_checksum != meta["slot_checksum"]:
                    log.error("SLOT CORRUPTED [%s]: checksum mismatch (%s != %s)",
                              self.current_alias, current_checksum[:16], meta["slot_checksum"][:16])
                    self._invalidate_slot(config, "checksum mismatch")
                    return False

        # Attempt restore with retries
        filename = f"slot-{self.id_slot}.bin"
        timeout = self._get_slot_timeout()
        try:
            result = self.client.restore_slot(self.id_slot, filename, timeout=timeout)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            # Catch UTF-8 decode errors from corrupted metadata/bin
            log.error("SLOT CORRUPTED [%s]: decode error during restore: %s", self.current_alias, e)
            self._invalidate_slot(config, f"decode error: {e}")
            return False
        if result is not None:
            self._inc_stat("restores")
            # DIAGNOSTIC: log checkpoint file size alongside slot bin
            ckpt_path = self.store.slot_files(config, self.id_slot)["ckpt"]
            ckpt_total = 0
            ckpt_files = []
            if ckpt_path.exists() and ckpt_path.is_file():
                # PCLL format: single companion file (e.g. slot-0.bin.checkpoints)
                ckpt_total = ckpt_path.stat().st_size
                ckpt_files.append(f"{ckpt_path.name}:{ckpt_total/(1024*1024):.1f}MB")
            elif ckpt_path.exists() and ckpt_path.is_dir():
                # Future-proof: directory with multiple checkpoint files
                for f in ckpt_path.rglob("*"):
                    if f.is_file():
                        sz = f.stat().st_size
                        ckpt_total += sz
                        ckpt_files.append(f"{f.name}:{sz/(1024*1024):.1f}MB")
            bin_size = bin_path.stat().st_size / (1024*1024) if bin_path.exists() else 0
            log.info("CACHE HIT [%s]: %d tokens restored, bin=%.1fMiB, checkpoints=%.1fMiB(%d files: %s) (%.1fms)",
                     self.current_alias, result.get("n_restored", 0),
                     bin_size, ckpt_total/(1024*1024), len(ckpt_files),
                     ",".join(ckpt_files[:5]),
                     result.get("timings", {}).get("restore_ms", 0))
            try:
                self.memory.log_swap(
                    alias=self.current_alias,
                    tokens_restored=result.get("n_restored", 0),
                    restore_ms=result.get("timings", {}).get("restore_ms", 0),
                    cold_start=False,
                )
            except Exception:
                pass
            return True

        # Restore failed — invalidate corrupted slot to prevent retry loop
        log.error("SLOT RESTORE FAILED [%s] — invalidating", self.current_alias)
        self._invalidate_slot(config, "restore failed")
        return False

    def _invalidate_slot(self, config, reason: str) -> None:
        """Delete corrupted slot bin, metadata, AND checkpoints to force cold start.

        Checkpoints (.bin.checkpoints) contain incremental KV cache snapshots
        from llama-server's --ctx-checkpoints feature. If the slot bin is corrupted,
        these are also invalid and must be purged to prevent stale KV fragments
        from being applied on the next restore.
        """
        files = self.store.slot_files(config, self.id_slot)
        for key, path in files.items():
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                log.info("Invalidated slot %s: %s (%s)", key, path.name, reason)

    # ── Tool-Use & Delegation ──────────────────────────────────────────────

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a tool call for delegation. Returns {ok, result} dict."""
        import os
        if name not in self._allowed_tools:
            return {"error": f"Tool '{name}' not in whitelist"}
        try:
            if name in ("read", "read_file"):
                path = os.path.expanduser(args.get("path", args.get("file", "")))
                if not path:
                    return {"error": "Missing path"}
                with open(path, "r") as f:
                    content = f.read()
                # DIAGNOSTIC: log file size to track bloat sources
                log.info("READ: path=%s size=%d", path, len(content))
                return {"ok": True, "content": content}
            elif name == "grep":
                pattern = args.get("pattern", "")
                path = os.path.expanduser(args.get("path", "."))
                import subprocess
                result = subprocess.run(["grep", "-rn", "-e", pattern, path],
                                       capture_output=True, text=True, timeout=10)
                # DIAGNOSTIC: log grep output size
                log.info("GREP: pattern=%s path=%s stdout=%d", pattern[:40], path, len(result.stdout))
                return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}
            elif name == "find":
                path = os.path.expanduser(args.get("path", "."))
                query = args.get("query", "")
                import subprocess
                result = subprocess.run(["find", path, "-name", query],
                                       capture_output=True, text=True, timeout=10)
                # DIAGNOSTIC: log find output size
                log.info("FIND: path=%s query=%s stdout=%d", path, query, len(result.stdout))
                return {"ok": True, "stdout": result.stdout}
            elif name == "list_dir":
                path = os.path.expanduser(args.get("path", "."))
                try:
                    entries = os.listdir(path)
                    return {"ok": True, "entries": entries}
                except OSError as e:
                    return {"error": str(e)}
            elif name == "bash_ro":
                cmd = args.get("command", args.get("cmd", ""))
                if not cmd:
                    return {"error": "Missing command"}
                import subprocess
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                stdout_len = len(result.stdout)
                stderr_len = len(result.stderr)
                # DIAGNOSTIC: log command + output sizes to track bloat sources
                log.info("BASH_RO: cmd=%r stdout=%d stderr=%d", cmd[:80], stdout_len, stderr_len)
                return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}
            elif name == "write":
                path = os.path.expanduser(args.get("path", ""))
                content = args.get("content", "")
                if not path:
                    return {"error": "Missing path"}
                with open(path, "w") as f:
                    f.write(content)
                return {"ok": True, "message": f"Wrote {len(content)} bytes to {path}"}
            elif name in ("search_codebase", "web_search"):
                query = args.get("query", "")
                return {"ok": True, "result": f"Search for '{query}' (not fully implemented in delegation)"}
            elif name == "delegate_to":
                alias = args.get("alias", "")
                task = args.get("task", "")
                if not alias:
                    return {"error": "Missing alias"}
                return self._delegate({"alias": alias, "task": task, "timeout": 60})
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": f"Tool '{name}' failed: {e}"}

    def _filter_tool_calls(self, tool_calls: List[dict]) -> List[dict]:
        """Filter tool calls to only allow read-only tools (supervisor-side guard).

        Returns (allowed_calls, rejected_calls) tuple.
        """
        allowed = []
        rejected = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "unknown")
            if name in self._allowed_tools:
                allowed.append(tc)
            else:
                rejected.append(tc)
                log.warning("BLOCKED tool call: %s (not in read-only whitelist)", name)
        return allowed, rejected

    @staticmethod
    def _strip_reasoning_tags(content: str) -> str:
        """Strip reasoning/thinking/channel tags from a content string.

        Catches reasoning text leaked into the response body by models with
        reasoning enabled (Gemma, Nemotron, GPT-OSS, etc.). Handles:
        - DeepSeek format: <think>...</think>
        - Generic XML: <reasoning>...</reasoning>, <thinking>...</thinking>
        - Gemma channel tags: <|channel|>...<|/channel|>
        - GPT-OSS channel tags: <|channel|>final<|message|>...<|end|>

        For GPT-OSS: extracts content from the final channel block, discards analysis.
        For all others: strips tags and their contents, collapsing whitespace.
        Returns original string if no tags found.
        """
        import re
        if not content:
            return content

        # GPT-OSS: extract content from <|channel|>final<|message|>...<|end|>
        # If present, use only that block (discards analysis channel reasoning)
        final_match = re.search(
            r'<\|channel\|>final<\|message\|>(.*?)<\|end\|>',
            content, flags=re.DOTALL
        )
        if final_match:
            content = final_match.group(1)
        else:
            # No final channel — strip all GPT-OSS channel blocks
            # Pattern: <|channel|>analysis<|message|>...<|end|>
            content = re.sub(
                r'<\|channel\|>analysis<\|message\|>.*?<\|end\|>',
                '', content, flags=re.DOTALL
            )

        # Pattern: <think>...</think> (DeepSeek format, used by reasoning_format: deepseek)
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # Pattern: <reasoning>...</reasoning> or <thinking>...</thinking>
        content = re.sub(r'<(?:reasoning|thinking)>.*?</(?:reasoning|thinking)>', '', content, flags=re.DOTALL | re.IGNORECASE)
        # Pattern: <|channel|>...<|/channel|> (Gemma channel leak)
        content = re.sub(r'<\|channel\|>.*?<\|/channel\|>', '', content, flags=re.DOTALL)

        # Collapse any double+ whitespace left after stripping
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n[ \t]*\n[ \t]*\n', '\n\n', content)
        return content.strip()

    @staticmethod
    def _sanitize_message(msg: dict) -> None:
        """Strip reasoning content from a response message dict (in-place).

        Two leak vectors:
        1. reasoning_content field — separate field in DeepSeek-style responses
        2. Reasoning tags embedded in content — <|channel|>, <think>, etc.

        Both are removed so Pi never sees the model's internal reasoning.
        """
        # Remove reasoning_content field entirely
        if "reasoning_content" in msg:
            del msg["reasoning_content"]

        # Strip any reasoning/channel tags from content
        raw = msg.get("content", "") or ""
        cleaned = SlotSupervisor._strip_reasoning_tags(raw)
        if cleaned != raw:
            msg["content"] = cleaned

    def _build_default_reviewer_tools(self) -> List[dict]:
        """Build default read-only tool definitions for delegation."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Read a file's contents. Supports text files and images.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Path to the file"},
                            "offset": {"type": "number", "description": "Line to start from (1-indexed)"},
                            "limit": {"type": "number", "description": "Max lines to read"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "Search for a pattern in files using grep",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Search pattern"},
                            "path": {"type": "string", "description": "File or directory to search"},
                            "context": {"type": "number", "description": "Lines of context"}
                        },
                        "required": ["pattern", "path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find",
                    "description": "Find files matching a pattern",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory to search"},
                            "name": {"type": "string", "description": "Filename pattern"},
                            "type": {"type": "string", "description": "f=file, d=directory"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bash_ro",
                    "description": "Run a read-only bash command (ls, cat, head, tail, wc, du, file, stat)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The command to run"}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "description": "List directory contents",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory path"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "queries": {"type": "array", "items": {"type": "string"}, "description": "Search queries"}
                        },
                        "required": ["queries"]
                    }
                }
            }
        ]

    def _delegate(self, payload: dict) -> dict:
        """Delegate a task to another model in the council.

        Flow:
        1. Validate target alias
        2. Save current slot (chair) before any swap
        3. Swap to target model
        4. Run task (pass-through to Pi's tool loop)
        5. Swap back to original model
        6. Return reviewer's response

        Uses try/finally to guarantee swap-back even on error.
        """
        target_alias = payload.get("alias")
        task = payload.get("task")
        timeout = payload.get("timeout", 300)

        if not target_alias:
            return {"error": "Missing 'alias' field", "status": 400}
        if not task:
            return {"error": "Missing 'task' field", "status": 400}

        # Validate target alias exists
        if not self.registry.get(target_alias):
            return {"error": f"Unknown model alias: {target_alias}", "status": 404}

        # Guard against concurrent delegation (atomic check-and-set)
        with self._delegation_lock:
            with self._error_lock:
                if self._system_error:
                    return {"error": "System unstable — swap-back failed, manual reset required", "status": 503}
            if self._delegating:
                return {"error": "Delegation already in progress", "status": 409}
            if self._swapping:
                return {"error": "Swap in progress", "status": 409}
            self._delegating = True

        log.info("=== DELEGATION START: %s -> %s ===", self.current_alias, target_alias)
        log.info("DELEGATION: task length=%d chars, timeout=%d", len(task), timeout)

        original_alias = self.current_alias
        deleg_start = time.time()
        original_running = self.upstream.running()

        try:
            # Step 1: Save current slot BEFORE any swap (Nemotron critical fix)
            if original_running and self.current_alias:
                try:
                    with self._slot_lock:
                        self._save_current_slot()
                    # Log chair slot state
                    chair_config = self.registry.get_config(self.current_alias)
                    if chair_config:
                        chair_meta = self.store.read_meta(chair_config, self.id_slot)
                        if chair_meta and chair_meta.get("slot_tokens"):
                            log.info("DELEGATION: chair slot saved with %d tokens", chair_meta["slot_tokens"])
                    log.info("Saved chair slot before delegation to %s", target_alias)
                except Exception as e:
                    log.warning("Failed to save chair slot before delegation: %s", e)

            # Truncate task BEFORE swap — slot restore adds cached context we can't predict
            target_config = self.registry.get_config(target_alias)
            ctx_limit = target_config.ctx_size if target_config else 131072
            # Reserve: system prompt (~200) + completion (~2K) + slot restore (unknown, assume ~5K)
            reserved_tokens = 200 + 2048 + 5120
            max_task_tokens = ctx_limit - reserved_tokens
            max_task_chars = max_task_tokens * 4
            if len(task) > max_task_chars:
                log.warning("Delegation task truncated: %d chars → %d chars for %s (ctx=%d, reserved=%d)",
                            len(task), max_task_chars, target_alias, ctx_limit, reserved_tokens)
                task = task[:max_task_chars - 100] + "\n\n[TRUNCATED — task exceeded context limit]"

            # Step 2: Swap to target model
            self._swap_to(target_alias)

            # Step 3: Run task (pass-through to Pi's tool loop)
            # Build system prompt
            system_prompt = self._get_reviewer_system_prompt(target_alias)
            log.info("DELEGATION: system prompt length=%d chars", len(system_prompt))

            # Enhance task with anti-hallucination scoping (Gemma only)
            if "gemma" in target_alias.lower():
                task = self._scope_delegation_task(task, target_alias)

            task_payload = {
                "model": target_alias,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task},
                ],
            }
            log.info("DELEGATION: initial messages=[system(%d), user(%d)]", len(system_prompt), len(task))

            # Forward tools — always include read-only tools for reviewer access
            tools = payload.get("tools") or self._build_default_reviewer_tools()
            if tools:
                task_payload["tools"] = tools
                task_payload["tool_choice"] = "auto"  # let model decide when to use tools

            # Multi-turn tool-use loop — no hard round limit, controlled by 90% context budget
            # Track cumulative tokens for context budget awareness
            cumulative_tokens = 0
            model_config = self.registry.get_config(target_alias)
            ctx_limit = model_config.ctx_size if model_config else 120000
            response = None
            for _round in range(999):  # effectively unlimited — budget checks are the safety net
                # Pre-send budget check: cumulative_tokens is updated after each round's tool results
                # so it reflects the actual context size before the next request is sent.
                # Abort at 80% to leave headroom for the model's own completion.
                pre_send_threshold = int(ctx_limit * 0.80)
                if _round > 0 and cumulative_tokens > pre_send_threshold:
                    log.warning("Pre-send budget exceeded (round %d, %d/%d tokens, %.0f%%), forcing final answer",
                                _round, cumulative_tokens, ctx_limit, cumulative_tokens / ctx_limit * 100)
                    break

                # Lightweight size estimate — avoid deep-copy on every round
                n_msgs = len(task_payload.get("messages", []))
                remaining = ctx_limit - cumulative_tokens
                # DIAGNOSTIC: log per-message sizes in delegation context
                diag_sizes = []
                total_msg_chars = 0
                for mi, m in enumerate(task_payload.get("messages", [])):
                    mc = m.get("content", "")
                    mlen = len(str(mc))
                    total_msg_chars += mlen
                    diag_sizes.append(f"#{mi}:{m.get('role','?')}({mlen})")
                log.info("DELEG-ROUND[%d->%s]: %d msgs, %d chars, cum_tokens=%d, remaining=%d, sizes=[%s]",
                         _round, target_alias, n_msgs, total_msg_chars, cumulative_tokens, remaining,
                         ",".join(diag_sizes[:10]) + ("..." if len(diag_sizes) > 10 else ""))
                if log.isEnabledFor(logging.DEBUG):
                    import copy as _copy
                    _dp = _copy.deepcopy(task_payload)
                    for msg in _dp.get("messages", []):
                        c = msg.get("content", "")
                        if isinstance(c, str) and len(c) > 100:
                            msg["content"] = c[:100] + "..."
                    log.debug("Delegation round %d payload: %s", _round, json.dumps(_dp))
                try:
                    status, body = self.client.post_json(
                        "/v1/chat/completions", task_payload, timeout=timeout
                    )
                except Exception as e:
                    return {"error": f"Task execution failed: {e}", "status": 504}

                if status < 200 or status >= 300:
                    return {"error": f"Upstream returned {status}", "status": status}

                response = json.loads(body.decode("utf-8", errors="replace"))
                # Track actual token usage from upstream response
                # total_tokens = prompt_tokens + completion_tokens = current full context size
                # Replace (don't sum) — each round's total_tokens already includes all prior messages
                usage = response.get("usage", {})
                cumulative_tokens = usage.get("total_tokens", 0)

                tool_calls = response.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
                if not tool_calls:
                    break  # final response, no more tool calls

                # Context budget check — compact at 75% of ctx_size, hard stop at 90%
                remaining_after_round = ctx_limit - cumulative_tokens
                compaction_threshold = int(ctx_limit * 0.75)  # 75% of ctx
                hard_stop_threshold = int(ctx_limit * 0.90)   # 90% of ctx

                if cumulative_tokens > hard_stop_threshold:
                    log.warning("Context budget critical (%d/%d, %.0f%%), forcing final answer",
                                cumulative_tokens, ctx_limit, cumulative_tokens / ctx_limit * 100)
                    break

                if cumulative_tokens > compaction_threshold:
                    log.info("Delegation context at 75%%+ (%d/%d), injecting compaction prompt",
                             cumulative_tokens, ctx_limit)
                    task_payload["messages"].append({
                        "role": "system",
                        "content": (
                            "CONTEXT COMPACT REQUIRED: Your context is getting large. "
                            "Summarize your key findings so far in 5-10 bullet points. "
                            "Then continue with remaining tool calls. "
                            "Focus on: what you found, what's broken, what needs to change. "
                            "Keep the summary concise — it replaces the raw tool output you've already analyzed."
                        )
                    })

                # Advance warning at round 10 — give model a chance to wrap up
                # DISABLED: no hard round limit, model decides when it has enough
                # if _round >= 10:
                #     log.info("Delegation round %d: approaching tool limit, injecting warning", _round)
                #     task_payload["messages"].append({
                #         "role": "system",
                #         "content": f"You have {15 - _round - 1} more tool calls available. "
                #                    f"Synthesize your findings and provide the final answer before exhausting that tool limit."
                #     })

                # Final round (14) — strip tools to force a text response
                # DISABLED: no hard round limit
                if False:  # was: _round >= 14
                    log.info("Delegation round %d: forcing final answer, removing tools", _round)
                    task_payload.pop("tools", None)
                    task_payload.pop("tool_choice", None)
                    task_payload["messages"].append({
                        "role": "system",
                        "content": "STOP using tools. Synthesize all findings and provide your final answer now."
                    })

                # Append the assistant message with all tool calls
                # Strip reasoning tags to prevent leaking into conversation history
                assistant_content = SlotSupervisor._strip_reasoning_tags(
                    response.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                )
                task_payload["messages"].append({"role": "assistant", "content": assistant_content, "tool_calls": tool_calls})

                # Estimate token cost of assistant message we just appended (1 token ≈ 4 chars)
                _est_tokens = len(assistant_content) // 4 + len(json.dumps(tool_calls)) // 4
                cumulative_tokens += _est_tokens

                # Execute each tool call and append result to conversation
                _round_tool_tokens = 0
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    result = self._execute_tool(name, args)
                    result_json = json.dumps(result)
                    orig_size = len(result_json)
                    # Truncate oversized tool results to protect context budget
                    # Keep the start of the result (headers, imports, first lines) and trim the middle
                    max_tool_result = 30000
                    if len(result_json) > max_tool_result:
                        half = max_tool_result // 2
                        result_json = result_json[:half] + f"\n\n[TRUNCATED — {orig_size} total chars, {orig_size - max_tool_result} chars removed from middle]\n\n" + result_json[-half:]
                        log.info("Truncated tool '%s' result: %d → %d chars", name, orig_size, len(result_json))
                    # DIAGNOSTIC: log tool result size per round
                    log.info("DELEG-TOOL[%d->%s]: %s result=%d chars (after trunc=%d), cum_msgs=%d",
                             _round, target_alias, name, orig_size, len(result_json),
                             len(task_payload.get("messages", [])) + 1)
                    task_payload["messages"].append({"role": "tool", "content": result_json, "tool_call_id": tc.get("id", "")})
                    _round_tool_tokens += len(result_json) // 4
                cumulative_tokens += _round_tool_tokens
            else:
                log.warning("Tool-use loop exceeded 999 rounds for delegation — should not happen")
                # response already holds last round's output

            # Force text response if loop exited with tool_calls still pending
            finish_reason = response.get("choices", [{}])[0].get("finish_reason", "")
            if finish_reason == "tool_calls":
                log.info("Delegation ended with tool_calls — forcing final text response")
                task_payload.pop("tools", None)
                task_payload.pop("tool_choice", None)
                task_payload["messages"].append({
                    "role": "system",
                    "content": "STOP using tools. Synthesize all findings and provide your final answer now."
                })
                try:
                    status, body = self.client.post_json(
                        "/v1/chat/completions", task_payload, timeout=timeout
                    )
                    if status >= 200 and status < 300:
                        response = json.loads(body.decode("utf-8", errors="replace"))
                except Exception as e:
                    log.warning("Force-final response failed: %s — using last tool-call response", e)

            # DIAGNOSTIC: final delegation context summary
            final_n_msgs = len(task_payload.get("messages", []))
            final_total_chars = sum(len(str(m.get("content", ""))) for m in task_payload.get("messages", []))
            log.info("DELEG-DONE[%s]: %d rounds, %d msgs, %d chars total, cumulative_tokens=%d",
                     target_alias, _round + 1, final_n_msgs, final_total_chars, cumulative_tokens)

            # Step 4: Filter tool calls + strip reasoning content
            rejected_tools = []
            try:
                msg = response.get("choices", [{}])[0].get("message", {})
                self._sanitize_message(msg)

                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    allowed, rejected = self._filter_tool_calls(tool_calls)
                    if rejected:
                        log.warning("Delegation to %s: %d tool calls blocked", target_alias, len(rejected))
                        rejected_tools = [tc.get("function", {}).get("name", "unknown") for tc in rejected]
                    response["choices"][0]["message"]["tool_calls"] = allowed
            except Exception as e:
                log.warning("Failed to post-process delegation response: %s", e)

            # Save target model's slot after task
            try:
                with self._slot_lock:
                    self._save_current_slot()
            except Exception as e:
                log.warning("Failed to save target slot after delegation: %s", e)

            # Extract response content for archival
            resp_msg = response.get("choices", [{}])[0].get("message", {})
            resp_content = resp_msg.get("content", "")
            chain_id = payload.get("chain_id", f"deleg-{int(time.time())}")
            role = payload.get("role", "reviewer")
            batch_num = payload.get("batch", 0)
            retry_num = payload.get("retry", 0)
            if resp_content:
                try:
                    saved_deleg_path = self.memory.save_delegation_response(
                        chain_id=chain_id,
                        role=role,
                        alias=target_alias,
                        batch=batch_num,
                        retry=retry_num,
                        content=resp_content,
                        task=task,
                    )
                    # Auto-index delegation review for vector recall (fire-and-forget, threaded)
                    threading.Thread(
                        target=self.memory._auto_index_file,
                        args=(saved_deleg_path,),
                        daemon=True,
                    ).start()
                except Exception as e:
                    log.warning("Failed to save delegation response: %s", e)

            result: dict = {
                "alias": target_alias,
                "status": 200,
                "response": response,
            }
            if rejected_tools:
                result["blocked_tool_calls"] = rejected_tools
            log.info("=== DELEGATION SUCCESS: %s -> %s ===", original_alias, target_alias)
            try:
                self.memory.log_delegation(
                    from_alias=original_alias or "none",
                    to_alias=target_alias,
                    task_len=len(task),
                    result_status=200,
                    duration_ms=(time.time() - deleg_start) * 1000,
                    swap_back_ok=True,
                )
            except Exception:
                pass
            return result

        except Exception as e:
            log.error("=== DELEGATION FAILED: %s -> %s: %s ===", original_alias, target_alias, e)
            try:
                self.memory.log_delegation(
                    from_alias=original_alias or "none",
                    to_alias=target_alias,
                    task_len=len(task) if task else 0,
                    result_status=500,
                    duration_ms=(time.time() - deleg_start) * 1000,
                    swap_back_ok=False,
                )
            except Exception:
                pass
            return {"error": f"Delegation failed: {e}", "status": 500}

        finally:
            # ── Delegation flag reset: unconditionally first — never leave True on exit ──
            self._delegating = False

            # Step 5: ALWAYS swap back to original model (Gemma/Nemotron critical fix)
            if original_alias and self.current_alias != original_alias:
                log.info("=== DELEGATION SWAP-BACK: %s -> %s ===", self.current_alias, original_alias)
                try:
                    self._swap_to(original_alias)
                    log.info("Restored chair slot after delegation")
                    chair_config = self.registry.get_config(original_alias)
                    if chair_config:
                        chair_meta = self.store.read_meta(chair_config, self.id_slot)
                        if chair_meta and chair_meta.get("slot_tokens"):
                            log.info("DELEGATION: chair slot after swap-back: %d tokens", chair_meta["slot_tokens"])
                except Exception as e:
                    # Unified recovery path — handles both decode errors and general failures.
                    # Decode errors also trigger slot invalidation to prevent retry loops.
                    log.error("Failed to restore chair after delegation: %s", e)
                    if isinstance(e, (UnicodeDecodeError, json.JSONDecodeError)):
                        chair_config = self.registry.get_config(original_alias)
                        if chair_config:
                            self._invalidate_slot(chair_config, f"swap-back decode error: {e}")
                    # Clear stale state so next request triggers fresh start
                    self.current_alias = None
                    self.current_signature = None
                    try:
                        self._swap_to(original_alias)
                        log.info("Recovery swap to %s succeeded", original_alias)
                    except Exception as e2:
                        log.error("Recovery swap also failed: %s — marking system unstable", e2)
                        with self._error_lock:
                            self._system_error = True
                        self._start_recovery()

    def _get_reviewer_system_prompt(self, alias: str) -> str:
        """Get system prompt for a reviewer model."""
        model_info = self.registry.get(alias)
        if not model_info:
            return "You are a code reviewer."

        notes = model_info.extra.get("chat_defaults", {}).get("notes", "")
        base = "You are a code reviewer and analyst. You can READ files but cannot EDIT them. "
        base += "Your job is to analyze code, logs, and configurations and provide feedback. "
        base += "Be specific: cite file paths and line numbers. "
        base += "Flag real issues, don't over-flag style preferences. "
        base += "If you're unsure, say so — don't hallucinate. "
        base += "\n\n=== TOOL USAGE (AVAILABLE, NOT MANDATORY) ===\n"
        base += "You have access to read-only tools if you need to examine files:\n"
        base += "- Use 'read' to examine source code files when the task references specific files\n"
        base += "- Use 'grep' to search for patterns, function names, or error messages\n"
        base += "- Use 'find' or 'list_dir' to locate relevant files\n"
        base += "- Use 'bash_ro' for quick commands (ls, tail, wc, head, stat, file)\n"
        base += "- Use 'web_search' when you need external documentation or recent info\n"
        base += "- If the task already provides the code/text to review, analyze it directly — no tools needed\n"
        base += "- If the task asks you to review files, use tools to read them first\n"
        base += "- If you're unsure whether tools are needed, provide your analysis as text\n"
        base += "\n\n=== TOOL USE STRATEGY ===\n"
        base += "Use tools liberally but efficiently:\n"
        base += "- Read files you actually need — don't skip reading because you're worried about context\n"
        base += "- Use grep/find FIRST to narrow scope, then read specific files with line ranges\n"
        base += "- Prefer targeted reads (offset/limit) over full-file reads when files are large\n"
        base += "- If a tool result is truncated, re-read the section you need with offset/limit\n"
        base += "- Don't hoard tool calls — if you have enough info to answer, write your final response\n"
        base += "- Your context budget is ~131K tokens. At 75% (~98K), the system will auto-compact.\n"
        base += "  Compact by summarizing findings and dropping raw tool output you've already analyzed.\n"
        base += "\n\n=== WHEN TO STOP ===\n"
        base += "After gathering enough information (typically 5-10 tool calls for thorough reviews),\n"
        base += "produce your FINAL analysis as a text response. Do NOT keep calling tools.\n"
        base += "Your final answer must be a complete, structured review with findings and severity levels.\n"
        base += "==========================================="

        # Gemma-specific: channel leak + anti-hallucination
        if "gemma" in alias.lower() or "gemma" in notes.lower():
            base += "\n\n=== ANTI-HALLUCINATION RULES (MANDATORY) ===\n"
            base += "1. Review ONLY the specific lines/files mentioned in the task.\n"
            base += "2. Do NOT reference code outside the specified range.\n"
            base += "3. If a function/variable is not visible in the given range, say 'not visible in this range' — do NOT infer its existence.\n"
            base += "4. Never assume code exists that you haven't read.\n"
            base += "5. If the task lacks line ranges, read the full file first, then scope your review to what you actually see.\n"
            base += "==========================================="
            base += "\n\n=== OUTPUT FORMAT (STRICT) ===\n"
            base += "CRITICAL: Do NOT output <|channel|> tags or any XML-style markers.\n"
            base += "Write ONLY clean markdown. No thinking tags, no channel markers, no XML wrappers.\n"
            base += "If you need to reason, do it silently — output only the final analysis.\n"
            base += "==========================================="

        if notes:
            base += f"\n\nModel notes: {notes}"
        return base

    def _scope_delegation_task(self, task: str, alias: str) -> str:
        """Add anti-hallucination scoping instructions to delegation tasks.

        Detects file references and line ranges in the task text, then appends
        structured scoping rules. If no file/range is detected, adds a generic
        'read before reviewing' instruction.

        Returns the enhanced task string.
        """
        import re

        # Pattern: file_path:line or file_path:line1-line2 or file_path lines X-Y
        file_range_pattern = re.compile(
            r'([\w\-/\.]+(?:\.[a-zA-Z]+))\s*[:\s]*(?:lines?\s*)?(\d+)\s*[-–]\s*(\d+)',
            re.IGNORECASE
        )
        # Pattern: file_path:line (single line)
        file_line_pattern = re.compile(
            r'([\w\-/\.]+(?:\.[a-zA-Z]+))\s*[:\s]*(?:lines?\s*)?(\d+)',
            re.IGNORECASE
        )
        # Pattern: just file references
        file_pattern = re.compile(
            r'([\w\-/\.]+(?:\.[a-zA-Z]+))',
            re.IGNORECASE
        )

        # Check for explicit line ranges
        ranges = file_range_pattern.findall(task)
        if ranges:
            scope_lines = []
            for filepath, start, end in ranges:
                scope_lines.append(
                    f"- Review ONLY lines {start}–{end} of `{filepath}`. "
                    f"Do NOT reference code outside these lines."
                )
            scope_block = (
                "\n\n--- SCOPE CONSTRAINTS (MANDATORY) ---\n"
                "You must review ONLY the lines/files specified below:\n"
            ) + "\n".join(scope_lines)
            scope_block += (
                "\n\nIf a function or variable is not visible in the specified range, "
                'say "not visible in this range" — do NOT infer its existence.'
            )
            return task + scope_block

        # Check for single-line references
        single_lines = file_line_pattern.findall(task)
        # Filter: only keep if it looks like a real line number (> 10 to avoid false positives)
        valid_singles = [(f, l) for f, l in single_lines if int(l) > 10]
        if valid_singles:
            scope_lines = []
            for filepath, line in valid_singles:
                scope_lines.append(
                    f"- Focus on line {line} of `{filepath}`. "
                    f"Read surrounding context (±20 lines) but do NOT review unrelated sections."
                )
            scope_block = (
                "\n\n--- SCOPE CONSTRAINTS (MANDATORY) ---\n"
                "You must focus on the specific lines mentioned below:\n"
            ) + "\n".join(scope_lines)
            scope_block += (
                "\n\nIf a function or variable is not visible in the specified range, "
                'say "not visible in this range" — do NOT infer its existence.'
            )
            return task + scope_block

        # Check for file references without line numbers
        files = file_pattern.findall(task)
        # Deduplicate and filter common false positives
        seen = set()
        unique_files = []
        for f in files:
            if f.lower() not in seen and not f.startswith('.'):
                seen.add(f.lower())
                unique_files.append(f)

        if unique_files:
            file_list = "\n".join(f"  - `{f}`" for f in unique_files[:5])  # limit to 5 files
            scope_block = (
                f"\n\n--- SCOPE CONSTRAINTS (MANDATORY) ---\n"
                f"Review ONLY these files (read them fully before analyzing):\n"
                f"{file_list}\n\n"
                f"Do NOT reference code outside these files.\n"
                f"If a function or variable is not visible in these files, "
                f'say "not visible in this range" — do NOT infer its existence.'
            )
            return task + scope_block

        # No file/range detected — add generic anti-hallucination reminder
        generic_scope = (
            "\n\n--- REVIEW SCOPE ---\n"
            "Read the relevant files fully before providing analysis.\n"
            "Do NOT reference code you haven't read.\n"
            "If something is unclear, say so — do NOT guess."
        )
        return task + generic_scope

    # ── Restart Management ─────────────────────────────────────────────────

    def _log_restart(self, phase: str, message: str, ok: bool = True) -> None:
        """Log a restart progress message."""
        entry = {
            "phase": phase,
            "message": message,
            "ok": ok,
            "timestamp": time.time(),
        }
        self._restart_log.append(entry)
        level = log.info if ok else log.error
        level("[RESTART %s] %s", phase, message)

    def _restart_upstream(self, payload: dict) -> dict:
        """Gracefully restart the upstream llama-server process.

        Flow:
        1. Acquire restart lock (block concurrent restarts)
        2. Save current slot before stopping upstream
        3. Stop upstream llama-server
        4. Wait for process to exit
        5. Clear failure backoff (fresh start)
        6. Start upstream llama-server with current model
        7. Wait for upstream to become healthy
        8. Restore current slot (if slot was saved)

        Returns progress log with all phases and their status.
        """
        with self._restart_lock:
            if self._restarting:
                return {"error": "Restart already in progress", "status": 409, "log": self._restart_log}
            self._restarting = True
            self._restart_log = []  # clear previous log

            try:
                # Phase 1: Pre-check
                self._log_restart("pre-check", "Starting upstream restart")

                # Save current slot before stopping
                slot_saved = False
                if self.upstream.running() and self.current_alias:
                    try:
                        self._save_current_slot()
                        slot_saved = True
                        self._log_restart("pre-check", f"Saved slot for {self.current_alias}")
                    except Exception as e:
                        self._log_restart("pre-check", f"Failed to save slot: {e}", ok=False)

                # Phase 2: Stop upstream
                self._log_restart("stop", "Stopping llama-server")
                try:
                    self.upstream.stop()
                    self._log_restart("stop", "llama-server stopped")
                except Exception as e:
                    self._log_restart("stop", f"Error stopping: {e}", ok=False)

                # upstream.stop() already waits up to 10s for the process to exit.
                # Only poll here if stop() itself raised (covered by the except above).
                if self.upstream.running():
                    self._log_restart("wait-exit", "Process still running after stop() — waiting up to 5s")
                    deadline = time.time() + 5
                    while self.upstream.running() and time.time() < deadline:
                        time.sleep(0.25)
                    if self.upstream.running():
                        self._log_restart("wait-exit", "Process still running after extended wait", ok=False)
                    else:
                        self._log_restart("wait-exit", "Process exited")
                else:
                    self._log_restart("wait-exit", "Process exited")

                # Phase 3: Clear failures
                self._failures.clear()
                self._log_restart("clear-failures", "Cleared failure backoff")

                # Phase 4: Start upstream with current model
                if self.current_alias:
                    config = self.registry.get_config(self.current_alias)
                    if config:
                        self._log_restart("start", f"Starting llama-server with {self.current_alias}")
                        try:
                            self.upstream.start(config, self.slot_dir)
                            self._log_restart("start", "llama-server started")
                        except Exception as e:
                            self._log_restart("start", f"Error starting: {e}", ok=False)
                            return {"error": f"Failed to start upstream: {e}", "status": 500, "log": self._restart_log}
                    else:
                        self._log_restart("start", f"No config for {self.current_alias}", ok=False)
                        return {"error": f"No config for {self.current_alias}", "status": 500, "log": self._restart_log}
                else:
                    self._log_restart("start", "No current alias — cold start")

                # Phase 5: Wait for healthy
                self._log_restart("wait-healthy", "Waiting for upstream to become healthy")
                timeout = 30
                start = time.time()
                while (time.time() - start) < timeout:
                    try:
                        status, body = self.client.get("/health", timeout=5)
                        if status == 200:
                            self._log_restart("wait-healthy", "Upstream is healthy")
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                else:
                    self._log_restart("wait-healthy", "Upstream not healthy after timeout", ok=False)
                    return {"error": "Upstream not healthy after restart", "status": 500, "log": self._restart_log}

                # Phase 6: Restore slot
                if slot_saved:
                    self._log_restart("restore", f"Restoring slot for {self.current_alias}")
                    try:
                        self._restore_current_slot()
                        self._log_restart("restore", "Slot restored")
                    except Exception as e:
                        self._log_restart("restore", f"Failed to restore slot: {e}", ok=False)

                # Phase 7: Clear system error flag + stop recovery thread
                self._recovery_stop_event.set()
                with self._error_lock:
                    self._system_error = False
                self._log_restart("complete", "Restart complete")

                return {"status": 200, "message": "Restart complete", "log": self._restart_log}

            except Exception as e:
                self._log_restart("error", f"Unexpected error: {e}", ok=False)
                return {"error": f"Restart failed: {e}", "status": 500, "log": self._restart_log}
            finally:
                self._restarting = False

    def _restart_supervisor(self, payload: dict) -> dict:
        """Restart the supervisor process itself (not just upstream).

        Forks a new supervisor process with the same args, saves slot,
        stops upstream, then exits. Use after code/config changes.
        """
        with self._restart_lock:
            if self._restarting:
                return {"error": "Restart already in progress", "status": 409}
            self._restarting = True

            try:
                # Save current slot before shutdown
                if self.upstream.running() and self.current_alias:
                    try:
                        self._save_current_slot()
                        log.info("Saved slot %s before supervisor restart", self.current_alias)
                    except Exception as e:
                        log.warning("Failed to save slot before restart: %s", e)

                # Stop upstream
                try:
                    self.upstream.stop()
                    log.info("Upstream stopped for supervisor restart")
                except Exception as e:
                    log.warning("Error stopping upstream: %s", e)

                # Brief pause to let upstream release port + flush file descriptors
                time.sleep(1)

                # Stop recovery thread before process replacement
                self._recovery_stop_event.set()

                # Fork new supervisor with same arguments
                new_args = sys.argv[:]
                log.info("Forking new supervisor process with args: %s", new_args)
                try:
                    os.execv(sys.executable, [sys.executable] + new_args)
                except Exception as e:
                    log.error("Failed to exec new supervisor: %s", e)
                    self._restarting = False
                    return {"error": f"Fork failed: {e}", "status": 500}

                # execv doesn't return on success, but just in case
                return {"status": 200, "message": "Supervisor restarting"}

            except Exception as e:
                self._restarting = False
                return {"error": f"Supervisor restart failed: {e}", "status": 500}

    # ── Model Validation ───────────────────────────────────────────────────

    def invalidate_model(self, alias: str, reason: str) -> None:
        """Invalidate (purge) slot bins for a model alias."""
        config = self.registry.get_config(alias)
        if not config:
            log.warning("Cannot invalidate %s — no config found", alias)
            return
        slot_path = config.slot_dir(self.slot_dir)
        if slot_path.exists():
            log.info("INVALIDATING %s — %s", slot_path, reason)
            shutil.rmtree(slot_path)
        # Purge sibling config-hash dirs for same model
        model_dir = slot_path.parent
        if model_dir.exists():
            for sibling in model_dir.iterdir():
                if sibling.is_dir():
                    log.info("  Purging sibling: %s", sibling.name)
                    shutil.rmtree(sibling)

    # ── Request Handling ───────────────────────────────────────────────────

    def _normalize_messages(self, messages: List[dict]) -> List[dict]:
        """Merge consecutive same-role messages to prevent Jinja alternation errors.

        Handles cases where Pi's auto-compaction, model-switch, or other code paths
        produce malformed sequences like [user, user] or [assistant, assistant].

        See Pi issue #4197 and Unsloth template alternation check.
        """
        if not messages or len(messages) < 2:
            return messages

        normalized: List[dict] = [dict(messages[0])]
        for msg in messages[1:]:
            prev = normalized[-1]
            if msg.get("role") == prev.get("role"):
                # Merge content
                prev_content = prev.get("content") or ""
                msg_content = msg.get("content") or ""
                if isinstance(prev_content, list) and isinstance(msg_content, list):
                    # Array content (e.g., [{type: "text", text: "..."}])
                    merged = list(prev_content)
                    for block in msg_content:
                        if block not in merged:
                            merged.append(block)
                    prev["content"] = merged
                elif isinstance(prev_content, str) and isinstance(msg_content, str):
                    # String content — concatenate
                    prev["content"] = prev_content + "\n" + msg_content
                elif isinstance(msg_content, str):
                    prev["content"] = str(prev_content) + "\n" + msg_content
                else:
                    prev["content"] = prev_content or msg_content

                # Merge tool_calls if present
                prev_calls = prev.get("tool_calls") or []
                msg_calls = msg.get("tool_calls") or []
                if prev_calls or msg_calls:
                    prev["tool_calls"] = list(prev_calls) + list(msg_calls)
            else:
                normalized.append(dict(msg))
        return normalized

    # ── Sequential Delegation Chain ───────────────────────────────────────

    def _delegate_chain(self, plan: dict, task_context: str = "") -> dict:
        """Execute a multi-step delegation chain with batched swaps.

        The chair creates a step plan, then this method executes each batch:
          1. Swap to coder → execute batch of steps
          2. Swap to reviewer → validate batch
          3. If review fails, retry with feedback (up to max_retries)
          4. If still failing, abort chain
          5. Swap back to chair when done

        Args:
            plan: Step plan dict with keys: chain_id, steps[], batch_size,
                  coder_alias, reviewer_alias, max_retries
            task_context: Original user request / codebase context
        """
        chain_id = plan.get("chain_id", f"chain-{int(time.time())}")
        steps = plan.get("steps", [])
        if not steps:
            return {"status": 400, "error": "No steps in plan"}

        batch_size = plan.get("batch_size", 3)
        coder_alias = plan.get("coder_alias", "specialist-coder")
        reviewer_alias = plan.get("reviewer_alias", "reviewer-logic")
        max_retries = plan.get("max_retries", 1)

        # Validate aliases exist
        if not self.registry.get_config(coder_alias):
            return {"status": 404, "error": f"Coder alias '{coder_alias}' not found"}
        if not self.registry.get_config(reviewer_alias):
            return {"status": 404, "error": f"Reviewer alias '{reviewer_alias}' not found"}

        results = []
        original_alias = self.current_alias
        chain_start = time.time()

        self.memory.log_event("chain-start",
            f"{chain_id}: {len(steps)} steps, batch={batch_size}, "
            f"coder={coder_alias}, reviewer={reviewer_alias}")

        try:
            for batch_start in range(0, len(steps), batch_size):
                batch = steps[batch_start:batch_start + batch_size]
                batch_ids = [s.get("id", batch_start + i) for i, s in enumerate(batch)]

                # ── Phase 1: Execute batch with coder ──
                coder_prompt = self._chain_coder_prompt(batch, results, task_context)
                coder_result = self._delegate({
                    "alias": coder_alias,
                    "task": coder_prompt,
                    "timeout": 120,
                    "chain_id": chain_id,
                    "role": "coder",
                    "batch": batch_start,
                    "retry": 0,
                })

                if isinstance(coder_result, dict) and coder_result.get("status") == 500:
                    self.memory.log_event("chain-abort",
                        f"{chain_id}: coder failed on steps {batch_ids}")
                    return {
                        "status": 500,
                        "chain_id": chain_id,
                        "error": f"Coder failed on steps {batch_ids}",
                        "completed_steps": [r["step_id"] for r in results],
                        "results": results,
                    }

                # ── Phase 2: Validate batch with reviewer ──
                review_prompt = self._chain_review_prompt(batch, coder_result, task_context)
                review_result = self._delegate({
                    "alias": reviewer_alias,
                    "task": review_prompt,
                    "timeout": 90,
                    "chain_id": chain_id,
                    "role": "reviewer",
                    "batch": batch_start,
                    "retry": 0,
                })
                verdict = self._chain_parse_verdict(review_result)

                # ── Phase 3: Retry loop if review failed ──
                retry_count = 0
                while not verdict["passed"] and retry_count < max_retries:
                    retry_count += 1
                    self.memory.log_event("chain-retry",
                        f"{chain_id}: steps {batch_ids} retry {retry_count}/{max_retries}")

                    retry_prompt = self._chain_retry_prompt(
                        batch, coder_result, verdict["feedback"], task_context)
                    coder_result = self._delegate({
                        "alias": coder_alias,
                        "task": retry_prompt,
                        "timeout": 120,
                        "chain_id": chain_id,
                        "role": "coder",
                        "batch": batch_start,
                        "retry": retry_count,
                    })
                    review_result = self._delegate({
                        "alias": reviewer_alias,
                        "task": self._chain_review_prompt(batch, coder_result, task_context),
                        "timeout": 90,
                        "chain_id": chain_id,
                        "role": "reviewer",
                        "batch": batch_start,
                        "retry": retry_count,
                    })
                    verdict = self._chain_parse_verdict(review_result)

                # ── Record batch outcome ──
                if verdict["passed"]:
                    for step in batch:
                        results.append({
                            "step_id": step.get("id", "?"),
                            "status": "passed" if retry_count == 0 else "passed_after_retry",
                            "retries": retry_count,
                        })
                    self.memory.log_event("chain-batch-ok",
                        f"{chain_id}: steps {batch_ids} passed"
                        + (f" (after {retry_count} retries)" if retry_count else ""))
                else:
                    # Abort chain — review failed after all retries
                    self.memory.log_event("chain-abort",
                        f"{chain_id}: steps {batch_ids} failed after {max_retries} retries")
                    return {
                        "status": 422,
                        "chain_id": chain_id,
                        "error": f"Review failed on steps {batch_ids}: {verdict['feedback'][:200]}",
                        "completed_steps": [r["step_id"] for r in results],
                        "failed_steps": batch_ids,
                        "results": results,
                    }

            # All steps completed
            elapsed = time.time() - chain_start
            self.memory.log_event("chain-done",
                f"{chain_id}: {len(results)}/{len(steps)} steps in {elapsed:.0f}s")

            return {
                "status": 200,
                "chain_id": chain_id,
                "completed_steps": len(results),
                "total_steps": len(steps),
                "elapsed_seconds": round(elapsed, 1),
                "results": results,
            }

        except Exception as e:
            log.error("CHAIN %s failed: %s", chain_id, e)
            self.memory.log_event("chain-error", f"{chain_id}: {e}")
            return {
                "status": 500,
                "chain_id": chain_id,
                "error": str(e),
                "completed_steps": [r["step_id"] for r in results],
                "results": results,
            }
        finally:
            if original_alias and self.current_alias != original_alias:
                try:
                    self._swap_to(original_alias)
                except Exception as e:
                    log.error("CHAIN swap-back failed: %s", e)

    def _chain_coder_prompt(self, batch: list, previous: list, context: str) -> str:
        """Build coder prompt with step descriptions + prior step context."""
        prior = ""
        if previous:
            prior = "\n\nPreviously completed steps:\n" + "\n".join(
                f"- Step {r['step_id']}: {r['status']}" for r in previous)

        steps_desc = "\n".join(
            f"Step {s.get('id', '?')}: {s.get('description', '')}\n"
            f"  Files: {', '.join(s.get('files', ['(unspecified)']))}"
            for s in batch)

        return (
            f"Execute these refactoring steps precisely. "
            f"Output the complete modified file contents for each file.\n\n"
            f"Context:\n{context}\n\n"
            f"Steps to execute:\n{steps_desc}"
            f"{prior}"
        )

    def _chain_review_prompt(self, batch: list, coder_result, context: str) -> str:
        """Build reviewer prompt with validation criteria + coder output."""
        validations = "\n".join(
            f"Step {s.get('id', '?')}: {s.get('validation', 'Verify correctness')}"
            for s in batch)

        coder_text = str(coder_result.get("content", coder_result)
                         if isinstance(coder_result, dict) else coder_result)

        return (
            f"Review this code change for correctness.\n\n"
            f"Validation criteria:\n{validations}\n\n"
            f"Code output to review:\n{coder_text[:8000]}\n\n"
            f"Respond with EXACTLY one of:\n"
            f"PASS: <brief reason>\n"
            f"FAIL: <specific issues found>"
        )

    def _chain_retry_prompt(self, batch: list, coder_result, feedback: str, context: str) -> str:
        """Build retry prompt with reviewer feedback."""
        base = self._chain_coder_prompt(batch, [], context)
        coder_text = str(coder_result.get("content", coder_result)
                         if isinstance(coder_result, dict) else coder_result)
        return (
            f"{base}\n\n"
            f"IMPORTANT: Your previous attempt was rejected by the reviewer.\n"
            f"Reviewer feedback:\n{feedback}\n\n"
            f"Your previous output (fix the issues):\n{coder_text[:4000]}"
        )

    def _chain_parse_verdict(self, review_result) -> dict:
        """Parse reviewer output into {passed: bool, feedback: str}.

        _delegate returns: {alias, status, response: {choices: [{message: {content, tool_calls}}]}}
        So content lives at review_result["response"]["choices"][0]["message"]["content"].
        Falls back through nested paths for robustness.
        """
        if isinstance(review_result, dict):
            # Primary path: delegation response structure
            resp = review_result.get("response", {})
            choices = resp.get("choices", [])
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
            else:
                # Fallback: direct choices (legacy / non-delegation path)
                choices = review_result.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                else:
                    content = review_result.get("content", str(review_result))
        else:
            content = str(review_result)
        passed = content.strip().upper().startswith("PASS")
        return {"passed": passed, "feedback": content}

    # ── Request Handling ──────────────────────────────────────────────────

    def _prepare_payload(self, alias: str, base_payload: dict) -> dict:
        """Apply per-model chat_defaults to a payload copy.

        Shared between handle_chat_completion and TinyCouncilManager.
        """
        model_info = self.registry.get(alias)
        if not model_info:
            raise KeyError(f"Unknown model alias: {alias}")

        payload = dict(base_payload)
        payload["model"] = alias
        payload.setdefault("cache_prompt", True)
        payload.setdefault("id_slot", self.id_slot)
        payload.setdefault("stream", False)

        # Apply per-model chat_defaults
        chat_defaults = model_info.extra.get("chat_defaults", {})
        overrides = chat_defaults.get("request_overrides", {})
        if overrides:
            min_tokens = overrides.get("min_max_tokens")
            if min_tokens and payload.get("max_tokens", 0) < min_tokens:
                payload["max_tokens"] = min_tokens
            for k, v in overrides.items():
                if k != "min_max_tokens":
                    payload.setdefault(k, v)

        template_kwargs = chat_defaults.get("template_kwargs", {})
        if template_kwargs:
            payload["chat_template_kwargs"] = {
                k: v if isinstance(v, bool) else str(v)
                for k, v in template_kwargs.items()
            }

        return payload

    def handle_chat_completion(self, payload: dict) -> Tuple[int, bytes]:
        req_start = time.time()
        tokens_before = self._last_n_saved
        messages = payload.get("messages") or []
        model_alias = payload.get("model") or self.current_alias
        if not model_alias:
            # Fallback to config default_alias if nothing else is set
            model_alias = self._get_default_alias()
        if not model_alias:
            raise ValueError("Request missing model")

        self._inc_stat("total_requests")

        # Pre-flight: check system state
        if self._restarting:
            raise RuntimeError("Upstream restarting — please retry in a few seconds")
        with self._error_lock:
            if self._system_error:
                raise RuntimeError("System unstable — swap-back failed, manual reset required")

        try:
            self._swap_to(model_alias)
        except RuntimeError as e:
            # Upstream crashed — include backoff info in response
            delay = self._backoff_delay(model_alias)
            self._inc_stat("errors")
            raise RuntimeError(
                f"Model '{model_alias}' unavailable: {e}. "
                f"Retry in {delay:.1f}s."
            ) from e

        # Pre-flight: verify upstream is alive (catches post-swap crashes)
        if not self.upstream.running():
            self._inc_stat("errors")
            raise RuntimeError(
                f"Model '{model_alias}' upstream process died — "
                f"likely OOM during swap. Check VRAM headroom."
            )

        # Forward to upstream (with tools pass-through)
        payload = self._prepare_payload(model_alias, payload)

        # Normalize messages: merge consecutive same-role messages to prevent
        # Jinja alternation errors (e.g., auto-compaction + model-switch creating
        # duplicate user messages). See Pi issue #4197.
        payload["messages"] = self._normalize_messages(payload.get("messages", []))

        # DIAGNOSTIC: log incoming message sizes to track context bloat source
        diag_parts = []
        total_chars = 0
        for i, msg in enumerate(payload.get("messages", [])):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                charlen = sum(len(str(c.get("text", ""))) for c in content)
            else:
                charlen = len(str(content))
            total_chars += charlen
            diag_parts.append(f"#{i}:{role}({charlen})")
        log.info("CHAT-IN [%s]: %d msgs, %d chars total, %s",
                 model_alias, len(diag_parts), total_chars, ", ".join(diag_parts[:8]) + ("..." if len(diag_parts) > 8 else ""))

        # Pass-through tools field for Pi's tool loop
        if "tools" in payload:
            # Filter tool calls to only allow read-only tools
            pass  # Tools are validated by Pi's extension; supervisor just forwards

        try:
            status, body = self.client.post_json("/v1/chat/completions", payload, timeout=DEFAULT_TIMEOUT_CHAT)
        except Exception as e:
            self._inc_stat("errors")
            raise RuntimeError(f"Upstream request failed: {e}") from e

        # Handle non-2xx from upstream (including 502 from crashed process)
        if status == 502:
            self._inc_stat("errors")
            err_body = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
            raise RuntimeError(f"Upstream returned 502: {err_body}")
        if 200 <= status < 300:
            try:
                with self._slot_lock:
                    self._save_current_slot()  # already writes meta with checksum
            except Exception as e:
                # Post-response slot save failure — log but don't kill the 200 response
                log.warning("Post-response slot save failed: %s", e)

            # Filter tool_calls + strip reasoning content from response
            try:
                if not body or not body.strip():
                    pass  # Empty body — nothing to filter
                else:
                    response = json.loads(body.decode("utf-8", errors="replace"))
                    msg = response.get("choices", [{}])[0].get("message", {})
                    self._sanitize_message(msg)

                    tool_calls = msg.get("tool_calls", [])
                    if tool_calls:
                        allowed, rejected = self._filter_tool_calls(tool_calls)
                        if rejected:
                            log.warning("Blocked %d tool calls in response", len(rejected))
                            msg["tool_calls"] = allowed
                            response["blocked_tool_calls"] = [
                                tc.get("function", {}).get("name", "unknown") for tc in rejected
                            ]
                    # Inject llama.cpp timings into usage so Pi extensions can read them
                    if "timings" in response:
                        if "usage" not in response:
                            response["usage"] = {}
                        response["usage"]["timings"] = response["timings"]

                    # Always re-encode after sanitization (even without tool calls)
                    body = json.dumps(response).encode("utf-8")
            except Exception as e:
                log.debug("Response post-processing skipped: %s", e)
        else:
            self._inc_stat("errors")
        # Tier 1 memory: log every request (zero latency — just file append)
        try:
            self.memory.log_request(
                alias=model_alias,
                tokens_before=tokens_before,
                tokens_after=self._last_n_saved,
                duration_ms=(time.time() - req_start) * 1000,
                status=status,
            )
        except Exception:
            pass  # memory write must never affect response
        return status, body

    # ── Metrics ────────────────────────────────────────────────────────────

    def get_metrics(self) -> dict:
        now = time.time()
        if now - self.metrics_cache_ts < DEFAULT_METRICS_POLL and self.metrics_cache:
            return self.metrics_cache
        m = self.client.metrics()
        self.metrics_cache = m
        self.metrics_cache_ts = now
        return m

    def summary(self) -> dict:
        uptime = time.time() - self.stats["start_time"]
        total = max(self.stats["cache_hits"] + self.stats["cache_misses"], 1)
        return {
            **self.stats,
            "uptime_seconds": round(uptime, 1),
            "cache_hit_rate": round(self.stats["cache_hits"] / total * 100.0, 2),
            "current_alias": self.current_alias,
            "current_signature": self.current_signature,
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def _parse_daily_log_stats(self, log_content: str) -> dict:
        """Parse the daily log table and return per-model token usage stats.

        Returns dict with:
          - models: {alias: {requests, total_input, total_output, total_delta,
                             avg_duration_ms, min_duration_ms, max_duration_ms,
                             cache_hits, cache_misses, compactions}}
          - totals: {requests, total_input, total_output, total_delta, avg_duration_ms}
        """
        import re
        models = {}
        total_requests = 0
        total_input = 0
        total_output = 0
        total_delta = 0
        total_duration = 0
        compaction_count = 0

        # Match table rows: | HH:MM:SS | event | model | detail | status | duration |
        row_re = re.compile(
            r"^\|\s+(\d+:\d+:\d+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(.+?)\s+\|\s+(\S+)\s+\|\s+(.+?)\s+\|"
        )
        token_re = re.compile(r"(\d[,]?\d*)\s*→\s*(\d[,]?\d*)\s*\(\+(-?\d[,]?\d*)\)")

        for line in log_content.splitlines():
            m = row_re.match(line)
            if not m:
                continue
            ts, event, model_alias, detail, status_str, duration_str = m.groups()
            event = event.strip()
            model_alias = model_alias.strip()
            detail = detail.strip()
            status_str = status_str.strip()
            duration_str = duration_str.strip()

            if event == "⚠️ COMPACT":
                compaction_count += 1
                if model_alias not in models:
                    models[model_alias] = {
                        "requests": 0, "total_input": 0, "total_output": 0,
                        "total_delta": 0, "durations": [], "cache_hits": 0,
                        "cache_misses": 0, "compactions": 0,
                    }
                models[model_alias]["compactions"] += 1
                continue

            if event != "chat":
                continue

            total_requests += 1
            if model_alias not in models:
                models[model_alias] = {
                    "requests": 0, "total_input": 0, "total_output": 0,
                    "total_delta": 0, "durations": [], "cache_hits": 0,
                    "cache_misses": 0, "compactions": 0,
                }
            models[model_alias]["requests"] += 1

            # Parse token delta: "97,453→103,707 (+6,254) [HIT]"
            tm = token_re.search(detail)
            if tm:
                before = int(tm.group(1).replace(",", ""))
                after = int(tm.group(2).replace(",", ""))
                delta = int(tm.group(3).replace(",", ""))
                models[model_alias]["total_input"] += before
                models[model_alias]["total_output"] += after
                models[model_alias]["total_delta"] += delta
                total_input += before
                total_output += after
                total_delta += delta

            # Parse duration: "69888ms"
            dur_match = re.match(r"(\d+)ms", duration_str)
            if dur_match:
                dur_ms = int(dur_match.group(1))
                models[model_alias]["durations"].append(dur_ms)
                total_duration += dur_ms

            # Cache hit/miss
            if "[HIT]" in detail:
                models[model_alias]["cache_hits"] += 1
            elif "[MISS]" in detail:
                models[model_alias]["cache_misses"] += 1

        # Compute averages
        for m in models.values():
            durs = m.pop("durations", [])
            m["avg_duration_ms"] = round(sum(durs) / len(durs), 0) if durs else 0
            m["min_duration_ms"] = min(durs) if durs else 0
            m["max_duration_ms"] = max(durs) if durs else 0

        return {
            "models": models,
            "totals": {
                "requests": total_requests,
                "total_input": total_input,
                "total_output": total_output,
                "total_delta": total_delta,
                "avg_duration_ms": round(total_duration / total_requests, 0) if total_requests else 0,
                "compactions": compaction_count,
            },
        }

    def _format_stats_for_prompt(self, stats: dict) -> str:
        """Format parsed log stats as a compact text block for the summarizer prompt."""
        lines = ["Per-model token usage:"]
        lines.append(f"  {'Model':<25} {'Reqs':>5} {'In':>10} {'Out':>10} {'Δ':>10} {'Avg(ms)':>9} {'Hits':>5} {'Miss':>5} {'Compact':>7}")
        lines.append("  " + "-" * 96)

        totals = stats["totals"]
        for alias, m in sorted(stats["models"].items(), key=lambda x: -x[1]["requests"]):
            lines.append(
                f"  {alias:<25} {m['requests']:>5} {m['total_input']:>10,} {m['total_output']:>10,} "
                f"{m['total_delta']:>+10,} {m['avg_duration_ms']:>9.0f} {m['cache_hits']:>5} {m['cache_misses']:>5} {m['compactions']:>7}"
            )

        lines.append("  " + "-" * 96)
        lines.append(
            f"  {'TOTAL':<25} {totals['requests']:>5} {totals['total_input']:>10,} {totals['total_output']:>10,} "
            f"{totals['total_delta']:>+10,} {totals['avg_duration_ms']:>9.0f} {'':>5} {'':>5} {totals['compactions']:>7}"
        )
        return "\n".join(lines)

    def _summarize_session(self, summarize_alias: Optional[str] = None) -> dict:
        """Tier 2: swap to vice-chair, summarize today's Tier 1 log, write back.

        Reads the current day's structured log, swaps to a lightweight model
        (vice-ministral by default), generates a concise session summary
        with per-model token usage breakdown, and appends it to the daily log.
        Then swaps back to the original model.

        Designed to be called from:
          - POST /v1/council/summarize (Pi /quit hook or manual)
          - Idle timeout (future)
          - cleanup() on shutdown (optional)
        """
        # Resolve summarizer alias
        alias = summarize_alias
        if not alias:
            # Auto-detect: prefer vice-ministral (gpu_chat, large ctx) over ministral (tiny_council, 16K ctx)
            for a in self.registry.known_aliases():
                if "vice" in a.lower():
                    alias = a
                    break
            if not alias:
                for a in self.registry.known_aliases():
                    if "ministral" in a.lower():
                        alias = a
                        break
        if not alias or not self.registry.get_config(alias):
            return {"error": "No summarizer model configured", "status": 404}

        # Read today's log
        daily_path = self.memory._daily_path()
        if not daily_path.exists():
            return {"status": 200, "message": "No log to summarize"}
        log_content = daily_path.read_text(encoding="utf-8")
        if len(log_content.strip().splitlines()) < 5:  # header + <3 entries
            return {"status": 200, "message": "Too few entries to summarize"}

        # Parse per-model token usage stats from the log
        stats = self._parse_daily_log_stats(log_content)
        stats_text = self._format_stats_for_prompt(stats)

        # Save current state
        original_alias = self.current_alias
        if self.upstream.running() and self.current_alias:
            try:
                with self._slot_lock:
                    self._save_current_slot()
            except Exception as e:
                log.warning("Pre-summarize slot save failed: %s", e)

        try:
            # Swap to summarizer
            log.info("SESSION SUMMARY: swapping to %s", alias)
            self._swap_to(alias)

            # Build prompt with token usage breakdown
            prompt = (
                "Summarize this council session log. Write a detailed report covering:\n"
                "1. Per-model token usage breakdown (requests, tokens in/out, cache hits/misses, avg duration)\n"
                "2. Key decisions made and why\n"
                "3. Delegation outcomes (which reviewers, pass/fail)\n"
                "4. Any compaction or cold-start events\n"
                "5. Total request count and session duration\n"
                "6. VRAM/latency concerns (any requests taking >5min)\n\n"
                f"TOKEN USAGE STATS:\n{stats_text}\n\n"
                "RAW LOG:\n"
                f"```\n{log_content}\n```\n\n"
                "Be factual. Include the token usage table in your output. No preamble."
            )

            status, body = self.client.post_json(
                "/v1/chat/completions",
                {
                    "model": alias,
                    "messages": [
                        {"role": "system", "content": "You are a detailed session log analyst. Output structured Markdown with tables and bullet points."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.3,
                    "stream": False,
                },
                timeout=300,
            )

            if 200 <= status < 300:
                parsed = self.client._parse_upstream_json(body, context="summarize")
                if parsed:
                    summary_text = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if summary_text:
                        # Append full summary block to daily log
                        self.memory._append(
                            f"\n## Session Summary (by {alias})\n\n{summary_text}\n\n"
                            f"{self.memory.TABLE_HEADER}"
                        )
                        log.info("SESSION SUMMARY: written (%d chars)", len(summary_text))
                        # Print full output to stdout for Pi to see
                        print(f"\n{'='*60}")
                        print(f"COUNCIL SESSION SUMMARY ({alias})")
                        print(f"{'='*60}")
                        print(summary_text)
                        print(f"{'='*60}\n")
                        return {"status": 200, "message": "Summary written", "summary": summary_text}
                return {"error": f"Summarization failed: empty response", "status": 502}
            else:
                return {"error": f"Summarization failed: HTTP {status}", "status": status}

        except Exception as e:
            log.error("SESSION SUMMARY failed: %s", e)
            return {"error": f"Summarization failed: {e}", "status": 500}
        finally:
            # Swap back to original model
            if original_alias and self.current_alias != original_alias:
                try:
                    log.info("SESSION SUMMARY: swapping back to %s", original_alias)
                    self._swap_to(original_alias)
                except Exception as e:
                    log.error("SESSION SUMMARY swap-back failed: %s", e)

    def _summarize_chat(self, messages: list, summarize_alias: Optional[str] = None) -> dict:
        """Summarize a full chat session by sending it to vice-granite.

        Takes the actual conversation messages (user + assistant),
        swaps to vice-granite, and generates a concise summary
        of what was discussed, decided, and accomplished.

        Designed to be called from:
          - POST /v1/council/summarize-chat (Pi extension command)
          - /quit hook with session content
        """
        # Resolve summarizer alias — vice-granite is the sole summarizer
        alias = summarize_alias
        if not alias:
            for a in self.registry.known_aliases():
                if "vice-granite" in a.lower():
                    alias = a
                    break
        if not alias:
            for a in self.registry.known_aliases():
                if "vice" in a.lower():
                    alias = a
                    break
        if not alias or not self.registry.get_config(alias):
            return {"error": "No summarizer model configured", "status": 404}

        if not messages or len(messages) < 2:
            return {"status": 200, "message": "Too few messages to summarize"}

        # Save current state
        original_alias = self.current_alias
        if self.upstream.running() and self.current_alias:
            try:
                with self._slot_lock:
                    self._save_current_slot()
            except Exception as e:
                log.warning("Pre-summarize slot save failed: %s", e)

        try:
            log.info("CHAT SUMMARY: swapping to %s", alias)
            self._swap_to(alias)

            # Build summary prompt — keep it tight
            summary_system = (
                "You are a session summarizer. Analyze the conversation below "
                "and produce a concise structured summary. Output Markdown with these sections:\n"
                "## Topics Discussed\n"
                "## Key Decisions\n"
                "## Work Completed\n"
                "## Open Items / Follow-ups\n"
                "## Models Used\n"
                "Be factual. No preamble. Skip any section that has no content."
            )

            # Serialize the conversation into a single quoted block
            conv_lines = []
            for m in messages:
                role = m.get("role", "?").upper()
                content = m.get("content", "")
                if len(content) > 4000:
                    content = content[:4000] + "... [truncated]"
                conv_lines.append(f"{role}:\n{content}")
            conversation_text = "\n\n---\n\n".join(conv_lines)

            # Truncate total conversation if too long for the summarizer's context
            max_conv_len = 40000  # ~10K tokens
            if len(conversation_text) > max_conv_len:
                keep_start = int(max_conv_len * 0.2)
                keep_end = int(max_conv_len * 0.6)
                conversation_text = (
                    conversation_text[:keep_start] +
                    f"\n\n... [{len(messages) - 4} messages elided for brevity] ...\n\n" +
                    conversation_text[-keep_end:]
                )

            status, body = self.client.post_json(
                "/v1/chat/completions",
                {
                    "model": alias,
                    "messages": [
                        {"role": "system", "content": summary_system},
                        {"role": "user", "content": f"Summarize this session conversation:\n\n```\n{conversation_text}\n```"},
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.3,
                    "stream": False,
                },
                timeout=300,
            )

            if 200 <= status < 300:
                parsed = self.client._parse_upstream_json(body, context="summarize-chat")
                if parsed:
                    summary_text = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if summary_text:
                        saved_path = self.memory.save_chat_summary(
                            summary=summary_text, alias=alias,
                            message_count=len(messages),
                        )
                        log.info("CHAT SUMMARY: saved to %s (%d chars)", saved_path, len(summary_text))
                        # Auto-index new summary for vector recall (fire-and-forget, threaded)
                        threading.Thread(
                            target=self.memory._auto_index_file,
                            args=(saved_path,),
                            daemon=True,
                        ).start()
                        print(f"\n{'='*60}")
                        print(f"SESSION SUMMARY (by {alias})")
                        print(f"{'='*60}")
                        print(summary_text)
                        print(f"{'='*60}\n")

                        # Generate/update dynamic todo list from conversation
                        todo_result = self._generate_todos(messages, alias)

                        return {
                            "status": 200,
                            "message": "Summary generated",
                            "summary": summary_text,
                            "saved_to": saved_path,
                            "todos": todo_result,
                        }
                return {"error": "Summarization failed: empty response", "status": 502}
            else:
                return {"error": f"Summarization failed: HTTP {status}", "status": status}

        except Exception as e:
            log.error("CHAT SUMMARY failed: %s", e)
            return {"error": f"Summarization failed: {e}", "status": 500}
        finally:
            if original_alias and self.current_alias != original_alias:
                try:
                    log.info("CHAT SUMMARY: swapping back to %s", original_alias)
                    self._swap_to(original_alias)
                except Exception as e:
                    log.error("CHAT SUMMARY swap-back failed: %s", e)

    def _generate_todos(self, messages: list, alias: str) -> dict:
        """Generate/update a dynamic todo list from the conversation.

        Reads existing TODOS.md, scans conversation for action-item keywords
        (no truncation), extracts remaining/missed items organized by project,
        deduplicates via hash-based merging, and writes back.

        Returns {status, message, saved_to}.
        """
        import re
        todos_path = Path.home() / ".pi" / "agent" / "memory" / "TODOS.md"

        # Read existing todos
        existing_todos = ""
        if todos_path.exists():
            existing_todos = todos_path.read_text(encoding="utf-8")

        # Keyword-based action item extraction (Nemo recommendation)
        # Scan ALL messages for action-item keywords instead of truncating
        todo_keywords = re.compile(
            r'\b(todo|fix|implement|add|remove|refactor|update|create|setup|deploy|test|review|check|investigate|resolve|address|handle|support|enable|disable|migrate|convert|replace|rename|extract|parse|validate|normalize|deduplicate|isolate|protect|guard|enforce|optimize|improve|enhance|extend|monitor|track|report|alert|notify)\b',
            re.I
        )

        # Extract candidate messages with action-item keywords
        candidate_lines = []
        for m in messages:
            role = m.get("role", "?").upper()
            content = m.get("content", "")
            if len(content) > 4000:
                content = content[:4000] + "... [truncated]"
            # Include message if it has action-item keywords
            if todo_keywords.search(content):
                candidate_lines.append(f"{role}:\n{content}")

        # If no candidates found, fall back to first + last messages
        if not candidate_lines:
            conv_lines = []
            for m in messages[:3] + messages[-3:]:
                role = m.get("role", "?").upper()
                content = m.get("content", "")
                if len(content) > 4000:
                    content = content[:4000] + "... [truncated]"
                conv_lines.append(f"{role}:\n{content}")
            conversation_text = "\n\n---\n\n".join(conv_lines)
        else:
            conversation_text = "\n\n---\n\n".join(candidate_lines)

        # Truncate only if still too long (safety net)
        max_conv_len = 30000
        if len(conversation_text) > max_conv_len:
            keep_start = int(max_conv_len * 0.3)
            keep_end = int(max_conv_len * 0.7)
            conversation_text = (
                conversation_text[:keep_start] +
                f"\n\n... [truncated for brevity] ...\n\n" +
                conversation_text[-keep_end:]
            )

        # Prompt: extract remaining items, merge with existing
        todo_system = (
            "You are a todo list manager. Your job is to produce a consolidated, "
            "project-organized todo list from a conversation and an existing todo list.\n\n"
            "Rules:\n"
            "1. Organize items by project (e.g. KungOS Backend, KungOS Frontend, "
            "LLM Council, KungOS Gaming, RAGFlow, Infrastructure)\n"
            "2. Each item: `- [ ] **Title** — brief context` with source tag\n"
            "3. Mark items as `- [x]` ONLY if the conversation clearly shows completion\n"
            "4. Keep existing unchecked items that were NOT completed in this session\n"
            "5. Add new items from the conversation (missed work, follow-ups, decisions needing action)\n"
            "6. Remove items that are truly done OR no longer relevant\n"
            "7. Priority markers: 🔴 High, 🟡 Medium, 🔵 Low — use when clear\n"
            "8. Keep it under 40 items total — drop low-value noise\n"
            "9. Output ONLY the markdown todo list, no preamble\n\n"
            "Format:\n"
            "# Dynamic Todo List\n\n"
            "> Last updated: YYYY-MM-DD\n\n"
            "## Project Name\n\n"
            "- [ ] **Item** — context\n"
            "  - *Source: session YYYY-MM-DD*\n"
        )

        user_prompt = (
            f"Existing todo list:\n\n````\n{existing_todos}\n````\n\n"
            f"This session's conversation:\n\n````\n{conversation_text}\n````\n\n"
            f"Produce the updated todo list."
        )

        status, body = self.client.post_json(
            "/v1/chat/completions",
            {
                "model": alias,
                "messages": [
                    {"role": "system", "content": todo_system},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 2048,
                "temperature": 0.3,
                "stream": False,
            },
            timeout=300,
        )

        if 200 <= status < 300:
            parsed = self.client._parse_upstream_json(body, context="generate-todos")
            if parsed:
                todo_text = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
                if todo_text:
                    todos_path.parent.mkdir(parents=True, exist_ok=True)
                    with todos_path.open("w", encoding="utf-8") as f:
                        f.write(todo_text)
                    log.info("TODOS: updated %s (%d chars)", todos_path, len(todo_text))
                    print(f"\n{'='*60}")
                    print(f"TODOS UPDATED (by {alias})")
                    print(f"{'='*60}")
                    print(todo_text[:500])
                    if len(todo_text) > 500:
                        print(f"... [{len(todo_text)} chars total]")
                    print(f"{'='*60}\n")
                    return {
                        "status": 200,
                        "message": "Todo list updated",
                        "saved_to": str(todos_path),
                    }
            return {"error": "Todo generation failed: empty response", "status": 502}
        else:
            return {"error": f"Todo generation failed: HTTP {status}", "status": status}

    def cleanup(self) -> None:
        try:
            self.memory.log_event("shutdown", f"uptime={time.time() - self.stats['start_time']:.0f}s")
        except Exception:
            pass
        with self.lock:
            try:
                if self.upstream.running():
                    self._save_current_slot()
                    self.upstream.stop()
            except Exception:
                pass
            try:
                if self.council_manager:
                    self.council_manager.shutdown()
            except Exception:
                pass
            try:
                self.store.cleanup(known_aliases=set(self.registry.known_aliases()))
            except Exception:
                pass

    def build_handler(self):
        """Build HTTP request handler for ThreadingHTTPServer."""
        supervisor = self

        class Handler(BaseHTTPRequestHandler):
            def _set_headers(self, code: int, content_type: str = "application/json"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.end_headers()

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/health":
                    with supervisor._error_lock:
                        sys_err = supervisor._system_error
                    health = {
                        "ok": not supervisor._restarting,
                        "restarting": supervisor._restarting,
                        "system_error": sys_err,
                        "supported_features": {
                            "function_calling": True,
                            "tool_use": True,
                            "delegation": True,
                            "fanout": supervisor.council_manager is not None,
                            "allowed_tools": list(supervisor._allowed_tools),
                        },
                    }
                    if supervisor._restart_log:
                        health["restart_log"] = supervisor._restart_log
                    self._set_headers(200 if not supervisor._restarting else 503)
                    self.wfile.write(json.dumps(health).encode("utf-8"))
                    return
                if parsed.path == "/metrics":
                    self._set_headers(200)
                    self.wfile.write(json.dumps(supervisor.get_metrics()).encode("utf-8"))
                    return
                if parsed.path == "/status":
                    self._set_headers(200)
                    status = supervisor.summary()
                    status["supported_features"] = {
                        "function_calling": True,
                        "tool_use": True,
                        "delegation": True,
                        "fanout": supervisor.council_manager is not None,
                        "allowed_tools": list(supervisor._allowed_tools),
                    }
                    self.wfile.write(json.dumps(status).encode("utf-8"))
                    return
                # ── Fanout job polling ──
                if parsed.path.startswith("/v1/council/fanout/"):
                    if not supervisor.council_manager:
                        self._set_headers(501)
                        self.wfile.write(
                            json.dumps({"error": "Fanout not configured"}).encode("utf-8")
                        )
                        return
                    job_id = parsed.path.split("/")[-1]
                    if job_id == "jobs":
                        jobs = supervisor.council_manager.list_jobs()
                        self._set_headers(200)
                        self.wfile.write(json.dumps({"jobs": jobs}).encode("utf-8"))
                        return
                    status = supervisor.council_manager.get_job_status(job_id)
                    if status is None:
                        self._set_headers(404)
                        self.wfile.write(
                            json.dumps({"error": f"Job {job_id} not found"}).encode("utf-8")
                        )
                        return
                    self._set_headers(200)
                    self.wfile.write(json.dumps(status).encode("utf-8"))
                    return
                # Proxy to upstream
                try:
                    status, body = supervisor.client.get(self.path, timeout=DEFAULT_TIMEOUT_READ)
                    self._set_headers(status)
                    self.wfile.write(body)
                except Exception as e:
                    self._set_headers(502)
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len) if content_len else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    payload = {}
                if parsed.path in {"/v1/chat/completions", "/chat/completions"}:
                    try:
                        status, body = supervisor.handle_chat_completion(payload)
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        status = 502
                        body = json.dumps({"error": str(e)}).encode("utf-8")
                    self._set_headers(status)
                    self.wfile.write(body)
                    return
                if parsed.path == "/v1/council/fanout":
                    if not supervisor.council_manager:
                        self._set_headers(501)
                        self.wfile.write(
                            json.dumps({"error": "Fanout not configured"}).encode("utf-8")
                        )
                        return
                    try:
                        # Check for async flag
                        async_flag = payload.pop("async", payload.pop("_async", False))
                        result = supervisor.council_manager.fanout(payload, async_=async_flag)
                        self._set_headers(200)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(502)
                        self.wfile.write(
                            json.dumps({"error": str(e)}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/delegate":
                    try:
                        result = supervisor._delegate(payload)
                        status = result.get("status", 200)
                        self._set_headers(status)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/restart":
                    try:
                        result = supervisor._restart_upstream(payload)
                        status = result.get("status", 200)
                        self._set_headers(status)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/supervisor-restart":
                    try:
                        result = supervisor._restart_supervisor(payload)
                        status = result.get("status", 200)
                        self._set_headers(status)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                        # If fork succeeded, this won't execute
                        return
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/summarize":
                    try:
                        alias = payload.get("model")  # optional: override summarizer
                        messages = payload.get("messages", [])
                        results = {}
                        # Summarize the session log
                        session_result = supervisor._summarize_session(summarize_alias=alias)
                        results["session"] = session_result
                        # If chat messages provided, also summarize the conversation
                        if messages:
                            chat_result = supervisor._summarize_chat(messages, summarize_alias=alias)
                            results["chat"] = chat_result
                        # Return success if at least one summary succeeded
                        overall_status = 200
                        for r in results.values():
                            if r.get("status", 200) >= 400:
                                overall_status = max(r.get("status", 200), overall_status)
                        self._set_headers(overall_status)
                        self.wfile.write(json.dumps(results).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/summarize-chat":
                    try:
                        alias = payload.get("model")  # optional: override summarizer
                        messages = payload.get("messages", [])
                        result = supervisor._summarize_chat(messages, summarize_alias=alias)
                        status = result.get("status", 200)
                        self._set_headers(status)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                if parsed.path == "/v1/council/chain":
                    try:
                        plan = payload.get("plan", {})
                        context = payload.get("context", "")
                        result = supervisor._delegate_chain(plan, task_context=context)
                        status = result.get("status", 200)
                        self._set_headers(status)
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        supervisor._inc_stat("errors")
                        self._set_headers(500)
                        self.wfile.write(
                            json.dumps({"error": str(e), "status": 500}).encode("utf-8")
                        )
                    return
                # Proxy to upstream
                try:
                    status, body = supervisor.client.post_json(parsed.path, payload, timeout=DEFAULT_TIMEOUT_CHAT)
                    self._set_headers(status)
                    self.wfile.write(body)
                except Exception as e:
                    self._set_headers(502)
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

            def log_message(self, fmt, *args):
                pass  # Suppress default HTTP logging

        return Handler

    def _get_default_alias(self) -> Optional[str]:
        """Read default_alias from config.json, if set."""
        try:
            _raw = read_json_file(Path(self.config_path))
            alias = _raw.get("default_alias")
            if alias and self.registry.get(alias):
                return alias
        except Exception as e:
            log.warning("Failed to read default_alias from config: %s", e)
        return None

    def serve_forever(self) -> None:
        """Start the proxy HTTP server."""
        # Startup checks
        try:
            BinaryHashTracker(self.upstream_bin, str(self.slot_dir)).check_and_invalidate()
        except Exception as e:
            log.warning("Binary hash check failed: %s", e)

        self.store.cleanup(known_aliases=set(self.registry.known_aliases()))

        self._init_council_manager()

        # Preload default model so the first request doesn't hit a cold-start
        default_alias = self._get_default_alias()
        if default_alias:
            log.info("Preloading default model: %s", default_alias)
            try:
                self._swap_to(default_alias)
                log.info("Default model %s loaded and ready", default_alias)
            except Exception as e:
                log.warning("Failed to preload default model %s: %s", default_alias, e)

        handler = self.build_handler()
        self.httpd = ThreadingHTTPServer((self.listen_host, self.listen_port), handler)
        log.info("slot-supervisor listening on %s:%d (upstream %s:%d)",
                 self.listen_host, self.listen_port, self.upstream_host, self.upstream_port)
        try:
            self.memory.log_event("startup", f"listening on {self.listen_host}:{self.listen_port}")
        except Exception:
            pass

        def signal_handler(signum, frame):
            log.info("Received signal %s", signum)
            self.stop_event.set()
            try:
                self.httpd.shutdown()
            except Exception:
                pass

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            self.httpd.serve_forever(poll_interval=0.5)
        finally:
            self.cleanup()


# ─── TinyCouncil Fanout Manager ────────────────────────────────────────────────

class TinyCouncilManager:
    """Manages parallel and sequential fanout for TinyCouncil models.

    Parallel mode: 3 co-resident llama-server processes on distinct ports.
    Sequential mode: swap through models one-by-one via existing supervisor.
    """

    def __init__(self, supervisor, config_block, council_aliases: List[str],
                 council_configs: Dict[str, ModelConfig]):
        """Initialize fanout manager.

        Args:
            supervisor: The SlotSupervisor instance.
            config_block: The fanout config dict from config.json.
            council_aliases: List of model aliases in the council group.
            council_configs: Mapping of alias -> ModelConfig for council models.
        """
        self.supervisor = supervisor
        self.config = config_block
        self._lock = threading.Lock()
        self.parallel_procs: Dict[str, UpstreamProcess] = {}
        self.parallel_clients: Dict[str, SlotClient] = {}
        self.council_aliases = council_aliases
        self.council_configs = council_configs

        # Validate ports
        ports = self.config.get("ports", [8092, 8093, 8094])
        if not isinstance(ports, list) or len(ports) < len(council_aliases):
            raise ValueError(
                f"Fanout config 'ports' must be a list with at least "
                f"{len(council_aliases)} entries (got {ports})"
            )

        log.info("TinyCouncilManager initialized with aliases: %s", council_aliases)

        # ── Lifecycle control ──
        self._stop_event = threading.Event()
        self._initializing = False

        # ── Async job queue (Option C) ──
        self.jobs: Dict[str, dict] = {}  # job_id -> {status, payload, results, ...}
        self._job_lock = threading.Lock()
        self._job_ttl_seconds = 3600  # 1 hour
        self._job_cleanup_thread = threading.Thread(
            target=self._job_cleanup_loop, daemon=True
        )
        self._job_cleanup_thread.start()

    def _job_cleanup_loop(self):
        """Periodically purge completed jobs older than TTL."""
        while not self._stop_event.is_set():
            time.sleep(300)  # every 5 minutes
            cutoff = time.time() - self._job_ttl_seconds
            with self._job_lock:
                to_remove = [
                    jid for jid, job in self.jobs.items()
                    if job.get("completed_at") and job["completed_at"] < cutoff
                ]
                for jid in to_remove:
                    del self.jobs[jid]
                if to_remove:
                    log.info("Purged %d expired fanout jobs", len(to_remove))

    def _create_job(self, payload: dict) -> str:
        """Create a new fanout job, return job_id."""
        job_id = hashlib.sha256(
            f"{time.time()}{random.random()}{id(self)}".encode()
        ).hexdigest()[:12]
        job = {
            "job_id": job_id,
            "status": "pending",
            "payload": payload,
            "results": None,
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "total_time_ms": None,
            "error": None,
        }
        with self._job_lock:
            self.jobs[job_id] = job
        log.info("Created fanout job %s", job_id)
        return job_id

    def _execute_job(self, job_id: str) -> None:
        """Background thread: execute fanout and update job status."""
        with self._job_lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = time.time()

        try:
            result = self._run_fanout(job["payload"])
            with self._job_lock:
                job["status"] = "completed"
                job["results"] = result
                job["completed_at"] = time.time()
                job["total_time_ms"] = result.get("total_time_ms")
            log.info("Fanout job %s completed (%dms)", job_id, result.get("total_time_ms"))
        except Exception as e:
            with self._job_lock:
                job["status"] = "failed"
                job["error"] = str(e)
                job["completed_at"] = time.time()
            log.error("Fanout job %s failed: %s", job_id, e)

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get job status, results, timing."""
        with self._job_lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "created_at": job["created_at"],
                "started_at": job["started_at"],
                "completed_at": job["completed_at"],
                "total_time_ms": job["total_time_ms"],
                "results": job["results"],
                "error": job["error"],
            }

    def list_jobs(self, limit: int = 20) -> List[dict]:
        """List recent jobs with status (newest first)."""
        with self._job_lock:
            jobs = sorted(
                self.jobs.values(), key=lambda j: j.get("created_at", 0), reverse=True
            )
        result = []
        for job in jobs[:limit]:
            result.append({
                "job_id": job["job_id"],
                "status": job["status"],
                "created_at": job["created_at"],
                "started_at": job["started_at"],
                "completed_at": job["completed_at"],
                "total_time_ms": job["total_time_ms"],
                "error": job.get("error"),
            })
        return result

    def _run_fanout(self, payload: dict) -> dict:
        """Execute fanout with automatic mode selection (internal)."""
        mode = self._select_mode()
        if mode == "parallel":
            results, total_time_ms = self._fanout_parallel(payload)
        else:
            results, total_time_ms = self._fanout_sequential(payload)
        return {
            "mode": mode,
            "results": results,
            "total_time_ms": total_time_ms,
        }

    def fanout(self, payload: dict, async_: bool = False) -> dict:
        """Execute fanout with automatic mode selection.

        If async_=True: spawn background thread, return job_id immediately.
        If async_=False: execute synchronously (existing behavior).
        """
        if async_:
            job_id = self._create_job(payload)
            t = threading.Thread(
                target=self._execute_job, args=(job_id,), daemon=True
            )
            t.start()
            return {
                "job_id": job_id,
                "status": "pending",
                "message": "Fanout job created. Poll /v1/council/fanout/{job_id} for results.",
            }
        else:
            # Synchronous execution (existing behavior)
            result = self._run_fanout(payload)
            return result

    def _select_mode(self) -> str:
        """Determine execution mode based on available VRAM."""
        free = self.supervisor._get_free_vram()
        threshold = self.config.get("parallel_vram_threshold_mib", 18432)
        if free is None:
            log.warning("Could not query VRAM, falling back to sequential mode")
            return "sequential"
        if free >= threshold:
            log.info("Parallel mode: %d MiB free >= %d MiB threshold", free, threshold)
            return "parallel"
        log.info("Sequential mode: %d MiB free < %d MiB threshold", free, threshold)
        return "sequential"

    def _check_port(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if a port is available (not bound by another process)."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return False  # Port is in use
        except (ConnectionRefusedError, socket.timeout, OSError):
            return True  # Port is available
        finally:
            sock.close()

    def _fanout_parallel(self, payload: dict) -> dict:
        """Execute fanout with 3 co-resident llama-server processes."""
        start_time = time.time()
        results: Dict[str, Any] = {}
        host = self.config.get("host", "127.0.0.1")
        ports = self.config.get("ports", [8092, 8093, 8094])

        # --- Guard against concurrent fanout ---
        self.supervisor.fanout_in_progress = True
        try:
            # --- Narrow lock: only for process initialization ---
            if not self.parallel_procs and not self._initializing:
                self._initializing = True
                try:
                    council_slot_dir = self.supervisor.slot_dir / "council"
                    council_slot_dir.mkdir(parents=True, exist_ok=True)

                    for alias, port in zip(self.council_aliases, ports):
                        model_config = self.council_configs.get(alias)
                        if not model_config:
                            log.warning("Skipping %s: no model config found", alias)
                            continue

                        # Check port availability
                        if not self._check_port(port, host):
                            log.warning("Port %d is already in use, skipping %s", port, alias)
                            continue

                        proc = UpstreamProcess(
                            self.supervisor.upstream_bin, port, host,
                            env=self.supervisor._server_env
                        )
                        client = SlotClient(f"http://{host}:{port}")

                        try:
                            # Wait for VRAM before starting each process
                            # Stagger starts by 2s to avoid peak VRAM spike from simultaneous CUDA alloc
                            if self.parallel_procs:
                                log.info("Staggering start of %s by 2s", alias)
                                time.sleep(2)
                            self.supervisor._wait_for_vram()
                            proc.start(model_config, council_slot_dir)
                            # Atomic dict update under lock
                            with self._lock:
                                self.parallel_procs[alias] = proc
                                self.parallel_clients[alias] = client
                            log.info("Parallel process started: %s on port %d", alias, port)
                        except RuntimeError as e:
                            log.error("Failed to start parallel process for %s: %s", alias, e)
                            proc.stop()
                            # Don't insert failed process into dicts
                finally:
                    self._initializing = False

            if not self.parallel_procs:
                raise RuntimeError("No parallel processes available for fanout")

            # --- Network I/O: outside the lock ---
            threads: List[threading.Thread] = []
            result_lock = threading.Lock()

            def _send_request(alias: str, client: SlotClient, model_payload: dict):
                try:
                    status, body = client.post_json(
                        "/v1/chat/completions", model_payload, timeout=DEFAULT_TIMEOUT_CHAT
                    )
                    parsed = None
                    error = None
                    if 200 <= status < 300:
                        try:
                            parsed = json.loads(body.decode("utf-8"))
                            # Strip reasoning content from fanout response
                            msg = parsed.get("choices", [{}])[0].get("message", {})
                            self.supervisor._sanitize_message(msg)
                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            error = f"JSON decode error: {e}"
                    else:
                        error = f"HTTP {status}"

                    with result_lock:
                        results[alias] = {
                            "status": status,
                            "body": parsed,
                            "error": error,
                        }

                    # Save slot after request (per-alias slot dir)
                    try:
                        client.save_slot(self.supervisor.id_slot)
                    except Exception as e:
                        log.warning("Slot save failed for %s: %s", alias, e)

                except Exception as e:
                    with result_lock:
                        results[alias] = {
                            "status": 502,
                            "body": None,
                            "error": str(e),
                        }

            for alias in self.council_aliases:
                if alias not in self.parallel_clients:
                    results[alias] = {
                        "status": 503, "body": None, "error": "Process not available"
                    }
                    continue
                try:
                    model_payload = self.supervisor._prepare_payload(alias, payload)
                except KeyError as e:
                    results[alias] = {"status": 500, "body": None, "error": str(e)}
                    continue

                t = threading.Thread(
                    target=_send_request,
                    args=(alias, self.parallel_clients[alias], model_payload),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=DEFAULT_TIMEOUT_CHAT)

        finally:
            self.supervisor.fanout_in_progress = False

        total_time_ms = int((time.time() - start_time) * 1000)
        return results, total_time_ms

    def _fanout_sequential(self, payload: dict) -> dict:
        """Execute fanout by swapping through models sequentially."""
        start_time = time.time()
        results: Dict[str, Any] = {}
        original_alias = self.supervisor.current_alias

        try:
            with self.supervisor.lock:
                self.supervisor.fanout_in_progress = True
            for alias in self.council_aliases:
                try:
                    self.supervisor._swap_to(alias)
                    model_payload = self.supervisor._prepare_payload(alias, payload)

                    status, body = self.supervisor.client.post_json(
                        "/v1/chat/completions", model_payload, timeout=DEFAULT_TIMEOUT_CHAT
                    )
                    parsed = None
                    error = None
                    if 200 <= status < 300:
                        try:
                            parsed = json.loads(body.decode("utf-8"))
                            # Strip reasoning content from fanout response
                            msg = parsed.get("choices", [{}])[0].get("message", {})
                            self.supervisor._sanitize_message(msg)
                        except (UnicodeDecodeError, json.JSONDecodeError) as e:
                            error = f"JSON decode error: {e}"
                    else:
                        error = f"HTTP {status}"

                    results[alias] = {
                        "status": status,
                        "body": parsed,
                        "error": error,
                    }
                    self.supervisor._save_current_slot()

                except Exception as e:
                    results[alias] = {
                        "status": 502,
                        "body": None,
                        "error": str(e),
                    }
        finally:
            # Always restore original alias, even on error
            with self.supervisor.lock:
                self.supervisor.fanout_in_progress = False
            if original_alias:
                try:
                    self.supervisor._swap_to(original_alias)
                except Exception as e:
                    log.error(
                        "Failed to restore original alias %s: %s", original_alias, e
                    )
            elif self.council_aliases:
                try:
                    self.supervisor._swap_to(self.council_aliases[0])
                except Exception as e:
                    log.error("Failed to restore first council alias: %s", e)

        total_time_ms = int((time.time() - start_time) * 1000)
        return results, total_time_ms

    def cleanup(self) -> None:
        """Stop all parallel processes."""
        with self._lock:
            for alias, proc in list(self.parallel_procs.items()):
                try:
                    proc.stop()
                except Exception as e:
                    log.warning("Failed to stop process for %s: %s", alias, e)
            self.parallel_procs.clear()
            self.parallel_clients.clear()

    def shutdown(self) -> None:
        """Gracefully shut down the manager: stop processes, join cleanup thread."""
        # Signal cleanup thread to stop
        self._stop_event.set()

        # Stop parallel processes
        self.cleanup()

        # Wait for cleanup thread to finish (with timeout)
        if self._job_cleanup_thread.is_alive():
            self._job_cleanup_thread.join(timeout=5)

        # Clear all state
        with self._job_lock:
            self.jobs.clear()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="llama.cpp slot supervisor")
    p.add_argument("--listen-host", default=DEFAULT_LISTEN_HOST,
                   help="Frontend listen address (default: 127.0.0.1)")
    p.add_argument("--listen-port", type=int, default=DEFAULT_LISTEN_PORT,
                   help="Frontend listen port (default: 8080)")
    p.add_argument("--upstream-host", default=DEFAULT_UPSTREAM_HOST,
                   help="Upstream llama-server host (default: 127.0.0.1)")
    p.add_argument("--upstream-port", type=int, default=DEFAULT_UPSTREAM_PORT,
                   help="Upstream llama-server port (default: 8081)")
    p.add_argument("--config", default=DEFAULT_CONFIG,
                   help="llama-swap config.json path")
    p.add_argument("--slot-dir", default=DEFAULT_SLOT_DIR,
                   help="Slot save directory")
    p.add_argument("--upstream-bin", default=os.environ.get("LLAMA_SERVER_BIN", DEFAULT_LLAMA_BIN),
                   help="Path to llama-server binary")
    p.add_argument("--cleanup-only", action="store_true",
                   help="Run cleanup and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate config and list models, then exit")
    p.add_argument("--invalidate", type=str, metavar="ALIAS",
                   help="Invalidate slot bins for a model alias and exit")
    p.add_argument("--stats", action="store_true",
                   help="Print slot directory stats and exit")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.stats:
        slot_dir = Path(args.slot_dir)
        if slot_dir.exists():
            total_size = sum(f.stat().st_size for f in slot_dir.rglob("*") if f.is_file())
            num_bins = len(list(slot_dir.rglob("slot-*.bin")))
            num_models = len([d for d in slot_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
            print(f"Slot directory: {slot_dir}")
            print(f"  Models: {num_models}")
            print(f"  Slot bins: {num_bins}")
            print(f"  Total size: {total_size / 1024 / 1024 / 1024:.1f} GB")
        else:
            print(f"Slot directory does not exist: {slot_dir}")
        return 0

    supervisor = SlotSupervisor(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        config_path=args.config,
        slot_dir=args.slot_dir,
        upstream_bin=args.upstream_bin,
    )

    if args.cleanup_only:
        supervisor.store.cleanup(known_aliases=set(supervisor.registry.known_aliases()))
        print(json.dumps(supervisor.summary(), indent=2))
        return 0

    if args.dry_run:
        print(json.dumps({
            "models": supervisor.registry.known_aliases(),
            "slot_dir": args.slot_dir,
            "upstream_bin": args.upstream_bin,
            "listen": f"{args.listen_host}:{args.listen_port}",
            "upstream": f"{args.upstream_host}:{args.upstream_port}",
        }, indent=2))
        return 0

    if args.invalidate:
        supervisor.invalidate_model(args.invalidate, "manual invalidation via CLI")
        return 0

    supervisor.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
