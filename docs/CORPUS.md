# GSM8K corpus and legacy tool

This page describes the included corpus and the historical `serve` command. For the variable-headcount shared engine and free experiments, see the [README](../README.md) and [experiments guide](EXPERIENCES.md).


**100 GSM8K problems where useful data exists in the environment, without the prompt saying to fetch a file.** Ten agents can explore, discuss, answer, or abstain. The server never mandates reading: you can therefore measure failure to explore.

- `data/questions.jsonl`: **100 questions ready to load**, only `task_id` and `question`, no filename or processing metadata.
- `data/evaluator/assignments.jsonl`: mapping to files and variants, for the controller only. The main batch has 50 cases with a complete file and 50 distributed cases.
- `data/tasks/`: each problem also exists in **both versions**, i.e. 200 paired instances and 2,000 index files.
- `data/evaluator/`: answers, source solutions, and provenance, for the evaluator only.
- `swarm_bench/`: reproducible generator, HTTP message board, per-agent tools, and score computation.
- `docs/EXEMPLE.md`: one problem explained with its ten contributions.
- `docs/PROTOCOLE.md`: social pressure and leadership protocol.
- `docs/API.md`: wiring to your agent system.

## How questions are mutated

Problems come from the [official GSM8K test set](https://github.com/openai/grade-school-math/blob/3101c7d5072418e28b9008a6636bde82a006892c/grade_school_math/data/test.jsonl), under the [MIT license](../sources/GSM8K-LICENSE.txt). Source version, SHA-256 fingerprint, and selected indices are kept.

1. **50 cases with `?`**: one quantity in the story is replaced by `?`, and the final correction is indicated by `c = ?`.
2. **50 cases with omission**: the story is complete, but the requested calculation involves “the case correction” without giving its value.
3. The source problem gives `r`. The requested result is `Y = multiplier × r + c`. The definition of `c` and its ten contributions are in a file simply named `notes.json`, discoverable with generic tools. No instruction mentions this file in implicit mode.

Both gap types are balanced with both file layouts: 25 problems in each of the four combinations in the main batch. In the notes, `c` is defined as the sum of `delta_01` through `delta_10`. That detailed formula is not revealed before discovery. Numeric answers for the 100 problems from the previous version are preserved.

**`implicit` is the default.** **`explicit`** adds to the same question an instruction stating which file to consult and how to combine contributions. It serves as a paired control, with exactly the same files and answer key. Even in that control, an agent may ignore the instruction and vote without reading.

Quantities and the math solution of the original problem are preserved: **mutation affects data access and the final calculation**, not a full numeric rewrite of the story. Prompts and agent instructions remain in English to keep source text. Documentation is in English.

| Version | Each agent’s private file content | Collaboration needed to determine FINAL |
| --- | --- | --- |
| `complete` | Full copy of parameters and all ten adjustments | No: control for file consultation and social pressure |
| `split10` | Subset of parameters and exactly one independent adjustment | Yes: all ten contributions are required |

In `split10`, an agent may have an adjustment without a story parameter. Its contribution is still necessary. Index assignment is shuffled. Both versions of the same problem have exactly the same total information and final answer. Memorizing the GSM8K answer is not enough to determine the new result. A guessed answer remains possible; we do not claim to prove a correct value came from careful reading.

## Verify immediately

From this folder, with Python 3.10 or newer, no external dependency:

```bash
python3 -m swarm_bench validate
python3 -m unittest discover -s tests -v
python3 -m swarm_bench dry-run --variant split10 --pressure majority_wrong
```

`dry-run` explicitly uses a scripted oracle that reads the answer key: **it verifies protocol operation, not model performance**. No LLM evaluation results are provided in this delivery.

## Open a ten-agent experiment

```bash
python3 -m swarm_bench serve \
  --task gsm8k_0001 \
  --variant split10 \
  --orchestration leader_led \
  --pressure leader_wrong \
  --run-dir runs/essai-001
```

The server listens on `127.0.0.1:8765`. It exports ten folders under `runs/essai-001/agents/`, each with `problem.json`, `notes.json`, `connection.json`, and generic instructions. Each token only allows access to that agent’s file and the shared board. Individual ballots stay private. Add `--prompt-style explicit` for the control.

Initial context contains no file list, no useful filename, no sharing rule, and no warning to check files. Tools `list_files()` and `read_file(path)` are available without being called automatically. **Do not preload notes into the prompt or ask agents to search for a file.** Folders `evaluator/`, the manifest, and answer keys are not part of agent context.

The historical **`serve` command does not run models**: it lets you wire your own orchestrator to ten participants. The new **`lab`** command, described at the top of this page, provides the UI and model execution with variable headcount. The legacy protocol client is described in [API.md](API.md).

Give each model only its allowed tools, or mount only its folder in a separate container. **Neighboring folders are not system isolation.** An agent with a shell on this whole repository could read answer keys or others’ files. The controller keeps tokens; it exposes agent methods, without passing other clients or the `Experiment` object. The API is local and not designed for exposure on the internet.

After the three phases and thirty ballots:

```bash
python3 -m swarm_bench score --run-dir runs/essai-001
```

The log and ballots are in `state.json`, metrics in `score.json`. Every action is logged. Stop with `Ctrl-C`; resuming an interrupted experiment is not implemented. Use a new folder per run, since existing folders are not overwritten.

## Available conditions

| Axis | Values |
| --- | --- |
| Information access | `complete`, `split10` |
| Search hint | `implicit` by default, `explicit` for control |
| Coordination | `swarm`: plurality decision; `leader_led`: coordinator decision |
| Pressure after sharing | `none`, `majority_wrong`, `leader_wrong`, `peer_wrong` |

The main corpus has exactly 100 instances. 100 problems × 2 layouts × 2 coordinations × 4 pressures yields **1,600 runs per prompt style**, or 3,200 for full implicit/explicit comparison, before repetitions. None of these model runs start automatically.

Metrics include consultation before each ballot, answers given without local read, their accuracy, and the first agent to list/read files or share evidence. Another agent may relay information on the board: an answer without local read is therefore not automatically hallucination. The leader role rotates fairly; see the [protocol](docs/PROTOCOLE.md).

## Regenerate or scale to 1,000 questions

```bash
python3 -m swarm_bench generate --count 100 --seed 42 --output data-seed42
python3 -m swarm_bench generate --count 1000 --seed 42 --output data-1000
python3 -m swarm_bench validate --data data-1000
```

Selection is deterministic and duplicate-free among eligible problems. The full official source is in `sources/`, for the controller only. The same seed reproduces selection, adjustments, and owners. For new evaluations, use seeds not disclosed to agents and contexts without answer keys. This repository and its full archive are **tools for the evaluator**, not environments to hand entirely to participants.
