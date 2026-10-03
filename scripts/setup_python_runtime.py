"""Install the pinned WASI guest. Host: uv venv .venv; uv pip install --python .venv/bin/python wasmtime==49.0.0"""
import hashlib
from pathlib import Path
import urllib.request

url='https://github.com/vmware-labs/webassembly-language-runtimes/releases/download/python/3.12.0%2B20231211-040d5a6/python-3.12.0.wasm'
expected='e5dc5a398b07b54ea8fdb503bf68fb583d533f10ec3f930963e02b9505f7a763'
with urllib.request.urlopen(url,timeout=60) as response: data=response.read()
assert hashlib.sha256(data).hexdigest()==expected
path=Path(__file__).resolve().parents[1]/'runs/runtime/python.wasm'
path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
print('Python WASI runtime installed and checksum verified')
