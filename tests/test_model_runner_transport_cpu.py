"""Local HTTP fixture checks the future runner's transport boundary; no Ollama call."""
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from scripts import development_qwen_v1_1 as runner


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/leak")
            self.end_headers()
        elif self.path == "/oversize":
            self.send_response(200)
            self.send_header("Content-Length", str(runner.MAX_RESPONSE + 1))
            self.end_headers()
            self.wfile.write(b"x" * (runner.MAX_RESPONSE + 1))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        self.send_response(307)
        self.send_header("Location", "http://example.invalid/leak")
        self.end_headers()


class TransportBoundaryTests(unittest.TestCase):
    def test_redirect_refused_for_get_and_full_prompt_post(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            with patch.object(runner, "BASE", base):
                with self.assertRaises(urllib.error.HTTPError) as got:
                    runner.get("/redirect")
                self.assertEqual(got.exception.code, 302)
                with self.assertRaises(urllib.error.HTTPError) as posted:
                    runner.bounded_chat_bytes({"messages": [{"role": "user", "content": "synthetic"}]}, 5)
                self.assertEqual(posted.exception.code, 307)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_read_only_response_budget(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(runner, "BASE", "http://127.0.0.1:" + str(server.server_port)):
                with self.assertRaisesRegex(RuntimeError, "read_only_response_too_large"):
                    runner.get("/oversize")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
