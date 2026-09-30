"""Deterministic fictional SOP revision and briefing state. No model in this path."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SITE = "DEMO-PLANT-A"
ROLES = ("helpdesk_agent", "shift_lead")
DEFAULT_AS_OF = "2026-10-01T10:00:00Z"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("invalid_time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid_time") from error
    if parsed.tzinfo is None:
        raise ValueError("time_requires_offset")
    return parsed.astimezone(timezone.utc)


def load_sources():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    data = {"manifest": manifest, "revisions": {}}
    for rev, entry in manifest["revisions"].items():
        path = FIXTURES / entry["path"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("source_hash_mismatch:" + rev)
        data["revisions"][rev] = json.loads(raw)
    for name in ("events.json", "dependencies.json"):
        raw = (FIXTURES / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[name]["sha256"]:
            raise ValueError("source_hash_mismatch:" + name)
        data[name[:-5]] = json.loads(raw)
    data["manifest_hash"] = hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest()
    for event in data["events"]:
        if event["kind"] in ("read_acknowledged", "assessment_recorded"):
            rev = event["revision"]
            expected = {"site": SITE, "source_hash": manifest["revisions"][rev]["sha256"],
                        "mapping_hash": manifest["dependencies.json"]["sha256"],
                        "mapping_version": data["dependencies"]["mapping_version"],
                        "effective_at": data["revisions"][rev]["effective_at"]}
            if any(event.get(key) != value for key, value in expected.items()):
                raise ValueError("historical_receipt_binding_mismatch")
    return data


class Desk:
    def __init__(self, sources=None):
        self.data = sources or load_sources()
        self._verify_disk = sources is None

    def verify_snapshot(self):
        if not self._verify_disk:
            return
        if hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest() != self.data["manifest_hash"]:
            raise ValueError("manifest_changed_restart_required")
        for rev, entry in self.data["manifest"]["revisions"].items():
            if hashlib.sha256((FIXTURES / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("source_changed_restart_required:" + rev)
        for name in ("events.json", "dependencies.json"):
            if hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() != self.data["manifest"][name]["sha256"]:
                raise ValueError("source_changed_restart_required:" + name)


    def _scope(self, as_of, role, site):
        if role not in ROLES or site != SITE:
            raise PermissionError("scope_not_available")
        return parse_time(as_of)

    def _events(self, rev, at):
        return [e for e in self.data["events"] if e["revision"] == rev and parse_time(e["at"]) <= at]

    def _lifecycle(self, rev, at):
        events = self._events(rev, at)
        kinds = {e["kind"] for e in events}
        published = next((e for e in events if e["kind"] == "published"), None)
        return {"drafted": "drafted" in kinds, "approved": "content_approved" in kinds,
                "published": published is not None, "rejected": "rejected" in kinds,
                "effective": bool(published and "content_approved" in kinds and
                                  not "rejected" in kinds and
                                  parse_time(published["effective_at"]) <= at),
                "published_effective_at": published["effective_at"] if published else None,
                "events": events}

    def _selected(self, at):
        states = {rev: self._lifecycle(rev, at) for rev in self.data["revisions"]}
        eligible = [r for r, state in states.items() if state["effective"]]
        current = max(eligible, key=lambda r: parse_time(self.data["revisions"][r]["effective_at"])) if eligible else None
        upcoming = [r for r, state in states.items() if state["published"] and state["approved"] and
                    not state["effective"] and not state["rejected"]]
        upcoming.sort(key=lambda r: parse_time(self.data["revisions"][r]["effective_at"]))
        return current, upcoming[0] if upcoming else None, states

    def diff(self, before="A", after="B"):
        old = {c["clause_id"]: c for c in self.data["revisions"][before]["clauses"]}
        new = {c["clause_id"]: c for c in self.data["revisions"][after]["clauses"]}
        rows = []
        for clause_id in sorted(old.keys() | new.keys()):
            left, right = old.get(clause_id), new.get(clause_id)
            kind = "added" if left is None else "removed" if right is None else \
                   "unchanged" if left == right else "changed"
            rows.append({"clause_id": clause_id, "kind": kind, "before": left, "after": right})
        return rows

    def mapping(self, role):
        rows = self.diff()
        changed = {row["clause_id"] for row in rows if row["kind"] != "unchanged"}
        entries = self.data["dependencies"]["dependencies"]
        known = set().union(*(set(e["clause_ids"]) for e in entries)) if entries else set()
        unknown = sorted(changed - known)
        affected = []
        for entry in entries:
            if role in entry["roles"] and changed.intersection(entry["clause_ids"]):
                affected.append({**entry, "changed_clause_ids": sorted(changed.intersection(entry["clause_ids"]))})
        return {"affected": affected, "unknown_clause_ids": unknown, "complete": not unknown,
                "changed_clause_ids": sorted(changed)}

    def _fingerprint(self, revision, role, site, briefing_id):
        rev = self.data["revisions"][revision]
        return digest({"document_id": rev["document_id"], "revision": revision,
                       "source_hash": self.data["manifest"]["revisions"][revision]["sha256"],
                       "mapping_hash": self.data["manifest"]["dependencies.json"]["sha256"],
                       "role": role, "site": site, "effective_at": rev["effective_at"],
                       "briefing_id": briefing_id})

    def _assigned(self, revision, role, at):
        return any(e["kind"] == "assigned" and role in e.get("roles", [])
                   for e in self._events(revision, at))

    def state(self, as_of=DEFAULT_AS_OF, role="helpdesk_agent", site=SITE, receipts=()):
        self.verify_snapshot()
        at = self._scope(as_of, role, site)
        current, upcoming, lifecycle = self._selected(at)
        briefing_visible = lifecycle["B"]["approved"] and lifecycle["B"]["published"]
        mapping = self.mapping(role) if briefing_visible else {
            "affected": [], "unknown_clause_ids": [], "complete": False, "changed_clause_ids": []}
        target = upcoming or current
        assigned = bool(target and self._assigned(target, role, at))
        queue = []
        if target == "B":
            for entry in mapping["affected"]:
                status = "upcoming_no_action" if target != current else \
                         "awaiting_assignment" if not assigned else "pending_read"
                fingerprint = self._fingerprint(target, role, site, entry["briefing_id"])
                matched = [r for r in receipts if r.get("fingerprint") == fingerprint]
                if matched:
                    status = "assessed_self_check" if any(r["kind"] == "assessment_recorded" for r in matched) \
                             else "read_acknowledged"
                queue.append({**entry, "status": status, "target_revision": target,
                              "fingerprint": fingerprint, "ack_allowed": target == current and assigned and mapping["complete"]})
        history = []
        for event in self.data["events"]:
            if event["kind"] in ("read_acknowledged", "assessment_recorded") and \
                    event.get("role") == role and parse_time(event["at"]) <= at:
                history.append({"receipt_id": event["event_id"], "revision": event["revision"],
                                "briefing_id": event["briefing_id"], "kind": event["kind"],
                                "at": event["at"], "origin": "fictional_fixture",
                                "role": role, "site": site,
                                "source_hash": event["source_hash"],
                                "mapping_hash": event["mapping_hash"],
                                "mapping_version": event["mapping_version"],
                                "effective_at": event["effective_at"],
                                "fingerprint": self._fingerprint(event["revision"], role, site, event["briefing_id"])})
        history.extend(dict(r) for r in receipts if r["role"] == role and r["site"] == site and parse_time(r["at"]) <= at)
        history.sort(key=lambda r: r["at"])
        for receipt in history:
            receipt["current_binding"] = bool(current and receipt["revision"] == current and
                                              receipt["fingerprint"] == self._fingerprint(
                                                  current, role, site, receipt["briefing_id"]))
        return {"as_of": as_of, "site": site, "role": role, "document_id": "IT-SOP-007",
                "source_manifest_hash": self.data["manifest_hash"],
                "current_revision": current, "upcoming_revision": upcoming,
                "excluded_revisions": [r for r, s in lifecycle.items() if s["rejected"]],
                "revision_states": {r: {k: v for k, v in s.items() if k != "events"} for r, s in lifecycle.items()},
                "diff": self.diff() if briefing_visible else [], "mapping": mapping, "queue": queue, "history": history,
                "draft_is_instruction": False, "ack_is_competence": False}

    def source(self, revision, clause_id, as_of=DEFAULT_AS_OF, role="helpdesk_agent", site=SITE):
        self.verify_snapshot()
        at = self._scope(as_of, role, site)
        if revision not in self.data["revisions"]:
            raise KeyError("revision_not_found")
        lifecycle = self._lifecycle(revision, at)
        if not lifecycle["drafted"]:
            raise PermissionError("source_not_available")
        clause = next((c for c in self.data["revisions"][revision]["clauses"]
                       if c["clause_id"] == clause_id), None)
        if clause is None:
            raise KeyError("clause_not_found")
        return {"revision": revision, "clause": clause, "source_hash":
                self.data["manifest"]["revisions"][revision]["sha256"],
                "state": "rejected_draft" if lifecycle["rejected"] else
                         "current" if lifecycle["effective"] and self._selected(at)[0] == revision else
                         "approved_future" if lifecycle["approved"] and lifecycle["published"] else "draft",
                "effective_at": self.data["revisions"][revision]["effective_at"],
                "site": site}
