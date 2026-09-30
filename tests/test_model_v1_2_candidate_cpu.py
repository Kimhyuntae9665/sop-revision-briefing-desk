import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CandidateSchemaTest(unittest.TestCase):
    def test_v1_2_is_a_versioned_pattern_removal_only(self):
        old = json.loads((ROOT / "docs/model-v1.1-frozen.json").read_text())
        new = json.loads((ROOT / "docs/model-v1.2-candidate.json").read_text())
        self.assertEqual(old["output_schema"]["properties"]["summaries"]["items"]["properties"]["summary_ko"]["pattern"], "[가-힣]")
        self.assertNotIn("pattern", new["output_schema"]["properties"]["summaries"]["items"]["properties"]["summary_ko"])
        new = copy.deepcopy(new)
        new["protocol_id"] = old["protocol_id"]
        new["output_schema"]["properties"]["protocol_id"]["enum"] = old["output_schema"]["properties"]["protocol_id"]["enum"]
        new["output_schema"]["properties"]["summaries"]["items"]["properties"]["summary_ko"]["pattern"] = "[가-힣]"
        for key in ("evaluation_status", "revision_note"):
            new[key] = old[key]
        self.assertEqual(new, old)

    def test_model_side_length_and_cpu_hangul_gate_retained(self):
        new = json.loads((ROOT / "docs/model-v1.2-candidate.json").read_text())
        field = new["output_schema"]["properties"]["summaries"]["items"]["properties"]["summary_ko"]
        self.assertEqual((field["minLength"], field["maxLength"]), (1, 120))
        # The candidate cannot be activated until the CPU validator is version-aware;
        # the v1.1 validator's gate remains the source of this behavior.
        source = (ROOT / "model/draft_protocol.py").read_text()
        self.assertIn('re.search("[가-힣]", summary)', source)


if __name__ == "__main__":
    unittest.main()
