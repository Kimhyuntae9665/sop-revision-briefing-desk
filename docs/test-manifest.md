# P13 verification and demo media

- Frozen fictional contract: initial commit 1ad3969, then independent pre-model correction 6958e1a. Source revision/manifest hashes are in fixtures/manifest.json. No model outcome informed the correction.
- Independent review checked A→B diff, effective and assignment times, role mapping and expected states; it found portable LF and historical receipt binding gaps, both corrected before code/model tests. Missing dependency is now an explicit mutation test.
- CPU: python3 -m unittest discover -s tests -q — 24 tests passed. JavaScript: node --check static/app.js passed.
- Browser: python3 tests/browser_demo.py on isolated 127.0.0.1:19114, installed system Chrome/ffmpeg. Tested A-current/B-future, B-current-before-assignment, A/B receipt separation, literal source modal and keyboard focus, read/self-check separation, export, delayed state/source responses, denied-site content clearing, and 390px reflow.
- Real screenshots: artifacts/demo/01 through 07, generated from live synthetic browser UI. At 390px, document width measured 390px; clause body computed 15px, selects 16px. Video workflow.mp4 was captured by Playwright then transcoded using system ffmpeg; no synthetic success frames were composited.
- Security boundary: loopback only, process-memory demonstration receipts, demo roles (no SSO), source hash and scope checks at APIs. No paid API, external writes, real worker or factory data. Model calls: 0. No model accuracy or business outcome score.

- Added live source-file tamper and idempotent replay revalidation tests; changed fixture bytes fail closed before state, source or export. Forged Host browser request is rejected (403).

- Role-specific dependency loss is checked separately; a globally mapped clause does not hide a missing briefing for the selected role.

- Independent code review found cross-role clause text in the initial diff/source API. Both are now role-filtered; direct API 403 and browser nonappearance checks pass.

- Temporal receipt fix: matched local receipts now require receipt.at <= as_of before status or assessment eligibility. Tested 00:30, 01:30, 01:59:59 and exact 02:00 boundary after a later read/self-check; 01:30 self-check mutation fails without a then-admitted read. A source becomes historical_superseded at B effective time. Native Chrome replays the earlier view after later receipts and inspects the historical A source.
- Optional model protocol v1 is frozen but unexecuted. CPU tests check both declared role-admitted packets, exact source quotes, complete four-row output, and blocked cross-role/site inputs. A mechanically valid synthetic draft remains human-review-required; these are engineering tests, not model results.
