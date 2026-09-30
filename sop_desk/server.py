"""Loopback-only P13 fictional SOP desk. Standard-library HTTP API."""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .core import Desk, DEFAULT_AS_OF, SITE
from .store import ReceiptError, ReceiptStore

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = {"": ROOT / "static/index.html", "index.html": ROOT / "static/index.html",
          "app.js": ROOT / "static/app.js", "styles.css": ROOT / "static/styles.css",
          "architecture.png": ROOT / "assets/architecture.png"}
DESK = Desk()
STORE = ReceiptStore(DESK)


class Handler(BaseHTTPRequestHandler):
    server_version = "FictionalSOPDesk/1.0"

    def log_message(self, format, *args):
        pass

    def _send(self, status, payload, content_type="application/json; charset=utf-8"):
        raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode() if \
              content_type.startswith("application/json") else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def _params(self, query):
        values = parse_qs(query, keep_blank_values=True)
        for key in ("as_of", "role", "site"):
            if len(values.get(key, [])) > 1:
                raise ValueError("duplicate_" + key)
        return (values.get("as_of", [DEFAULT_AS_OF])[0],
                values.get("role", ["helpdesk_agent"])[0],
                values.get("site", [SITE])[0])

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/state":
                as_of, role, site = self._params(url.query)
                return self._send(200, DESK.state(as_of, role, site, STORE.all()))
            if url.path == "/api/source":
                as_of, role, site = self._params(url.query)
                query = parse_qs(url.query)
                if len(query.get("revision", [])) != 1 or len(query.get("clause_id", [])) != 1:
                    raise ValueError("source_parameters_required")
                return self._send(200, DESK.source(query["revision"][0], query["clause_id"][0],
                                                   as_of, role, site))
            if url.path.startswith("/api/export/"):
                as_of, role, site = self._params(url.query)
                receipt_id = unquote(url.path.removeprefix("/api/export/"))
                if "/" in receipt_id or len(receipt_id) > 100:
                    raise ValueError("invalid_receipt_id")
                return self._send(200, STORE.export(receipt_id, as_of, role, site))
            if url.path.startswith("/api/"):
                return self._send(404, {"error": "not_found"})
            name = url.path.lstrip("/")
            if name not in PUBLIC:
                return self._send(404, {"error": "not_found"})
            path = PUBLIC[name]
            if not path.exists():
                return self._send(404, {"error": "asset_unavailable"})
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype == "application/javascript":
                ctype += "; charset=utf-8"
            return self._send(200, path.read_bytes(), ctype)
        except PermissionError as error:
            return self._send(403, {"error": str(error)})
        except KeyError as error:
            return self._send(404, {"error": str(error)})
        except (ValueError, ReceiptError) as error:
            return self._send(400, {"error": str(error)})

    def do_POST(self):
        try:
            url = urlparse(self.path)
            if url.path not in ("/api/ack", "/api/assess"):
                return self._send(404, {"error": "not_found"})
            origin = self.headers.get("Origin")
            host = self.headers.get("Host")
            allowed_hosts = {"127.0.0.1:" + str(self.server.server_port),
                             "localhost:" + str(self.server.server_port)}
            if host not in allowed_hosts or (origin and origin != "http://" + host):
                return self._send(403, {"error": "origin_not_allowed"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("json_required")
            count = int(self.headers.get("Content-Length", "-1"))
            if count < 0 or count > 4096:
                raise ValueError("invalid_length")
            payload = json.loads(self.rfile.read(count))
            kind = "read_acknowledged" if url.path == "/api/ack" else "assessment_recorded"
            return self._send(201, STORE.submit(kind, payload))
        except PermissionError as error:
            return self._send(403, {"error": str(error)})
        except (ValueError, ReceiptError, json.JSONDecodeError) as error:
            return self._send(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19113)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
