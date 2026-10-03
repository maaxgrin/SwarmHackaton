"""Describe communication tool use from an exported run; never calls a model."""
import argparse
import json
from pathlib import Path


def analyze(data):
    if data['config']['scenario'] != 'communication':
        raise ValueError('Expected a communication run export')
    requests={e['request_id']:e for e in data['events'] if e['kind']=='model_request'}
    agents=[]
    for agent in data['config']['agents']:
        events=[e for e in data['events'] if e.get('agent_id')==agent]
        notes=[n for n in data['notes'] if n['agent_id']==agent]
        posts=[e for e in events if e['kind']=='note_posted']
        end=next((e for e in events if e['kind']=='agent_finished'),None)
        first=posts[0] if posts else None
        first_context=requests[first['request_id']]['exposed_note_ids'] if first else None
        agents.append({'agent_id':agent,'board_read_calls':sum(e['kind']=='board_read' for e in events),
                       'published_notes':len(notes),
                       'post_note_attempts':sum(e['kind']=='tool_called' and e['tool']=='post_note' for e in events),
                       'first_post_received_peer_note_ids':first_context,
                       'first_post_without_prior_peer_content':not first_context if first is not None else None,
                       'status':data['agent_status'][agent],
                       'completion_reason':end['reason'] if end else None,
                       'calls':data['usage'][agent]['calls'],
                       'tool_errors':sum(e['kind']=='tool_error' for e in events)})
    return {'run_id':data['id'],'status':data['status'],'agent_count':len(agents),
            'agents_that_read_board':sum(a['board_read_calls']>0 for a in agents),
            'agents_that_published':sum(a['published_notes']>0 for a in agents),
            'limited_or_failed_agents':[a['agent_id'] for a in agents if a['status'] in ('limit','error')],
            'agents':agents,
            'interpretation':'Descriptive counts within one interacting group, not independent statistical samples. A post before peer content is not a claim about psychological intent. No automatic semantic quality score.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export',type=Path)
    args=parser.parse_args()
    print(json.dumps(analyze(json.loads(args.export.read_text())),ensure_ascii=False,indent=2))
