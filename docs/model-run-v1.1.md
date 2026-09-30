# One controlled Qwen development request — predeclared limits

This is synthetic development case D1 from docs/model-v1.1-frozen.json: helpdesk_agent, DEMO-PLANT-A, cutoff 2026-10-01T10:00:00Z, exactly EVD-02, NEW-06, OLD-05 and TKT-01. No held-out evaluation is authorized by this run. The model receives only the four admitted A/B clause pairs; server-owned revision state and hashes remain in a separate envelope.

Before generation, scripts/development_qwen_v1_1.py performs a render-only call to the installed Ollama 0.17.7 qwen3:4b template, then counts the actual rendered text with the pinned CPU tokenizer. It records model tag digest, template SHA-256, tokenizer metadata, prompt and schema hashes, input tokens, GPU/RAM, and a fit receipt. It refuses the generation if input tokens + 768 output tokens + 64 extra headroom exceed 4096 context tokens. Input truncation and context shift are both disabled. The runner requests think:false, temperature 0, concurrency one, localhost only, and a whole-request 60-second deadline. It creates an immutable attempt marker before its sole generation request. A transport timeout latches the shared inference.lock.blocked marker and prohibits automatic retry.

The bounded single-flight guard is copied from quality-investigation-chronology commit cf90af5a2a15d34ad00a3391f6d6ac5ff834deb3, which credits project 01 source commit 721949d17891bbb009b31b19a20469bd0946991c (MIT). The CPU GGUF tokenizer is copied from korean-equipment-evidence-desk commit 858f2d93382c9438525f5dbb7dad844e9f51faff (MIT), without copying weights. The already-installed optional tokenizers engine 0.23.2 is used; no install or download is part of this run.

These are request limits and safeguards, not measured fit or model performance. The CPU source copy validator may pass while a summary still makes unsupported claims. Human semantic review is separate. The raw server response, including any failure, and timings are retained under artifacts/model-dev-v1.1.


## Actual one-call result, 2026-09-30 21:39 UTC

The render-only preflight produced 580 CPU-reconstructed prompt tokens. With 768 output tokens and 64 extra headroom, the planned total was 1412/4096. Ollama 0.17.7 returned model tag digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7 and installed template SHA-256 2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9. This was a CPU tokenizer count of the actual rendered template; a generation-side token-count parity check was impossible because generation returned HTTP 500.

Exactly one generation request was sent. It received HTTP 500 after 1.701 seconds, with no retry. The Ollama service journal shows a completed /api/chat 500 after loading the model but no explanatory message. The runner's HTTPError handler recorded the status and time but did not read the error body; therefore the full raw HTTP error response was **not preserved and cannot be recovered** from this attempt. This evidence gap is explicit in artifacts/model-dev-v1.1/failure-report.json. No generated content, source copy result, Korean summary or per-clause semantic result can be evaluated. This is not a model-quality failure score.

After the response, the shared lock had no owner, the timeout marker was absent, /api/ps had no loaded model and nvidia-smi showed no compute process. GPU ownership was released. Any corrected future attempt requires a separately versioned runner/protocol and explicit new GPU grant. Never repeat this v1.1 attempt; its attempt marker remains.
