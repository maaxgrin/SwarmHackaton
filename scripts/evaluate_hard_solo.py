"""Offline WASI evaluation of a submitted LiveCodeBench stdin program; no model feedback."""
import base64
import io
import json
import pickle
from pathlib import Path
import sys
import urllib.request
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from swarm_bench.python_runtime import run_python

class DataOnly(pickle.Unpickler):
    def find_class(self,*_): raise ValueError('Executable pickle objects are forbidden')

def main(rid):
    root=Path(__file__).resolve().parents[1]/'runs/deepseek'/rid
    task=json.loads((root/'benchmark.json').read_text())
    with urllib.request.urlopen('http://127.0.0.1:8766/api/runs/'+rid+'/export',timeout=20) as response:run=json.load(response)
    (root/'export.json').write_text(json.dumps(run,ensure_ascii=False,indent=2))
    answers=run['answers']['agent_01']
    if not answers: raise SystemExit('No submitted code yet')
    code=answers[0]['raw_answer']
    if code.startswith('```'):
        code=code.split('\n',1)[1].rsplit('```',1)[0]
    (root/'submitted.py').write_text(code)
    private=DataOnly(io.BytesIO(zlib.decompress(base64.b64decode(task['private_test_cases'])))).load()
    if isinstance(private,str): private=json.loads(private)
    tests=[('public',t) for t in json.loads(task['public_test_cases'])]+[('private',t) for t in private]
    results=[]
    for i,(kind,test) in enumerate(tests):
        output=run_python(code,test['input'])
        equal=output['exit_code']==0 and output['stdout'].split()==test['output'].split()
        row={'index':i,'kind':kind,'passed':equal,'timed_out':output['timed_out'],'exit_code':output['exit_code']}
        if not equal:row.update(input=test['input'][:2000],expected=test['output'][:2000],actual=output['stdout'][:2000],stderr=output['stderr'][:1000])
        results.append(row)
        (root/'evaluation.json').write_text(json.dumps({'run_id':rid,'total_cases':len(tests),'tested':len(results),'passed':sum(r['passed'] for r in results),'runtime':'CPython 3.12 WASI; 10 sec/case, 256 MiB','cases':results},indent=2))
        print(json.dumps(row),flush=True)
    print(json.dumps({'tested':len(results),'passed':sum(r['passed'] for r in results)}),flush=True)

if __name__=='__main__':main(sys.argv[1])
