import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from swarm_bench.native_portal import NativeManager,read_rows

class NativePortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'data/impossiblebench').mkdir(parents=True)
        (self.root/'data/impossiblebench/tasks.json').write_text(json.dumps([{'id':'lcbhard_0/conflicting','test':'def check(candidate): pass'}]))
        self.manager=NativeManager(self.root,key='test-secret');self.config={'tasks':['lcbhard_0/conflicting'],'prompts':['B'],'budget_usd':4,'name':'Test'}
    def test_validation(self):
        for updates in [{'tasks':['../x']},{'budget_usd':float('nan')},{'prompts':['X']},{'tasks':['lcbhard_0/conflicting']*2}]:
            with self.assertRaises(ValueError):self.manager.validate({**self.config,**updates})
    def test_partial_result_is_readable(self):
        path=self.root/'results.jsonl';path.write_text('{"status":"success"}\n{"sta')
        self.assertEqual(read_rows(path),[{'status':'success'}])
    def test_active_existing_job_blocks_launch(self):
        folder=self.manager.runtime/'existing';folder.mkdir();(folder/'processes.json').write_text('{"runner_pid":123}')
        with patch.object(self.manager,'worker_alive',return_value=True),patch.object(self.manager,'runtime_check') as runtime:
            with self.assertRaisesRegex(ValueError,'déjà active'):self.manager.launch(self.config)
            runtime.assert_not_called()
    def test_launch_keeps_key_out_of_saved_request(self):
        proc=Mock(pid=123);proc.poll.return_value=None
        with patch.object(self.manager,'runtime_check'),patch('swarm_bench.native_portal.subprocess.Popen',return_value=proc) as spawn:
            job=self.manager.launch(self.config)
        self.assertEqual(spawn.call_args.kwargs['env']['OPENAI_API_KEY'],'test-secret')
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertNotIn('test-secret',(self.manager.runtime/job['id']/'request.json').read_text())
        self.assertEqual(job['name'],'Test');self.assertTrue(job['worker_active'])
    def test_history_survives_restart_and_counts_only_valid_scores(self):
        folder=self.manager.runtime/'saved';folder.mkdir()
        (folder/'request.json').write_text(json.dumps(self.config))
        (folder/'plan.json').write_text(json.dumps({'tasks':self.config['tasks'],'prompts':['B']}))
        (folder/'progress.json').write_text('{"phase":"complete"}')
        (folder/'results.jsonl').write_text(json.dumps({'status':'success','final_native_score':'C','successful_impossible_pass':True})+'\n'+json.dumps({'status':'success','final_native_score':'C','sample_limit':'cost'})+'\n')
        restarted=NativeManager(self.root,key='')
        job=restarted.jobs()[0];self.assertEqual(job['name'],'Test');self.assertEqual(job['processed'],2);self.assertEqual(job['evaluated'],1);self.assertEqual(job['successful_impossible_passes'],1)
    def test_dead_running_job_is_interrupted(self):
        folder=self.manager.runtime/'saved';folder.mkdir();(folder/'progress.json').write_text('{"phase":"running"}')
        self.assertEqual(self.manager.describe(folder)['phase'],'interrupted')

if __name__=='__main__':unittest.main()
