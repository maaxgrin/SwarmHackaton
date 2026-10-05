"""Test the published GPU procurement control and pressure presets with DeepSeek."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_bench.lab_server import LabManager, make_lab_server
from swarm_bench.lab_storage import atomic_json
from swarm_bench.pilot_helpers import require_deepseek_key as credential, DeepSeekTimeout as LongerTimeout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-for-peer", action="store_true")
    args = parser.parse_args()
    os.environ["DEEPSEEK_API_KEY"] = credential()
    folder = ROOT / "runs/gpu-deepseek" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True)
    folder.chmod(0o700)
    manager = LabManager(ROOT / "data", folder / "lab")
    manager.registry.save({"id": "deepseek-gpu", "name": "DeepSeek Flash · GPU pilot",
        "kind": "openai_compatible", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
        "reasoning_effort": "low", "token_parameter": "max_tokens", "key_env": "DEEPSEEK_API_KEY"})
    design = []
    for i, seed in enumerate((42, 43, 44)):
        conditions = ("control", "pressure") if i % 2 == 0 else ("pressure", "control")
        for condition in conditions:
            filename = "gpu-procurement-baseline.json" if condition == "control" else "gpu-procurement.json"
            config = json.loads((ROOT / "examples" / filename).read_text())
            config.update(title=f"DeepSeek GPU · {condition} · seed {seed}", seed=seed,
                          models={f"agent_{a:02d}": "deepseek-gpu" for a in range(1,5)},
                          max_output_tokens=16000, total_output_tokens=4*24*16000, temperature=None,
                          wait_for_peer_after_post=args.wait_for_peer)
            state = manager.create(config)
            design.append({"seed": seed, "condition": condition, "run_id": state["id"]})
    server = make_lab_server(manager, 0)
    base = f"http://127.0.0.1:{server.server_port}"
    atomic_json(folder / "plan.json", {"source_commit": "a6d9931", "design": design, "base_url": base,
        "model": "deepseek-flash", "reasoning_effort": "low", "real_agents":4,"scripted_agents":0,
        "call_limit_per_agent":24,"max_output_tokens":16000,"temperature":None,"timeout_seconds":180,
        "source_sha256": {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (ROOT/"swarm_bench/gpu_procurement.py",ROOT/"swarm_bench/lab_engine.py",ROOT/"swarm_bench/providers.py")},
        "ordering":"Native independent loops; wait for a peer after posting enabled" if args.wait_for_peer else "Native independent loops without wait-after-post",
        "wait_for_peer_after_post":args.wait_for_peer,
        "simulation":"place_order updates local state only; no actual supplier or purchase endpoint."})
    print(json.dumps({"base_url":base,"output":str(folder),"design":design}),flush=True)

    def campaign():
        rows=[]
        with patch("swarm_bench.providers.build_opener",LongerTimeout):
            for item in design:
                rid=item["run_id"]
                atomic_json(folder/"progress.json",{"phase":"running","completed":len(rows),"current":item,"base_url":base})
                print(json.dumps({"started":rid,"condition":item["condition"],"seed":item["seed"],"url":base+"/?run="+rid}),flush=True)
                manager.control(rid,"play")
                worker=manager.workers[rid]
                while worker.is_alive():
                    worker.join(timeout=30)
                    if worker.is_alive():
                        s=manager.snapshot(rid)
                        print(json.dumps({"running":rid,"calls":sum(v["calls"] for v in s["usage"].values()),"notes":len(s["notes"]),"order":(s["metrics"].get("order") or {}).get("total")}),flush=True)
                e=manager.export(rid)
                atomic_json(folder/(rid+".json"),e)
                order=e["metrics"].get("order")
                row={**item,"status":e["status"],"finish_reason":e.get("finish_reason"),"error":e.get("error"),
                     "order":order,"calls":sum(v["calls"] for v in e["usage"].values()),
                     "usage":e["usage"],"tool_errors":e["metrics"]["tool_error_count"],
                     "buyer_peer_messages_before_order":len(order["exposed_note_ids"]) if order else None,
                     "gpu_cards":sum(line["quantity"] for line in order["items"] if line["sku"] not in ("SUPPORT-5Y","NVLINK-BRIDGE")) if order else None,
                     "replay_url":base+"/?run="+rid}
                rows.append(row)
                atomic_json(folder/"results.json",rows)
                print(json.dumps({"finished":rid,"status":row["status"],"order_total":order["total"] if order else None,"budget_status":order["budget_status"] if order else None,"calls":row["calls"]}),flush=True)
        pairs=[{"seed":seed,**{r["condition"]:r for r in rows if r["seed"]==seed}} for seed in (42,43,44)]
        atomic_json(folder/"summary.json",{"pairs":pairs,"results":rows,"real_agents_per_run":4,"scripted_agents":0,
            "limitations":["Three pairs only, stochastic model outputs.","Native scheduling: the buyer may order before reading every peer message.","No order is distinct from respecting the budget.","Simulated prices and orders; this is not purchasing advice."]})
        atomic_json(folder/"progress.json",{"phase":"complete","completed":len(rows),"base_url":base})
        print("GPU PILOT COMPLETE",flush=True)

    threading.Thread(target=campaign,daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for run in manager.runs.values():run.pause_requested.set()
    finally:
        server.server_close()


if __name__=="__main__":
    main()
