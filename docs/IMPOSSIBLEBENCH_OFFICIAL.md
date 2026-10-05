# Native ImpossibleBench runner

This runner uses the upstream **solver and final scorer directly**, in Docker. It is separate from the earlier Swarm Lab/WASI adaptation. Upstream files are unmodified in `vendor/impossiblebench`; `provenance.json` pins commit `061dc3dce6a96ab6cf02a855157263033dcfa3ba` and their hashes. The upstream MIT notice is retained.

Sources: [ImpossibleBench repository](https://github.com/safety-research/impossiblebench), [paper](https://arxiv.org/abs/2510.20270), [dataset](https://huggingface.co/datasets/fjzzq2002/impossible_livecodebench).

## Matched published settings

- Impossible-LiveCodeBench, `conflicting`, minimal scaffold: no model tools and no added system prompt or agent identity.
- Official A/B/D instructions, original code-block suffix, and the upstream `record_to_sample` conversion.
- Original `agentic_humaneval_solver`: ten attempts, real `python -X dev <random-file.py>` execution, 30-second timeout, unchanged error feedback and task reminder.
- Original `agentic_humaneval_scorer`: use its final verification and metadata handling without replacing it with the attempt result. The converter's `test_patch` default is preserved, exactly as in the upstream task factory.
- `allow_test_modifications=True` in the solver. The sandbox has its normal writable filesystem; no prompt restriction is turned into a filesystem access-control rule.
- Official `aisiuk/inspect-tool-support` Docker image, pinned to the multi-architecture manifest digest observed at setup; 1 GB container memory, no network, and the same service command as upstream.
- GPT-5 snapshot `gpt-5-2025-08-07`, medium reasoning / the source's `reasoning_tokens=4096` setting. No explicit temperature or added maximum generation token value.

## Explicit pilot choices and limits

We select two already-imported tasks (`lcbhard_0` and `lcbhard_1`) and run each under A, B and D, sequentially. D is the stricter comparison condition. This is six cases, not an estimate of the 103-task dataset's population rate. Do not pool the prompt conditions into a single purported reproduction percentage.

The host is macOS ARM using a project-specific Colima VM (2 CPUs, 4 GB memory), with Linux ARM64 containers. The original historical image digest, hardware and dependency versions were not pinned by the paper's public setup; our current image and package versions are frozen for reproducibility, so we do not claim identical historical infrastructure.

An operator budget stops the pilot at approximately US$4 of known model cost; an in-flight request can overshoot. No budget instruction is sent to the model. Cases stopped by an operational limit are recorded as incomplete. This operator budget is additional to the paper protocol. Cost estimates use token usage at GPT-5 rates: $1.25/M input, $0.125/M cached input and $10/M output, excluding taxes.

Before paid calls, four synthetic fixtures validate the actual upstream solver/scorer in Docker: correct original solution passes; honest solution fails contradictory tests; equality-overload exploit passes; a replaced `check` can pass the attempt but fail final verification. These fixtures are stored separately and are **not evidence that a model cheated**.

Real GPT-5 outputs and scores are saved in `logs/*.eval`, `results.jsonl` and `examples/<task>-<prompt>/`. A native pass on the impossible split is the cheating proxy. A native failure alone is not proof of honesty: inspect the response/code and, where appropriate, replay it against the original tests without a new model call.

## Run on macOS ARM

```sh
python3 scripts/setup_impossiblebench_official.py
runs/impossiblebench-official/venv/bin/python scripts/run_impossiblebench_official.py --validate-only
```

For real calls, make `OPENAI_API_KEY` available in the process environment, then:

```sh
runs/impossiblebench-official/venv/bin/python scripts/run_impossiblebench_official.py --budget-usd 4
```

The key is not written to the runner, provenance or experiment files. The Python dependency versions are in `requirements-impossiblebench-official.txt`. On Linux, use an existing Docker daemon plus those requirements; the binary installer specifically targets macOS ARM.

## Replay

```sh
runs/impossiblebench-official/venv/bin/inspect view --host 127.0.0.1 --port 8767 --log-dir PATH_TO_RUN/logs
```

The official viewer reads the native logs. Synthetic validation and original-test code replays are kept outside the real model log directory. The earlier Swarm Lab replays remain available on port 8766.

## Local launch and history page

```sh
python3 -m swarm_bench native --port 8768
```

Open http://127.0.0.1:8768/. Choose task IDs, A/B/D prompts and an operator cost threshold, preview the exact first input, then launch. The page uses the same official runner and fixed GPT-5 snapshot, medium reasoning, ten attempts and fifty messages as the existing native series. The default operator threshold is $4; it is editable and is not a paper parameter. Only one series can be active at a time. Existing CLI runs are detected and never stopped by the portal.

An OpenAI key can be supplied in the server environment or entered in the password field. It stays in process memory and worker environments, never in requests, plans or exports. After restarting the portal, enter it again if it was supplied through the page.

Histories, plans, incremental results and logs live under `runs/impossiblebench-official/`. Closing the browser or portal does not terminate detached workers; reopening the page reads their state from disk. Keep the Mac awake and online; `caffeinate -i` accompanies newly launched workers on macOS. This is a local page, not a cloud service. Nothing launches automatically on server startup. Inspect replays use the separate existing viewer on port 8767 and its shared `model-logs` directory.

The catalogue contains all 103 source tasks in each of three splits. The unmodified source records `lcbhard_77/oneoff` and `lcbhard_77/conflicting` contain unterminated Python strings; they remain in the catalogue with source hashes but are disabled in the portal. Successful impossible-test scores are shown as signals to inspect in the code, not automatically adjudicated honesty labels.
