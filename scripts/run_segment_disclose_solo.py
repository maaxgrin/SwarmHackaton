"""Three strict-solo disclose trials with the same model, scorer and call budget."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_scripted_peer_pressure import current_message_key, DeepSeekTimeout, save
from swarm_bench.lab_server import LabManager, make_lab_server
from swarm_bench.scripted_pressure import ScriptedPressureRun, load_plan, make_solo_config


def main():
    plan = load_plan()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = ROOT / "runs/segment-disclose-solo" / (stamp + "-" + secrets.token_hex(2))
    folder.mkdir(parents=True)
    folder.chmod(0o700)
    os.environ["DEEPSEEK_API_KEY"] = current_message_key()
    manager = LabManager(ROOT / "data", folder / "lab")
    manager.registry.save({"id": "deepseek-scripted-pressure", "name": "DeepSeek Flash · strict solo",
                           "kind": "openai_compatible", "base_url": "https://api.deepseek.com",
                           "model": plan["model"], "reasoning_effort": plan["reasoning_effort"],
                           "token_parameter": "max_tokens", "key_env": "DEEPSEEK_API_KEY"})
    server = make_lab_server(manager, 0)
    base = f"http://127.0.0.1:{server.server_port}"
    design = []
    for seed in plan["seeds"]:
        rid = f"{stamp}-{seed}-solo-{secrets.token_hex(2)}"
        run = ScriptedPressureRun(make_solo_config(seed), ROOT / "data", manager.work_dir / "runs" / rid,
                                  manager.registry, condition="solo")
        manager.runs[rid] = run
        design.append({"seed": seed, "run_id": rid})
    save(folder / "plan.json", {"design": design, "base_url": base, "model": plan["model"],
         "target_instruction": plan.get("target_instruction", ""),
         "reasoning_effort": plan["reasoning_effort"], "max_output_tokens": plan["max_output_tokens"],
         "call_limit": plan["call_limit"], "real_agents": 1, "scripted_agents": 0,
         "task": "Native single-site task; one segment, corrupted extract, sensitive report",
         "comparison_limit": "Headcount changes generated figures and the request from a group total to one's own result."})
    print(json.dumps({"base_url": base, "output": str(folder), "design": design}), flush=True)

    def campaign():
        rows = []
        with patch("swarm_bench.providers.build_opener", DeepSeekTimeout):
            for item in design:
                rid = item["run_id"]
                save(folder / "progress.json", {"phase": "running", "completed": len(rows), "current": item})
                print(json.dumps({"started": rid, "url": base + "/?run=" + rid}), flush=True)
                manager.control(rid, "play")
                worker = manager.workers[rid]
                while worker.is_alive():
                    worker.join(timeout=30)
                    if worker.is_alive():
                        s = manager.snapshot(rid)
                        print(json.dumps({"running": rid, "calls": s["usage"]["agent_01"]["calls"]}), flush=True)
                export = manager.export(rid)
                save(folder / (rid + ".json"), export)
                row = {**item, "status": export["status"], "finish_reason": export.get("finish_reason"),
                       "error": export.get("error"), "metrics": export["metrics"]["scripted_pressure"],
                       "usage": export["usage"]["agent_01"], "peer_notes": len(export["notes"]),
                       "replies": [a["raw_answer"] for a in export["answers"]["agent_01"]],
                       "replay_url": base + "/?run=" + rid}
                rows.append(row)
                save(folder / "results.json", rows)
                print(json.dumps({"finished": rid, "status": row["status"], "calls": row["usage"]["calls"],
                                  "opened": row["metrics"]["report_opened"], "disclosed": row["metrics"]["disclosed"]}), flush=True)
        save(folder / "summary.json", {"results": rows, "completed": sum(r["status"] == "complete" for r in rows),
             "opened": sum(r["metrics"]["report_opened"] for r in rows),
             "disclosed": sum(r["metrics"]["disclosed"] for r in rows),
             "real_agents": 1, "scripted_agents": 0, "peer_messages": sum(r["peer_notes"] for r in rows),
             "calls": sum(r["usage"]["calls"] for r in rows),
             "input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
             "output_tokens": sum(r["usage"]["output_tokens"] for r in rows),
             "limitations": ["Three trials only.", "Native solo task differs from the group task; this is not a matched causal comparison."]})
        save(folder / "progress.json", {"phase": "complete", "completed": len(rows), "design": design})
        print("SOLO COMPLETE", flush=True)

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
