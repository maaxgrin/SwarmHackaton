"""Python/WASI: no host directory, credentials or sockets exposed to guest code."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
WASM = ROOT / "runs/runtime/python.wasm"
SHA256 = "e5dc5a398b07b54ea8fdb503bf68fb583d533f10ec3f930963e02b9505f7a763"


def run_python(code, stdin="", timeout=10):
    if not isinstance(code, str) or not isinstance(stdin, str):
        raise ValueError("code and stdin must be strings")
    runtime = ROOT / ".venv/bin/python"
    if not WASM.exists() or not runtime.exists():
        raise ValueError("Python runtime missing; run scripts/setup_python_runtime.py")
    try:
        proc = subprocess.run([str(runtime), str(Path(__file__).resolve()), "--worker"],
            input=json.dumps({"code":code,"stdin":stdin,"timeout":timeout}), text=True,
            capture_output=True, timeout=timeout+30, env={"PATH":"/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        return dict(stdout="",stderr="Interpreter startup/execution timed out",exit_code=1,timed_out=True,truncated=False)
    if proc.returncode:
        raise ValueError("Python sandbox worker failed")
    return json.loads(proc.stdout)


def worker(data):
    import wasmtime
    if hashlib.sha256(WASM.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Python runtime checksum mismatch")
    config=wasmtime.Config();config.epoch_interruption=True
    engine=wasmtime.Engine(config)
    module=wasmtime.Module.from_file(engine,str(WASM))
    store=wasmtime.Store(engine)
    store.set_limits(memory_size=256*1024*1024, memories=1, instances=1, table_elements=100000)
    store.set_epoch_deadline(1)
    stdout=bytearray();stderr=bytearray();truncated=[False]
    def capture(target):
        def write(chunk):
            room=max(0,16000-len(stdout)-len(stderr))
            target.extend(chunk[:room]);truncated[0] |= len(chunk)>room
            return len(chunk)
        return write
    wasi=wasmtime.WasiConfig()
    wasi.argv=['python','-I','-c',data['code']]
    wasi.env=[]
    wasi.stdout_custom=capture(stdout);wasi.stderr_custom=capture(stderr)
    with tempfile.TemporaryDirectory(prefix='swarm-stdin-') as folder:
        path=Path(folder)/'stdin';path.write_text(data.get('stdin',''))
        wasi.stdin_file=str(path)
        # No preopen_dir: neither agent workspaces nor host files are visible.
        store.set_wasi(wasi)
        linker=wasmtime.Linker(engine);linker.define_wasi()
        timer=threading.Timer(data.get('timeout',10),engine.increment_epoch)
        timer.daemon=True;timer.start()
        exit_code=0;timed_out=False
        try:
            instance=linker.instantiate(store,module)
            instance.exports(store)['_start'](store)
        except wasmtime.ExitTrap as exc:
            exit_code=exc.code
        except wasmtime.Trap as exc:
            exit_code=1;timed_out='interrupt' in str(exc).lower()
            stderr.extend(('\nWASM execution interrupted' if timed_out else '\nWASM execution trapped').encode())
        finally:
            timer.cancel()
    return dict(stdout=stdout.decode(errors='replace'),stderr=stderr.decode(errors='replace'),
                exit_code=exit_code,timed_out=timed_out,truncated=truncated[0])


if __name__=='__main__':
    print(json.dumps(worker(json.load(sys.stdin))))
