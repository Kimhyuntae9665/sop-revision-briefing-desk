# P13 verification and demo media

- Frozen fictional contract: initial commit 1ad3969, then independent pre-model correction 6958e1a. Source revision/manifest hashes are in fixtures/manifest.json. No model outcome informed the correction.
- Independent review checked A→B diff, effective and assignment times, role mapping and expected states; it found portable LF and historical receipt binding gaps, both corrected before code/model tests. Missing dependency is now an explicit mutation test.
- CPU: python3 -m unittest discover -s tests -q — 34 tests passed. JavaScript: node --check static/app.js passed.
- Browser: python3 tests/browser_demo.py on isolated 127.0.0.1:19113, installed system Chrome/ffmpeg. Tested A-current/B-future, B-current-before-assignment, A/B receipt separation, literal source modal and keyboard focus, read/self-check separation, export, delayed state/source responses, denied-site content clearing, and 390px reflow.
- Real screenshots: artifacts/demo/01 through 07, generated from live synthetic browser UI. At 390px, document width measured 390px; clause body computed 15px, selects 16px. Video workflow.mp4 was captured by Playwright then transcoded using system ffmpeg; no synthetic success frames were composited.
- Security boundary: loopback only, process-memory demonstration receipts, demo roles (no SSO), source hash and scope checks at APIs. No paid API, external writes, real worker or factory data. This CPU/UI scenario made 0 model calls; the separately preserved v1.1/v1.2 development attempts remain documented. No model accuracy or business outcome score.

- Added live source-file tamper and idempotent replay revalidation tests; changed fixture bytes fail closed before state, source or export. Forged Host browser request is rejected (403).

- Role-specific dependency loss is checked separately; a globally mapped clause does not hide a missing briefing for the selected role.

- Independent code review found cross-role clause text in the initial diff/source API. Both are now role-filtered; direct API 403 and browser nonappearance checks pass.

- Temporal receipt fix: matched local receipts now require receipt.at <= as_of before status or assessment eligibility. Tested 00:30, 01:30, 01:59:59 and exact 02:00 boundary after a later read/self-check; 01:30 self-check mutation fails without a then-admitted read. A source becomes historical_superseded at B effective time. Native Chrome replays the earlier view after later receipts and inspects the historical A source.
- Optional model protocol v1 is frozen but unexecuted. CPU tests check both declared role-admitted packets, exact source quotes, complete four-row output, and blocked cross-role/site inputs. A mechanically valid synthetic draft remains human-review-required; these are engineering tests, not model results.

- Independent review of ece5cb3 found two low-severity protocol format gaps. Before inference, v1.1 was saved alongside v1; CPU gate now rejects shortened packets and summaries without Hangul. No model outcome informed the revision.

- P13 v1.1 D1 model development: one actual generation request after 580-token rendered-template preflight. HTTP 500 after 1.701 s; no retry, no summary/content, no model quality score. HTTP error body not captured; see docs/model-run-v1.1.md and durable failure-report.json. GPU lock/marker/process checks allowed safe release.

## P09-reference UI refit, current media

- Actual reference inspected: approved P09 v2 development screenshot. Page `#f1f4f6`, text `#142635`, primary `#173f60`, white cards with 1px `#9eaeba`, evidence `#e7edf1`, max width 1120px, padding 24px and 20px two-column gap. P13 keeps its clause diff and role/revision controls.
- Before: dark full-width header and 1540px workspace. After: one-line large Korean title and restrained two-column white panels. No app data or model trace changed.
- `python3 -m unittest discover -s tests -q`: 34 tests passed; `node --check static/app.js`: passed; `python3 tests/browser_demo.py`: passed with the same source/receipt/ACL/time-travel assertions. Desktop 1440px, mobile 390px with document scroll width exactly 390px. Keyboard source-dialog focus return passed.
- Nine current screenshots and a current browser-recorded video are in `artifacts/demo`; the old nine images/video are retained under `artifacts/demo-historical-v1` and must not be presented as the current UI. See `artifacts/demo/PROVENANCE.md`.
- P13 v1.2 model result remains rejected: before/after source IDs and quotes matched, clause identity `EVD-02` was copied as `EVD-:02`, plus two separate semantic summary failures. This refit sent zero model requests.
