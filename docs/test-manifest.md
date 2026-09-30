# P13 verification and demo media

- Frozen fictional contract: initial commit 1ad3969, then independent pre-model correction 6958e1a. Source revision/manifest hashes are in fixtures/manifest.json. No model outcome informed the correction.
- Independent review checked A→B diff, effective and assignment times, role mapping and expected states; it found portable LF and historical receipt binding gaps, both corrected before code/model tests. Missing dependency is now an explicit mutation test.
- CPU: python3 -m unittest discover -s tests -q — 19 tests passed. JavaScript: node --check static/app.js passed.
- Browser: python3 tests/browser_demo.py on isolated 127.0.0.1:19114, installed system Chrome/ffmpeg. Tested A-current/B-future, B-current-before-assignment, A/B receipt separation, literal source modal and keyboard focus, read/self-check separation, export, delayed state/source responses, denied-site content clearing, and 390px reflow.
- Real screenshots: artifacts/demo/01 through 07, generated from live synthetic browser UI. At 390px, document width measured 390px; clause body computed 15px, selects 16px. Video workflow.mp4 was captured by Playwright then transcoded using system ffmpeg; no synthetic success frames were composited.
- Security boundary: loopback only, process-memory demonstration receipts, demo roles (no SSO), source hash and scope checks at APIs. No paid API, external writes, real worker or factory data. Model calls: 0. No model accuracy or business outcome score.

- Added live source-file tamper and idempotent replay revalidation tests; changed fixture bytes fail closed before state, source or export. Forged Host browser request is rejected (403).

- Role-specific dependency loss is checked separately; a globally mapped clause does not hide a missing briefing for the selected role.

- Independent code review found cross-role clause text in the initial diff/source API. Both are now role-filtered; direct API 403 and browser nonappearance checks pass.
