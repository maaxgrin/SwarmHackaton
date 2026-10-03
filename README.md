# Swarm Lab

**The shared foundation for building your collective-behavior experiments among LLM agents.** Configure the group, prompts, models, tools, and private information; observe exchanges and export traces.

**Peer pressure** is the first included experiment. Sacrifice, emergence of a leader, following a designated leader, and use of the message board are research directions to define with the group. The tool does not assign them a score or default protocol.

## Getting started

```bash
git clone https://github.com/maaxgrin/SwarmHackaton.git
cd SwarmHackaton
python3 -m swarm_bench lab --port 8766
```

On Windows, use `python` instead of `python3` if that command is not on your PATH.

Open **http://127.0.0.1:8766**. The lab UI needs **Python 3.10+** only (stdlib; no `pip install` required). The GitHub repository is public; profiles and API keys stay local and are not included.

- To explore the monitor without a key: under **Experiment type**, choose **Peer pressure · split data**, set **Execution** to **Demo · no LLM**, then create and start. Scripted demo is available only for peer pressure (its five default tools).
- For your protocol: choose **Free experiment · your protocol**, enter the shared task, open **Prompts, files, tools, and models**, then prepare each agent’s settings. Demo is disabled here; use **Live models** when you are ready to run.
- To run LLMs: open **Models**, create profiles, assign one per agent, set **Execution** to **Live models**, then create and start. Keys can stay empty during preparation; local servers may work without a key.

## What the shared foundation provides

| Element | Settings and behavior |
| --- | --- |
| Group | 1 to 32 agents, identical or different models, optional leader |
| Scenarios | Peer pressure, free experiment, communication, altruism with Python, group misalignment, and ARC-AGI-3 |
| Prompts | Customizable common prompt, private instructions per agent, preview of the exact prompt |
| Task and files | Included corpus or free task; private text / JSON files per agent |
| Tool calls | Global or per-agent selection among file tools, `read_board`, `post_note`, `submit_answer`, isolated Python, and ARC tools |
| Message board | Shared board; voluntary read, optional automatic publication, or direct injection of a note into peers’ context |
| Execution | Independent loops; optional wait for a peer after posting, message cap, temperature, token budget, call cap, pause and stop |
| Leader and answer | Leader designation separate from collective answer choice: plurality, leader answer, or individual answers only |
| Models | OpenAI Chat Completions–compatible API, Anthropic Messages; configurable URL and model, local or remote |
| Sharing | JSON config import/export, copy settings from a run, full JSON logs and CSV comparison |

A disabled tool is truly unavailable. Conversely, in peer pressure, `don't access files` is a prompt instruction: `read_file` remains usable to observe whether the agent transgresses. An incorrect math answer does not block continuing runs or analyzing transgressions.

Models only access files in their environment through exposed tools. Full exports are for researchers: they include prompts, private files, conversations, calls, and tool results. Demos are scripted and labeled; they do not measure any LLM.

**Optional runtimes** (not required to open the lab): agent Python runs in an isolated WASI VM (`python3 scripts/setup_python_runtime.py`); ARC-AGI-3 needs the official runtime and public games (`python3 scripts/setup_arc_runtime.py`). Those setup scripts expect a Unix-style layout (for example `.venv/bin/python`); use Linux, macOS, or WSL on Windows for altruism Python and ARC experiments.

## Preparing an experiment as a team

1. Import [the minimal free configuration](examples/custom.json) or [peer pressure](examples/peer-pressure.json), or use the form.
2. Define the task, available information, instructions, and tools. Assign your own model profiles.
3. Export the configuration and add it to the repository to share. Import does not start any run.
4. Agree on your experiment’s criteria and analyze exported traces. No general “swarm spirit” score is defined yet.

[Create and extend an experiment](docs/EXPERIENCES.md) · [Lab guide and peer pressure](docs/LABORATOIRE.md) · [Corpus and legacy protocol](docs/CORPUS.md)

## Local data and keys

The repository contains no API keys, model weights, or logs from our local runs. Profiles and runs are stored in `runs/lab/`, ignored by Git. A key entered in the UI stays in server memory; you can also use an environment variable. Profiles are per installation.

The server listens only on `127.0.0.1`. File isolation is enforced by engine tools; do not give participants a shell on the whole repository, which contains GSM8K answer keys reserved for the evaluator.

The [restored seven-agent preset](examples/peer-pressure-seven-agents.json), its [loading instructions](docs/EXPERIENCES.md#seven-contribution-preset), and a [keyless Terra profile](examples/provider-terra.json) are included. The latest measurement, budget, and persistence fixes are documented in [audit corrections](docs/AUDIT_CORRECTIONS.md).

## Verify the project

```bash
python3 -m unittest discover -s tests -v
python3 -m swarm_bench validate
```

Provider tests use fake servers, with no key or paid request. The corpus includes 100 mutated GSM8K questions, their two variants, and source provenance under the [MIT license](sources/GSM8K-LICENSE.txt).
