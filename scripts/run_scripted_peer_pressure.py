"""Run matched control/pressure pairs and keep a local replay server open."""
import copy
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_bench.lab_server import LabManager, make_lab_server
from swarm_bench.scripted_pressure import ScriptedPressureRun, load_plan, make_config
from swarm_bench.pilot_helpers import require_deepseek_key as current_message_key, DeepSeekTimeout


def save(path, value):
    from swarm_bench.lab_storage import atomic_json
    atomic_json(path, value)


def main():
    plan = load_plan()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-output-tokens", type=int, default=plan["max_output_tokens"])
    parser.add_argument("--seeds", type=int, nargs="+", default=plan["seeds"])
    args = parser.parse_args()
    plan["max_output_tokens"] = args.max_output_tokens
    if len(args.seeds) != len(set(args.seeds)):
        parser.error("Each seed must appear once")
    plan["seeds"] = args.seeds
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = ROOT / "runs/scripted-peer-pressure" / (stamp + "-" + secrets.token_hex(2))
    folder.mkdir(parents=True)
    folder.chmod(0o700)
    os.environ["DEEPSEEK_API_KEY"] = current_message_key()
    manager = LabManager(ROOT / "data", folder / "lab")
    manager.registry.save({"id": "deepseek-scripted-pressure", "name": "DeepSeek Flash · scripted peers",
                           "kind": "openai_compatible", "base_url": "https://api.deepseek.com",
                           "model": plan["model"], "reasoning_effort": plan["reasoning_effort"],
                           "token_parameter": "max_tokens", "key_env": "DEEPSEEK_API_KEY"})
    server = make_lab_server(manager, 0)
    base = f"http://127.0.0.1:{server.server_port}"
    design = []
    for i, seed in enumerate(plan["seeds"]):
        for condition in (plan["conditions"] if i % 2 == 0 else plan["conditions"][::-1]):
            run_id = f"{stamp}-{seed}-{condition}-{secrets.token_hex(2)}"
            config = make_config(seed, condition)
            config.update(max_output_tokens=plan["max_output_tokens"],
                          total_output_tokens=plan["call_limit"] * plan["max_output_tokens"])
            run = ScriptedPressureRun(config, ROOT / "data",
                                      manager.work_dir / "runs" / run_id,
                                      manager.registry, condition=condition)
            manager.runs[run_id] = run
            design.append({"seed": seed, "condition": condition, "run_id": run_id})
    save(folder / "plan.json", {**plan, "design": design, "base_url": base,
         "timeout_seconds": 180, "temperature": None, "board_delivery": "push",
         "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (ROOT / "swarm_bench/scripted_pressure.py", ROOT / "swarm_bench/lab_engine.py",
                                      ROOT / "swarm_bench/segment_report.py", ROOT / "swarm_bench/providers.py")},
         "interpretation": "Paired exploratory pilot, not a general rate estimate; numeric matching requires response review."})
    save(folder / "progress.json", {"phase": "prepared", "completed": 0, "design": design})
    print(json.dumps({"base_url": base, "output": str(folder), "design": design}), flush=True)

    def campaign():
        rows = []
        with patch("swarm_bench.providers.build_opener", DeepSeekTimeout):
            for item in design:
                rid = item["run_id"]
                save(folder / "progress.json", {"phase": "running", "completed": len(rows),
                                               "current": item, "base_url": base, "design": design})
                print(json.dumps({"started": rid, "condition": item["condition"], "seed": item["seed"],
                                  "url": base + "/?run=" + rid}), flush=True)
                manager.control(rid, "play")
                worker = manager.workers[rid]
                while worker.is_alive():
                    worker.join(timeout=30)
                    if worker.is_alive():
                        snapshot = manager.snapshot(rid)
                        print(json.dumps({"running": rid, "calls": snapshot["usage"]["agent_01"]["calls"],
                                          "opened": snapshot["metrics"]["scripted_pressure"]["report_opened"],
                                          "pressure_notes": snapshot["metrics"]["scripted_pressure"]["pressure_notes"]}), flush=True)
                export = manager.export(rid)
                save(folder / (rid + ".json"), export)
                row = {**item, "status": export["status"], "finish_reason": export.get("finish_reason"),
                       "error": export.get("error"), "metrics": export["metrics"]["scripted_pressure"],
                       "usage": export["usage"]["agent_01"], "scripted_peer_calls":
                           sum(export["usage"][a]["calls"] for a in plan["peers"]),
                       "replay_url": base + "/?run=" + rid}
                rows.append(row)
                save(folder / "results.json", rows)
                print(json.dumps({"finished": rid, "status": row["status"], "calls": row["usage"]["calls"],
                                  "disclosed": row["metrics"]["disclosed"],
                                  "after_pressure": row["metrics"]["disclosure_after_pressure"]}), flush=True)
        pairs = []
        for seed in plan["seeds"]:
            matched = {r["condition"]: r for r in rows if r["seed"] == seed}
            pairs.append({"seed": seed, **{condition: {
                "run_id": row["run_id"], "status": row["status"],
                "opened": row["metrics"]["report_opened"], "disclosed": row["metrics"]["disclosed"],
                "after_pressure": row["metrics"]["disclosure_after_pressure"],
                "calls": row["usage"]["calls"]} for condition, row in matched.items()}})
        save(folder / "summary.json", {"pairs": pairs, "results": rows,
             "real_agents_per_run": 1, "scripted_agents_per_run": 3,
             "scripted_peer_api_calls": sum(r["scripted_peer_calls"] for r in rows),
             "input_tokens": sum(r["usage"]["input_tokens"] for r in rows),
             "output_tokens": sum(r["usage"]["output_tokens"] for r in rows),
             "limitations": ["Three pairs only; generation is not seeded by the dataset seed.",
                             "Numeric disclosures are a proxy; review the published text.",
                             "Messages demand only the missing figure, never an explicit confidentiality breach."]})
        save(folder / "progress.json", {"phase": "complete", "completed": len(rows), "base_url": base, "design": design})
        print("CAMPAIGN COMPLETE", flush=True)

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
