"""Resume each failed pilot once from its checkpoint without resetting budgets."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_scripted_peer_pressure import current_message_key, DeepSeekTimeout, save
from swarm_bench.lab_server import LabManager, make_lab_server
from swarm_bench.lab_storage import load_run
from swarm_bench.scripted_pressure import ScriptedPressureRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    folder = parser.parse_args().campaign.resolve()
    plan = json.loads((folder / "plan.json").read_text())
    os.environ["DEEPSEEK_API_KEY"] = current_message_key()
    manager = LabManager(ROOT / "data", folder / "lab")
    pending = []
    before = folder / "before-resume"
    before.mkdir(exist_ok=True)
    for item in plan["design"]:
        rid = item["run_id"]
        state, histories = load_run(manager.work_dir / "runs" / rid)
        if state["status"] != "error":
            continue
        if state.get("bounded_resume_attempted"):
            continue
        assert state["token_budget"]["in_flight"] == 0
        snapshot = manager.export(rid)
        save(before / (rid + ".json"), snapshot)
        run = ScriptedPressureRun(state["config"], ROOT / "data", manager.work_dir / "runs" / rid,
                                  manager.registry, condition=item["condition"], preview=True)
        assert run.workspaces == state["workspace_state"]
        assert run.prompt(run.target) == histories[run.target][0]["content"]
        assert run.question == state["question"]
        profile, key = manager.registry.resolve(run.config["models"][run.target])
        assert profile == state["provider_profiles"][run.target]
        run.state = copy.deepcopy(state)
        run.histories = copy.deepcopy(histories)
        run._provider_keys = {run.target: key}
        run.preview = False
        run.state["bounded_resume_attempted"] = True
        run.state["resume_source_sha256"] = hashlib.sha256((ROOT / "swarm_bench/scripted_pressure.py").read_bytes()).hexdigest()
        run.persist()
        manager.archives.pop(rid, None)
        manager.archive_histories.pop(rid, None)
        manager.runs[rid] = run
        pending.append(item)
    server = make_lab_server(manager, 0)
    base = f"http://127.0.0.1:{server.server_port}"
    save(folder / "resume-plan.json", {"pending": pending, "base_url": base,
         "rule": "One resume, same histories, no repeated contributions, preserved counters and caps."})
    print(json.dumps({"base_url": base, "pending": pending, "output": str(folder)}), flush=True)

    def campaign():
        with patch("swarm_bench.providers.build_opener", DeepSeekTimeout):
            for item in pending:
                rid = item["run_id"]
                save(folder / "progress.json", {"phase": "resuming", "current": item, "base_url": base})
                manager.control(rid, "play")
                worker = manager.workers[rid]
                while worker.is_alive():
                    worker.join(timeout=30)
                    if worker.is_alive():
                        s = manager.snapshot(rid)
                        print(json.dumps({"resuming": rid, "calls": s["usage"]["agent_01"]["calls"]}), flush=True)
                e = manager.export(rid)
                save(folder / (rid + ".json"), e)
                print(json.dumps({"resumed": rid, "status": e["status"],
                                  "calls": e["usage"]["agent_01"]["calls"],
                                  "disclosed": e["metrics"]["scripted_pressure"]["disclosed"],
                                  "error": e.get("error")}), flush=True)
        rows = []
        for item in plan["design"]:
            e = manager.export(item["run_id"])
            save(folder / (item["run_id"] + ".json"), e)
            rows.append({**item, "status": e["status"], "finish_reason": e.get("finish_reason"),
                         "error": e.get("error"), "metrics": e["metrics"]["scripted_pressure"],
                         "usage": e["usage"]["agent_01"], "scripted_peer_calls": sum(
                             e["usage"][a]["calls"] for a in ("agent_02", "agent_03", "agent_04")),
                         "resumed": bool(e.get("bounded_resume_attempted")),
                         "replay_url": base + "/?run=" + item["run_id"]})
        save(folder / "results.json", rows)
        summary = {"results": rows, "completed": sum(r["status"] == "complete" for r in rows),
                   "incomplete": sum(r["status"] != "complete" for r in rows),
                   "scripted_peer_api_calls": sum(r["scripted_peer_calls"] for r in rows),
                   "input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
                   "output_tokens": sum(r["usage"]["output_tokens"] for r in rows),
                   "limitations": ["Small paired sample; resumed technical errors are recorded.",
                                   "Generation is stochastic; dataset seeds do not seed model generation."]}
        save(folder / "summary.json", summary)
        save(folder / "progress.json", {"phase": "complete", "completed": summary["completed"],
                                       "incomplete": summary["incomplete"], "base_url": base})
        print("RESUMES COMPLETE", flush=True)

    threading.Thread(target=campaign, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for run in manager.runs.values():
            run.pause_requested.set()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
