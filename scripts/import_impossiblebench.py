"""Import a small, unmodified official Impossible-LiveCodeBench subset."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATASET = "fjzzq2002/impossible_livecodebench"
DEFAULT_TASKS = ["lcbhard_0", "lcbhard_1", "lcbhard_41"]


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS)
    args = parser.parse_args()
    info = fetch("https://huggingface.co/api/datasets/" + DATASET)
    tasks = []
    for split in ("original", "oneoff", "conflicting"):
        offset = 0
        found = {}
        while True:
            query = urllib.parse.urlencode(dict(dataset=DATASET, config="default", split=split, offset=offset, length=100))
            url = "https://datasets-server.huggingface.co/rows?" + query
            page = fetch(url)
            for item in page["rows"]:
                row = item["row"]
                if row["task_id"] in args.tasks:
                    found[row["task_id"]] = (row, url)
            offset += len(page["rows"])
            if len(found) == len(args.tasks) or not page["rows"] or offset >= page["num_rows_total"]:
                break
        missing = set(args.tasks) - set(found)
        if missing:
            raise ValueError(f"Missing official tasks in {split}: {sorted(missing)}")
        for task_id in args.tasks:
            row, url = found[task_id]
            assert row["impossible_type"] == split
            canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            tasks.append({"id": f"{task_id}/{split}", **row, "source_rows_url": url,
                          "source_record_sha256": hashlib.sha256(canonical.encode()).hexdigest()})
    target = ROOT / "data/impossiblebench"
    target.mkdir(parents=True, exist_ok=True)
    (target / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
    manifest = {"dataset": DATASET, "dataset_url": "https://huggingface.co/datasets/" + DATASET,
                "official_repo": "https://github.com/safety-research/impossiblebench",
                "paper": "https://arxiv.org/abs/2510.20270", "dataset_revision_at_import": info["sha"],
                "downloaded_at": datetime.now(timezone.utc).isoformat(), "tasks": args.tasks,
                "splits": ["original", "oneoff", "conflicting"], "record_count": len(tasks),
                "selection": "Three small single-file examples; no published per-task cheating rates used.",
                "provenance_note": "Rows are the dataset-viewer snapshot; revision is repository metadata observed at import. Per-record hashes identify the exact imported content.",
                "modifications": "None to prompt, test, original_test or entry_point."}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"imported": len(tasks), "path": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
