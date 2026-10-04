import copy
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from swarm_bench.providers import ProviderError, ProviderRegistry, completion, responses_input


class ResponsesProviderTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.replies = []
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                outer.requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                response = json.dumps(outer.replies.pop(0)).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.profile = {'kind':'openai_responses','model':'test-model','reasoning_effort':'low',
                        'base_url':f'http://127.0.0.1:{self.server.server_port}/v1'}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_stateless_tool_roundtrip_preserves_reasoning_and_call_ids(self):
        reasoning = {'type':'reasoning','id':'rs_1','summary':[], 'encrypted_content':'opaque-test-context'}
        call = {'type':'function_call','id':'fc_1','call_id':'call_1','name':'read_file','arguments':'{"path":"notes.json"}', 'status':'completed'}
        self.replies = [
            {'status':'completed','output':[reasoning,call], 'usage':{'input_tokens':10,'output_tokens':20,'output_tokens_details':{'reasoning_tokens':14}}},
            {'status':'completed','output':[{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':'42'}]}], 'usage':{'input_tokens':35,'output_tokens':4}},
        ]
        history = [{'role':'system','content':'policy'}, {'role':'user','content':'task'}]
        tool = {'type':'function','function':{'name':'read_file','description':'Read a file','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}}}
        message, usage = completion(self.profile, '', history, [tool], 4096, None)
        self.assertEqual(message['tool_calls'][0]['id'], 'call_1')
        self.assertEqual(usage, {'input_tokens':10,'output_tokens':20,'reasoning_tokens':14})
        history += [message, {'role':'tool','tool_call_id':'call_1','content':'{"value":42}'}]
        before = copy.deepcopy(history)
        final, _ = completion(self.profile, '', history, [tool], 4096, None)
        self.assertEqual(final['content'], '42')
        self.assertEqual(final['_response_items'][0]['phase'],'final_answer')
        self.assertEqual(history,before)
        path, body = self.requests[1]
        self.assertEqual(path,'/v1/responses')
        self.assertFalse(body['store'])
        self.assertEqual(body['reasoning'],{'effort':'low','summary':'auto'})
        self.assertNotIn('reasoning_text', message)
        self.assertNotIn('temperature',body)
        self.assertEqual(body['max_output_tokens'],4096)
        self.assertEqual(body['tools'][0],{'type':'function',**tool['function']})
        self.assertEqual(body['input'][-3:],[reasoning,call,{'type':'function_call_output','call_id':'call_1','output':'{"value":42}'}])
        self.assertNotIn('opaque-test-context',message['content'])
        # No synthetic duplicate of a native function call when replaying history.
        self.assertEqual(sum(item.get('type')=='function_call' for item in body['input']),1)

    def test_incomplete_response_preserves_usage_without_exposing_partial_tools(self):
        self.replies = [{'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'},
                         'output':[{'type':'function_call','call_id':'x','name':'read_file','arguments':'{}'}],
                         'usage':{'input_tokens':30,'output_tokens':128,'output_tokens_details':{'reasoning_tokens':120}}}]
        with self.assertRaises(ProviderError) as result:
            completion(self.profile,'',[{'role':'user','content':'task'}],[],128)
        self.assertEqual(result.exception.usage,{'input_tokens':30,'output_tokens':128,'reasoning_tokens':120})
        self.assertNotIn('tools',self.requests[0][1])

    def test_profile_and_legacy_message_conversion(self):
        with tempfile.TemporaryDirectory() as temp:
            registry = ProviderRegistry(Path(temp)/'models.json')
            saved=registry.save({**self.profile,'id':'luna','name':'Luna','api_key':'unit-test-secret'})
            self.assertEqual(saved[0]['token_parameter'],'max_output_tokens')
            self.assertNotIn('unit-test-secret',(Path(temp)/'models.json').read_text())
        converted=responses_input([{'role':'assistant','content':'checking','tool_calls':[{'id':'call_a','function':{'name':'read_board','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'call_a','content':'{"notes":[]}'}])
        self.assertEqual(converted[1]['call_id'],converted[2]['call_id'])
        self.assertEqual(converted[2]['type'],'function_call_output')

    def test_empty_or_failed_response_is_not_a_success(self):
        for response in ({'status':'failed','error':{'message':'untrusted upstream content'}}, {'status':'completed','output':None}):
            self.replies=[response]
            with self.assertRaises(ProviderError):
                completion(self.profile,'',[{'role':'user','content':'task'}],[],128)


if __name__=='__main__': unittest.main()
