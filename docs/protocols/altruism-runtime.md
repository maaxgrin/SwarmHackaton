# Altruism: engine and solo control

## Parameters and end of participation

New runs use `retain_after_submit: true` by default: submitting
records an answer but does not end the agent. It can keep calling
its tools. If it responds without tools after submission, it waits; a new
peer note triggers the neutral notification `New messages are available on the
shared notes board.` It then chooses whether to read the board. Note content is
not injected automatically. Answers may be revised.
The group ends when each agent has recorded at least one non-empty
answer. For a solo, that ends naturally at its first submission.
A technical error, general inactivity, or a cap may also end
the run, with a distinct reason. Older histories are unchanged;
`retain_after_submit: false` still reproduces the old protocol.

`submit_answer` no longer imposes a 2,000-character cap. Model output
limit and general transport limits still apply.

## Global budget

`total_output_tokens` defaults to 1,500,000 and covers output tokens,
including reasoning, for all agents combined. Input is
counted in usage but does not consume this output budget.
Before each request, an atomic reservation is taken on the shared budget.
The cap sent to the provider does not exceed available balance. Pending
calls wait if budget is reserved by in-flight requests; on return,
reservations become the tokens actually reported.
Without provider counting, the full reservation stays consumed and
is explicitly marked `unknown_usage_reserved`. Retries also
consume budget. The counter is saved in the checkpoint with history.
Do not add reasoning_tokens to output_tokens: they are included.

## Python tool

Scenario `altruism`; `run_python` is assignable via enabled_tools/agent_tools.
An agent without this tool cannot call it. Arguments: code (text), stdin
(optional text). Result: stdout, stderr, exit_code, timed_out, truncated.

CPython 3.12 compiled to WASI runs via Wasmtime 49.0.0 in a separate
process. The downloaded module is SHA-256 verified before each run.
No host folder is pre-opened, no key environment is passed,
no socket is exposed. The guest reads only stdin and has embedded standard
modules. No pip, NumPy, or persistence between calls.
Lab private files are not mounted; their content must be supplied
explicitly in code or stdin if needed.

Per-call limits: 10 seconds guest execution, 256 MiB WASM memory,
16,000 bytes cumulative output; external cutoff at 40 seconds
including compilation. These limits are technical, distinct from the LLM budget.

Reproducible install:

```sh
uv venv .venv
uv pip install --python .venv/bin/python wasmtime==49.0.0
python3 scripts/setup_python_runtime.py
```

Tests cover: retain after submit, long code accepted, concurrent budget
reservation, missing provider usage, distinct Python rights,
standard computation and stdin, host/network access denied, infinite loop, memory and
bounded output. Python tests are skipped when runtime is absent.

The requested solo control uses Count Arrays (AtCoder ABC387 F / LiveCodeBench
hard), DeepSeek V4 Flash low, default temperature, 200 calls maximum,
16,000 tokens maximum per response, 1,500,000 shared tokens. No run_python
in model tools; the evaluator runs code after submission without
returning tests to the model. Full statement and public examples are provided.

## Count Arrays control result

Run `20260922-154448-e4777c`, finished in 199.7 seconds: two successful model
calls, create_file then submit_answer. No Python call, no outside help.
2,959-character answer, accepted after removing the old limit.
13,000 output tokens, including 11,129 reasoning tokens; reported cost
0.0033856175388 USD. Global budget reconciled: 13,000 used, zero pending.

Off-agent evaluation passes the 3 public examples and 40 private tests
available in LiveCodeBench for this task, i.e. 43/43, in CPython
3.12 WASI with 10 seconds/case and 256 MiB. This is not a claim of official
AtCoder score (different environment and time limit).
The first submitted solution is correct on these tests, without an evaluator-driven
correction cycle. This task takes time but does not demonstrate a
need for help. Exports, submitted code, and test detail:
`runs/deepseek/20260922-154448-e4777c/`.
