"""Run one public ARC-AGI-2 calibration task. Test outputs stay evaluator-only."""
import hashlib
import json
from pathlib import Path
import urllib.request

BASE='http://127.0.0.1:8766'
ROOT=Path(__file__).resolve().parents[1]

def fetch(url,data=None):
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json','User-Agent':'Swarm-Lab-calibration'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def main():
    profile=next(p for p in fetch(BASE+'/api/bootstrap')['providers'] if p['id']=='deepseek-v4-flash')
    if not profile.get('key_present'):raise SystemExit('DeepSeek key missing; no run started')
    revision=fetch('https://api.github.com/repos/arcprize/ARC-AGI-2/commits/main')['sha']
    listing=fetch(f'https://api.github.com/repos/arcprize/ARC-AGI-2/contents/data/evaluation?ref={revision}')
    filename=sorted(x['name'] for x in listing if x['name'].endswith('.json'))[0]
    task_id=filename[:-5]
    source=f'https://raw.githubusercontent.com/arcprize/ARC-AGI-2/{revision}/data/evaluation/{filename}'
    task=fetch(source)
    public={'train':task['train'],'test':[{'input':p['input']} for p in task['test']]}
    prompt=('Infer the transformation from the demonstration input/output grids and apply it to each test input. '
            'Grids are rectangular arrays of color IDs 0 through 9. '
            'Submit your predicted test outputs using submit_answer. The answer field must contain a JSON object '
            'of the form {"outputs": [grid_for_test_1, grid_for_test_2, ...]}, in test order. '
            'Return complete grids with all cells. Only the demonstration outputs are provided.')
    config=dict(title=f'DeepSeek · ARC-AGI-2 {task_id} · solo sans Python',scenario='altruism',task_id='arc2/'+task_id,
        agent_count=1,mode='live',models={'agent_01':'deepseek-v4-flash'},common_prompt=prompt,
        custom_question=json.dumps(public,separators=(',',':')),restricted=[],leader=None,agent_prompts={},
        workspace_files={'agent_01':{}},enabled_tools=['list_files','read_file','create_file','edit_file','read_board','post_note','submit_answer'],
        agent_tools={},board_delivery='tool_only',answer_policy='none',idle_policy='finish',idle_wait_seconds=0,
        call_limit=200,max_output_tokens=16000,total_output_tokens=1500000,temperature=None,seed=0,
        importance='normal',submit_only=True,retain_after_submit=True,transient_retries=2,budget_usd=None)
    run=fetch(BASE+'/api/runs',config)
    folder=ROOT/'runs/arc2'/run['id'];folder.mkdir(parents=True)
    (folder/'task-evaluator.json').write_text(json.dumps(task))
    (folder/'provenance.json').write_text(json.dumps({'source':source,'revision':revision,'task_id':task_id,
        'selection':'first public evaluation filename in lexicographic order','run_id':run['id'],
        'sha256_canonical_json':hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest()},indent=2))
    fetch(BASE+'/api/runs/'+run['id']+'/control',{'action':'play'})
    print(json.dumps({'id':run['id'],'task_id':task_id,'train_examples':len(task['train']),'test_inputs':len(task['test']),
        'question_chars':len(config['custom_question']),'source':source}),flush=True)

if __name__=='__main__':main()
