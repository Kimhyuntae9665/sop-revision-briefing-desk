"""One separately versioned P13 synthetic development call after exact CPU template/token preflight.

No retries. v1.1 failure artifacts remain untouched. Reuses the local MIT inference guard and CPU tokenizer with provenance
in docs/model-run-v1.2.md. Run preflight, inspect receipt, then run once.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOOLING = Path.home() / "ax-lab" / "artifacts" / "p06-tokenizer-tooling"
if TOOLING.is_dir():
    sys.path.insert(0, str(TOOLING))
from model.draft_protocol_v1_2 import PROTOCOL, build_packet, check_draft
from sop_desk.core import Desk, canonical
from sop_desk.tokenizer import load_tokenizer
from sop_desk import inference_guard as guard

BASE = "http://127.0.0.1:11434"
OUT = ROOT / "artifacts" / "model-dev-v1.2"
CASE = PROTOCOL["development_cases"][0]
MODEL = PROTOCOL["runtime_proposal"]["model_tag"]
CTX = 4096
PREDICT = 768
RESERVE = PREDICT + 64
TIMEOUT = 60
MAX_RESPONSE = 1_000_000
EXPECTED_OLLAMA_VERSION = "0.17.7"
EXPECTED_MODEL_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
EXPECTED_TEMPLATE_SHA256 = "2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9"
EXPECTED_REQUEST_SHA256 = "f1b1837f3e0d97f01892bba212f40fd5a5e6b3c273a2e67d05774d1975e30d76"
EXPECTED_SCHEMA_SHA256 = "080b925d98ea03c74a3e17e01cde08e3f079ba0a13506d582546191a5a54d74b"
EXPECTED_INPUT_SHA256 = "acec6c78d6f6a9b807315a715000e15cfdd0a61793e5d4865762a0742f162710"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


# Ignore proxy environment and reject redirects so the synthetic source prompt
# can only reach the literal loopback base above. Added after the failed v1.1 call.
LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_json(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode()
    fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(name, value):
    fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, value)
        os.fsync(fd)
    finally:
        os.close(fd)


def post(endpoint, payload, timeout=10):
    req = urllib.request.Request(BASE + endpoint, data=canonical(payload),
                                 headers={"Content-Type": "application/json"})
    with LOCAL_OPENER.open(req, timeout=timeout) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("read_only_response_too_large")
    return json.loads(data)


def get(endpoint, timeout=10):
    with LOCAL_OPENER.open(BASE + endpoint, timeout=timeout) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("read_only_response_too_large")
    return json.loads(data)


class AmbiguousTransportError(RuntimeError):
    pass


class HTTPResponseError(RuntimeError):
    """A complete HTTP status response with a bounded, preserved body."""

    def __init__(self, status, body, complete):
        super().__init__("HTTP status " + str(status))
        self.status = status
        self.body = body
        self.complete = complete


def bounded_chat_bytes(payload, deadline_s=TIMEOUT):
    req = urllib.request.Request(BASE + "/api/chat", data=canonical(payload),
                                 headers={"Content-Type": "application/json"})
    if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
        raise RuntimeError("existing_process_deadline")
    old_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signal, _frame):
        raise TimeoutError("whole_request_deadline")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, deadline_s)
    try:
        try:
            with LOCAL_OPENER.open(req, timeout=deadline_s) as response:
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > MAX_RESPONSE:
                    raise ValueError("response_byte_budget")
                data = response.read(MAX_RESPONSE + 1)
                if len(data) > MAX_RESPONSE:
                    raise ValueError("response_byte_budget")
                if declared is not None and len(data) != int(declared):
                    raise ValueError("response_length_mismatch")
                return data
        except urllib.error.HTTPError as error:
            # Keep error-body reading inside the same whole-request deadline.
            # If that read is interrupted, server state is ambiguous: latch the barrier.
            try:
                body = error.read(MAX_RESPONSE + 1)
            except BaseException as read_error:
                raise AmbiguousTransportError(
                    "http_error_body_read_" + type(read_error).__name__) from read_error
            raise HTTPResponseError(error.code, body[:MAX_RESPONSE],
                                    len(body) <= MAX_RESPONSE) from error
        except BaseException as error:
            raise AmbiguousTransportError(type(error).__name__ + ": " + str(error)[:300]) from error
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def resources():
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
         "--format=csv,noheader,nounits"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "MemTotal:")):
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
    return {"gpu_csv_mib_percent": gpu.stdout.strip(), "meminfo_kib": mem}


def acquire():
    lease = guard._open_inference_lease()
    try:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard._check_timeout_barrier()
        return lease
    except Exception:
        lease.close()
        raise


def release(lease):
    if lease in guard._timeout_guard_leases:
        while True:
            time.sleep(30)
    lease.close()


def request():
    desk = Desk()
    packet = build_packet(desk, CASE["as_of"], CASE["role"], CASE["site"])
    model_input = packet["model_input"]
    ids = [pair["clause_id"] for pair in model_input["pairs"]]
    if ids != CASE["expected_clause_ids"]:
        raise RuntimeError("frozen_development_case_changed")
    if packet["server_envelope"]["current_revision"] != CASE["expected_current_revision"]:
        raise RuntimeError("current_revision_changed")
    if packet["server_envelope"]["upcoming_revision"] != CASE["expected_upcoming_revision"]:
        raise RuntimeError("upcoming_revision_changed")
    content = PROTOCOL["user_prefix"] + json.dumps(
        {"admitted_pairs": model_input}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = {"model": MODEL,
               "messages": [{"role": "system", "content": PROTOCOL["system_prompt"]},
                            {"role": "user", "content": content}],
               "format": PROTOCOL["output_schema"], "stream": False,
               "think": False, "truncate": False, "shift": False,
               "keep_alive": "30s",
               "options": {"num_ctx": CTX, "num_predict": PREDICT, "temperature": 0}}
    if (sha(payload) != EXPECTED_REQUEST_SHA256 or
        sha(payload["format"]) != EXPECTED_SCHEMA_SHA256 or
        sha(model_input) != EXPECTED_INPUT_SHA256):
        raise RuntimeError("frozen_request_or_source_changed")
    return packet, payload


def model_state():
    version = get("/api/version")
    tags = get("/api/tags")
    matches = [m for m in tags.get("models", []) if m.get("name") == MODEL]
    if len(matches) != 1 or not isinstance(matches[0].get("digest"), str):
        raise RuntimeError("model_tag_unavailable")
    shown = post("/api/show", {"model": MODEL})
    template = shown.get("template")
    if not isinstance(template, str) or not template:
        raise RuntimeError("model_template_unavailable")
    actual = (version["version"], matches[0]["digest"],
              hashlib.sha256(template.encode()).hexdigest())
    expected = (EXPECTED_OLLAMA_VERSION, EXPECTED_MODEL_DIGEST, EXPECTED_TEMPLATE_SHA256)
    if actual != expected:
        raise RuntimeError("frozen_ollama_model_or_template_changed")
    return actual


def preflight():
    if any((OUT / name).exists() for name in ("request.json", "preflight.json", "attempt-started.json")):
        raise RuntimeError("prior_preflight_or_attempt_exists_no_retry")
    lease = acquire()
    try:
        packet, payload = request()
        version, digest, template_hash = model_state()
        tokenizer = load_tokenizer()
        begun = time.monotonic()
        try:
            data = bounded_chat_bytes({**payload, "_debug_render_only": True}, TIMEOUT)
        except AmbiguousTransportError:
            guard._latch_timeout(lease)
            raise
        debug = json.loads(data)
        rendered = debug.get("_debug_info", {}).get("rendered_template")
        if not isinstance(rendered, str) or not rendered:
            raise RuntimeError("render_only_missing_template")
        tokens = tokenizer.count_rendered_prompt(rendered)
        receipt = {"at": now(), "case_id": CASE["case_id"],
                   "development_only": True, "generation_requests": 0,
                   "protocol_id": PROTOCOL["protocol_id"],
                   "protocol_sha256": hashlib.sha256((ROOT/"docs/model-v1.2-frozen.json").read_bytes()).hexdigest(),
                   "ollama_version": version, "model_tag": MODEL, "model_tag_digest": digest,
                   "model_layer_digest": tokenizer.provenance["model_manifest_layer_digest"],
                   "gguf_metadata_sha256": tokenizer.provenance["metadata_sha256"],
                   "template_sha256": template_hash, "request_sha256": sha(payload),
                   "schema_sha256": sha(payload["format"]), "model_input_sha256": sha(packet["model_input"]),
                   "rendered_prompt_sha256": tokens["rendered_prompt_sha256"],
                   "rendered_prompt_utf8_bytes": tokens["prompt_utf8_bytes"],
                   "input_tokens_cpu": tokens["input_tokens"], "num_ctx": CTX,
                   "num_predict": PREDICT, "extra_headroom": 64,
                   "output_plus_headroom_reserve": RESERVE,
                   "fits": tokens["input_tokens"] + RESERVE <= CTX,
                   "think": False, "truncate": False, "shift": False,
                   "timeout_seconds": TIMEOUT, "concurrency": 1,
                   "render_wall_s": round(time.monotonic()-begun, 3),
                   "runner_token_parity_proven": False, "resources_after_render": resources()}
        atomic_json("request.json", {"payload": payload, "server_envelope": packet["server_envelope"]})
        atomic_json("preflight.json", receipt)
        print(json.dumps({"preflight": receipt}, ensure_ascii=False))
    finally:
        release(lease)


def run_once():
    receipt_path = OUT / "preflight.json"
    if not receipt_path.is_file():
        raise RuntimeError("preflight_required")
    if (OUT / "attempt-started.json").exists():
        raise RuntimeError("attempt_already_started_no_retry")
    receipt = json.loads(receipt_path.read_text())
    if not receipt["fits"]:
        raise RuntimeError("context_not_fit")
    lease = acquire()
    try:
        packet, payload = request()
        version, digest, template_hash = model_state()
        if (sha(payload) != receipt["request_sha256"] or
            sha(packet["model_input"]) != receipt["model_input_sha256"] or
            digest != receipt["model_tag_digest"] or template_hash != receipt["template_sha256"] or
            version != receipt["ollama_version"] or
            hashlib.sha256((ROOT/"docs/model-v1.2-frozen.json").read_bytes()).hexdigest() != receipt["protocol_sha256"]):
            raise RuntimeError("preflight_binding_changed")
        before = resources()
        atomic_json("attempt-started.json", {
            "at": now(), "request_sha256": receipt["request_sha256"],
            "timeout_seconds": TIMEOUT, "num_ctx": CTX, "num_predict": PREDICT,
            "output_plus_headroom_reserve": RESERVE, "model_digest": digest,
            "template_sha256": template_hash, "resources_before": before,
            "planned_generation_requests": 1})
        begun = time.monotonic()
        try:
            raw = bounded_chat_bytes(payload, TIMEOUT)
        except HTTPResponseError as error:
            atomic_bytes("raw-http-error-body.bin", error.body)
            atomic_json("http-error.json", {
                "at": now(), "status": error.status,
                "request_wall_s": round(time.monotonic()-begun, 3),
                "body_bytes_saved": len(error.body),
                "body_complete_within_budget": error.complete})
            raise
        except AmbiguousTransportError as error:
            guard._latch_timeout(lease)
            atomic_json("transport-error.json", {"at": now(), "type": type(error).__name__,
                        "message": str(error)[:400], "timeout_barrier": True})
            raise
        wall = round(time.monotonic()-begun, 3)
        atomic_bytes("raw-http-response.json", raw)
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            guard._latch_timeout(lease)
            atomic_json("outcome.json", {"at": now(), "request_wall_s": wall,
                        "structural_status": "server_response_invalid_json", "timeout_barrier": True})
            raise
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        thinking = message.get("thinking") if isinstance(message, dict) else None
        outcome = {"at": now(), "request_wall_s": wall, "http_request_count": 1,
                   "done": response.get("done"), "done_reason": response.get("done_reason"),
                   "ollama_metrics": {k: response.get(k) for k in
                        ("total_duration", "load_duration", "prompt_eval_duration",
                         "prompt_eval_count", "eval_duration", "eval_count")},
                   "content_chars": len(content) if isinstance(content, str) else None,
                   "thinking_chars": len(thinking) if isinstance(thinking, str) else None,
                   "resources_after": resources(), "structural_status": None,
                   "semantic_status": "human_review_pending"}
        if not response.get("done") or response.get("done_reason") == "length":
            outcome["structural_status"] = "incomplete_generation"
        elif not isinstance(content, str):
            outcome["structural_status"] = "missing_content"
        else:
            try:
                proposed = json.loads(content)
                checked = check_draft(packet, proposed)
                outcome["structural_status"] = checked
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
                outcome["structural_status"] = "invalid_model_json:" + type(error).__name__
        atomic_json("outcome.json", outcome)
        print(json.dumps({"outcome": outcome}, ensure_ascii=False))
    finally:
        release(lease)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "run"))
    args = parser.parse_args()
    if args.mode == "preflight":
        preflight()
    else:
        run_once()
