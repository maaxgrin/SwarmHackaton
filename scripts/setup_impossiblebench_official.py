"""Install a project-local Inspect environment and Docker runtime for macOS ARM."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'runs/impossiblebench-official'
ASSETS=[
 ('colima','https://github.com/abiosoft/colima/releases/download/v0.10.3/colima-Darwin-arm64','980ad8bf61a4ca370243f4cb41401a61276dcd2c2502bee7b9b86f9250169f34'),
 ('lima.tar.gz','https://github.com/lima-vm/lima/releases/download/v2.2.1/lima-2.2.1-Darwin-arm64.tar.gz','9e9eacce88f37e185c346bad73aa6136f738d8cdf8c3bb23cd42b071824bc66e'),
 ('docker-compose','https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-darwin-aarch64','bd714a42b46e51757fc1121085b3096b9064e3f80d3ca5a991e33f44df4f43c9'),
 ('docker.tar.gz','https://download.docker.com/mac/static/stable/aarch64/docker-29.8.2.tgz','5ffa2bafbabe073470f0333f4a129599230b73d1170bb61146b3d9b08e1d1325'),
]


def main():
    if platform.system()!='Darwin' or platform.machine()!='arm64':
        raise SystemExit('This runtime installer targets macOS ARM. On Linux use Docker and the pinned Python requirements directly.')
    bins=RUNTIME/'bin';bins.mkdir(parents=True,exist_ok=True)
    for name,url,digest in ASSETS:
        path=bins/name
        if not path.exists():
            print('Downloading',name,flush=True)
            with urllib.request.urlopen(url,timeout=90) as source,path.open('wb') as output:shutil.copyfileobj(source,output)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Checksum mismatch: '+name)
        if name.endswith('.tar.gz'):
            destination=RUNTIME/('lima' if name.startswith('lima') else 'docker');destination.mkdir(exist_ok=True)
            with tarfile.open(path) as archive:archive.extractall(destination,filter='data')
            if name.startswith('docker'):shutil.copy2(destination/'docker/docker',bins/'docker')
        else:path.chmod(0o755)
    (bins/'docker').chmod(0o755)
    config=RUNTIME/'docker-config';config.mkdir(exist_ok=True)
    (config/'config.json').write_text(json.dumps({'cliPluginsExtraDirs':[str(bins)]}))
    uv=shutil.which('uv')
    if not uv:raise RuntimeError('uv is required to create the isolated Python environment')
    if not (RUNTIME/'venv/bin/python').exists():
        subprocess.run([uv,'venv',str(RUNTIME/'venv'),'--python','3.12'],check=True)
    subprocess.run([uv,'pip','install','--python',str(RUNTIME/'venv/bin/python'),'-r',str(ROOT/'requirements-impossiblebench-official.txt')],check=True)
    env={**os.environ,'PATH':str(bins)+':'+str(RUNTIME/'lima/bin')+':'+os.environ['PATH'],'DOCKER_CONFIG':str(config)}
    subprocess.run([str(bins/'colima'),'--profile','swarm-impossiblebench','start','--vm-type','vz','--cpu','2','--memory','4','--disk','30'],env=env,check=True)
    env['DOCKER_HOST']='unix://'+str(Path.home()/'.colima/swarm-impossiblebench/docker.sock')
    subprocess.run([str(bins/'docker'),'pull','aisiuk/inspect-tool-support@sha256:bbaecf7a093cfe24703c97d562bb059899e272cd5d57f16d9916fe05e6614419'],env=env,check=True)
    print('Official Docker/Inspect runtime ready')


if __name__=='__main__':main()
