"""Local launch/history page for the official runner; never resumes jobs on startup."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
from urllib.parse import urlparse

from .common import ROOT
from .impossiblebench import paper_instruction


def read_json(path, default=None):
    try:return json.loads(path.read_text())
    except (OSError, ValueError):return default


def read_rows(path):
    try:lines=path.read_text().splitlines()
    except OSError:return []
    rows=[]
    for line in lines:
        try:rows.append(json.loads(line))
        except ValueError:continue  # A writer may still be appending the last line.
    return rows


class NativeManager:
    def __init__(self, root=ROOT, key=None):
        self.root=Path(root);self.runtime=self.root/'runs/impossiblebench-official'
        self.runtime.mkdir(parents=True,exist_ok=True)
        self.key=os.environ.get('OPENAI_API_KEY','') if key is None else key
        self.lock=threading.RLock();self.workers={}

    def tasks(self):
        return read_json(self.root/'data/impossiblebench/tasks.json',[])

    @staticmethod
    def task_error(row):
        try:compile(row['test'],'test.py','exec')
        except SyntaxError:return 'Tests source invalides (syntaxe Python)'
        return None

    def folder(self, identity):
        if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',identity):raise ValueError('Identifiant de série invalide')
        folder=self.runtime/identity
        if not folder.is_dir():raise ValueError('Série inconnue')
        return folder

    def worker_alive(self, identity, folder):
        process=self.workers.get(identity)
        if process is not None:return process.poll() is None
        pid=(read_json(folder/'processes.json',{}) or {}).get('runner_pid')
        if not isinstance(pid,int):return False
        try:
            probe=subprocess.run(['ps','-p',str(pid),'-o','args='],capture_output=True,text=True,timeout=2)
            return probe.returncode==0 and 'scripts/run_impossiblebench_official.py' in probe.stdout
        except (OSError,subprocess.TimeoutExpired):return False

    def describe(self, folder, detailed=False):
        plan={**(read_json(folder/'request.json',{}) or {}), **(read_json(folder/'plan.json',{}) or {})}
        progress=read_json(folder/'progress.json',{}) or {}
        rows=read_rows(folder/'results.jsonl')
        alive=self.worker_alive(folder.name,folder)
        phase=progress.get('phase','validating' if alive else 'interrupted')
        if phase in ('running','validating') and not alive:phase='interrupted'
        valid=[r for r in rows if r.get('status')=='success' and not r.get('sample_limit') and r.get('final_native_score') in ('C','I')]
        result={'id':folder.name,'name':plan.get('name') or folder.name,'phase':phase,'worker_active':alive,
                'planned':len(plan.get('tasks',[]))*len(plan.get('prompts',[]))*plan.get('repetitions',1), 'processed':len(rows),'evaluated':len(valid),
                'successful_impossible_passes':sum(r.get('successful_impossible_pass') is True for r in valid),
                'cost_usd':max(progress.get('estimated_cost_usd',0) or 0,sum(r.get('estimated_cost_usd',0) or 0 for r in rows)),
                'budget_usd':plan.get('operator_budget_usd',plan.get('budget_usd')),
                'current_task':progress.get('task_id') if alive else None,'current_prompt':progress.get('prompt_variant') if alive else None,
                'tasks':plan.get('tasks',[]),'prompts':plan.get('prompts',[]),'model':plan.get('model'),
                'started_at':plan.get('started_at',folder.name[:15]),'replay_url':'http://127.0.0.1:8767/'}
        if detailed:
            result.update(plan=plan,progress=progress,results=rows)
            try:tail='\n'.join((folder/'orchestrator.log').read_text().splitlines()[-18:])
            except OSError:tail=''
            result['log_tail']=re.sub(r'\bsk-(?:proj-|or-v1-)?[A-Za-z0-9_-]{10,}','[clé masquée]',tail)
        return result

    def jobs(self):
        folders=[p for p in self.runtime.iterdir() if p.is_dir() and
                 any((p/name).exists() for name in ('processes.json','results.jsonl','request.json'))]
        return [self.describe(p) for p in sorted(folders,key=lambda p:p.name,reverse=True)]

    def bootstrap(self):
        with self.lock:
            jobs=self.jobs();used={t for j in jobs for t in j['tasks']}
            return {'jobs':jobs,'busy':any(j['worker_active'] for j in jobs),'key_present':bool(self.key),
                    'runtime_installed':(self.runtime/'venv/bin/python').exists(),
                    'model':'openai/gpt-5-2025-08-07',
                    'tasks':[{'id':r['id'],'task_id':r['task_id'],'function':r['entry_point'],
                              'split':r['impossible_type'],'used':r['id'] in used,'unavailable':self.task_error(r)} for r in self.tasks()],
                    'prompts':{v:paper_instruction(v) for v in ('A','B','D')}}

    def validate(self, body):
        tasks=body.get('tasks');prompts=body.get('prompts');budget=body.get('budget_usd',4)
        available={r['id'] for r in self.tasks() if not self.task_error(r)}
        if not isinstance(tasks,list) or not 1<=len(tasks)<=103 or any(t not in available for t in tasks) or len(set(tasks))!=len(tasks):
            raise ValueError('Choisir 1 à 103 tâches distinctes du catalogue')
        if not isinstance(prompts,list) or not prompts or len(set(prompts))!=len(prompts) or any(v not in ('A','B','D') for v in prompts):
            raise ValueError('Choisir au moins un prompt officiel A, B ou D')
        if isinstance(budget,bool) or not isinstance(budget,(int,float)) or not math.isfinite(budget) or not 0<budget<=100:
            raise ValueError('Seuil de coût : nombre positif, maximum 100 $')
        name=body.get('name','Nouvelle série ImpossibleBench')
        if not isinstance(name,str) or not 1<=len(name.strip())<=140:raise ValueError('Nom invalide')
        attempts=body.get('max_attempts',10);repetitions=body.get('repetitions',1)
        if type(attempts) is not int or not 1<=attempts<=10:raise ValueError('Tentatives : 1 à 10')
        if type(repetitions) is not int or not 1<=repetitions<=20:raise ValueError('Répétitions : 1 à 20')
        peer=body.get('peer_discussion')
        if peer is not None and (not isinstance(peer,str) or not 1<=len(peer)<=20000):raise ValueError('Discussion : 1 à 20 000 caractères')
        config={'tasks':tasks,'prompts':prompts,'budget_usd':budget,'name':name.strip(),'max_attempts':attempts,'repetitions':repetitions}
        if peer:config['peer_discussion']=peer
        return config

    def runtime_check(self):
        python=self.runtime/'venv/bin/python'
        if not python.exists():raise ValueError('Runtime absent : exécuter scripts/setup_impossiblebench_official.py')
        docker=self.runtime/'bin/docker'
        env={**os.environ,'DOCKER_HOST':'unix://'+str(Path.home()/'.colima/swarm-impossiblebench/docker.sock'),
             'DOCKER_CONFIG':str(self.runtime/'docker-config')}
        try:
            result=subprocess.run([str(docker),'info','--format','{{.ServerVersion}}'],env=env,capture_output=True,timeout=8)
            if result.returncode:raise ValueError('Docker ne répond pas. Démarrer le runtime avant de lancer.')
        except (OSError,subprocess.TimeoutExpired) as e:raise ValueError('Docker indisponible') from e

    def launch(self, body):
        config=self.validate(body)
        with self.lock:
            if any(j['worker_active'] for j in self.jobs()):raise ValueError('Une série est déjà active. Attendre sa fin pour lancer la suivante.')
            if not self.key:raise ValueError('Renseigner une clé OpenAI dans la page avant de lancer')
            self.runtime_check()
            identity=datetime.now().strftime('%Y%m%d-%H%M%S-')+secrets.token_hex(3)+'-ui'
            folder=self.runtime/identity;folder.mkdir(mode=0o700)
            request={**config,'model':'openai/gpt-5-2025-08-07','started_at':datetime.now().astimezone().isoformat()}
            (folder/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
            shared=self.runtime/'model-logs';shared.mkdir(exist_ok=True)
            argv=[str(self.runtime/'venv/bin/python'),'-u',str(self.root/'scripts/run_impossiblebench_official.py'),
                  '--tasks',*config['tasks'],'--prompts',*config['prompts'],'--budget-usd',str(config['budget_usd']),
                  '--max-attempts',str(config['max_attempts']),'--repetitions',str(config['repetitions']),
                  '--output',str(folder),'--log-dir',str(shared)]
            if Path('/usr/bin/caffeinate').exists():argv=['/usr/bin/caffeinate','-i',*argv]
            if config.get('peer_discussion'):
                transcript=folder/'synthetic-peer-discussion.txt'
                transcript.write_text(config['peer_discussion'])
                argv+=['--peer-discussion',str(transcript)]
            env={**os.environ,'OPENAI_API_KEY':self.key}
            with (folder/'orchestrator.log').open('a') as log:
                process=subprocess.Popen(argv,cwd=self.root,env=env,stdout=log,stderr=log,start_new_session=True)
            self.workers[identity]=process
            (folder/'processes.json').write_text(json.dumps({'runner_pid':process.pid}))
            return self.describe(folder)


def make_server(manager,port=8768):
    static=Path(__file__).parent/'web'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def send(self,status,data,mime='application/json; charset=utf-8',attachment=None):
            raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            if attachment:self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
            self.end_headers();self.wfile.write(raw)
        def allowed(self):
            host=self.headers.get('Host','');origin=self.headers.get('Origin')
            valid={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            return host in valid and (not origin or origin in {'http://'+h for h in valid})
        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')
        def dispatch(self,method):
            if not self.allowed():self.send(403,{'error':'Accès local uniquement'});return
            parts=urlparse(self.path).path.strip('/').split('/')
            try:
                if method=='GET':
                    if parts==['api','bootstrap']:self.send(200,manager.bootstrap())
                    elif len(parts)>=3 and parts[:2]==['api','jobs']:
                        job=manager.describe(manager.folder(parts[2]),detailed=True)
                        self.send(200,job,attachment=(parts[2]+'.json') if parts[-1]=='export' else None)
                    elif parts in ([''],['native.html'],['native.js'],['native.css']):
                        name='native.html' if parts==[''] else parts[0]
                        mime='text/html' if name.endswith('html') else 'text/javascript' if name.endswith('js') else 'text/css'
                        self.send(200,(static/name).read_bytes(),mime+'; charset=utf-8')
                    else:self.send(404,{'error':'Route inconnue'})
                    return
                if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('JSON requis')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1000000:raise ValueError('Requête trop volumineuse')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('Objet JSON requis')
                if parts==['api','jobs']:self.send(201,manager.launch(body))
                elif parts==['api','key']:
                    key=body.get('api_key')
                    if not isinstance(key,str) or not key.strip():raise ValueError('Clé vide')
                    manager.key=key.strip();self.send(200,{'key_present':True})
                elif parts==['api','preview']:
                    config=manager.validate(body);row=next(r for r in manager.tasks() if r['id']==config['tasks'][0])
                    v=config['prompts'][0]
                    text=paper_instruction(v)+'\n\n```\n'+row['prompt']+'\n\n'+row['test']+f"\n\n# Use check({row['entry_point']}) to run tests.\n```"
                    self.send(200,{'prompt':text,'cases':len(config['tasks'])*len(config['prompts'])})
                else:self.send(404,{'error':'Route inconnue'})
            except (ValueError,TypeError,KeyError) as e:self.send(400,{'error':str(e)})
            except OSError:self.send(500,{'error':'Erreur locale de lecture ou de lancement'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve_native(port=8768):
    server=make_server(NativeManager(),port)
    print(f'ImpossibleBench — lancement et historique : http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()  # Workers have their own sessions and remain active.
