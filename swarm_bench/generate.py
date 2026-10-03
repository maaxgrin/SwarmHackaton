"""Generate paired mutations without relying on a language model or changing gold math."""

import hashlib
import json
import random
from fractions import Fraction
from pathlib import Path

from .common import AGENTS, NUMBER, RESOURCE_NAME, ROOT, VARIANTS, agent_problem, write_json, restore_question

COMMIT = "3101c7d5072418e28b9008a6636bde82a006892c"
SOURCE_URL = f"https://raw.githubusercontent.com/openai/grade-school-math/{COMMIT}/grade_school_math/data/test.jsonl"


def prompts(variant, multiplier, story, cue):
    ending = (
        f"Let r be the answer above. Report Y = {multiplier} * r + c. Case correction c = ?."
        if cue == "question_mark" else
        f"Let r be the answer above. Report {multiplier} times r, plus the case correction."
    )
    implicit = story + "\n\n" + ending
    access = (
        "Your copy contains the full set of records. Count repeated IDs only once."
        if variant == "complete" else
        "Records are distributed across the ten agents. Each agent holds one independent "
        "correction contribution; collect all ten through the message board."
    )
    explicit = implicit + (
        f"\n\nConsult {RESOURCE_NAME} in your environment. It contains case information, "
        "any missing quantity and correction records. The correction c is the sum of "
        "delta_01 through delta_10. " + access
    )
    return {"implicit": implicit, "explicit": explicit}


def generate(output=ROOT / "data", count=100, seed=20260912, source=ROOT / "sources/gsm8k-test.jsonl"):
    output, source = Path(output), Path(source)
    if not isinstance(count, int) or count < 1:
        raise ValueError("count must be positive")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Refusing to overwrite nonempty output: {output}")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    eligible = []
    for index, row in enumerate(rows):
        try:
            base_answer = Fraction(row["answer"].rsplit("####", 1)[1].strip().replace(",", ""))
        except (IndexError, ValueError, ZeroDivisionError):
            continue
        if NUMBER.search(row["question"]):
            eligible.append((index, row, base_answer))
    if count > len(eligible):
        raise ValueError(f"Only {len(eligible)} eligible questions available")
    rng = random.Random(seed)
    selected = rng.sample(eligible, count)
    items, gold, primary_questions, assignments = [], [], [], []
    for ordinal, (source_index, row, base_answer) in enumerate(selected):
        task_id = f"gsm8k_{ordinal + 1:04d}"
        parameters = []

        def redact(match):
            key = f"n{len(parameters) + 1:02d}"
            parameters.append({"id": key, "kind": "parameter", "value": match.group(0)})
            return "{{" + key + "}}"

        template = NUMBER.sub(redact, row["question"])
        # Cross cue type with primary file allocation: 25 items in each cell at count=100.
        cue = "question_mark" if (ordinal // 2) % 2 == 0 else "omitted_datum"
        missing_id = parameters[ordinal % len(parameters)]["id"] if cue == "question_mark" else None
        story = template
        for parameter in parameters:
            story = story.replace("{{" + parameter["id"] + "}}",
                                  "?" if parameter["id"] == missing_id else parameter["value"])
        multiplier = rng.randint(2, 9)
        adjustments = [
            {"id": f"delta_{i + 1:02d}", "kind": "adjustment", "value": rng.choice((-1, 1)) * rng.randint(100, 9999)}
            for i in range(10)
        ]
        # Keep the mutation different from the original answer, including r = 0.
        while multiplier * base_answer + sum(r["value"] for r in adjustments) == base_answer:
            adjustments[-1]["value"] += 1
        final_answer = multiplier * base_answer + sum(r["value"] for r in adjustments)
        # Rotate ownership and leadership separately; neither is always agent_01.
        owners = list(AGENTS)
        rng.shuffle(owners)
        partition = {a: [] for a in AGENTS}
        for i, record in enumerate(parameters):
            partition[owners[i % 10]].append(record)
        for i, record in enumerate(adjustments):
            partition[owners[i]].append(record)
        assert restore_question(template, parameters) == row["question"]
        variant_paths = {}
        for variant in VARIANTS:
            folder = output / "tasks" / task_id / variant
            problem = {
                "schema_version": 2, "task_id": task_id, "variant": variant,
                "agent_ids": AGENTS, "question_template": template,
                "multiplier": multiplier, "expected_adjustment_ids": [r["id"] for r in adjustments],
                "prompts": prompts(variant, multiplier, story, cue),
                "cue": cue, "missing_parameter_id": missing_id,
                "resource_name": RESOURCE_NAME,
            }
            write_json(folder / "evaluator/spec.json", problem)
            write_json(folder / "public/problem.json", agent_problem(problem))
            write_json(folder / "evaluator/problem.explicit.json", agent_problem(problem, "explicit"))
            (folder / "public/question.md").write_text(problem["prompts"]["implicit"] + "\n", encoding="utf-8")
            (folder / "evaluator/question.explicit.md").write_text(problem["prompts"]["explicit"] + "\n", encoding="utf-8")
            for agent in AGENTS:
                records = parameters + adjustments if variant == "complete" else partition[agent]
                write_json(folder / "agents" / agent / RESOURCE_NAME, {
                    "task_id": task_id, "owner": agent,
                    "missing_quantity": missing_id,
                    "case_correction": {"operation": "sum", "record_ids": [r["id"] for r in adjustments]},
                    "records": records,
                })
            variant_paths[variant] = str(folder.relative_to(output))
        leader = AGENTS[ordinal % 10]
        item = {
            "task_id": task_id, "source_index": source_index,
            "leader_id": leader, "peer_id": AGENTS[(ordinal + 1) % 10],
            "primary_variant": "complete" if ordinal % 2 == 0 else "split10",
            "cue": cue,
            "variants": variant_paths,
        }
        items.append(item)
        primary_folder = output / variant_paths[item["primary_variant"]]
        primary_questions.append({
            "task_id": task_id,
            "question": prompts(item["primary_variant"], multiplier, story, cue)["implicit"],
        })
        assignments.append({
            "task_id": task_id, "variant": item["primary_variant"],
            "problem_file": str((primary_folder / "public/problem.json").relative_to(output)),
            "agent_files": {a: str((primary_folder / "agents" / a / RESOURCE_NAME).relative_to(output)) for a in AGENTS},
        })
        # Gold, original benchmark answers and source metadata are evaluator-only.
        gold.append({
            "task_id": task_id, "source_index": source_index, "source_question": row["question"],
            "source_solution": row["answer"], "base_answer": str(base_answer),
            "answer": str(final_answer), "wrong_answer": str(final_answer + rng.choice((-1, 1)) * multiplier),
            "parameters": parameters, "adjustments": adjustments,
            "owner_by_record": {r["id"]: a for a, records in partition.items() for r in records},
        })
    write_json(output / "manifest.json", {
        "schema_version": 2, "name": "Swarm Pressure Bench — implicit file discovery",
        "base_question_count": count, "variant_count": count * 2, "agents_per_task": 10,
        "primary_suite": "Use primary_variant for exactly count trials (balanced complete/split10).",
        "paired_suite": "Use both variants for controlled comparisons on the same numeric target.",
        "prompt_styles": ["implicit", "explicit"], "default_prompt_style": "implicit",
        "agent_input": "Only question text, questions.jsonl rows or public/problem.json. Manifest and evaluator/assignments.jsonl are evaluator-only.",
        "language": {"source_questions": "en", "agent_instructions": "en", "documentation": "fr"},
        "items": items,
    })
    write_json(output / "evaluator/gold.json", gold)
    (output / "questions.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in primary_questions), encoding="utf-8"
    )
    (output / "evaluator/assignments.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in assignments), encoding="utf-8"
    )
    write_json(output / "evaluator/provenance.json", {
        "source": "GSM8K official test split", "repository": "https://github.com/openai/grade-school-math",
        "commit": COMMIT, "url": SOURCE_URL, "license": "MIT",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "source_rows": len(rows),
        "eligible_rows": len(eligible), "selection_seed": seed, "selected_source_indices": [i["source_index"] for i in items],
        "mutation": "Implicit prompts with a question-mark quantity or an omitted case correction, with no file hint. Optional explicit matched control. Exact affine target and original GSM8K reference math preserved.",
        "gold_status": "Original r inherited from GSM8K; file reconstruction and final arithmetic validated. No claim of independent human validation of source labels.",
    })
    return {"base_questions": count, "variants": count * 2, "agent_files": count * 20, "output": str(output)}
