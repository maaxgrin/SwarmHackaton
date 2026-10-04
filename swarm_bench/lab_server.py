"""Local operator UI and run controller. No agent can access these operator endpoints."""
import copy
import csv
import io
import json
import mimetypes
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .common import ROOT, read_json, write_json
from .lab_engine import DEFAULT_COMMON_PROMPT, DEFAULT_SOLO_COMMON_PROMPT, DEFAULT_COMMUNICATION_PROMPT, DEFAULT_RESTRICTION, ASSET_RESTRICTION, SEGMENT_RESTRICTION, TOOLS, GROUP_TOOLS, PYTHON_TOOL, ARC_TOOLS, ACCOUNT_TOOL, ARC_PROMPT, LabRun, agent_text_defaults, assemble_prompt, is_segment
from .lab_storage import atomic_json, load_run, save_run
from .pdf_export import render_run_pdf
from .providers import ProviderError, ProviderRegistry, load_local_env

_TITLE_SUFFIX = re.compile(r"^(.*) \(\d+\)$")
_MAX_TITLE_LEN = 150
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_CLIENT_DISCONNECTED = (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)


def unique_experiment_title(title, existing_titles):
    """If title is taken, append Windows-style (1), (2), … to the base name."""
    taken = set(existing_titles)
    if title not in taken:
        return title
    match = _TITLE_SUFFIX.match(title)
    base = match.group(1) if match else title
    n = 1
    while True:
        suffix = f" ({n})"
        room = _MAX_TITLE_LEN - len(suffix)
        candidate = (base[:room] if len(base) > room else base) + suffix
        if candidate not in taken:
            return candidate
        n += 1


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
        self.favorites = self._read_favorites()
        stale = self.favorites - set(self.archives)
        if stale:
            self.favorites -= stale
            try:
                self._write_favorites()
            except OSError:
                pass
        self.tasks = []
        for item in read_json(self.data_dir / "manifest.json")["items"]:
            problem = read_json(self.data_dir / item["variants"]["split10"] / "public/problem.json")
            self.tasks.append({"id": item["task_id"], "question": problem["question"], "cue": item["cue"]})

    def summary(self, state):
        metrics = state.get("metrics", {})
        return {"id": state["id"], "title": state["config"]["title"], "config": state["config"],
                "status": state["status"], "created_at": state["created_at"], "metrics": metrics,
                "favorite": state["id"] in self.favorites}

    def bootstrap(self):
        with self.lock:
            states = list(self.archives.values()) + [r.snapshot() for r in self.runs.values()]
            return {"tasks": self.tasks, "providers": self.registry.public(), "restriction_prompt": DEFAULT_RESTRICTION,
                    "asset_restriction_prompt": ASSET_RESTRICTION, "segment_restriction_prompt": SEGMENT_RESTRICTION,
                    "common_prompt": DEFAULT_COMMON_PROMPT, "solo_common_prompt": DEFAULT_SOLO_COMMON_PROMPT,
                    "communication_prompt": DEFAULT_COMMUNICATION_PROMPT, "arc_prompt": ARC_PROMPT, "tools": copy.deepcopy(TOOLS + [t for t in ARC_TOOLS if t["function"]["name"] not in {x["function"]["name"] for x in TOOLS}] + [ACCOUNT_TOOL]),
                    "runs": [self.summary(s) for s in sorted(states, key=lambda s: s["created_at"], reverse=True)]}

    def create(self, config):
        config = copy.deepcopy(config)
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        with self.lock:
            titles = [s["config"]["title"] for s in self.archives.values()]
            titles.extend(r.state["config"]["title"] for r in self.runs.values())
            title = config.get("title", "Peer pressure experiment")
            if isinstance(title, str):
                config["title"] = unique_experiment_title(title, titles)
            run = LabRun(config, self.data_dir, self.work_dir / "runs" / run_id, self.registry)
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
            raise ValueError("Unknown experiment")

    def inspect(self, run_id, agent):
        if run_id in self.runs:
            return self.runs[run_id].inspect(agent)
        state = self.snapshot(run_id)
        if agent not in state["config"]["agents"]:
            raise ValueError("Unknown agent")
        folder = self.work_dir / "runs" / run_id
        history = copy.deepcopy(self.archive_histories[run_id].get(agent, []))
        account = None
        intact = None
        if state["config"].get("scenario") in ("custom", "communication", "group_misalignment", "altruism", "arc"):
            files = state.get("workspace_state", state["config"].get("workspace_files", {})).get(agent, {})
            file = files
        elif is_segment(state["config"].get("scenario")):
            files = state.get("workspace_state", {}).get(agent, {})
            intact = state.get("segment_report", {}).get("intact_notes", {}).get(agent)
            file = json.loads(intact) if intact else files
            if agent not in state["config"].get("restricted", []):
                intact = None
        elif state["config"].get("scenario") == "asset_aggregation":
            account = state.get("accounts", {}).get(agent)
            file, files = account, state.get("workspace_state", {}).get(agent, {})
        else:
            file = read_json(folder / "agents" / agent / "notes.json")
            files = {"notes.json": file}
        names = state["config"].get("agent_tools", {}).get(agent, state["config"].get("enabled_tools", [t["function"]["name"] for t in TOOLS]))
        sections, exact = assemble_prompt(state["config"], agent) if history else (None, None)
        if exact != (history[0]["content"] if history else None):
            sections = None
        return {"agent_id": agent, "system_prompt": history[0]["content"] if history else "History unavailable for this agent.",
                "question": state["question"], "file": file, "files": files,
                **({"sections": sections} if sections is not None else {}),
                **({"account": account} if account is not None else {}),
                **({"intact_file": intact} if intact is not None else {}),
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

    def export_pdf(self, run_id, kind):
        return render_run_pdf(self.export(run_id), kind)

    def control(self, run_id, action):
        with self.lock:
            if run_id not in self.runs:
                raise ValueError("Archived run is view-only; duplicate its configuration to run again")
            run = self.runs[run_id]
            if run.state["status"] in ("complete", "stopped"):
                raise ValueError("Experiment finished")
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
                raise ValueError("Unknown command")
            if self.workers.get(run_id) and self.workers[run_id].is_alive():
                raise ValueError("Execution is already in progress")
            if not run.remaining_agents():
                raise ValueError("Call limit reached; create a new run to use a fresh budget")
            if run.config["mode"] == "demo" and not run.demo_supported():
                raise ValueError("Scripted demo uses a peer pressure type with all of its default tools; choose Live models for a free configuration")
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
                        run.state.update(status="error", error="Internal execution error. See run events.")
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

    def _favorites_path(self):
        return self.work_dir / "favorites.json"

    def _read_favorites(self):
        path = self._favorites_path()
        if not path.exists():
            return set()
        try:
            data = read_json(path)
        except (OSError, ValueError):
            return set()
        ids = data.get("ids") if isinstance(data, dict) else None
        if not isinstance(ids, list):
            return set()
        return {item for item in ids if isinstance(item, str) and _RUN_ID.fullmatch(item)}

    def _write_favorites(self):
        atomic_json(self._favorites_path(), {"ids": sorted(self.favorites)})

    def _known(self, run_id):
        return run_id in self.runs or run_id in self.archives

    def _run_ids(self, ids):
        if not isinstance(ids, list) or not ids:
            raise ValueError("Choose at least one experiment")
        if len(ids) > 200:
            raise ValueError("Too many experiments at once")
        unique = []
        seen = set()
        for item in ids:
            if not isinstance(item, str) or not _RUN_ID.fullmatch(item):
                raise ValueError("Unknown experiment")
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def _run_folder(self, run_id):
        root = (self.work_dir / "runs").resolve()
        folder = (root / run_id).resolve()
        if folder.parent != root:
            raise ValueError("Unknown experiment")
        return folder

    def _titles(self, except_id=None):
        titles = []
        for run_id, state in self.archives.items():
            if run_id != except_id:
                titles.append(state["config"]["title"])
        for run_id, run in self.runs.items():
            if run_id != except_id:
                with run.lock:
                    titles.append(run.config["title"])
        return titles

    @staticmethod
    def _clean_title(title):
        if not isinstance(title, str):
            raise ValueError("Enter a name")
        title = " ".join(title.split())
        if not title or len(title) > _MAX_TITLE_LEN:
            raise ValueError("Name must be 1-150 characters")
        return title

    def rename(self, run_id, title):
        title = self._clean_title(title)
        with self.lock:
            if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id) or not self._known(run_id):
                raise ValueError("Unknown experiment")
            if title in self._titles(except_id=run_id):
                raise ValueError("An experiment already uses this name")
            if run_id in self.runs:
                run = self.runs[run_id]
                with run.lock:
                    previous = run.config["title"]
                    if previous == title:
                        return self.summary(run.snapshot())
                    run.config["title"] = title
                    try:
                        run.persist()
                    except Exception:
                        run.config["title"] = previous
                        raise
            else:
                state = self.archives[run_id]
                previous = state["config"]["title"]
                if previous != title:
                    state["config"]["title"] = title
                    try:
                        save_run(self._run_folder(run_id), state, self.archive_histories[run_id])
                    except Exception:
                        state["config"]["title"] = previous
                        raise
            return self.summary(self.snapshot(run_id))

    def set_favorites(self, ids, favorite):
        if not isinstance(favorite, bool):
            raise ValueError("Invalid favorite value")
        unique = self._run_ids(ids)
        with self.lock:
            if any(not self._known(run_id) for run_id in unique):
                raise ValueError("Unknown experiment")
            if favorite:
                self.favorites.update(unique)
            else:
                self.favorites.difference_update(unique)
            self._write_favorites()
            return {"ids": unique, "favorite": favorite}

    def delete_runs(self, ids):
        unique = self._run_ids(ids)
        with self.lock:
            if any(not self._known(run_id) for run_id in unique):
                raise ValueError("Unknown experiment")
            busy = []
            for run_id in unique:
                worker = self.workers.get(run_id)
                if worker and worker.is_alive() and run_id in self.runs:
                    with self.runs[run_id].lock:
                        busy.append(self.runs[run_id].config["title"])
            if busy:
                names = ", ".join(busy[:3])
                extra = "" if len(busy) <= 3 else f" +{len(busy) - 3}"
                raise ValueError("Stop running experiments before deleting them: " + names + extra)
            for run_id in unique:
                folder = self._run_folder(run_id)
                if folder.exists():
                    if not folder.is_dir():
                        raise ValueError("Unknown experiment")
                    shutil.rmtree(folder)
                self.runs.pop(run_id, None)
                self.archives.pop(run_id, None)
                self.archive_histories.pop(run_id, None)
                self.workers.pop(run_id, None)
                self.favorites.discard(run_id)
            self._write_favorites()
            return {"deleted": unique}


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
            try:
                self.end_headers()
                self.wfile.write(data)
            except _CLIENT_DISCONNECTED:
                return

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
                self.send(403, {"error": "Local access only"})
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
                        elif len(parts) == 4 and parts[3] in ("export.pdf", "chats.pdf"):
                            kind = "results" if parts[3] == "export.pdf" else "chats"
                            suffix = "" if kind == "results" else "-chats"
                            self.send(200, manager.export_pdf(parts[2], kind), "application/pdf", "swarm-lab-" + parts[2] + suffix + ".pdf")
                        elif len(parts) == 4 and parts[3] == "export":
                            self.send(200, manager.export(parts[2]), attachment="swarm-lab-" + parts[2] + ".json")
                        elif len(parts) == 3:
                            self.send(200, manager.snapshot(parts[2]))
                        else:
                            self.send(404, {"error": "Unknown route"})
                    elif path in ("/", "/app.js", "/style.css"):
                        file = static / ("index.html" if path == "/" else path[1:])
                        self.send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
                    elif path == "/favicon.ico":
                        self.send(204, b"", "image/x-icon")
                    else:
                        self.send(404, {"error": "Unknown route"})
                    return
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    raise ValueError("Content-Type application/json required")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
                if path == "/api/providers":
                    self.send(200, {"providers": manager.registry.save(body)})
                elif path == "/api/preview":
                    run = LabRun(body, manager.data_dir, manager.work_dir / "preview", manager.registry, preview=True)
                    self.send(200, {"question": run.question, "agents": {a: {"prompt": run.prompt(a), "sections": run.prompt_sections(a),
                              "file": run.files[a], "files": run.workspaces[a], "tools": run.tools_for(a),
                              "defaults": agent_text_defaults(run.config, a),
                              **({"account": run.accounts[a]} if run.accounts else {}),
                              **({"intact_file": run.segment_data["intact_notes"][a]}
                                 if is_segment(run.config["scenario"]) and a in run.config["restricted"] else {})}
                              for a in run.agents}})
                elif path == "/api/runs":
                    self.send(201, manager.create(body))
                elif path == "/api/runs/delete":
                    self.send(200, manager.delete_runs(body.get("ids")))
                elif path == "/api/runs/favorite":
                    self.send(200, manager.set_favorites(body.get("ids"), body.get("favorite")))
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "rename":
                    self.send(200, manager.rename(parts[2], body.get("title")))
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "control":
                    self.send(200, manager.control(parts[2], body.get("action")))
                else:
                    self.send(404, {"error": "Unknown route"})
            except (ValueError, TypeError, KeyError, ProviderError) as exc:
                self.send(400, {"error": str(exc)})
            except OSError as exc:
                if isinstance(exc, _CLIENT_DISCONNECTED) or getattr(exc, "winerror", None) == 10053:
                    return
                self.send(500, {"error": "Local read or write error"})
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_lab(data_dir=ROOT / "data", work_dir=ROOT / "runs/lab", port=8766):
    load_local_env(ROOT / ".env")
    manager = LabManager(data_dir, work_dir)
    server = make_lab_server(manager, port)
    print(f"Swarm Lab — http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for run in manager.runs.values():
            run.pause_requested.set()
    finally:
        server.server_close()
