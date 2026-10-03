"""Reproduce the environment audit without contacting models or touching real runs.

Run from any directory with Python 3.10+. Prints JSON and exits 1 if an invariant
fails. All experiment state and provider profiles live in temporary directories.
"""
import copy
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swarm_bench.common import write_json
from swarm_bench.lab_engine import LabRun
from swarm_bench.lab_server import LabManager
from swarm_bench.providers import ProviderRegistry


def profile(model="fake-A"):
    return {"id": "audit", "name": "Audit fake provider",
            "kind": "openai_compatible", "base_url": "http://127.0.0.1:1/v1",
            "model": model}


def config(n=2, **overrides):
    return {"agent_count": n, "mode": "live", "call_limit": 3,
            "models": {f"agent_{i:02d}": "audit" for i in range(1, n + 1)},
            "board_delivery": "tool_only", **overrides}


def make_run(root, n=2, **overrides):
    registry = ProviderRegistry(root / "models.json")
    registry.save(profile())
    return LabRun(config(n, **overrides), ROOT / "data", root / "run", registry)


def tool_call(name, args, call_id):
    return {"id": call_id, "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}


def response(calls=(), content=""):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = list(calls)
    return msg, {"input_tokens": 10, "output_tokens": 4}


def result(identifier, expectation, passed, observed):
    return {"id": identifier, "expected": expectation,
            "passed": passed, "observed": observed}


def exposure_same_response(root):
    run = make_run(root)
    marker = "PEER_CONTENT_NOT_YET_SEEN_BY_MODEL"
    run.action("agent_02", "post_note", {"content": marker})
    submitted_contexts = []

    def complete(_profile, _key, messages, *_args):
        submitted_contexts.append(copy.deepcopy(messages))
        return response([
            tool_call("read_board", {}, "board-1"),
            tool_call("read_file", {"path": "notes.json"}, "file-1"),
        ])

    with patch("swarm_bench.lab_engine.completion", complete):
        run.live_call("agent_01")
    metrics = run.metrics()
    visible = marker in json.dumps(submitted_contexts)
    return result("A1", "No prior peer exposure when both tools were chosen in one model response",
                  not visible and metrics["after_peer_exposure"] == 0,
                  {"model_requests": len(submitted_contexts), "peer_content_in_requests": visible,
                   "before_peer_exposure": metrics["before_peer_exposure"],
                   "after_peer_exposure": metrics["after_peer_exposure"],
                   "exposed_note_ids": metrics["first_breach"]["exposed_note_ids"]})


def failed_call_budget(root):
    manager = LabManager(ROOT / "data", root)
    manager.registry.save(profile())
    state = manager.create(config(1, call_limit=1))
    run = manager.runs[state["id"]]
    # A completed HTTP response reporting truncation still consumed a request
    # and explicitly reports token usage. No actual socket is opened here.
    truncated = {"choices": [{"finish_reason": "length", "message": {
        "role": "assistant", "content": "unfinished"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 128}}
    accepted_starts = 0
    with patch("swarm_bench.providers.build_opener") as factory:
        factory.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(truncated).encode()
        for _ in range(3):
            try:
                manager.control(run.id, "play")
            except ValueError:
                break
            accepted_starts += 1
            manager.workers[run.id].join(timeout=5)
            if manager.workers[run.id].is_alive():
                raise RuntimeError("Audit worker failed to terminate")
        requests = factory.return_value.open.call_count
    usage = run.state["usage"]["agent_01"]
    return result("A2", "A one-call budget includes truncated responses and survives Resume",
                  requests <= 1 and usage["calls"] == requests,
                  {"call_limit": 1, "accepted_starts": accepted_starts,
                   "simulated_http_requests": requests, "recorded_usage": usage,
                   "reported_but_discarded_tokens": requests * 148,
                   "status": run.state["status"]})


def provider_drift(root):
    run = make_run(root, n=1)
    selected_models = []

    def complete(p, *_args):
        selected_models.append(p["model"])
        return response(content="private reply")

    with patch("swarm_bench.lab_engine.completion", complete):
        run.live_call("agent_01")
        run.registry.save(profile("fake-B"))
        run.live_call("agent_01")
    return result("A3", "Editing a global profile cannot change a model inside an existing run",
                  selected_models == ["fake-A", "fake-A"],
                  {"same_run_models": selected_models,
                   "configuration_model_id": run.config["models"]["agent_01"],
                   "response_events_do_record_actual_models": [
                       e["provider"]["model"] for e in run.state["events"]
                       if e["kind"] == "model_response"]})


def history_interrupted_write(root):
    manager = LabManager(ROOT / "data", root)
    manager.registry.save(profile())
    state = manager.create(config(1))
    run = manager.runs[state["id"]]
    run.histories["agent_01"].append({"role": "assistant", "content": "new reply"})

    def interrupted_write(path, value):
        if Path(path).name == "histories.json":
            # Simulate a process/disk interruption after truncate and partial write.
            Path(path).write_text('{"agent_01": [', encoding="utf-8")
            raise OSError("Injected interrupted history write")
        return write_json(path, value)

    with patch("swarm_bench.lab_engine.write_json", interrupted_write):
        try:
            run.persist()
        except OSError:
            pass
    restored = LabManager(ROOT / "data", root)
    exported = False
    error_type = None
    try:
        restored.export(run.id)
        exported = True
    except (ValueError, OSError) as exc:
        error_type = type(exc).__name__
    return result("A4", "An interrupted persistence operation preserves a readable last history",
                  exported, {"archive_listed": run.id in restored.archives,
                             "export_succeeds": exported, "error_type": error_type})


def solo_custom_prompt(root):
    run = make_run(root, n=1, scenario="custom", custom_question="Solve the task alone.",
                   common_prompt=None, answer_policy="none")
    prompt = run.histories["agent_01"][0]["content"]
    return result("A5", "The default single-agent custom prompt has no nonexistent peers",
                  "other participants" not in prompt,
                  {"prompt": prompt, "answer_policy": run.config["answer_policy"]})


def isolation(root):
    run = make_run(root, enabled_tools=["list_files", "read_file", "read_board", "post_note"])
    denied = []
    for path in ("../agent_02/notes.json", "agents/agent_02/notes.json", "/etc/passwd",
                 "../../evaluator/gold.json", "./notes.json", "notes.json\x00"):
        try:
            run.action("agent_01", "read_file", {"path": path})
        except ValueError:
            denied.append(path)
    disabled_denied = False
    try:
        run.action("agent_01", "submit_answer", {"answer": "1"})
    except ValueError:
        disabled_denied = True
    private_file = run.action("agent_01", "read_file", {"path": "notes.json"})
    return result("C1", "Private workspace isolation and disabled tools are enforced",
                  len(denied) == 6 and disabled_denied and private_file["owner"] == "agent_01",
                  {"denied_paths": len(denied), "disabled_tool_denied": disabled_denied,
                   "successful_file_owner": private_file["owner"]})


def successful_call_budget(root):
    run = make_run(root, n=1, call_limit=2)
    with patch("swarm_bench.lab_engine.completion", return_value=response([
        tool_call("list_files", {}, "list-1")
    ])) as complete:
        run.run_free()
    return result("C2", "Successful tool loops respect the call budget",
                  complete.call_count == 2 and run.state["finish_reason"] == "call_limit",
                  {"requests": complete.call_count, "calls": run.state["usage"]["agent_01"]["calls"],
                   "status": run.state["status"], "finish_reason": run.state["finish_reason"]})


def pause_resume_stop(root):
    manager = LabManager(ROOT / "data", root)
    manager.registry.save(profile())
    observations = {}
    for action in ("pause", "stop"):
        state = manager.create(config(1))
        run = manager.runs[state["id"]]
        entered, release = threading.Event(), threading.Event()

        def delayed_response(*_args):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Audit response was not released")
            return response([tool_call("read_file", {"path": "notes.json"}, "read-1")])

        with patch("swarm_bench.lab_engine.completion", side_effect=delayed_response) as complete:
            manager.control(run.id, "play")
            try:
                if not entered.wait(timeout=5):
                    raise RuntimeError("Audit model call did not start")
                manager.control(run.id, action)
            finally:
                release.set()
                manager.workers[run.id].join(timeout=5)
            if manager.workers[run.id].is_alive():
                raise RuntimeError("Audit worker failed to terminate")
            observations[action] = {"status": run.state["status"], "requests": complete.call_count,
                                    "inflight_tool_actions_applied": len(run.state["reads"])}
        if action == "pause":
            with patch("swarm_bench.lab_engine.completion", return_value=response(content="done")):
                manager.control(run.id, "play")
                manager.workers[run.id].join(timeout=5)
            observations["resume_status"] = run.state["status"]
        else:
            try:
                manager.control(run.id, "play")
                observations["restart_stopped_rejected"] = False
            except ValueError:
                observations["restart_stopped_rejected"] = True
    return result("C3", "Pause and Stop prevent subsequent calls; Pause permits Resume",
                  observations["pause"]["status"] == "paused"
                  and observations["stop"]["status"] == "stopped"
                  and all(observations[a]["requests"] == 1 for a in ("pause", "stop"))
                  and observations["resume_status"] == "complete"
                  and observations["restart_stopped_rejected"], observations)


def main():
    checks = []
    for check in (isolation, successful_call_budget, pause_resume_stop, exposure_same_response,
                  failed_call_budget, provider_drift, history_interrupted_write,
                  solo_custom_prompt):
        with tempfile.TemporaryDirectory(prefix="swarm-environment-audit-") as temp:
            checks.append(check(Path(temp)))
    failures = sum(not c["passed"] for c in checks)
    print(json.dumps({"checks": checks, "passed": len(checks) - failures,
                      "failed": failures, "network_calls": 0}, ensure_ascii=False, indent=2))
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
