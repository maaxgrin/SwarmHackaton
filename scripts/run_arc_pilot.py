"""Start one DeepSeek ARC-AGI-3 pilot, without exposing Python to the agent."""
import getpass
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_bench.lab_engine import ARC_PROMPT, ARC_TOOLS

def request(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:8766'+path,
        data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def main():
    key=getpass.getpass('OpenRouter key (hidden): ').strip()
    if not key:raise SystemExit('No key; nothing launched')
    req=urllib.request.Request('https://openrouter.ai/api/v1/credits',headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(req,timeout=20) as response:credit=json.load(response)['data']
    print(json.dumps({'balance_usd':credit['total_credits']-credit['total_usage']}),flush=True)
    request('/api/providers',dict(id='deepseek-v4-flash',name='DeepSeek V4 Flash · low',kind='openai_compatible',
        base_url='https://openrouter.ai/api/v1',model='deepseek/deepseek-v4-flash',key_env='',
        token_parameter='max_tokens',reasoning_effort='low',api_key=key))
    key=None
    config=dict(title='DeepSeek · ARC-AGI-3 LS20 · solo sans Python',scenario='arc',task_id='ls20-9607627b',arc_game_id='ls20-9607627b',
        agent_count=1,mode='live',models={'agent_01':'deepseek-v4-flash'},common_prompt=ARC_PROMPT,
        custom_question='Explore the environment and complete its levels.',restricted=[],leader=None,agent_prompts={},
        workspace_files={'agent_01':{}},enabled_tools=[t['function']['name'] for t in ARC_TOOLS if t['function']['name']!='run_python'],
        agent_tools={},board_delivery='tool_only',answer_policy='none',idle_policy='finish',idle_wait_seconds=0,
        call_limit=200,max_output_tokens=16000,total_output_tokens=1500000,temperature=None,seed=0,
        importance='normal',submit_only=True,retain_after_submit=True,transient_retries=2,budget_usd=None)
    run=request('/api/runs',config)
    folder=ROOT/'runs/arc'/run['id'];folder.mkdir(parents=True)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'runs/runtime/arc-games/ls20/9607627b').iterdir() if p.is_file()}
    (folder/'manifest.json').write_text(json.dumps({'id':run['id'],'config':config,'arc_agi':'0.9.9','arcengine':'0.9.3','game_files_sha256':hashes},indent=2))
    request('/api/runs/'+run['id']+'/control',{'action':'play'})
    print(json.dumps({'run_id':run['id'],'folder':str(folder)}),flush=True)

if __name__=='__main__':main()
