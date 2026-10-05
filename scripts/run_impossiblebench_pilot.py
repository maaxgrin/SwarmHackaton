"""Run a few imported tasks sequentially through Swarm Lab; keep all traces."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="ollama-gpt-oss-20b-32k-medium")
    parser.add_argument("--agents", type=int, default=1)
    parser.add_argument("--scaffold", choices=["minimal", "tools"], default="minimal")
    parser.add_argument("--halt-on-error", action="store_true", help="Stop the series if the provider or runner fails")
    parser.add_argument("--prompt-variants", nargs="+", choices=["A", "B", "D"], default=["D"])
    parser.add_argument("--tasks", nargs="+", default=["lcbhard_0/conflicting", "lcbhard_1/conflicting", "lcbhard_41/conflicting"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = "http://127.0.0.1:8766"

    def api(path, body=None):
        request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    bootstrap = api("/api/bootstrap")
    if not any(p["id"] == args.model for p in bootstrap["providers"]):
        raise ValueError("Requested model profile is unavailable; no calls made")
    imported = {t["id"] for t in bootstrap.get("impossiblebench_tasks", [])}
    if not set(args.tasks) <= imported:
        raise ValueError("Requested tasks are not imported; no calls made")
    folder = args.output or ROOT / "runs/impossiblebench" / datetime.now().strftime("%Y%m%d-%H%M%S-pilot")
    folder.mkdir(parents=True, exist_ok=True)
    plan = dict(tasks=args.tasks, prompt_variants=args.prompt_variants, model=args.model, agent_count=args.agents, scaffold=args.scaffold,
                conditions="paper prompt and 10 feedback attempts" if args.scaffold == "minimal" else "private files, board push")
    (folder / "plan.json").write_text(json.dumps(plan, indent=2))
    rows = []
    for task_id, prompt_variant in ((t,v) for t in args.tasks for v in args.prompt_variants):
        config = api("/api/impossiblebench/config", {"task_id": task_id, "agent_count": args.agents, "scaffold": args.scaffold, "prompt_variant": prompt_variant})
        config["models"] = {a: args.model for a in config["models"]}
        run = api("/api/runs", config)
        run_id = run["id"]
        (folder / "progress.json").write_text(json.dumps(dict(current=run_id, task_id=task_id, prompt_variant=prompt_variant, completed=len(rows), phase="running")))
        print(json.dumps(dict(started=run_id, task_id=task_id, url=base + "/?run=" + run_id)), flush=True)
        api(f"/api/runs/{run_id}/control", {"action": "play"})
        last_log = 0
        while True:
            state = api(f"/api/runs/{run_id}")
            if state["status"] in ("complete", "stopped", "error", "archived"):
                break
            if time.monotonic() - last_log >= 60:
                print(json.dumps(dict(run_id=run_id, status=state["status"],
                    calls=sum(u["calls"] for u in state["usage"].values()), events=len(state["events"]))), flush=True)
                last_log = time.monotonic()
            time.sleep(5)
        row = dict(run_id=run_id, task_id=task_id, prompt_variant=prompt_variant, status=state["status"], finish_reason=state.get("finish_reason"),
                   error=state.get("error"), evaluations=state["metrics"].get("benchmark_evaluations", {}),
                   test_edits=state["metrics"].get("benchmark_test_edits", 0), notes=len(state["notes"]),
                   tool_errors=[e for e in state["events"] if e["kind"] == "tool_error"])
        rows.append(row)
        with (folder / "results.jsonl").open("a") as output:
            output.write(json.dumps(row) + "\n")
        print(json.dumps(dict(finished=run_id, status=row["status"], evaluated=len(row["evaluations"]),
                             tool_errors=len(row["tool_errors"]), test_edits=row["test_edits"])), flush=True)
        if args.halt_on_error and row["status"] == "error":
            (folder / "progress.json").write_text(json.dumps(dict(current=None, completed=len(rows), phase="error", error=row["error"])))
            print("PILOT HALTED ON EXECUTION ERROR", flush=True)
            return
    (folder / "progress.json").write_text(json.dumps(dict(current=None, completed=len(rows), phase="complete")))
    print("PILOT COMPLETE", flush=True)


if __name__ == "__main__":
    main()
