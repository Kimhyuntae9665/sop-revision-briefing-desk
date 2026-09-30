"""P13 v1.2 freeze and transport tests; no Ollama or GPU use."""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from model.draft_protocol_v1_2 import PROTOCOL, check_draft
from scripts import development_qwen_v1_1 as v11
from scripts import development_qwen_v1_2 as v12


class ErrorHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = b'{"error":"synthetic schema error"}'
        self.send_response(500)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class V12RunnerTests(unittest.TestCase):
    def test_request_changes_only_output_schema_version_and_pattern(self):
        packet_old, old = v11.request()
        packet_new, new = v12.request()
        self.assertEqual(packet_old, packet_new)
        self.assertEqual(v12.OUT.name, "model-dev-v1.2")
        self.assertEqual((v12.CTX, v12.PREDICT, v12.RESERVE, v12.TIMEOUT),
                         (4096, 768, 832, 60))
        self.assertEqual(new["model"], "qwen3:4b")
        self.assertEqual((new["think"], new["truncate"], new["shift"],
                          new["stream"]), (False, False, False, False))
        normalized = copy.deepcopy(new)
        normalized["format"]["properties"]["protocol_id"]["enum"] = (
            old["format"]["properties"]["protocol_id"]["enum"])
        normalized["format"]["properties"]["summaries"]["items"]["properties"]["summary_ko"]["pattern"] = "[가-힣]"
        self.assertEqual(normalized, old)
        self.assertEqual(PROTOCOL["development_cases"][0]["case_id"], "D1-helpdesk-upcoming")
        self.assertEqual(v12.sha(new), v12.EXPECTED_REQUEST_SHA256)
        self.assertEqual(v12.sha(new["format"]), v12.EXPECTED_SCHEMA_SHA256)
        self.assertEqual(v12.sha(packet_new["model_input"]), v12.EXPECTED_INPUT_SHA256)
        with patch.object(v12, "EXPECTED_INPUT_SHA256", "0" * 64):
            with self.assertRaisesRegex(RuntimeError, "frozen_request_or_source_changed"):
                v12.request()

    def test_source_korean_length_and_version_gate(self):
        packet, _ = v12.request()
        rows = [dict(pair, summary_ko="원문 조항 표현이 변경되었습니다.")
                for pair in packet["model_input"]["pairs"]]
        answer = {"protocol_id": PROTOCOL["protocol_id"], "draft_only": True,
                  "summaries": rows}
        self.assertTrue(check_draft(packet, answer)["ok"])
        wrong = copy.deepcopy(answer)
        wrong["protocol_id"] = v11.PROTOCOL["protocol_id"]
        self.assertEqual(check_draft(packet, wrong)["reason"], "not_draft")
        wrong = copy.deepcopy(answer)
        wrong["summaries"][0]["summary_ko"] = "English only"
        self.assertEqual(check_draft(packet, wrong)["reason"], "summary_length")
        wrong = copy.deepcopy(answer)
        wrong["summaries"][0]["summary_ko"] = "가" * 121
        self.assertEqual(check_draft(packet, wrong)["reason"], "summary_length")
        wrong = copy.deepcopy(answer)
        wrong["summaries"][0]["before_quote"] += "추가"
        self.assertEqual(check_draft(packet, wrong)["reason"], "source_or_kind_mismatch")
        wrong = copy.deepcopy(answer)
        wrong["summaries"].pop()
        self.assertEqual(check_draft(packet, wrong)["reason"], "incomplete")

    def test_complete_http_error_body_is_available_under_deadline(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ErrorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(v12, "BASE", "http://127.0.0.1:" + str(server.server_port)):
                with self.assertRaises(v12.HTTPResponseError) as got:
                    v12.bounded_chat_bytes({"messages": []}, 5)
            self.assertEqual(got.exception.status, 500)
            self.assertEqual(got.exception.body, b'{"error":"synthetic schema error"}')
            self.assertTrue(got.exception.complete)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_attempt_marker_blocks_repeat_before_any_model_access(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "preflight.json").write_text('{"fits":true}')
            (out / "attempt-started.json").write_text("{}")
            with patch.object(v12, "OUT", out):
                with self.assertRaisesRegex(RuntimeError, "attempt_already_started_no_retry"):
                    v12.run_once()

    def test_installed_model_and_template_must_match_frozen_digest(self):
        template = "synthetic test template"
        exact_hash = hashlib.sha256(template.encode()).hexdigest()
        def fake_get(endpoint, timeout=10):
            if endpoint == "/api/version":
                return {"version": "0.17.7"}
            return {"models": [{"name": "qwen3:4b", "digest": "frozen-test-digest"}]}
        with patch.object(v12, "get", side_effect=fake_get), patch.object(
                v12, "post", return_value={"template": template}), patch.object(
                v12, "EXPECTED_MODEL_DIGEST", "frozen-test-digest"), patch.object(
                v12, "EXPECTED_TEMPLATE_SHA256", exact_hash):
            self.assertEqual(v12.model_state(), ("0.17.7", "frozen-test-digest", exact_hash))
        with patch.object(v12, "get", side_effect=fake_get), patch.object(
                v12, "post", return_value={"template": template}):
            with self.assertRaisesRegex(RuntimeError, "frozen_ollama_model_or_template_changed"):
                v12.model_state()


if __name__ == "__main__":
    unittest.main()
