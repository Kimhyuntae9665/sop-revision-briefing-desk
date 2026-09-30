# P13 v1.1 HTTP 500: CPU diagnosis and v1.2 proposal

## Observed

- One development generation used the saved exact payload in `artifacts/model-dev-v1.1/request.json`; its canonical payload SHA-256 is `db55d89faf8003032a7e3592f79b45383771a1b29e6b456aa7b8e8ce7adc3adc`, matching the preflight receipt. The canonical schema SHA-256 is `24ffdda5c91607bb7a5fe7f075661a56692e597c47638594ebbb16c1074e79fc`.
- At 2026-09-30 21:39:36 UTC the local Ollama 0.17.7 `/api/chat` returned HTTP 500 after 1.701 s. The bounded journal window contains model loading and the completed 500, but no explanatory error. The v1.1 transport did not preserve the HTTP error body. It cannot be recovered from this attempt.
- Actual rendered-template input was counted on CPU as 580 tokens. With 768 output tokens and 64 extra headroom, 1412/4096 fits. A model response and generated-token measurements do not exist.
- The original v1.1 attempt marker, request, schema, receipts and failure report remain untouched. This is a transport/schema-compatibility failure, not a model-quality result.

## High-confidence source-based cause, not observed server text

The exact saved `summary_ko` JSON Schema has `"pattern": "[가-힣]"`. The installed command reports Ollama 0.17.7. Its [version-matched grammar converter](https://github.com/ollama/ollama/blob/v0.17.7/llama/llama.cpp/common/json-schema-to-grammar.cpp#L319-L323) requires a pattern to start with `^` and end with `$`; it records a conversion error otherwise. The [schema visitor](https://github.com/ollama/ollama/blob/v0.17.7/llama/llama.cpp/common/json-schema-to-grammar.cpp#L884-L903) takes the pattern branch before the min/max-length branch, and [conversion raises on accumulated errors](https://github.com/ollama/ollama/blob/v0.17.7/llama/llama.cpp/common/json-schema-to-grammar.cpp#L925-L929). This exact request therefore contains a documented grammar incompatibility. The absent HTTP error body prevents proving this was the only cause of the observed 500.

## Separately versioned CPU proposal

`docs/model-v1.2-frozen.json` is a separately frozen development protocol, not an executed or evaluated model result:
- v1.1 file SHA-256: `46f8f399a9a251d2c1ca2d0a025fa24ead570bcc7b0a26a6dbdf764ca5e807da`
- frozen file SHA-256: `e74a825644b39038c9c2e49be0bcbeac49c472e0f6c67584fb0ef6f2035ffd6c`
- Change output protocol ID to v1.2 and remove only the unsupported `pattern` field from `summary_ko`; preserve its `minLength: 1` and `maxLength: 120`. A CPU comparison test guards against other runtime/schema/input changes.
- Preserve the already-existing `model.draft_protocol.check_draft` Hangul and length gate for emitted text. The model grammar would no longer constrain Hangul during decoding; outputs without Hangul must fail CPU admission. Exact source-copy and independent human semantic checks remain required.
- The distinct v1.2 runner and version-aware validator are now implemented, with a fresh output directory and attempt marker, bounded HTTP error-body capture, actual template/token preflight, shared single-flight lock and timeout barrier. The runner is frozen but has not been invoked. Obtain a new explicit GPU lease before preflight or generation. Allow exactly one development call on D1, with no automatic retry; preserve HTTP body or complete raw output. Do not evaluate held-out cases from that call.

If the reviewer needs literal confirmation of the original HTTP error, only a separately authorized diagnostic generation with the **unchanged** saved v1.1 payload could capture it using the hardened bounded transport. That would be a new GPU request and is not needed to identify the documented schema incompatibility. No generation or service change was made during this CPU diagnosis.
