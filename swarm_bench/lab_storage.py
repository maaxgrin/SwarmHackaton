"""Atomic experiment checkpoints, with legacy files kept as compatibility mirrors."""
import json
import os
import tempfile
from pathlib import Path

from .common import read_json


def atomic_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_run(folder, state, histories):
    folder = Path(folder)
    # One rename commits the state and every conversation together.
    atomic_json(folder / "checkpoint.json", {"format": 1, "state": state, "histories": histories})
    # A mirror failure cannot invalidate the committed checkpoint.
    for name, value in (("state.json", state), ("histories.json", histories)):
        try:
            atomic_json(folder / name, value)
        except OSError:
            pass


def load_run(folder):
    folder = Path(folder)
    checkpoint = folder / "checkpoint.json"
    if checkpoint.exists():
        saved = read_json(checkpoint)
        if saved.get("format") != 1 or not isinstance(saved.get("histories"), dict):
            raise ValueError("Format de sauvegarde d'expérience invalide")
        return saved["state"], saved["histories"]
    state = read_json(folder / "state.json")
    try:
        histories = read_json(folder / "histories.json")
        if not isinstance(histories, dict):
            raise ValueError("Historique invalide")
    except (OSError, ValueError):
        # Do not invent a lost conversation or make the surviving observations inaccessible.
        histories = {}
    histories = {a: h for a, h in histories.items() if isinstance(h, list) and
                 all(isinstance(m, dict) and "role" in m and "content" in m for m in h)}
    if any(not histories.get(a) for a in state["config"]["agents"]):
        state["archive_warnings"] = ["Conversations de cet ancien essai absentes ou illisibles ; export partiel."]
    return state, histories
