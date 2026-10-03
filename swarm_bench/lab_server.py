"""Local operator UI and run controller. No agent can access these operator endpoints."""
import copy
import csv
import io
import json
import mimetypes
import secrets
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .common import ROOT, read_json, write_json
from .lab_engine import DEFAULT_COMMON_PROMPT, DEFAULT_SOLO_COMMON_PROMPT, DEFAULT_COMMUNICATION_PROMPT, DEFAULT_RESTRICTION, TOOLS, GROUP_TOOLS, PYTHON_TOOL, ARC_TOOLS, ARC_PROMPT, LabRun
from .lab_storage import load_run
from .providers import ProviderError, ProviderRegistry


class LabManager:
    def __init__(self, data_dir, work_dir):
        self.data_dir, self.work_dir = Path(data_dir), Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.chmod(0o700)
        self.registry = ProviderRegistry(self.work_dir / "models.json")
        self.runs = {}
        self.workers = {}
        self.lock = threading.RLock()
        # Preserve previous runs as inspectable archives. Never silently resume model calls.
        self.archives = {}
        self.archive_histories = {}
        for folder in (self.work_dir / "runs").glob("*"):
            if not folder.is_dir():
                continue
            try:
                s, histories = load_run(folder)
                if s["status"] in ("running", "ready", "paused", "error"):
                    s["status"] = "archived"
                self.archives[s["id"]] = s
                self.archive_histories[s["id"]] = histories
            except (ValueError, KeyError, OSError):
                continue
        self.tasks = []
        for item in read_json(self.data_dir / "manifest.json")["items"]:
            problem = read_json(self.data_dir / item["variants"]["split10"] / "public/problem.json")
            self.tasks.append({"id": item["task_id"], "question": problem["question"], "cue": item["cue"]})

    def summary(self, state):
        metrics = state.get("metrics", {})
        return {"id": state["id"], "title": state["config"]["title"], "config": state["config"],
                "status": state["status"], "created_at": state["created_at"], "metrics": metrics}

    def bootstrap(self):
        with self.lock:
            states = list(self.archives.values()) + [r.snapshot() for r in self.runs.values()]
            return {"tasks": self.tasks, "providers": self.registry.public(), "restriction_prompt": DEFAULT_RESTRICTION,
                    "common_prompt": DEFAULT_COMMON_PROMPT, "solo_common_prompt": DEFAULT_SOLO_COMMON_PROMPT,
                    "communication_prompt": DEFAULT_COMMUNICATION_PROMPT, "arc_prompt": ARC_PROMPT, "tools": copy.deepcopy(TOOLS + [t for t in ARC_TOOLS if t["function"]["name"] not in {x["function"]["name"] for x in TOOLS}]),
                    "runs": [self.summary(s) for s in sorted(states, key=lambda s: s["created_at"], reverse=True)]}

    def create(self, config):
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        run = LabRun(config, self.data_dir, self.work_dir / "runs" / run_id, self.registry)
        with self.lock:
            self.runs[run_id] = run
        return run.snapshot()

    def snapshot(self, run_id):
        with self.lock:
            if run_id in self.runs:
                snapshot = self.runs[run_id].snapshot()
                snapshot["worker_active"] = bool(self.workers.get(run_id) and self.workers[run_id].is_alive())
                if snapshot["worker_active"] and snapshot["status"] == "paused":
                    snapshot["status"] = "running"
                return snapshot
            if run_id in self.archives:
                return copy.deepcopy(self.archives[run_id])
            raise ValueError("Expérience inconnue")

    def inspect(self, run_id, agent):
        if run_id in self.runs:
            return self.runs[run_id].inspect(agent)
        state = self.snapshot(run_id)
        if agent not in state["config"]["agents"]:
            raise ValueError("Agent inconnu")
        folder = self.work_dir / "runs" / run_id
        history = copy.deepcopy(self.archive_histories[run_id].get(agent, []))
        if state["config"].get("scenario") in ("custom", "communication", "group_misalignment", "altruism", "arc"):
            files = state.get("workspace_state", state["config"].get("workspace_files", {})).get(agent, {})
            file = files
        else:
            file = read_json(folder / "agents" / agent / "notes.json")
            files = {"notes.json": file}
        names = state["config"].get("agent_tools", {}).get(agent, state["config"].get("enabled_tools", [t["function"]["name"] for t in TOOLS]))
        return {"agent_id": agent, "system_prompt": history[0]["content"] if history else "Historique indisponible pour cet agent.",
                "question": state["question"], "file": file, "files": files,
                "tools": state.get("tool_schemas", {}).get(agent, [t for t in TOOLS if t["function"]["name"] in names]),
                "answers": state["answers"][agent], "history": history,
                **({"archive_warnings": state["archive_warnings"]} if state.get("archive_warnings") else {})}

    def export(self, run_id):
        # Snapshot and agent histories belong to the same instant, including during a live run.
        with self.lock:
            run = self.runs.get(run_id)
            with run.lock if run else threading.RLock():
                state = self.snapshot(run_id)
                return {**state, "schema_version": 1,
                        "participants": {a: self.inspect(run_id, a) for a in state["config"]["agents"]}}

    def control(self, run_id, action):
        with self.lock:
            if run_id not in self.runs:
                raise ValueError("Un historique est consultable ; dupliquez sa configuration pour relancer")
            run = self.runs[run_id]
            if run.state["status"] in ("complete", "stopped"):
                raise ValueError("Expérience terminée")
            if action in ("pause", "stop"):
                run.pause_requested.set()
                with run.changed:
                    run.event("operator_" + action)
                    if not self.workers.get(run_id, None) or not self.workers[run_id].is_alive():
                        run.state["status"] = "stopped" if action == "stop" else "paused"
                    run.state["stop_requested"] = action == "stop"
                    run.changed.notify_all()
                    run.persist()
                return self.snapshot(run_id)
            if action != "play":
                raise ValueError("Commande inconnue")
            if self.workers.get(run_id) and self.workers[run_id].is_alive():
                raise ValueError("L'exécution est déjà en cours")
            if not run.remaining_agents():
                raise ValueError("Plafond d'appels atteint ; créer un nouvel essai pour utiliser un nouveau budget")
            if run.config["mode"] == "demo" and (run.config["scenario"] != "peer_pressure" or
                    any(len(run.tools_for(a)) != len(TOOLS) for a in run.agents)):
                raise ValueError("La démo scénarisée utilise la peer pressure et ses cinq outils ; choisir Modèles réels pour une configuration libre")
            if run.config["mode"] == "live":
                run.freeze_providers()
            run.pause_requested.clear()
            run.state["stop_requested"] = False

            def work():
                try:
                    run.run_free()
                except (ProviderError, ValueError):
                    pass  # Error already persisted in the run.
                except Exception:
                    with run.lock:
                        run.state.update(status="error", error="Erreur interne d'exécution. Voir les événements du run.")
                        run.event("internal_error")
                finally:
                    with run.lock:
                        if run.state.get("stop_requested"):
                            run.state["status"] = "stopped"
                        elif run.pause_requested.is_set() and run.state["status"] not in ("error", "complete"):
                            run.state["status"] = "paused"
                        run.state["metrics"] = run.metrics()
                        run.persist()
            thread = threading.Thread(target=work, daemon=True)
            self.workers[run_id] = thread
            thread.start()
            return self.snapshot(run_id)

    def export_csv(self):
        rows = self.bootstrap()["runs"]
        buffer = io.StringIO()
        fields = ["id", "scenario", "mode", "task_id", "agents", "restricted", "leader", "importance", "status", "breaches",
                  "breach_rate", "before_peer_exposure", "after_peer_exposure", "team_correct", "notes", "seed"]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            c, m = r["config"], r["metrics"]
            writer.writerow({"id": r["id"], "scenario": c.get("scenario", "peer_pressure"), "mode": c["mode"], "task_id": c["task_id"], "agents": c["agent_count"],
                             "restricted": len(c["restricted"]), "leader": c["leader"] or "", "importance": c["importance"],
                             "status": r["status"], "breaches": m.get("breach_count"), "breach_rate": m.get("breach_rate"),
                             "before_peer_exposure": m.get("before_peer_exposure"), "after_peer_exposure": m.get("after_peer_exposure"),
                             "team_correct": m.get("team_correct"), "notes": m.get("note_count"), "seed": c["seed"]})
        return buffer.getvalue()


def make_lab_server(manager, port=8766):
    static = Path(__file__).parent / "web"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, mime="application/json; charset=utf-8", attachment=None):
            if not isinstance(data, bytes):
                data = (json.dumps(data, ensure_ascii=False) if mime.startswith("application/json") else data).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
            self.end_headers()
            self.wfile.write(data)

        def origin_ok(self):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin in {"http://" + h for h in allowed})

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def dispatch(self, method):
            if not self.origin_ok():
                self.send(403, {"error": "Accès local uniquement"})
                return
            try:
                path = urlparse(self.path).path
                parts = path.strip("/").split("/")
                if method == "GET":
                    if path == "/api/bootstrap":
                        self.send(200, manager.bootstrap())
                    elif path == "/api/export.csv":
                        self.send(200, manager.export_csv(), "text/csv; charset=utf-8", "swarm-lab-comparisons.csv")
                    elif len(parts) >= 3 and parts[:2] == ["api", "runs"]:
                        if len(parts) == 5 and parts[3] == "agents":
                            self.send(200, manager.inspect(parts[2], parts[4]))
                        elif len(parts) == 4 and parts[3] == "export":
                            self.send(200, manager.export(parts[2]), attachment="swarm-lab-" + parts[2] + ".json")
                        elif len(parts) == 3:
                            self.send(200, manager.snapshot(parts[2]))
                        else:
                            self.send(404, {"error": "Route inconnue"})
                    elif path in ("/", "/app.js", "/style.css"):
                        file = static / ("index.html" if path == "/" else path[1:])
                        self.send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
                    elif path == "/favicon.ico":
                        self.send(204, b"", "image/x-icon")
                    else:
                        self.send(404, {"error": "Route inconnue"})
                    return
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    raise ValueError("Content-Type application/json requis")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError("Taille de requête invalide")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Objet JSON requis")
                if path == "/api/providers":
                    self.send(200, {"providers": manager.registry.save(body)})
                elif path == "/api/preview":
                    run = LabRun(body, manager.data_dir, manager.work_dir / "preview", manager.registry, preview=True)
                    self.send(200, {"question": run.question, "agents": {a: {"prompt": run.prompt(a), "file": run.files[a],
                              "files": run.workspaces[a], "tools": run.tools_for(a)} for a in run.agents}})
                elif path == "/api/runs":
                    self.send(201, manager.create(body))
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "control":
                    self.send(200, manager.control(parts[2], body.get("action")))
                else:
                    self.send(404, {"error": "Route inconnue"})
            except (ValueError, TypeError, KeyError, ProviderError) as exc:
                self.send(400, {"error": str(exc)})
            except OSError:
                self.send(500, {"error": "Erreur de lecture ou d'écriture locale"})
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_lab(data_dir=ROOT / "data", work_dir=ROOT / "runs/lab", port=8766):
    manager = LabManager(data_dir, work_dir)
    server = make_lab_server(manager, port)
    print(f"Swarm Lab — http://127.0.0.1:{server.server_port} — aucune clé préconfigurée", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for run in manager.runs.values():
            run.pause_requested.set()
    finally:
        server.server_close()
