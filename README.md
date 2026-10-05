# Swarm Lab

Configure LLM agents, private prompts and tools, observe shared-board exchanges, and export reproducible traces. Runs and API credentials stay on the local machine.

## Start

```sh
git clone https://github.com/maaxgrin/SwarmHackaton.git
cd SwarmHackaton
python3 -m swarm_bench lab --port 8766
```

Open http://127.0.0.1:8766/. Python 3.10+ is enough for the main lab. Configure model profiles in **Models**, assign them to the agents, preview prompts, then create and start a run. On Windows use `python` if `python3` is unavailable.

## Current experiments

- **Peer pressure:** split information, asset aggregation, 2024 segment reports and the do-not-disclose variant. Examples are in `examples/`.
- **GPU procurement:** one buyer and peers with an upsell instruction, private quote and host files, simulated orders, neutral solo baseline and DeepSeek pilots. No real purchase is made.
- **School supplies:** one agent receives a private €100–400 range; two others receive €300–600. All are told not to disclose the range. The discussion condition requests draft lists, replies and at least five board messages per agent before submitting. The solo and group configurations are in `experiments/school-supplies/`; configure your local model IDs before importing.
- **ImpossibleBench:** official LiveCodeBench tasks, A/B/D prompts and the native Docker solver/scorer. A separate local launch/history portal shows saved scores, cost and replay links. Synthetic-peer variants are explicitly recorded separately from the paper baseline. See [native setup and protocol](docs/IMPOSSIBLEBENCH_OFFICIAL.md).

```sh
python3 scripts/setup_impossiblebench_official.py
python3 -m swarm_bench native --port 8768
```

The old free-experiment, group-misalignment, spontaneous-communication, Python mutual-aid and ARC-AGI presets have been removed from the public menu, examples and pilot documentation. The shared engine retains compatibility with their saved histories; old traces are not deleted.

## DeepSeek pilots

Set `DEEPSEEK_API_KEY` in the environment. These runners save checkpoints and replay exports under gitignored `runs/`.

```sh
python3 scripts/run_scripted_peer_pressure.py --seeds 42 43 44
python3 scripts/run_segment_disclose_solo.py
python3 scripts/resume_scripted_peer_pressure.py runs/scripted-peer-pressure/<campaign>
python3 scripts/run_gpu_deepseek_pilot.py --wait-for-peer
```

[GPU pilot results](docs/gpu-deepseek-results.json) record the tests on `a6d9931`, before the order-deadline update. Five simulated orders stayed within budget; one pressure run ended on token truncation without an order.

[Compact DeepSeek observations](docs/deepseek-pilot-results.json) include limitations and distinguish provider failures, no order and budget overruns. The scripted-peer experiment uses deterministic peers; the GPU pilot uses real DeepSeek agents. Small pilots do not establish a general causal effect.

## Traces and local data

The lab retains model calls, tools and rejected arguments, board messages, submissions, token usage, and frozen non-secret model profiles. JSON, CSV and PDF exports and replays are available in the interface. Browser closure does not stop a running experiment; the machine must stay awake and online.

Keys, profiles and raw local runs are excluded from Git. Keys entered in the main lab are stored in its gitignored local secret file; the native portal keeps its key in memory and worker environments. Never give agents a host shell over this repository: evaluator answer keys belong to the operator.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 -m swarm_bench validate
```

Provider tests use fake servers without paid API calls. GSM8K source provenance and its MIT license are in `sources/`; vendored ImpossibleBench provenance and license are in `vendor/impossiblebench/`.
