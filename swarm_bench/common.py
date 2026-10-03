import json
import re
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = tuple(f"agent_{i:02d}" for i in range(1, 11))
VARIANTS = ("complete", "split10")
ORCHESTRATIONS = ("swarm", "leader_led")
PRESSURES = ("none", "majority_wrong", "leader_wrong", "peer_wrong")
PROMPT_STYLES = ("implicit", "explicit")
RESOURCE_NAME = "notes.json"
NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?(?![\w.])")


def agent_problem(spec, prompt_style="implicit"):
    """Minimal participant view: never expose evaluator metadata or the other prompt."""
    if prompt_style not in PROMPT_STYLES:
        raise ValueError("Unknown prompt style")
    return {"task_id": spec["task_id"], "question": spec["prompts"][prompt_style]}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def number(value):
    """Canonical exact number, rejecting booleans, floats, expressions and infinities."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Use an integer or a numeric string, for example '3/2' or '1.5'.")
    value = str(value).strip()
    if len(value) > 128 or not re.fullmatch(r"[+-]?\d+(?:\.\d+|/[1-9]\d*)?", value):
        raise ValueError("Invalid number: use an integer, decimal or fraction; no units or commas.")
    return str(Fraction(value))


def restore_question(template, records):
    result = template
    seen = set()
    for record in records:
        if record["kind"] == "parameter":
            key = record["id"]
            if key in seen:
                raise ValueError(f"Duplicate parameter: {key}")
            seen.add(key)
            result = result.replace("{{" + key + "}}", record["value"])
    if re.search(r"\{\{n\d+\}\}", result):
        raise ValueError("Missing question parameters")
    return result


def reconstruct_evidence(problem, files):
    """Join published records, deduplicating complete copies and rejecting gaps/conflicts."""
    records = {}
    for file in files:
        if file["task_id"] != problem["task_id"]:
            raise ValueError("Evidence belongs to another task")
        for record in file["records"]:
            key = record["id"]
            if key in records and records[key] != record:
                raise ValueError(f"Conflicting record: {key}")
            records[key] = record
    deltas = {key: r["value"] for key, r in records.items() if r["kind"] == "adjustment"}
    if set(deltas) != set(problem["expected_adjustment_ids"]):
        raise ValueError("Missing or unexpected adjustment records")
    question = restore_question(problem["question_template"], list(records.values()))
    return question, sum(deltas.values())
