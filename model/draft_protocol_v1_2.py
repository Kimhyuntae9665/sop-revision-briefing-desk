"""Versioned v1.2 CPU draft gate. No model call or approval action."""
from __future__ import annotations

import json
import re
from pathlib import Path

from model.draft_protocol import FIELDS, build_packet

PROTOCOL = json.loads((Path(__file__).resolve().parents[1] / "docs" / "model-v1.2-frozen.json").read_text())


def check_draft(packet, output):
    """Mechanical validation; independent human semantic review remains required."""
    pairs = packet["model_input"]["pairs"]
    if not isinstance(pairs, list) or len(pairs) != 4:
        return {"ok": False, "reason": "packet_scope_or_size"}
    if not isinstance(output, dict) or set(output) != {"protocol_id", "draft_only", "summaries"}:
        return {"ok": False, "reason": "shape"}
    if output["protocol_id"] != PROTOCOL["protocol_id"] or output["draft_only"] is not True:
        return {"ok": False, "reason": "not_draft"}
    rows = output["summaries"]
    if not isinstance(rows, list) or len(rows) != len(pairs):
        return {"ok": False, "reason": "incomplete"}
    for row, pair in zip(rows, pairs):
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            return {"ok": False, "reason": "row_shape"}
        for key in FIELDS[:-1]:
            if row[key] != pair[key]:
                return {"ok": False, "reason": "source_or_kind_mismatch", "clause_id": pair["clause_id"]}
        summary = row["summary_ko"]
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 120 or not re.search("[가-힣]", summary):
            return {"ok": False, "reason": "summary_length", "clause_id": pair["clause_id"]}
    return {"ok": True, "status": "mechanical_pass_human_review_required",
            "meaning_verified": False, "content_approved": False}
