# NR AI Monitoring — What Worked, What Didn't, What We Fixed

Findings from instrumenting a real multi-LLM Python app (FastAPI) with New Relic Python Agent 12.x.
Services: `ai-svc` (recommendations — Gemini/Claude/OpenAI) and `pulse-ai-dontask` (chat — same three providers).

---

## TL;DR

| Provider | Auto events? | Token counts? | Usable out of the box? |
|----------|-------------|---------------|------------------------|
| Gemini | Yes — empty shell | No | No |
| OpenAI | Yes — no tokens, causes duplicates | No | No |
| Claude | **No events at all** | No | No |

**None of the three providers worked out of the box for token-level observability.** All required manual instrumentation.

---

## Provider-by-provider findings

### Gemini (`google-genai` SDK)

**What worked out of the box:**
- NR agent fires `LlmChatCompletionSummary` automatically via `mlmodel_gemini.py`
- APM transaction spans around the call exist — latency is visible

**What was missing:**
- The auto-fired event contains only `timestamp`. No model, no tokens, no duration, no finish reason — an empty shell
- `gemini-3.1-flash-lite-preview` does not return `usage_metadata` at all, so token counts cannot be read from the response object even when doing manual instrumentation

**What we had to build:**
- Manually fire `LlmChatCompletionSummary` + `LlmChatCompletionMessage` after every call with all required fields
- Token estimation fallback: `input ≈ len(prompt) // 4`, `output ≈ len(reply) // 4` — approximate but non-zero, sufficient for demo and trend monitoring

---

### OpenAI (`openai` SDK ≥ 1.x)

**What worked out of the box:**
- NR agent fires `LlmChatCompletionSummary` automatically via `mlmodel_openai.py`
- APM spans exist, latency visible

**What was missing:**
- The auto-fired event contains only `span_id`, `vendor`, and rate-limit response headers (`response.headers.ratelimit*`) — no token counts, no model, no content
- No `transaction_id` on auto events (makes deduplication impossible without a manual marker)

**What we had to build:**
- Manually fire complete events alongside the NR auto events
- Add `WHERE transaction_id IS NOT NULL` to **all** dashboard queries — NR auto events don't have this field, so it's the only reliable way to exclude the empty auto-fired duplicates and avoid double-counting

---

### Claude / Anthropic (`anthropic` SDK)

**What worked out of the box:**
- Nothing. NR Python Agent 12.x has no `mlmodel_anthropic.py` hook
- NR only auto-instruments Anthropic via Bedrock (botocore). Direct Anthropic SDK calls are invisible

**What was missing:**
- All of it: no events, no spans, no token counts, no model attribution

**What we considered and rejected:**
- LangChain wrapper would have given NR auto-instrumentation, but pulls in 13+ transitive dependencies including Rust/C extensions (`orjson`, `jiter`, `xxhash`, `zstandard`) — caused 35+ minute QEMU arm64 CI builds. Not viable.

**What we had to build:**
- Full manual instrumentation: fire `LlmChatCompletionSummary` + `LlmChatCompletionMessage` after every `anthropic` SDK call
- Read `response.usage.input_tokens` and `response.usage.output_tokens` directly from the Anthropic response object

---

## The field naming problem (affects all providers)

Even after manually firing events with correct token counts, the **NR curated AI Monitoring dashboard queries returned null for Claude and Gemini**.

**Root cause:** NR's built-in NRQL queries use OpenAI's naming convention:
- `response.usage.prompt_tokens` (OpenAI calls it `prompt_tokens`)
- `response.usage.completion_tokens` (OpenAI calls it `completion_tokens`)
- `token_count` on `LlmChatCompletionMessage`

We had instrumented using the native API field names (`input_tokens`, `output_tokens` — which is what Claude and Gemini return). NR's curated views hardcode the OpenAI names.

**Fix:** emit both sets of field names on every event, regardless of provider:

```python
"response.usage.input_tokens": input_tokens,      # native naming
"response.usage.output_tokens": output_tokens,
"response.usage.prompt_tokens": input_tokens,      # OpenAI alias for NR curated queries
"response.usage.completion_tokens": output_tokens,
```

And on `LlmChatCompletionMessage`:
```python
"token_count": input_tokens,   # user message (sequence=0)
"token_count": output_tokens,  # assistant message (sequence=1)
```

After this fix, the NR curated "Prompt tokens" query returned data for all three providers.

---

## What genuinely worked well

- **APM transaction tracing** — latency, error rate, throughput visible for all Python services immediately after adding `newrelic-admin run-program uvicorn ...` in the Dockerfile. Zero code changes needed.
- **Distributed tracing** — service-to-service HTTP calls between `ai-svc → event-svc → PostgreSQL` and `ai-svc → session-svc` appeared as connected traces in NR without any manual span creation. The Go agent and Python agent interoperate correctly.
- **NR Infrastructure** — K8s pod CPU/RAM, OOMKill events, restarts all visible out of the box via the K8s integration
- **LLM feedback events** — `newrelic.agent.record_llm_feedback_event(trace_id, rating)` worked exactly as documented. Thumbs-up/down from the chat UI flows through to NR AI Monitoring feedback view with no issues.
- **NR Browser** — page load, JS errors, and custom `addPageAction` events all worked. The MFE (Module Federation) setup required the micro-agent variant for the remote MFE and the full SPA agent on the host shell.
- **Custom events and metrics** — `record_custom_event()` and `record_custom_metric()` worked reliably for all custom signals (circuit breaker state, opt-out events, preference updates).

---

## Summary for the team

| Capability | Status | Notes |
|------------|--------|-------|
| APM latency + throughput | ✅ Out of the box | Just `newrelic-admin` in Dockerfile |
| Distributed tracing (cross-service) | ✅ Out of the box | Go ↔ Python works |
| K8s infrastructure metrics | ✅ Out of the box | NR K8s integration |
| LLM events appearing in NR | ⚠️ Partial | Auto events exist but are empty shells for Gemini/OpenAI, absent for Claude |
| Token counts in NR UI | ❌ Not out of the box | Manual instrumentation required for all 3 providers |
| Claude visibility | ❌ Not out of the box | No NR hook for direct Anthropic SDK — must fire events manually |
| NR curated AI Monitoring queries | ❌ Not out of the box | Require OpenAI-convention field name aliases even for non-OpenAI providers |
| LLM feedback | ✅ Out of the box | `record_llm_feedback_event` works as documented |
| NR Browser + MFE | ✅ With minor config | Micro-agent needed for Module Federation remotes |

**Bottom line:** NR AI Monitoring works well once instrumented, but the out-of-the-box story for non-OpenAI providers is weak. Expect to write a `_record_llm_event()` helper for any provider that isn't vanilla OpenAI. The effort is low (50–80 lines) but the gap between the documentation promise and the reality needs to be clearly communicated to customers before they try to instrument Gemini or Claude.
