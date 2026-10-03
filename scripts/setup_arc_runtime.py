"""Fetch the official public game once, then use OFFLINE mode for experiments.

uv venv --python 3.12 runs/runtime/arc-venv
uv pip install --python runs/runtime/arc-venv/bin/python arc-agi==0.9.9 arcengine==0.9.3
runs/runtime/arc-venv/bin/python scripts/setup_arc_runtime.py
"""
import logging
from pathlib import Path
logging.disable(logging.CRITICAL)
import arc_agi

root=Path(__file__).resolve().parents[1]
arc=arc_agi.Arcade(environments_dir=str(root/'runs/runtime/arc-games'))
env=arc.make('ls20-9607627b')
assert env is not None
print('Public LS20 environment cached; subsequent experiments can run offline')
