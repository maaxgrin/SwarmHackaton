# Connecting the ten agents

The server is independent of the model provider and coordination library. A trusted controller creates ten clients, each with its agent’s `connection.json` file. It exposes only the corresponding public methods as tools. Models must not be able to inspect Python attributes, change tokens, or access the controller’s filesystem.

```python
from swarm_bench.client import AgentClient

# Run by the controller, not in a free shell offered to the model.
client = AgentClient("runs/essai-001/agents/agent_01/connection.json")
tools = [
    client.context,
    client.list_files,
    client.read_file,
    client.read_board,
    client.post_message,
    client.submit_ballot,
]
# Register these six methods in your agent framework.
# Repeat for agent_02 through agent_10 with ten separate contexts.
```

`list_files()` discovers available entries; `read_file(path)` reads the requested one and logs the access. These tools have generic descriptions. Do not call them before handing off to the model: deciding to use them is precisely the measured behavior. The initial context does not automatically list available entries.

A physical copy also exists in the exported folder. If you offer direct filesystem access, instrument reads in the adapter and log them to the controller via `GET /file`, without adding instructions to the model. Otherwise, direct reads will not appear in metrics. Logs establish that a tool was used, not that every datum was understood.

## Endpoints

Each request uses `Authorization: Bearer <agent-specific token>`. Identity comes from the token; a field allowing impersonation of another author is rejected.

| Method and path | Function |
| --- | --- |
| `GET /context` | Question, role, phase, and instructions; no answer key or peer’s private vote |
| `GET /files` | Lists workspace entries; this discovery is logged |
| `GET /file?path=PATH` | Reads the requested path, limited to the agent’s environment |
| `GET /board?after=0` | Board messages and cursor; closed during `initial` |
| `POST /messages` | Post with author enforced by the token |
| `POST /ballots` | Sealed private vote for the current phase |

Post:

```json
{
  "content": "My delta_09 is 1523, according to my local file.",
  "evidence": ["delta_09"]
}
```

`evidence` contains only identifiers present in the author’s file. A reply or calculation based on other agents’ messages may mention them in `content`, without declaring them as local evidence.

Ballot:

```json
{
  "stage": "initial",
  "answer": null,
  "base_answer": null,
  "justification": "I have only my own adjustment; the remaining contributions are missing."
}
```

Stages are `initial`, `pre_pressure`, `final`. `answer` is the mutated result, `base_answer` is the reconstructed problem’s `r`. Answers may be JSON integers or strings like `"30"`, `"1.5"`, `"3/2"`; JSON floats, units, and expressions are rejected. A short justification is enough.

**No file read is required to vote**, in all three stages and both prompt styles. A read error does not reveal the expected filename. File mentions in examples in this documentation are for the controller; do not inject them into model instructions.

The first ten ballots automatically open the board. The ten `pre_pressure` ballots trigger the intervention and open `final`. Each agent must then reread the board from zero or from a cursor before injected messages before voting. The ten final ballots end the run.

Errors: `403` for forbidden token or file, `400` for bad request or incompatible phase, `404` for unknown endpoint. JSON requests are limited to 20,000 bytes. Messages may contain at most 5,000 characters and justifications 2,000.

## Orchestration loop

1. Serve the ten agents in the initial phase, without waiting for a single agent to advance the phase alone.
2. After the barrier, let the ten agents discuss for the fixed budget, with their tools available. They decide themselves whether to explore files; do not give them a nudge oriented toward that search.
3. Request the ten `pre_pressure` ballots.
4. Have all ten agents reread the board after the transition, then run the planned verification rounds.
5. Request the ten final ballots and compute the score on the evaluator side.

Modes `swarm` and `leader_led` change instructions and aggregation; scheduling calls and any parallelism remain your responsibility. `dry-run` provides a deterministic test of file, message, and ballot flow, without a model.

The only problem fields sent to the model are `task_id` and `question`. Reconstruction rules stay in `evaluator/spec.json`. Explicit control answers are also stored on the evaluator side; only `--prompt-style explicit` selects them for a new run. The main JSONL has no paths; use `data/evaluator/assignments.jsonl` on the controller side to find files.
