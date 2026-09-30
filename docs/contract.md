# Frozen P13 source and transition contract v1

All records are original fictional helpdesk SOP examples for DEMO-PLANT-A, IT-SOP-007. No operational machine or physical safety instruction is represented. Source files and this expected-state contract were frozen before model work. No model calls are authorized yet.

- Revision A: content approved 2026-08-25, published 2026-08-28, effective 2026-09-01T00:00:00Z. It remains current through 2026-10-01T23:59:59Z.
- Revision B: drafted 2026-09-20, content approved 2026-09-28, published 2026-09-29 with future effective time 2026-10-02T00:00:00Z. Assignment event is 2026-10-02T01:00:00Z. Before its effective time, B is explicitly upcoming and A remains current. Between effective time and assignment, B is current but acknowledgment is not enabled.
- Revision C: drafted 2026-09-29 and rejected 2026-09-30. It never becomes effective or assigned.
- The immutable source hash for each revision is SHA-256 of its canonical fixture JSON bytes; fixture manifest binds events and dependencies. The source text is not a model-generated statement.

Stable clause IDs: TKT-01, EVD-02, SEC-03, HAND-04, OLD-05, NEW-06. A→B: three changed, one removed, one added, SEC-03 unchanged. Literal text comparison is the CPU baseline. Role scopes are helpdesk_agent and shift_lead; no actual employee identity or SSO.

Declared dependencies: BR-TKT→TKT-01/Q-TKT for both roles; BR-EVD→EVD-02+NEW-06/Q-EVD for helpdesk_agent; BR-HAND→HAND-04+NEW-06/Q-HAND for shift_lead; BR-OLD→OLD-05 for both roles. Changed/added/removed clauses refresh only mapped briefings and questions. An absent or unknown dependency blocks a complete-coverage claim rather than silently treating it as unaffected.

States are separate: drafted, content_approved, published_with_effective_time, assigned, read_acknowledged, assessment_recorded. A's read receipt and self-check result do not transfer to B. Reading does not prove understanding, competence, or operational authorization. An acknowledgment requires current published effective revision, role assignment and an exact source hash, mapping version, role, site and effective time. Export rechecks those bindings; stale receipts remain visible as historical only. Repeated identical request IDs are idempotent; a reused request ID with changed payload is rejected.

Expected states are fixed in tests/frozen_expected.json and deliberately excluded from runtime/model retrieval. This is an authored engineering test oracle, not an independent benchmark. No unseen evaluation or enterprise outcome claim.
