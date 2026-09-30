"""Process-local fictional acknowledgment and self-check receipts."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone

from .core import Desk, DEFAULT_AS_OF, SITE, ROLES, digest


class ReceiptError(ValueError):
    pass


class ReceiptStore:
    def __init__(self, desk=None):
        self.desk = desk or Desk()
        self._lock = threading.RLock()
        self._receipts = []
        self._requests = {}

    def all(self):
        with self._lock:
            return [dict(r) for r in self._receipts]

    def _validate(self, payload, kind):
        if not isinstance(payload, dict):
            raise ReceiptError("invalid_payload")
        allowed = {"as_of", "role", "site", "briefing_id", "fingerprint",
                   "request_id", "answer"}
        if set(payload) - allowed:
            raise ReceiptError("unsupported_field")
        required = allowed - {"answer"}
        if not required <= set(payload):
            raise ReceiptError("missing_field")
        for key in required:
            if not isinstance(payload[key], str) or not payload[key] or len(payload[key]) > 160:
                raise ReceiptError("invalid_" + key)
        if len(payload["request_id"]) < 8:
            raise ReceiptError("short_request_id")
        if kind == "assessment_recorded":
            if not isinstance(payload.get("answer"), str):
                raise ReceiptError("missing_answer")
        elif "answer" in payload:
            raise ReceiptError("answer_not_allowed")

    def submit(self, kind, payload):
        if kind not in ("read_acknowledged", "assessment_recorded"):
            raise ReceiptError("invalid_kind")
        self._validate(payload, kind)
        with self._lock:
            request_id = payload["request_id"]
            payload_hash = digest({"kind": kind, "payload": payload})
            existing = self._requests.get(request_id)
            if existing and existing[0] != payload_hash:
                raise ReceiptError("request_id_payload_conflict")
            state = self.desk.state(payload["as_of"], payload["role"], payload["site"], self._receipts)
            if not state["mapping"]["complete"]:
                raise ReceiptError("unknown_dependency")
            item = next((q for q in state["queue"] if q["briefing_id"] == payload["briefing_id"]), None)
            if not item or not item["ack_allowed"] or item["target_revision"] != state["current_revision"]:
                raise ReceiptError("not_current_assigned_briefing")
            if item["fingerprint"] != payload["fingerprint"]:
                raise ReceiptError("stale_fingerprint")
            if existing:
                return dict(existing[1])
            if kind == "read_acknowledged" and item["status"] not in ("pending_read",):
                raise ReceiptError("already_acknowledged")
            if kind == "assessment_recorded":
                if item["status"] != "read_acknowledged":
                    raise ReceiptError("read_ack_required")
                if payload["answer"] not in item["changed_clause_ids"]:
                    raise ReceiptError("incorrect_source_clause")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            receipt = {"receipt_id": "RC-" + hashlib.sha256(request_id.encode()).hexdigest()[:16],
                       "kind": kind, "revision": item["target_revision"],
                       "briefing_id": item["briefing_id"], "fingerprint": item["fingerprint"],
                       "role": payload["role"], "site": payload["site"],
                       "source_hash": self.desk.data["manifest"]["revisions"][item["target_revision"]]["sha256"],
                       "mapping_hash": self.desk.data["manifest"]["dependencies.json"]["sha256"],
                       "mapping_version": self.desk.data["dependencies"]["mapping_version"],
                       "effective_at": self.desk.data["revisions"][item["target_revision"]]["effective_at"],
                       "at": payload["as_of"], "recorded_at": now,
                       "source_clause_id": payload.get("answer") if kind == "assessment_recorded" else None,
                       "result": "source_clause_selected_self_check" if kind == "assessment_recorded" else None,
                       "origin": "local_demo"}
            self._receipts.append(receipt)
            self._requests[request_id] = (payload_hash, receipt)
            return dict(receipt)

    def export(self, receipt_id, as_of, role, site):
        with self._lock:
            state = self.desk.state(as_of, role, site, self._receipts)
            match = next((r for r in state["history"] if r["receipt_id"] == receipt_id), None)
            if not match:
                raise KeyError("receipt_not_found")
            if not match["current_binding"] or match["role"] != role or match["revision"] != state["current_revision"]:
                raise ReceiptError("stale_or_wrong_scope")
            if not any(q["briefing_id"] == match["briefing_id"] and q["ack_allowed"] and
                       q["fingerprint"] == match["fingerprint"] for q in state["queue"]):
                raise ReceiptError("assignment_or_source_changed")
            return {"receipt": match, "document_id": state["document_id"],
                    "source_manifest_hash": state["source_manifest_hash"],
                    "scope": {"as_of": as_of, "role": role, "site": site},
                    "claim_limit": "Reading and a self-check do not prove competence or operational authorization."}
