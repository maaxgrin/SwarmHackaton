import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from swarm_bench.arc_runtime import ArcSession, encode_frames, ROOT
from swarm_bench.lab_engine import LabRun, ARC_TOOLS

class ArcTests(unittest.TestCase):
    def test_encoding_is_lossless(self):
        frame=[[0,1,15],[0,1,15],[2,3,4]]
        encoded=encode_frames([frame])[0];rows=[]
        for start,end,text in encoded['rows']:
            self.assertEqual(start,len(rows))
            rows.extend([[int(c,16) for c in text] for _ in range(end-start+1)])
        self.assertEqual(rows,frame)

    def test_no_submit_no_python_and_independent_sessions(self):
        class Fake:
            def __init__(self,*_):self.observation={'state':'NOT_FINISHED','frames':[],'levels_completed':0,'win_levels':1,'available_actions':['ACTION1']}
            def step(self,*_):self.observation={**self.observation,'state':'WIN','levels_completed':1};return self.observation
        tools=[t['function']['name'] for t in ARC_TOOLS if t['function']['name']!='run_python']
        c=dict(scenario='arc',mode='demo',custom_question='Explore.',agent_count=2,enabled_tools=tools,answer_policy='none',board_delivery='tool_only')
        r=LabRun(c,ROOT/'data',ROOT/'runs/unused',preview=True)
        with patch('swarm_bench.arc_runtime.ArcSession',Fake):
            r.action('agent_01','arc_observe',{})
            r.action('agent_02','arc_observe',{})
            r.action('agent_01','arc_step',{'action':'ACTION1'})
            self.assertEqual(r.state['arc']['agent_02']['observation']['state'],'NOT_FINISHED')
            self.assertNotEqual(r.state['status'],'complete')
            r.action('agent_02','arc_step',{'action':'ACTION1'})
            self.assertEqual(r.state['finish_reason'],'arc_all_won')
        for name,args in [('submit_answer',{'answer':'WIN'}),('run_python',{'code':'print(1)'})]:
            with self.assertRaises(ValueError):r.action('agent_01',name,args)

    @unittest.skipUnless((ROOT/'runs/runtime/arc-games/ls20/9607627b').exists(),'Local ARC game absent')
    def test_real_environment_public_boundary_and_replay(self):
        a=ArcSession('ls20-9607627b',0);b=ArcSession('ls20-9607627b',0)
        try:
            start=copy.deepcopy(a.observation)
            self.assertEqual(start,b.observation)
            self.assertEqual(set(start),{'game_id','state','levels_completed','win_levels','available_actions','frames'})
            a.step('ACTION1')
            self.assertEqual(b.observation,start)
            with self.assertRaises(ValueError):a.step('ACTION6',x=0,y=0)
            with self.assertRaises(ValueError):a.step('ACTION1',x=1)
        finally:a.close();b.close()

if __name__=='__main__':unittest.main()
