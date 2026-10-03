import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from swarm_bench.lab_engine import LabRun, GROUP_TOOL_NAMES
from swarm_bench.common import ROOT
from swarm_bench.python_runtime import run_python, WASM

def reply(name,args,used=10):
    return {'role':'assistant','content':'','tool_calls':[{'id':'c','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}, {'input_tokens':10,'output_tokens':used}

class NewRuntimeTests(unittest.TestCase):
    def make(self,n=2,**kw):
        c=dict(scenario='altruism',custom_question='Write code.',common_prompt='Solve it.',
            agent_count=n,mode='live',models={f'agent_{i:02d}':'fake' for i in range(1,n+1)},
            enabled_tools=GROUP_TOOL_NAMES,answer_policy='none',board_delivery='tool_only',
            call_limit=20,max_output_tokens=128,**kw)
        r=LabRun(c,ROOT/'data',ROOT/'runs/unused-preview',preview=True)
        r.state['provider_profiles']={a:{} for a in r.agents};r._provider_keys={a:'' for a in r.agents}
        return r

    def test_submit_remains_active_and_large_code_accepted(self):
        r=self.make()
        with patch('swarm_bench.lab_engine.completion',return_value=reply('submit_answer',{'answer':'# long code\n'*1000})):
            r.live_call('agent_01')
        self.assertNotEqual(r.state['agent_status']['agent_01'],'done')
        r.action('agent_02','post_note',{'content':'Help with my bug'})
        with patch('swarm_bench.lab_engine.completion',return_value=reply('post_note',{'content':'Try a boundary case'})):
            r.live_call('agent_01')
        with patch('swarm_bench.lab_engine.completion',return_value=reply('submit_answer',{'answer':'code'})):
            r.live_call('agent_02')
        self.assertEqual(r.state['finish_reason'],'all_submitted')
        self.assertEqual(len(r.state['notes']),2)

    def test_global_budget_concurrent_reservations(self):
        r=self.make(total_output_tokens=256)
        barrier=threading.Barrier(2)
        def model(*args):
            barrier.wait(timeout=3)
            return reply('read_board',{},used=128)
        with patch('swarm_bench.lab_engine.completion',model):
            ts=[threading.Thread(target=r.live_call,args=(a,)) for a in r.agents]
            for t in ts:t.start()
            for t in ts:t.join(timeout=5)
        with patch('swarm_bench.lab_engine.completion') as model:r.live_call('agent_01');model.assert_not_called()
        self.assertEqual(r.state['token_budget']['accounted'],256)
        self.assertEqual(r.state['token_budget']['in_flight'],0)
        self.assertEqual(r.state['finish_reason'],'token_limit')

    def test_unknown_usage_keeps_full_reservation(self):
        r=self.make(n=1,total_output_tokens=128)
        with patch('swarm_bench.lab_engine.completion',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):r.live_call('agent_01')
        self.assertEqual(r.state['token_budget']['unknown_usage_reserved'],128)

    def test_large_reply_budget_reaches_provider_and_respects_total(self):
        config={**self.make(n=1).config,'max_output_tokens':384000,'total_output_tokens':500000}
        r=LabRun(config,ROOT/'data',ROOT/'runs/unused-preview',preview=True)
        r.state['provider_profiles']={'agent_01':{}};r._provider_keys={'agent_01':''}
        with patch('swarm_bench.lab_engine.completion',return_value=reply('read_board',{},used=384000)) as model:
            r.live_call('agent_01')
            self.assertEqual(model.call_args.args[4],384000)
        with patch('swarm_bench.lab_engine.completion',return_value=reply('read_board',{},used=116000)) as model:
            r.live_call('agent_01')
            self.assertEqual(model.call_args.args[4],116000)
        self.assertEqual(r.state['token_budget']['accounted'],500000)
        self.assertEqual(r.state['token_budget']['in_flight'],0)

    def test_python_only_assigned_agent_has_access(self):
        r=self.make(agent_tools={'agent_01':GROUP_TOOL_NAMES+['run_python']})
        with self.assertRaises(ValueError):r.action('agent_02','run_python',{'code':'print(1)'})
        with patch('swarm_bench.python_runtime.run_python',return_value={'exit_code':0,'timed_out':False}) as py:
            r.action('agent_01','run_python',{'code':'print(1)'})
            py.assert_called_once()

@unittest.skipUnless(WASM.exists(),'WASI runtime not installed')
class PythonIsolationTests(unittest.TestCase):
    def test_python_stdlib_stdin_and_no_host_access(self):
        code='''import sys,os,json,math
print(math.factorial(6),sys.stdin.read())
print('keys',list(os.environ))
try: print(open('/etc/passwd').read())
except OSError: print('host-denied')
try:
 import socket
 socket.create_connection(('127.0.0.1',8766))
 print('network-accessible')
except Exception: print('network-denied')
'''
        r=run_python(code,'sample')
        self.assertEqual(r['exit_code'],0)
        self.assertIn('720 sample',r['stdout'])
        self.assertIn('host-denied',r['stdout']);self.assertIn('network-denied',r['stdout'])
        self.assertNotIn('API_KEY',r['stdout'])

    def test_infinite_loop_times_out(self):
        self.assertTrue(run_python('while True: pass',timeout=1)['timed_out'])

    def test_output_and_memory_bounded(self):
        r=run_python("print('x'*20000)")
        self.assertTrue(r['truncated']);self.assertLessEqual(len(r['stdout']),16000)
        r=run_python("a=bytearray(300*1024*1024)")
        self.assertNotEqual(r['exit_code'],0)
