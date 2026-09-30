"""Frozen source, transition, authorization and receipt regressions for fictional P13."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from sop_desk.core import Desk, DEFAULT_AS_OF, FIXTURES, SITE, load_sources
from sop_desk.store import ReceiptError, ReceiptStore


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.desk = Desk()

    def test_manifest_and_historical_receipt_bindings(self):
        data = load_sources()
        self.assertEqual(data["manifest_hash"],
                         json.loads((Path(__file__).parent / "frozen_expected.json").read_text())
                         ["source_manifest_sha256"])
        events = [e for e in data["events"] if e["kind"] == "read_acknowledged"]
        self.assertEqual(events[0]["source_hash"], data["manifest"]["revisions"]["A"]["sha256"])

    def test_frozen_snapshots(self):
        gold = json.loads((Path(__file__).parent / "frozen_expected.json").read_text())
        for expected in gold["snapshots"]:
            state = self.desk.state(expected["as_of"])
            self.assertEqual(state["current_revision"], expected["current"])
            self.assertEqual(state["upcoming_revision"], expected["upcoming"])
            if "rejected" in expected:
                self.assertEqual(state["excluded_revisions"], expected["rejected"])
            self.assertEqual(self.desk._assigned("B", "helpdesk_agent",
                             __import__("sop_desk.core", fromlist=["parse_time"]).parse_time(expected["as_of"])),
                             expected["B_assigned"])
            if "B_ack_allowed" in expected:
                self.assertTrue(all(q["ack_allowed"] == expected["B_ack_allowed"]
                                    for q in state["queue"]))

    def test_literal_diff(self):
        gold = json.loads((Path(__file__).parent / "frozen_expected.json").read_text())
        rows = self.desk.diff()
        for kind in ("changed", "removed", "added", "unchanged"):
            self.assertEqual(sorted(r["clause_id"] for r in rows if r["kind"] == kind),
                             sorted(gold["diff_A_B"][kind]))

    def test_role_mapping(self):
        gold = json.loads((Path(__file__).parent / "frozen_expected.json").read_text())
        for role, expected in gold["role_briefings"].items():
            self.assertEqual([b["briefing_id"] for b in self.desk.mapping(role)["affected"]], expected)

    def test_role_scoped_diff_and_source(self):
        helpdesk = self.desk.state(DEFAULT_AS_OF, role="helpdesk_agent")
        lead = self.desk.state(DEFAULT_AS_OF, role="shift_lead")
        self.assertNotIn("HAND-04", [r["clause_id"] for r in helpdesk["diff"]])
        self.assertNotIn("EVD-02", [r["clause_id"] for r in lead["diff"]])
        self.assertIn("EVD-02", [r["clause_id"] for r in helpdesk["diff"]])
        self.assertIn("HAND-04", [r["clause_id"] for r in lead["diff"]])
        with self.assertRaisesRegex(PermissionError, "clause_not_in_role_scope"):
            self.desk.source("B", "EVD-02", DEFAULT_AS_OF, role="shift_lead")
        with self.assertRaisesRegex(PermissionError, "clause_not_in_role_scope"):
            self.desk.source("A", "HAND-04", DEFAULT_AS_OF, role="helpdesk_agent")

    def test_missing_dependency_blocks_completeness(self):
        data = copy.deepcopy(self.desk.data)
        data["dependencies"]["dependencies"] = [e for e in data["dependencies"]["dependencies"]
                                                  if e["briefing_id"] != "BR-OLD"]
        mutated = Desk(data)
        state = mutated.state("2026-10-02T02:00:00Z")
        self.assertEqual(state["mapping"]["unknown_clause_ids"], ["OLD-05"])
        self.assertFalse(state["mapping"]["complete"])
        self.assertTrue(all(not q["ack_allowed"] for q in state["queue"]))

    def test_role_mapping_gap_blocks_only_affected_role(self):
        data = copy.deepcopy(self.desk.data)
        entry = next(e for e in data["dependencies"]["dependencies"] if e["briefing_id"] == "BR-EVD")
        entry["roles"] = ["shift_lead"]
        changed = Desk(data)
        helpdesk = changed.state("2026-10-02T02:00:00Z", role="helpdesk_agent")
        self.assertEqual(helpdesk["mapping"]["unknown_clause_ids"], ["EVD-02", "NEW-06"])
        self.assertFalse(helpdesk["mapping"]["complete"])
        self.assertTrue(all(not item["ack_allowed"] for item in helpdesk["queue"]))

    def test_future_revision_does_not_replace_A(self):
        state = self.desk.state(DEFAULT_AS_OF)
        self.assertEqual(state["current_revision"], "A")
        self.assertEqual(state["upcoming_revision"], "B")
        self.assertTrue(all(not q["ack_allowed"] for q in state["queue"]))
        self.assertEqual(state["revision_states"]["C"]["rejected"], True)

    def test_B_current_before_assignment(self):
        state = self.desk.state("2026-10-02T00:30:00Z")
        self.assertEqual(state["current_revision"], "B")
        self.assertEqual({q["status"] for q in state["queue"]}, {"awaiting_assignment"})

    def test_A_receipt_does_not_transfer_to_B(self):
        before = self.desk.state(DEFAULT_AS_OF)
        self.assertTrue(any(r["revision"] == "A" and r["kind"] == "read_acknowledged"
                            for r in before["history"]))
        after = self.desk.state("2026-10-02T02:00:00Z")
        self.assertTrue(all(q["status"] == "pending_read" for q in after["queue"]))
        self.assertTrue(all(not r["current_binding"] for r in after["history"]))

    def test_source_scope_and_draft_state(self):
        source = self.desk.source("B", "TKT-01", DEFAULT_AS_OF)
        self.assertEqual(source["state"], "approved_future")
        self.assertEqual(source["clause"]["clause_id"], "TKT-01")
        self.assertEqual(self.desk.source("C", "TKT-01", DEFAULT_AS_OF)["state"], "rejected_draft")
        with self.assertRaises(PermissionError):
            self.desk.source("B", "TKT-01", "2026-09-10T00:00:00Z")
        with self.assertRaises(PermissionError):
            self.desk.state(DEFAULT_AS_OF, site="DEMO-PLANT-B")

    def test_unpublished_future_not_in_state(self):
        state = self.desk.state("2026-09-10T10:00:00Z")
        self.assertIsNone(state["upcoming_revision"])
        self.assertEqual(state["diff"], [])
        self.assertEqual(state["queue"], [])

    def test_exact_hash_change_invalidates_receipt(self):
        store = ReceiptStore(self.desk)
        payload = make_payload(self.desk, "BR-TKT", "REQUEST-ONE")
        original = store.submit("read_acknowledged", payload)
        self.assertEqual(store.export(original["receipt_id"], payload["as_of"],
                                      payload["role"], payload["site"])["receipt"]["receipt_id"],
                         original["receipt_id"])
        changed = copy.deepcopy(self.desk.data)
        changed["manifest"]["revisions"]["B"]["sha256"] = "f" * 64
        store.desk = Desk(changed)
        with self.assertRaises(ReceiptError):
            store.export(original["receipt_id"], payload["as_of"], payload["role"], payload["site"])

    def test_read_assessment_and_idempotency(self):
        store = ReceiptStore(self.desk)
        payload = make_payload(self.desk, "BR-TKT", "REQUEST-TWO")
        first = store.submit("read_acknowledged", payload)
        self.assertEqual(first, store.submit("read_acknowledged", payload))
        self.assertEqual(len(store.all()), 1)
        changed = dict(payload, request_id="REQUEST-TWO", briefing_id="BR-EVD")
        with self.assertRaisesRegex(ReceiptError, "request_id_payload_conflict"):
            store.submit("read_acknowledged", changed)
        assessment = dict(payload, request_id="REQUEST-THREE", answer="TKT-01")
        receipt = store.submit("assessment_recorded", assessment)
        self.assertNotEqual(receipt["receipt_id"], first["receipt_id"])
        self.assertEqual(receipt["result"], "source_clause_selected_self_check")
        self.assertEqual(len(store.all()), 2)
        state = self.desk.state(payload["as_of"], payload["role"], payload["site"], store.all())
        self.assertEqual(next(q for q in state["queue"] if q["briefing_id"] == "BR-TKT")["status"],
                         "assessed_self_check")

    def test_ack_before_effective_or_assignment_rejected(self):
        for when in (DEFAULT_AS_OF, "2026-10-02T00:30:00Z"):
            state = self.desk.state(when)
            item = next(q for q in state["queue"] if q["briefing_id"] == "BR-TKT")
            payload = {"as_of": when, "role": "helpdesk_agent", "site": SITE,
                       "briefing_id": "BR-TKT", "fingerprint": item["fingerprint"],
                       "request_id": "REQUEST-FOUR"}
            with self.assertRaises(ReceiptError):
                ReceiptStore(self.desk).submit("read_acknowledged", payload)

    def test_stale_or_wrong_scope_export_rejected(self):
        store = ReceiptStore(self.desk)
        payload = make_payload(self.desk, "BR-TKT", "REQUEST-FIVE")
        receipt = store.submit("read_acknowledged", payload)
        with self.assertRaises((ReceiptError, KeyError)):
            store.export(receipt["receipt_id"], DEFAULT_AS_OF, "helpdesk_agent", SITE)
        with self.assertRaises((ReceiptError, KeyError)):
            store.export(receipt["receipt_id"], payload["as_of"], "shift_lead", SITE)

    def test_live_source_change_blocks_state_and_export(self):
        with tempfile.TemporaryDirectory() as scratch:
            copied = Path(scratch) / "fixtures"
            shutil.copytree(FIXTURES, copied)
            with patch("sop_desk.core.FIXTURES", copied):
                desk = Desk()
                store = ReceiptStore(desk)
                payload = make_payload(desk, "BR-TKT", "REQUEST-TAMPER")
                receipt = store.submit("read_acknowledged", payload)
                self.assertEqual(desk.state(payload["as_of"])["current_revision"], "B")
                path = copied / "revisions" / "B.json"
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "source_changed_restart_required"):
                    desk.state(payload["as_of"])
                with self.assertRaisesRegex(ValueError, "source_changed_restart_required"):
                    store.export(receipt["receipt_id"], payload["as_of"], payload["role"], payload["site"])

    def test_replayed_request_rechecks_new_source_binding(self):
        store = ReceiptStore(self.desk)
        payload = make_payload(self.desk, "BR-TKT", "REQUEST-REPLAY")
        store.submit("read_acknowledged", payload)
        changed = copy.deepcopy(self.desk.data)
        changed["manifest"]["revisions"]["B"]["sha256"] = "a" * 64
        store.desk = Desk(changed)
        with self.assertRaisesRegex(ReceiptError, "stale_fingerprint"):
            store.submit("read_acknowledged", payload)

    def test_assessment_requires_read_and_matching_clause(self):
        store = ReceiptStore(self.desk)
        payload = make_payload(self.desk, "BR-TKT", "REQUEST-SIX")
        with self.assertRaisesRegex(ReceiptError, "read_ack_required"):
            store.submit("assessment_recorded", dict(payload, answer="TKT-01"))
        store.submit("read_acknowledged", payload)
        with self.assertRaisesRegex(ReceiptError, "incorrect_source_clause"):
            store.submit("assessment_recorded", dict(payload, request_id="REQUEST-SEVEN",
                                                     answer="SEC-03"))
        self.assertEqual(len(store.all()), 1)


def make_payload(desk, briefing, request_id):
    as_of = "2026-10-02T02:00:00Z"
    state = desk.state(as_of)
    item = next(q for q in state["queue"] if q["briefing_id"] == briefing)
    return {"as_of": as_of, "role": "helpdesk_agent", "site": SITE,
            "briefing_id": briefing, "fingerprint": item["fingerprint"],
            "request_id": request_id}


if __name__ == "__main__":
    unittest.main()
