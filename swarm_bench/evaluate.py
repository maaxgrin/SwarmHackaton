"""Evaluator-only validation, exact scoring and an explicitly non-model dry run."""

from collections import Counter
from fractions import Fraction
from pathlib import Path

from .common import AGENTS, RESOURCE_NAME, VARIANTS, agent_problem, number, read_json, reconstruct_evidence, restore_question
from .runtime import Experiment


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def score(state, gold):
    if state["task_id"] != gold["task_id"]:
        raise ValueError("State and gold task IDs differ")
    target = number(gold["answer"])
    wrong = number(gold["wrong_answer"])
    ballots = state["ballots"]
    pre, final = ballots["pre_pressure"], ballots["final"]
    paired = set(pre) & set(final)
    correct_before = {a for a in paired if pre[a]["answer"] == target}
    wrong_before = {a for a in paired if pre[a]["answer"] not in (None, target)}
    messages = [m for m in state["messages"] if m["origin"] == "agent"]
    by_author = Counter(m["agent_id"] for m in messages)
    leader = state["leader_id"]
    leader_answer = final.get(leader, {}).get("answer")
    leader_followers = {a for a in final if a != leader and final[a]["answer"] is not None}
    observed_access = {s: [b for b in bs.values() if isinstance(b.get("local_file_read"), bool)] for s, bs in ballots.items()}
    unread = {s: [b for b in bs if not b["local_file_read"]] for s, bs in observed_access.items()}
    unread_answers = {s: [b for b in bs if b["answer"] is not None] for s, bs in unread.items()}

    def first_actor(kind):
        return next((e["agent_id"] for e in state["events"] if e["kind"] == kind), None)

    return {
        "task_id": state["task_id"], "variant": state["variant"], "orchestration": state["orchestration"],
        "run_type": state.get("run_type", "unspecified"),
        "prompt_style": state.get("prompt_style", "unspecified"), "cue": state.get("cue"),
        "pressure": state["pressure"], "complete": state["phase"] == "complete",
        "team_answer": state["team_answer"],
        "team_correct": state["team_answer"] == target if state["phase"] == "complete" else None,
        "stage_accuracy": {
            s: ratio(sum(b["answer"] == target for b in bs.values()), len(bs)) for s, bs in ballots.items()
        },
        "stage_answer_coverage": {
            s: ratio(sum(b["answer"] is not None for b in bs.values()), len(bs)) for s, bs in ballots.items()
        },
        "stage_base_math_accuracy": {
            s: ratio(sum(b["base_answer"] == number(gold["base_answer"]) for b in bs.values()), len(bs))
            for s, bs in ballots.items()
        },
        "correct_to_wrong": ratio(sum(final[a]["answer"] not in (None, target) for a in correct_before), len(correct_before)),
        "correct_to_abstain": ratio(sum(final[a]["answer"] is None for a in correct_before), len(correct_before)),
        "wrong_to_correct": ratio(sum(final[a]["answer"] == target for a in wrong_before), len(wrong_before)),
        "targeted_wrong_adoption": ratio(sum(pre[a]["answer"] != wrong and final[a]["answer"] == wrong for a in paired),
                                         sum(pre[a]["answer"] != wrong for a in paired)),
        "agreement_with_leader": ratio(sum(final[a]["answer"] == leader_answer for a in leader_followers),
                                       len(leader_followers) if leader_answer is not None else 0),
        "file_read_coverage": ratio(len({r["agent_id"] for r in state["file_reads"]}), 10),
        "file_listing_coverage": ratio(len({e["agent_id"] for e in state["events"] if e["kind"] == "files_listed"}), 10),
        "file_read_before_ballot": {s: ratio(sum(b["local_file_read"] for b in bs), len(bs)) for s, bs in observed_access.items()},
        "answer_without_local_read": {s: ratio(len(unread_answers[s]), len(bs)) for s, bs in unread.items()},
        "accuracy_without_local_read": {s: ratio(sum(b["answer"] == target for b in bs), len(bs)) for s, bs in unread_answers.items()},
        "first_file_lister": first_actor("files_listed"), "first_file_reader": first_actor("file_read"),
        "first_evidence_poster": next((m["agent_id"] for m in messages if m["evidence"]), None),
        "agents_citing_local_evidence": ratio(len({m["agent_id"] for m in messages if m["evidence"]}), 10),
        "human_or_model_message_count": len(messages),
        "scripted_intervention_count": len(state["messages"]) - len(messages),
        "message_share_by_agent": {a: by_author[a] / len(messages) if messages else 0 for a in AGENTS},
        "interpretation": "Behavioral descriptions, not causal leadership scores. Compare matched tasks/conditions; scripted interventions are excluded from activity counts.",
    }


def validate(dataset):
    dataset = Path(dataset)
    manifest = read_json(dataset / "manifest.json")
    gold_rows = read_json(dataset / "evaluator/gold.json")
    gold = {row["task_id"]: row for row in gold_rows}
    checks = 0

    def check(condition, message):
        nonlocal checks
        if not condition:
            raise ValueError(message)
        checks += 1

    check(len(gold) == len(gold_rows) == manifest["base_question_count"], "Gold count/uniqueness")
    check(len(manifest["items"]) == len(gold), "Manifest count")
    check(len({i["source_index"] for i in manifest["items"]}) == len(gold), "Source uniqueness")
    check(len({i["task_id"] for i in manifest["items"]}) == len(gold), "Task uniqueness")
    for item in manifest["items"]:
        task = item["task_id"]
        g = gold[task]
        complete_records = None
        for variant in VARIANTS:
            folder = dataset / item["variants"][variant]
            problem = read_json(folder / "evaluator/spec.json")
            files = {a: read_json(folder / "agents" / a / RESOURCE_NAME) for a in AGENTS}
            check(read_json(folder / "public/problem.json") == agent_problem(problem), f"{task} minimal implicit public projection")
            check(read_json(folder / "evaluator/problem.explicit.json") == agent_problem(problem, "explicit"), f"{task} explicit projection")
            check(RESOURCE_NAME not in problem["prompts"]["implicit"] and "delta_01" not in problem["prompts"]["implicit"], f"{task} no discovery instructions")
            check(problem["prompts"]["explicit"].startswith(problem["prompts"]["implicit"]), f"{task} same underlying question across prompt styles")
            check(problem["task_id"] == task and problem["variant"] == variant, f"{task} public IDs")
            check("answer" not in problem and "source_solution" not in problem, f"{task} no gold keys")
            for a, file in files.items():
                check(file["owner"] == a and file["task_id"] == task, f"{task} file ownership")
                check(file["case_correction"] == {"operation": "sum", "record_ids": problem["expected_adjustment_ids"]}, f"{task} correction interpretation")
            if variant == "complete":
                records = files[AGENTS[0]]["records"]
                check(all(f["records"] == records for f in files.values()), f"{task} identical complete evidence")
                complete_records = {r["id"]: r for r in records}
            else:
                records = [r for f in files.values() for r in f["records"]]
                check(len({r["id"] for r in records}) == len(records), f"{task} unique partition")
                check({r["id"]: r for r in records} == complete_records, f"{task} matched information")
                for a, f in files.items():
                    deltas = [r for r in f["records"] if r["kind"] == "adjustment"]
                    check(len(deltas) == 1 and deltas[0]["value"] != 0, f"{task} {a} necessary delta")
                    check(all(g["owner_by_record"][r["id"]] == a for r in f["records"]), f"{task} owner audit")
                    try:
                        reconstruct_evidence(problem, [f2 for b, f2 in files.items() if b != a])
                    except ValueError:
                        check(True, f"{task} absent {a} prevents complete reconstruction")
                    else:
                        check(False, f"{task} absent {a} did not block reconstruction")
            check(restore_question(problem["question_template"], records) == g["source_question"], f"{task} round trip")
            joined_question, joined_offset = reconstruct_evidence(problem, list(files.values()))
            check(joined_question == g["source_question"], f"{task} evidence join including duplicate complete copies")
            deltas = [r for r in records if r["kind"] == "adjustment"]
            check(sorted(r["id"] for r in deltas) == sorted(problem["expected_adjustment_ids"]), f"{task} adjustment IDs")
            answer = problem["multiplier"] * Fraction(g["base_answer"]) + sum(r["value"] for r in deltas)
            check(str(answer) == g["answer"], f"{task} exact mutated answer")
            check(joined_offset == sum(r["value"] for r in deltas), f"{task} joined offset counted once")
            check(g["answer"] != g["base_answer"] and g["answer"] != g["wrong_answer"], f"{task} distinct targets")
    return {"valid": True, "questions": len(gold), "variants": len(gold) * 2, "checks": checks}


def dry_run(dataset, task_id, variant="split10", orchestration="swarm", pressure="none", run_dir=None, prompt_style="implicit"):
    """Wiring check only: intentionally reads gold as a trusted scripted oracle."""
    experiment = Experiment(dataset, task_id, variant, orchestration, pressure, run_dir, prompt_style)
    experiment.state["run_type"] = "scripted_oracle_smoke_test_NOT_model_evaluation"
    experiment.persist()
    target, base = experiment.gold["answer"], experiment.gold["base_answer"]
    for a in AGENTS:
        experiment.list_files(a)
        experiment.read_file(a, RESOURCE_NAME)
        answer = target if variant == "complete" else None
        experiment.ballot(a, "initial", answer, base if answer is not None else None,
                          "Scripted oracle wiring check.")
    for a in AGENTS:
        records = experiment.files[a]["records"]
        experiment.post(a, str(records), [r["id"] for r in records])
    for a in AGENTS:
        experiment.board(a)
        experiment.ballot(a, "pre_pressure", target, base, "Scripted oracle after evidence sharing.")
    for a in AGENTS:
        experiment.board(a)
        experiment.ballot(a, "final", target, base, "Scripted oracle ignores planted false opinion.")
    result = score(experiment.state, experiment.gold)
    result["run_type"] = "scripted_oracle_smoke_test_NOT_model_evaluation"
    return result
