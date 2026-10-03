# Audit corrections — September 13, 2026

The five anomalies reproduced in local code are fixed. The initial report and its results remain unchanged in the audit folder.

| Anomaly | Fixed behavior | Validation |
| --- | --- | --- |
| A1 — Premature exposure | Actions use notes present in the request that produced their response. Fetching the board does not count as sending to the model. Events carry request and tool-call identifiers. | Two tools in one response; note arriving during generation; receipt on next request |
| A2 — Bypassable cap | Each attempt is counted before send. Errors and retries keep the cumulative total. Tokens reported in a truncated or invalid response are retained; unknown usage remains flagged. | Cap of 1: only one request despite three retry attempts, 20 input and 128 output tokens retained; fake OpenAI-compatible and Anthropic |
| A3 — Variable profile | All provider parameters are frozen at first start, before the first request. Editing a profile affects future runs. Keys are bound in memory to the initial provider and excluded from backups. | Same model and URL for two agents in one run after global edit; new profile used in new run; no keys in exports and files |
| A4 — Fragile persistence | One atomic checkpoint contains state and all conversations. Effects of a response and its tool results are saved together. Compatibility mirrors are not authoritative. | Failures before checkpoint validation, during mirrors, and between action and result; old corrupted conversations exported as partial |
| A5 — Contradictory free solo | Default prompt depends on headcount. A free solo no longer asks to collaborate; an explicitly custom prompt is preserved. | Prompt absent, null, or explicitly provided; UI preview in solo and headcount change |

## Verification

- **57 tests passed**, including 12 new regressions in [test_lab_audit_regressions.py](../tests/test_lab_audit_regressions.py).
- **8 audit checks passed, no failing invariants**, vs. 3 passed and 5 failed before fixes.
- **9,704 corpus checks passed**, across 100 questions and 200 variants.
- JavaScript syntax and diff verified.
- UI checked: free solo without fictitious peers, custom prompt preserved, opening old runs. No JavaScript defect detected.
- Solo and eight-agent archive exports verified after server restart.

Model tests use fake providers. UI checks use previews and archives; they do not measure real LLM behavior.

## Interpreting older data

New traces carry `trace_version: 2`. Earlier archives are not rewritten: they may have under-counted failed requests and their tokens. Unlogged tokens cannot be reconstructed by this fix. Defect A1 concerns tools chosen in a single response; the initial audit had not found that case in examined local LLM histories.

The legacy audit probe field `reported_but_discarded_tokens` is computed as a theoretical total, without subtracting recorded tokens. To verify the fix, look at `recorded_usage`: the 148 tokens from its truncated response are now present. The new suite explicitly checks those values.

The checkpoint guarantees a last consistent save, not reconstruction of a response lost before logging. An attempt reserved before an incident remains counted. An unreadable old conversation is reported as a partial export, without inventing its content.
