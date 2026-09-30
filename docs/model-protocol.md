# Proposed optional model draft protocol — not executed

Frozen before any inference on 2026-09-30. No GPU lease has been granted for P13 and this repository records zero model calls.

Input would be server-admitted A/B changed clauses for one permitted role and site, with exact clause IDs, revision/source SHA-256, effective-status envelope and literal text. The model never receives the frozen expected file, unapproved C text, private records or a write tool.

A bounded JSON response would require a nonempty array of exactly the affected briefing IDs, each with a short Korean draft summary, changed clause IDs, verbatim source spans and an explicit proposal_only=true. Empty or partial arrays fail structural completeness. Each quote must be found in its specified admitted revision and clause; source-state and source-hash binding are checked server-side. Semantically unsupported values, reversed additions/removals, future B described as currently effective at an A cutoff, or claims of competence/approval fail review. Exact span matching alone does not prove semantic support.

CPU literal diff and role dependency mapping are the reference. Any real Qwen experiment would be a separately granted, serialized GPU run with raw successes and failures, context fit and whole-request duration saved. Model output cannot approve content, publish a revision, assign staff, record acknowledgment, assess competence or export a receipt.
