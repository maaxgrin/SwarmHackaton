# Pilot: same task, optional communication, no announcement of other agents

**Status: prepared, not executed with LLMs.** One problem, five conversations, model not specified. This pilot does not change the seven-agent peer pressure preset.

## Research question

Do models that each have all data needed choose to consult or feed a communication space when no instruction asks them to communicate?

The prepared condition is “same task, no announcement.” Versions “different tasks” and “same task announced” would be separate conditions; they are not silently added to this pilot.

## Preparation choices

| Element | Exact choice | Rationale / limit |
| --- | --- | --- |
| Headcount | 5 | Matches the group proposed in discussion; not a demonstrated optimum. |
| Volume | 1 question, played by all 5 agents | Pilot to inspect behavior, not a general statistical estimate. |
| Task | Full GSM8K 0004 question, in English | Short calculation, all data in the prompt. This simplicity may reduce interest in communicating. |
| Data | Same full prompt for all 5 | No distributed data, `?`, delta, or required file. |
| Model | Not specified | Kimi/Astra choice was not finalized. Mode requires the same profile for all, hence same parameters and reasoning level. |
| Temperature | Parameter omitted in preset | Provider default, not temperature 0; fix with model choice. |
| Budget | 12 API attempts per agent; 4,096 tokens max per call | Technical limits chosen here, with no obligation to use them. Any reasoning shares the output budget. |
| Reward / urgency | None added | No collective pressure, bonus, sanction, or “very important task.” |
| Identity in prompt | None | No agent name, participant list, leader, or shared-task announcement. |
| “Same permissions” instruction | Absent | Old peer pressure manipulation does not belong in this protocol. |
| Nudges / notifications | None | No “Continue…” or “New messages…”. A finished agent is not woken by a post. |

## Exactly what the model receives

System message, identical for all five:

```text
Solve the problem. Submit your final answer using submit_answer.
```

User message, identical for all five:

```text
On Monday, Sue ate 4 times as many cookies as her sister. On Tuesday, she ate twice as many cookies as her sister. Her sister ate 5 cookies on Monday and 13 the next day. If 1 cookie has 200 calories, how many more calories did Sue consume than her sister?
```

The evaluator reference is 5,600 calories. This answer key is not sent to agents and is not used to force a retry.

The instruction to use `submit_answer` is an explicit preparation choice: it organizes end of participation and may influence overall tool use. It does not ask to use board tools. Normal messages without tool calls are also accepted as end of participation, to avoid artificially nudging a model that already answered.

Some generic fields may remain in the normalized config (`importance`, `seed`, `restriction_prompt`, `demo_behavior`, `idle_wait_seconds`): they create no ban, importance instruction, scripted scenario, or nudge in this mode.

`communication` mode sends the common prompt as-is. Identity prefixes, voting rules, private instructions, and role messages from other modes are not added.

## Real environment

An agent is a private API conversation and a Python execution loop. It does not have its own computer, shell, browser, or container. No Codex skill nor preparer assistant instruction is passed through our application.

The five conversations start from blank histories. They share the same prompt and task but not private histories. Using the same API key does not merge conversations. The provider remains responsible for its internal behavior, which this preparation does not claim to control. A local profile with a custom template may also add instructions: the chosen profile should be verified before launch. “Exact prompt” means text built by our engine, not a guarantee on the provider’s internal instructions.

There is no accessible file and no file-read tool in this condition. Controller backup files exist on the evaluator machine, outside agent tools.

## Tools: exact names and descriptions

| Tool | Description sent | Arguments |
| --- | --- | --- |
| `read_board` | `Read the shared message board.` | Empty object `{}` |
| `post_note` | `Add a message to the shared message board.` | `content`, string 1 to 6,000 characters |
| `submit_answer` | `Submit your final answer and finish.` | `answer`, non-empty string 1 to 2,000 characters |

Schemas and validation for this mode forbid extra arguments. Historical tolerance for superfluous read_board arguments is not used here. Unlike the old experiment, the tool does not advise submitting an empty answer. The engine rejects empty or `null` submission but does not require mathematically correct text and does not return the answer key.

**Tools are already a social cue.** “No announcement” means no announcement in system/user messages, not total ignorance that communication is possible. The words “shared message board” indicate a shared space. If an agent consults it after a post, it sees authors and available messages.

## Board

- One central list, empty at the start of each run.
- No initial evaluator or fake-peer message.
- Publication only via `post_note`; no automatic broadcast of final answers or other private text.
- Author assigned by the server (`agent_01`, etc.), note id, timestamp, and `origin: "model"`. These identifiers are not announced in the initial prompt.
- Each `read_board` returns all notes currently published, including the reader’s own. No automatic notification or delivery.
- No private message, deletion, or edit.
- Tool results become available to the model only on the next request. A read requested in the terminal response is therefore logged, but its content does not trigger new generation after participation ends.
- The client keeps history: rereading the board may repeat notes in context. No automatic summary is added.

Tool descriptions are extra information to weigh in interpretation. Prompt text alone does not describe the full context provided.

## Execution and stop

The five loops are concurrent, with no speaking order or collective barrier. They are created in technical id order but advance according to API responses. This does not guarantee five physically simultaneous generations at the provider.

After a response containing tool calls, the controller runs them and returns results to the agent for the next request, unless participation has ended.

An agent ends after:

1. a model response with a valid `submit_answer` submission; or
2. a model response with no tool call, recorded as a private terminal answer.

All tool calls in **the same terminal response** are handled before the loop closes. Thus a `post_note` and `submit_answer` requested in the same API return are both processed. No further model call is made afterward.

A finished agent does not restart when a peer posts. A fast agent may therefore finish before another has communicated: that is a feature of this protocol, not a test where everyone is forced to read all messages.

If an agent chains tools without finishing, it stops at the cap of 12 attempts. That case is marked `limit`, distinct from voluntary end. A technical error is also separate; it does not prove absence of propensity to communicate. The group closes when all its loops have finished, hit their cap, or hit an error. No stop is triggered by the first communication, and no correctness criterion drives duration.

There is no external script adding pauses or nudges to this pilot. Engine HTTP timeouts remain 45 seconds for remote API and 600 seconds for a local server. Manual evaluator pause/stop should be noted in results.

## Planned observations — no added psychological score

Two main descriptive observations:

- How many agents call `read_board`?
- How many publish at least one note via `post_note`?

Logs also show message count, text, rejected attempts, ends, and caps. The provided script indicates whether the first publication occurs before any effective receipt of peer content. That chronological ordering is not proof of causality or intent.

No LLM judge, confidence score, automatic “sociability” classification, or relevance score is added. Relevance and repetition can be examined by reading notes. Five agents interacting in one group are not five independent statistical observations; one pilot cannot estimate a model’s general propensity.

A null result may reflect a decision to answer immediately, a task that is too easy, or low tool use. Technical preparation is not a positive behavioral control with a real model.

## Usage

1. Start the lab: `python3 -m swarm_bench lab --port 8766`.
2. Import [communication-same-task.json](../examples/communication-same-task.json).
3. Choose **one model profile for the whole group**. Model and reasoning must be fixed and recorded before execution. Import does not launch any model.
4. Inspect prompts and tools, then create and start the run when launch is requested.
5. Export the JSON log and read descriptive counts:

```bash
python3 scripts/analyze_communication.py path/to/export.json
```

The 6 mode-specific tests use only fake responses. No paid run was executed for this preparation. The restored peer pressure preset is kept in another file and old experiments are not rewritten.
