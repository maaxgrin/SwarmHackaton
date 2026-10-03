# Agent loop and task choice audit — September 22, 2026

Read-only audit of the engine and histories; no new paid LLM calls.
No engine fixes applied during this audit.

## References inspected

- AutoGen, tool loop: https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py
  `_process_model_result`: `max_tool_iterations` loop, tool execution,
  append `FunctionExecutionResultMessage` to context, new model call.
- AutoGen, coordination: https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat_manager.py
  event propagation and participant selection. That is a different
  message-routing protocol than our voluntarily read board.
- CAMEL: https://github.com/camel-ai/camel/blob/master/camel/agents/chat_agent.py
  `_record_assistant_tool_calls_from_requests`, `_execute_tool`,
  `_record_tool_calling`: keep assistant message then result
  linked to the same id; model loop and context management.

Remote branches were read on the audit date, without installing
those libraries. Comparison validates loop principles, not equivalence of
all features or experimental protocols.

## Local checks

- 92 tests passed (`python3 -m unittest discover -s tests -q`).
- 153 checkpoints, 458 agent histories, 4,169 tool_calls inspected: no
  inconsistency between call ids and results,
  no missing result at end of history, no id reuse in
  the same history. Old runs without checkpoint are not included.
- Network call uses `/chat/completions`, sends history and tool
  schemas, then keeps tool_calls and tool-role results.
- Agents have separate conversations; `run_free` launches one thread
  per agent. Network calls may be concurrent. Tool effect application
  uses a shared lock for consistent updates.
- Failed attempts are counted before send and checkpoints are
  atomic. Tests notably cover exposure to messages actually
  present in the request, file isolation, and rejection of absent tools.

## Confirmed issues and limits

1. **2,000-character submission limit.** `lab_engine.py:436` rejects any
   longer code. A correct algorithmic solution could be rejected
   for protocol reasons. Reproduced with string > 2,000 characters.
2. **1.5M global token budget not implemented.** `validate_config` keeps
   `call_limit` and `max_output_tokens`, but no global token counter.
   A hypothetical `total_output_tokens` field is ignored. Product
   200 calls × 7,500 tokens bounded the last solo, not a group of five.
3. **After submit_answer, an agent can no longer help.** In
   communication/group_misalignment scenarios, it goes to done and its loop stops.
   Reproduction: posting a peer request after submission triggers
   no new call. That is a current protocol rule, not a network bug.
   It matters especially for studying help after solving.
4. **Board is read voluntarily.** A post does not push its
   content into histories. Active agents may read again; a
   finished agent will not. That matches the requested board and explains
   why a late request may get no response.
5. **Correction of earlier explanation: read_board includes own note.**
   The result contains the full board. Only the observation field `note_ids`
   filters different authors. Reproduction: author finds their note
   in the result even when `board_read.note_ids` is [].
6. **Retries do not cover all incidents.** HTTP 402, timeouts, and
   network errors are not retried. Retry-After headers are not
   used; retriable 429/5xx use 10 then 20 seconds. An earlier
   402 does not allow pinpointing cause without its body.
7. **Python scenario not yet implemented.** No run_python tool nor
   interpreter isolation exists in the engine. It can do the control
   without Python, but not yet the condition with an equipped agent.
8. **No context management for long discussions.** Each read_board
   returns the full board and old results stay in history.
   That multiplies input tokens; CAMEL has context management,
   but adopting one here would be an explicit protocol choice.

Other parameters not to hide: submit_only mode may insert a submission
reminder; multiple tools in one response are all handled before individual
end; desired profile is frozen, but exact OpenRouter routing provider
identity is not recorded in each result.

## Proposed harder tasks

Presence and hard difficulty verified in:
https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/test6.jsonl
Protocol reference: https://github.com/LiveCodeBench/LiveCodeBench

- `abc387_f`, Count Arrays: count modulo 998244353 vectors x with
  x[i] <= x[A[i]], N,M <= 2025. Dependency graph, cycles, and counting.
  https://atcoder.jp/contests/abc387/tasks/abc387_f?lang=en
- `abc388_f`, Dangerous Sugoroku: reach cell N avoiding forbidden
  intervals, with jumps of length A..B; N up to 10^12, M up to 20,000,
  1 <= A <= B <= 20. Per-cell simulation does not meet constraints.
  https://atcoder.jp/contests/abc388/tasks/abc388_f?lang=en
- `abc388_g`, Simultaneous Kagamimochi 2: maximize disjoint pairs
  a,b with 2a <= b, on many intervals of a sorted list;
  N,Q up to 200,000. Difficulty combines optimization and many queries.
  https://atcoder.jp/contests/abc388/tasks/abc388_g?lang=en

Python would help build exhaustive solutions on small cases, test an
optimized solution, and search counterexamples. That does not guarantee
failure without Python: problems are public and model capability must
be calibrated empirically with a fixed number of first solo solutions.
Recommendation: start with Count Arrays and Dangerous Sugoroku, then keep
tasks where solo solving is neither systematic nor nearly impossible.
Do not call this multi-agent protocol the official LiveCodeBench score.

Alternative more directly sensitive to the interpreter: execution prediction
(LiveCodeBench Code Execution / CRUXEval-O). CRUXEval however has
short programs and is not a difficulty guarantee for DeepSeek V4.
Artificially inflating their complexity would be benchmark adaptation
and should be explicitly named.
