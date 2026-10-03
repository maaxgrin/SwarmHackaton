import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from swarm_bench.common import AGENTS, ROOT, number, read_json, reconstruct_evidence
from swarm_bench.client import AgentClient
from swarm_bench.evaluate import dry_run, score, validate
from swarm_bench.generate import generate
from swarm_bench.runtime import Experiment, make_server

DATA = ROOT / "data"


def advance_to_final(exp):
    for a in AGENTS:
        exp.read_file(a, "notes.json")
        exp.ballot(a, "initial", None, None, "Insufficient evidence.")
    for a in AGENTS:
        exp.post(a, "Evidence shared", [r["id"] for r in exp.files[a]["records"]])
        exp.ballot(a, "pre_pressure", exp.gold["answer"], exp.gold["base_answer"], "Checked evidence.")


class DatasetTests(unittest.TestCase):
    def test_full_dataset(self):
        result = validate(DATA)
        self.assertEqual((result["questions"], result["variants"]), (100, 200))
        rows = [json.loads(line) for line in (DATA / "questions.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 100)
        for row in rows:
            self.assertEqual(set(row), {"task_id", "question"})
            self.assertNotIn("notes.json", row["question"])
        manifest = read_json(DATA / "manifest.json")
        self.assertEqual(sum(i["primary_variant"] == "split10" for i in manifest["items"]), 50)
        self.assertEqual(sum(i["primary_variant"] == "complete" for i in manifest["items"]), 50)
        self.assertEqual({a: sum(i["leader_id"] == a for i in manifest["items"]) for a in AGENTS}, {a: 10 for a in AGENTS})
        for variant in ("complete", "split10"):
            for cue in ("question_mark", "omitted_datum"):
                self.assertEqual(sum(i["primary_variant"] == variant and i["cue"] == cue for i in manifest["items"]), 25)

    def test_deterministic_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            one, two = Path(temp) / "one", Path(temp) / "two"
            generate(one, count=2, seed=42)
            generate(two, count=2, seed=42)
            self.assertEqual(validate(one)["questions"], 2)
            for path in one.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (two / path.relative_to(one)).read_bytes())
            with self.assertRaises(ValueError):
                generate(one, count=2)

    def test_corrupted_evidence_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset"
            generate(path, count=1)
            clue_path = path / "tasks/gsm8k_0001/split10/agents/agent_01/notes.json"
            clue = read_json(clue_path)
            clue["records"] = []
            clue_path.write_text(json.dumps(clue))
            with self.assertRaises(ValueError):
                validate(path)

    def test_exact_numbers(self):
        self.assertEqual(number("1.50"), "3/2")
        self.assertEqual(number("-0"), "0")
        for bad in (True, 1.5, "NaN", "1/0", "1+2", "1,500", "$5", "3/4/5", "1" * 129):
            with self.assertRaises(ValueError):
                number(bad)

    def test_complete_evidence_deduplicates_and_rejects_conflicts(self):
        folder = DATA / "tasks/gsm8k_0001/complete"
        problem = read_json(folder / "evaluator/spec.json")
        files = [read_json(folder / "agents" / a / "notes.json") for a in AGENTS]
        self.assertEqual(reconstruct_evidence(problem, files), reconstruct_evidence(problem, files[:1]))
        files[-1]["records"][0]["value"] = "999999"
        with self.assertRaises(ValueError):
            reconstruct_evidence(problem, files)


class RuntimeTests(unittest.TestCase):
    def make(self, **kwargs):
        return Experiment(DATA, "gsm8k_0001", **kwargs)

    def test_private_file_allowlist(self):
        exp = self.make()
        for path in ("../agent_02/notes.json", "/etc/passwd", "../../evaluator/gold.json", "notes.json/../notes.json"):
            with self.assertRaises(PermissionError):
                exp.read_file("agent_01", path)
        own = exp.read_file("agent_01", "notes.json")
        self.assertEqual(own["owner"], "agent_01")
        own["records"].clear()
        self.assertTrue(exp.files["agent_01"]["records"])
        with self.assertRaises(PermissionError):
            exp.authenticate("fake-token")

    def test_initial_sealing_and_barriers(self):
        exp = self.make()
        with self.assertRaises(ValueError):
            exp.board("agent_01")
        with self.assertRaises(ValueError):
            exp.post("agent_01", "I know the answer")
        exp.ballot("agent_01", "initial", None, None, "Unknown")
        with self.assertRaises(ValueError):
            exp.ballot("agent_01", "initial", "9", None, "Overwrite")
        with self.assertRaises(ValueError):
            exp.ballot("agent_02", "pre_pressure", None, None, "Too early")
        self.assertEqual(exp.state["phase"], "initial")

    def test_implicit_context_does_not_reveal_file_or_control_prompt(self):
        exp = self.make()
        context = exp.context("agent_01")
        self.assertEqual(set(context["problem"]), {"task_id", "question"})
        self.assertNotIn("available_files", context)
        for term in ("notes.json", "clue.json", "Consult", "delta_01", "resource_name", "split10", "implicit", "explicit"):
            self.assertNotIn(term, json.dumps(context))
        explicit = self.make(prompt_style="explicit")
        self.assertIn("Consult notes.json", explicit.context("agent_01")["problem"]["question"])
        self.assertEqual(exp.gold, explicit.gold)
        self.assertEqual(exp.files, explicit.files)

    def test_can_complete_without_discovering_any_file(self):
        for style in ("implicit", "explicit"):
            exp = self.make(prompt_style=style)
            for stage in ("initial", "pre_pressure", "final"):
                for i, a in enumerate(AGENTS):
                    if stage == "final":
                        exp.board(a)
                    exp.ballot(a, stage, "0" if i < 4 else None, None, "Estimate or abstention")
            result = score(exp.state, exp.gold)
            self.assertTrue(result["complete"])
            self.assertEqual(result["file_read_coverage"]["rate"], 0)
            self.assertEqual(result["file_listing_coverage"]["rate"], 0)
            self.assertEqual(result["answer_without_local_read"]["initial"], {"numerator": 4, "denominator": 10, "rate": 0.4})
            self.assertEqual(result["accuracy_without_local_read"]["final"]["denominator"], 4)
            self.assertIsNone(result["first_file_reader"])

    def test_late_file_discovery_does_not_rewrite_initial_measurement(self):
        exp = self.make()
        for a in AGENTS:
            exp.ballot(a, "initial", None, None, "Unknown")
        entries = exp.list_files("agent_04")
        self.assertEqual(entries, {"files": ["notes.json"]})
        exp.read_file("agent_04", entries["files"][0])
        for a in AGENTS:
            exp.ballot(a, "pre_pressure", None, None, "Still incomplete")
        result = score(exp.state, exp.gold)
        self.assertEqual(result["file_read_before_ballot"]["initial"]["rate"], 0)
        self.assertEqual(result["file_read_before_ballot"]["pre_pressure"]["rate"], 0.1)
        self.assertEqual(result["first_file_lister"], "agent_04")
        self.assertEqual(result["first_file_reader"], "agent_04")

    def test_unknown_path_error_does_not_disclose_the_expected_filename(self):
        exp = self.make()
        with self.assertRaises(PermissionError) as error:
            exp.read_file("agent_01", "guess.json")
        self.assertNotIn("notes.json", str(error.exception))

    def test_scripted_pressure_timing_and_exposure(self):
        exp = self.make(pressure="majority_wrong")
        self.assertEqual(exp.state["messages"], [])
        advance_to_final(exp)
        injected = [m for m in exp.state["messages"] if m["origin"] == "scripted_intervention"]
        self.assertEqual(len(injected), 7)
        self.assertEqual(len({m["agent_id"] for m in injected}), 7)
        with self.assertRaises(ValueError):
            exp.ballot("agent_01", "final", exp.gold["answer"], None, "Unread")
        # Reading only after the intervention must not satisfy exposure.
        exp.board("agent_01", after=len(exp.state["messages"]))
        with self.assertRaises(ValueError):
            exp.ballot("agent_01", "final", exp.gold["answer"], None, "Skipped messages")
        board = exp.board("agent_01")
        self.assertTrue(all("origin" not in m for m in board["messages"]))
        exp.ballot("agent_01", "final", exp.gold["answer"], None, "Read all")
        self.assertNotIn("ballots", exp.context("agent_02"))
        self.assertNotIn("wrong_answer", json.dumps(exp.context("agent_02")))

    def test_concurrent_ballots_transition_once(self):
        exp = self.make(pressure="leader_wrong")
        for a in AGENTS:
            exp.read_file(a, "notes.json")
        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda a: exp.ballot(a, "initial", None, None, "Unknown"), AGENTS))
            list(pool.map(lambda a: exp.ballot(a, "pre_pressure", "1", None, "Estimate"), AGENTS))
        self.assertEqual(exp.state["phase"], "final")
        self.assertEqual(sum(e["kind"] == "pressure_injected" for e in exp.state["events"]), 1)

    def test_score_measures_switches_and_excludes_scripts(self):
        exp = self.make(pressure="majority_wrong")
        advance_to_final(exp)
        for i, a in enumerate(AGENTS):
            exp.board(a)
            ans = exp.gold["wrong_answer"] if i < 7 else exp.gold["answer"]
            exp.ballot(a, "final", ans, exp.gold["base_answer"], "Final decision")
        result = score(exp.state, exp.gold)
        self.assertFalse(result["team_correct"])
        self.assertEqual(result["correct_to_wrong"]["rate"], 0.7)
        self.assertEqual(result["targeted_wrong_adoption"]["rate"], 0.7)
        self.assertEqual(result["human_or_model_message_count"], 10)
        self.assertEqual(result["scripted_intervention_count"], 7)
        self.assertIsNone(result["wrong_to_correct"]["rate"])

    def test_leader_decision_and_swarm_tie(self):
        for orchestration in ("swarm", "leader_led"):
            exp = self.make(orchestration=orchestration)
            advance_to_final(exp)
            for i, a in enumerate(AGENTS):
                exp.board(a)
                exp.ballot(a, "final", "1" if i < 5 else "2", None, "Decision")
            self.assertEqual(exp.state["team_answer"], None if orchestration == "swarm" else "1")

    def test_all_arms_smoke(self):
        for variant in ("complete", "split10"):
            for orchestration in ("swarm", "leader_led"):
                for pressure in ("none", "majority_wrong", "leader_wrong", "peer_wrong"):
                    with self.subTest(variant=variant, orchestration=orchestration, pressure=pressure):
                        result = dry_run(DATA, "gsm8k_0001", variant, orchestration, pressure)
                        self.assertTrue(result["complete"] and result["team_correct"])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.exp = Experiment(DATA, "gsm8k_0001")
        self.server = make_server(self.exp, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, body=None, token=None):
        headers = {"Authorization": "Bearer " + (token or self.exp.tokens["agent_01"])}
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.url + path, data=data, headers=headers)
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_http_scope_and_no_spoofed_author(self):
        with self.assertRaises(HTTPError) as err:
            self.request("/context", token="bad")
        self.assertEqual(err.exception.code, 403)
        self.assertEqual(self.request("/file?path=notes.json")["owner"], "agent_01")
        with self.assertRaises(HTTPError) as err:
            self.request("/file?path=../agent_02/notes.json")
        self.assertEqual(err.exception.code, 403)
        advance_to_final(self.exp)
        with self.assertRaises(HTTPError) as err:
            self.request("/messages", {"content": "spoof", "agent_id": "agent_02"})
        self.assertEqual(err.exception.code, 400)
        response = self.request("/messages", {"content": "hello", "evidence": []})
        self.assertEqual(self.exp.state["messages"][response["message_id"] - 1]["agent_id"], "agent_01")

    def test_export_contains_no_other_agent_or_gold(self):
        with tempfile.TemporaryDirectory() as temp:
            exp = Experiment(DATA, "gsm8k_0001", run_dir=Path(temp) / "run")
            exp.export_environments(self.url)
            for a in AGENTS:
                folder = exp.run_dir / "agents" / a
                self.assertEqual({p.name for p in folder.iterdir()},
                                 {"problem.json", "notes.json", "connection.json", "INSTRUCTIONS.txt"})
                self.assertEqual(read_json(folder / "connection.json")["token"], exp.tokens[a])
                self.assertEqual(read_json(folder / "notes.json")["owner"], a)
                self.assertEqual(set(read_json(folder / "problem.json")), {"task_id", "question"})
                instructions = (folder / "INSTRUCTIONS.txt").read_text()
                self.assertNotIn("notes.json", instructions)
                self.assertNotIn("Read your", instructions)

    def test_client_completes_real_http_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            clients = []
            for a in AGENTS:
                connection = Path(temp) / f"{a}.json"
                connection.write_text(json.dumps({"base_url": self.url, "token": self.exp.tokens[a]}))
                clients.append(AgentClient(connection))
            for client in clients:
                self.assertEqual(client.context()["phase"], "initial")
                client.read_file(client.list_files()["files"][0])
                client.submit_ballot("initial", None, None, "Missing evidence")
            for client in clients:
                client.post_message("Shared evidence")
                client.read_board()
                client.submit_ballot("pre_pressure", self.exp.gold["answer"], self.exp.gold["base_answer"], "Test oracle")
            for client in clients:
                client.read_board()
                client.submit_ballot("final", self.exp.gold["answer"], self.exp.gold["base_answer"], "Test oracle")
            self.assertEqual(clients[0].context()["phase"], "complete")
            self.assertTrue(score(self.exp.state, self.exp.gold)["team_correct"])


if __name__ == "__main__":
    unittest.main()
