"""Build actor-admitted clause packets and check a proposed draft mechanically.

This module does not call the model or approve its summaries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sop_desk.core import Desk

PROTOCOL = json.loads((Path(__file__).resolve().parents[1] / "docs" / "model-v1.1-frozen.json").read_text())
FIELDS = ("clause_id", "change_type", "before_source_id", "before_quote",
          "after_source_id", "after_quote", "summary_ko")


def build_packet(desk: Desk, as_of: str, role: str, site: str):
    state = desk.state(as_of, role, site)
    if not state["mapping"]["complete"]:
        raise ValueError("unknown_dependency")
    pairs = []
    provenance = []
    for row in state["diff"]:
        if row["kind"] == "unchanged":
            continue
        clause_id = row["clause_id"]
        sources = {}
        for side, revision in (("before", "A"), ("after", "B")):
            if row[side] is None:
                sources[side] = None
            else:
                source = desk.source(revision, clause_id, as_of, role, site)
                sources[side] = source
                if source["clause"]["text"] != row[side]["text"]:
                    raise ValueError("diff_source_mismatch")
        pairs.append({
            "clause_id": clause_id,
            "change_type": row["kind"],
            "before_source_id": "A/" + clause_id if sources["before"] else "",
            "before_quote": sources["before"]["clause"]["text"] if sources["before"] else "",
            "after_source_id": "B/" + clause_id if sources["after"] else "",
            "after_quote": sources["after"]["clause"]["text"] if sources["after"] else "",
        })
        provenance.append({"clause_id": clause_id,
                           "before_source_hash": sources["before"]["source_hash"] if sources["before"] else None,
                           "after_source_hash": sources["after"]["source_hash"] if sources["after"] else None})
    if not pairs:
        raise ValueError("no_admitted_change")
    # Server-owned status, hashes and as-of stay outside the model input.
    model_input = {"document_id": state["document_id"], "site": site, "role": role, "pairs": pairs}
    envelope = {"as_of": as_of, "current_revision": state["current_revision"],
                "upcoming_revision": state["upcoming_revision"],
                "source_manifest_hash": state["source_manifest_hash"],
                "provenance": provenance, "requires_content_review": True}
    return {"model_input": model_input, "server_envelope": envelope}


def check_draft(packet, output):
    """Return a mechanical result only; semantic support requires a human review."""
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
