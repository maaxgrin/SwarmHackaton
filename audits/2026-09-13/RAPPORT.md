# Agent environment audit — Swarm Lab

**Date: September 13, 2026. Verdict: the foundation works, but two priority defects prevent treating measurements and budgets as fully reliable.** Five anomalies were reproduced. File isolation, disabled tools, and normal loops passed checks performed.

The audit covers the project `SprintHF` lab, its `LabRun` engine, adapters, local server, and logs. It does not cover general Codex configuration. Starting point is commit `0e9be46`, with seven files already modified locally, including the engine and tests. Findings describe this local code. The only files added by this audit are in this folder.

## Checks performed

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | **45 tests passed**, including lab and legacy protocol |
| `python3 -m swarm_bench validate` | **100 questions, 200 variants, 9,704 checks passed** |
| Targeted reproductions from this audit | **3 checks passed, 5 invariants failed** |
| Server running on `127.0.0.1:8766` | Reachable; 100 tasks and five expected tools |
| Server preview compared to code on disk | Identical for peer pressure solo with restriction at top and free solo |
| Ollama on `127.0.0.1:11434` | Reachable; four configured local profiles reference installed models |
| Fifth profile | Draft without URL or model; not ready to start |
| Local history | 27 runs listed, 24 marked `live_models` and three demos |

Probes use fake providers and temp folders. No new LLM generation call was launched. Access to the existing server was limited to read and two previews without creating a run. The diagnosis therefore does not certify current quality of each real model’s responses.

Local traces were examined without copying them into this folder. They span several engine versions: they are not all validations of current code.

## Confirmed anomalies

### A1 — P1: a read is classified “after exposure” before the model received messages

**Code:** [lab_engine.py](../../swarm_bench/lab_engine.py), lines 311–314 and 401–425.

A peer posts a note. The restricted agent, which has not received it yet, produces **one response** with two calls: `read_board`, then `read_file`. The engine runs the first tool and immediately updates `exposures`. It then runs the second and classifies the read as after peer exposure.

Reproduction gives `after_peer_exposure = 1` and `before_peer_exposure = 0`, while note content was in **no request sent to the model**. Both tool decisions were already produced before execution.

**Consequence:** measurement confuses tool execution order with information available when the model chose its action. Transgression count stays correct, but temporal classification may be wrong.

**Proposed fix:** keep, for each model response, notes included in its request. Attribute to actions in that response that prior exposure. `read_board` results become available for a later decision. Distinguish in traces “tool result retrieved” and “result sent to model”, with request and call ids.

**Scope observed:** defect reproduced with fake model; no message simultaneously containing `read_board` and `read_file` was found in the 24 examined local LLM histories. This audit therefore does not attribute this defect to transgressions already observed.

### A2 — P1: truncated responses escape call counter and cap

**Code:** [providers.py](../../swarm_bench/providers.py), lines 153–168; [lab_engine.py](../../swarm_bench/lab_engine.py), lines 401–410 and 438–440; [lab_server.py](../../swarm_bench/lab_server.py), lines 104–154.

The adapter raises when the response hits the token cap. The counter increments only after a successful adapter return. The request actually made and tokens reported by that response are lost for accounting. An errored run can then resume with the same counter.

**Reproduction:** with `call_limit = 1`, three start/resume cycles produce **three simulated HTTP requests**, but counters stay at **zero calls and zero tokens**. Fake responses report 444 tokens total that are not recorded.

**Consequence:** underestimation of resources consumed and exceeding cumulative budget via successive resumes. There is no infinite automatic retry; reproduced overrun goes through “Resume”. Truncation errors also exist in local histories, without cost reconstructable from those counters.

**Proposed fix:** count each call attempt before send, distinguish attempts, successes, and errors, then keep available usage even if the response is unusable. Apply cap to cumulative attempts, including resumes. Do not count failed profile validation before any call as a sent request.

### A3 — P2: editing a global profile changes an existing run’s model

**Code:** [lab_engine.py](../../swarm_bench/lab_engine.py), lines 401–411; [providers.py](../../swarm_bench/providers.py), lines 70–90.

Each call resolves the global profile again by id. In reproduction, first call uses `fake-A`. After editing the same profile, the second call of the same agent and run uses `fake-B`, while run config keeps the same profile id.

**Consequence:** risk of involuntarily changing an experimental condition while preparing other experiments or between pause and resume. `model_response` events correctly keep the profile actually used; drift remains detectable in detailed export.

**Proposed fix:** freeze a copy of each profile’s non-secret parameters at first start. A global edit should apply to new runs. If mid-run change is desired, make it an explicit logged intervention. No need to freeze plaintext secrets on disk.

### A4 — P2: a save interruption can make a history unusable

**Code:** [lab_engine.py](../../swarm_bench/lab_engine.py), lines 269–276; [common.py](../../swarm_bench/common.py), function `write_json`; [lab_server.py](../../swarm_bench/lab_server.py), lines 75–102.

`state.json` is replaced via a temp file. `histories.json` is rewritten directly, truncating previous content. Interruption during that write can leave incomplete JSON.

**Reproduction with injected failure:** a history write is interrupted after a JSON fragment. After reloading the manager, the run appears in archives but export fails with `JSONDecodeError`.

**Consequence:** loss of viewability and export after write incident or stop at the wrong moment. No corruption of this type was seen in read local files: it is a fault-injection test.

**Proposed fix:** also replace histories atomically and preserve last valid version. To guarantee consistency between state and conversations after incident, use a common snapshot or snapshot generations with a validation pointer. Also test interruption between saving an action and saving its result in history.

### A5 — P2: free solo prompt asks to collaborate with nonexistent agents

**Code:** [lab_engine.py](../../swarm_bench/lab_engine.py), lines 44, 120–122 and 239–244.

With `scenario = custom`, one agent, and default common prompt, the system first says the agent works alone, then asks it to work with other participants. The defect was also confirmed via preview on the currently open server.

**Consequence:** the free solo control receives contradictory instructions and may seek contributions that do not exist. Peer pressure preset solo passes its tests; it is the free branch that lacks coverage.

**Proposed fix:** choose a common default suited to headcount, while keeping a researcher-explicit custom common prompt. Add a test covering `custom` with one agent and absent or `null` prompt.

## Confirmed behavior and limits

- **Private files:** six out-of-scope path forms are rejected in the extra probe. An authorized read returns only the calling agent’s file. Contents come from the engine’s private dict, without shell access.
- **Tools:** a disabled tool is refused at execution. Textual no-read restriction remains intentionally transgressable, per protocol.
- **Prompts:** tests verify private restrictions are not added to peers’ prompts, top position works, and files are not preloaded.
- **Coordination:** tests verify independent agent start, immediate board access, plurality and leader rules, and distinction between explicit and automatic publication.
- **Normal budget:** successful tool-loop calls stop at the intended cap. Problem A2 concerns failed calls, notably truncated responses.
- **Pause, resume, stop:** probes confirm no further calls after command is honored and resume after pause. However, an HTTP request already in flight completes and **its tools are still executed**, including after stop request. `operator_stop` events mark a request, not immediate cutoff of observations. Configured local HTTP delay can reach 600 seconds.
- **Secrets and archives:** existing tests verify a test key is neither persisted nor returned in profiles, provider redirects are refused, and third-party origins are rejected. Reloading archives does not relaunch any model.

The server remains for the local evaluator. Tested isolation is that of tools offered to LLMs; it does not make the whole repository a sandbox for an agent given a shell separately.

## Reproduce and decide

From project root:

```bash
python3 audits/2026-09-13/check_environment.py
```

The script uses only the standard library, produces JSON, and returns **exit code 1 while at least one invariant fails**. Results of that run are kept in [results.json](results.json). It writes no run under `runs/lab` and opens no network connection.

**Priority: fix A1 and A2 before a comparative campaign, then A3–A5.** Add corresponding cases to the regression suite and redo a short path with chosen local models to then distinguish engine guarantees from those models’ real capabilities. Scripted demos and fake tests are not enough to establish that a model follows an instruction or yields to pressure.
