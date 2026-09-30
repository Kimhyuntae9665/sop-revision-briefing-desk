"""Request contract checks only; no Ollama or GPU call."""
import unittest
from scripts.development_qwen_v1_1 import CASE, CTX, PREDICT, RESERVE, TIMEOUT, request


class RunnerContractTests(unittest.TestCase):
    def test_single_development_request_bounds_and_source_scope(self):
        packet, payload = request()
        self.assertEqual(CASE["case_id"], "D1-helpdesk-upcoming")
        self.assertEqual([p["clause_id"] for p in packet["model_input"]["pairs"]],
                         ["EVD-02", "NEW-06", "OLD-05", "TKT-01"])
        self.assertEqual(payload["options"]["num_ctx"], CTX)
        self.assertEqual(payload["options"]["num_predict"], PREDICT)
        self.assertEqual((CTX, PREDICT, RESERVE, TIMEOUT), (4096, 768, 832, 60))
        self.assertIs(payload["think"], False)
        self.assertIs(payload["truncate"], False)
        self.assertIs(payload["shift"], False)
        self.assertIs(payload["stream"], False)
        self.assertNotIn("C/", payload["messages"][1]["content"])
        self.assertNotIn("HAND-04", payload["messages"][1]["content"])
        self.assertNotIn("current_revision", payload["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
