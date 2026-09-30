"""CPU-only development protocol checks. No model calls or evaluation score."""
import copy
import unittest

from model.draft_protocol import build_packet, check_draft
from sop_desk.core import Desk, SITE


class DraftProtocolTests(unittest.TestCase):
    def setUp(self):
        self.desk = Desk()

    def test_declared_development_cases_exact_scope_and_sources(self):
        cases = [
            ("2026-10-01T10:00:00Z", "helpdesk_agent",
             ["EVD-02", "NEW-06", "OLD-05", "TKT-01"], "A", "B"),
            ("2026-10-02T02:00:00Z", "shift_lead",
             ["HAND-04", "NEW-06", "OLD-05", "TKT-01"], "B", None),
        ]
        for as_of, role, expected, current, upcoming in cases:
            with self.subTest(role=role):
                packet = build_packet(self.desk, as_of, role, SITE)
                model_input, envelope = packet["model_input"], packet["server_envelope"]
                self.assertEqual(set(model_input), {"document_id", "site", "role", "pairs"})
                self.assertEqual([p["clause_id"] for p in model_input["pairs"]], expected)
                self.assertEqual(envelope["current_revision"], current)
                self.assertEqual(envelope["upcoming_revision"], upcoming)
                self.assertNotIn("HAND-04", [p["clause_id"] for p in
                    build_packet(self.desk, as_of, "helpdesk_agent", SITE)["model_input"]["pairs"]])
                self.assertNotIn("EVD-02", [p["clause_id"] for p in
                    build_packet(self.desk, as_of, "shift_lead", SITE)["model_input"]["pairs"]])
                self.assertNotIn("source_manifest_hash", model_input)
                self.assertNotIn("effective_at", model_input)

    def test_exact_quote_and_full_coverage_gate(self):
        packet = build_packet(self.desk, "2026-10-01T10:00:00Z", "helpdesk_agent", SITE)
        rows = [dict(pair, summary_ko="원문 조항 표현이 변경되었습니다.")
                for pair in packet["model_input"]["pairs"]]
        output = {"protocol_id": "P13-SOP-CITED-DRAFT-v1.1",
                  "draft_only": True, "summaries": rows}
        self.assertEqual(check_draft(packet, output)["status"],
                         "mechanical_pass_human_review_required")
        altered = copy.deepcopy(output)
        altered["summaries"][0]["after_quote"] = "비슷하지만 다른 문장"
        self.assertEqual(check_draft(packet, altered)["reason"], "source_or_kind_mismatch")
        altered = copy.deepcopy(output)
        altered["summaries"].pop()
        self.assertEqual(check_draft(packet, altered)["reason"], "incomplete")
        shortened = copy.deepcopy(packet)
        shortened["model_input"]["pairs"].pop()
        self.assertEqual(check_draft(shortened, dict(output, summaries=rows[:-1]))["reason"],
                         "packet_scope_or_size")
        altered = copy.deepcopy(output)
        altered["summaries"][0]["summary_ko"] = "Changed source text"
        self.assertEqual(check_draft(packet, altered)["reason"], "summary_length")
        altered = copy.deepcopy(output)
        altered["summaries"][0]["content_approved"] = True
        self.assertEqual(check_draft(packet, altered)["reason"], "row_shape")

    def test_inaccessible_site_and_prepublication_blocked(self):
        with self.assertRaises(PermissionError):
            build_packet(self.desk, "2026-10-01T10:00:00Z", "helpdesk_agent", "OTHER")
        with self.assertRaises(ValueError):
            build_packet(self.desk, "2026-09-10T10:00:00Z", "helpdesk_agent", SITE)


if __name__ == "__main__":
    unittest.main()
