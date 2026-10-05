import unittest
from unittest.mock import patch
from swarm_bench.providers import ProviderError, completion
import json


class Reply:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self, _): return json.dumps(self.data).encode()


class ProviderErrorTests(unittest.TestCase):
    def test_gpt5_reasoning_request_has_long_timeout(self):
        profile={'kind':'openai_compatible','model':'gpt-5','base_url':'https://api.openai.com/v1',
                 'reasoning_effort':'medium','token_parameter':'max_completion_tokens'}
        with patch('swarm_bench.providers.build_opener') as opener:
            opener.return_value.open.return_value=Reply({'choices':[{'message':{'content':'42'}}]})
            completion(profile,'fake-key',[{'role':'user','content':'Task'}],[],16000)
            payload=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['model'],'gpt-5')
            self.assertEqual(payload['reasoning_effort'],'medium')
            self.assertEqual(payload['max_completion_tokens'],16000)
            self.assertNotIn('temperature',payload)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],600)
    def test_o1_uses_reasoning_token_budget_without_sampling_or_tools(self):
        profile={'kind':'openai_compatible','model':'o1','base_url':'https://api.openai.com/v1',
                 'reasoning_effort':'medium','token_parameter':'max_completion_tokens'}
        with patch('swarm_bench.providers.build_opener') as opener:
            opener.return_value.open.return_value=Reply({'choices':[{'message':{'content':'42'}}]})
            completion(profile,'fake-key',[{'role':'user','content':'Task'}],[],16000)
            payload=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['model'],'o1')
            self.assertEqual(payload['max_completion_tokens'],16000)
            self.assertEqual(payload['reasoning_effort'],'medium')
            for field in ('max_tokens','temperature','thinking','tools'):self.assertNotIn(field,payload)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],600)

    def test_direct_deepseek_thinking_and_timeout(self):
        profile={'kind':'openai_compatible','model':'deepseek-flash','base_url':'https://api.deepseek.com','reasoning_effort':'medium'}
        with patch('swarm_bench.providers.build_opener') as opener:
            opener.return_value.open.return_value=Reply({'choices':[{'message':{'content':'42'}}]})
            completion(profile,'fake-key',[{'role':'user','content':'Task'}],[],16000)
            request=opener.return_value.open.call_args.args[0]
            payload=json.loads(request.data)
            self.assertEqual(payload['thinking'],{'type':'enabled'})
            self.assertEqual(payload['reasoning_effort'],'high')
            self.assertNotIn('tools',payload)
            self.assertNotIn('temperature',payload)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],600)

    def test_direct_deepseek_none_really_disables_thinking(self):
        profile={'kind':'openai_compatible','model':'deepseek-flash','base_url':'https://api.deepseek.com','reasoning_effort':'none'}
        with patch('swarm_bench.providers.build_opener') as opener:
            opener.return_value.open.return_value=Reply({'choices':[{'message':{'content':'42'}}]})
            completion(profile,'fake-key',[],[],128)
            payload=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['thinking'],{'type':'disabled'})
            self.assertNotIn('reasoning_effort',payload)

    def call(self, data):
        profile = {'kind':'openai_compatible', 'model':'test', 'base_url':'https://openrouter.ai/api/v1'}
        with patch('swarm_bench.providers.build_opener') as opener:
            opener.return_value.open.return_value = Reply(data)
            return completion(profile, 'secret-test', [], [], 8192)

    def test_http_200_error_preserves_code_without_sensitive_body(self):
        with self.assertRaises(ProviderError) as caught:
            self.call({'error':{'code':503,'message':'secret-test private content'}})
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.diagnostic['provider_error_code'],503)
        self.assertNotIn('secret-test',str(caught.exception))

    def test_null_message_is_structural_error_not_invented_answer(self):
        with self.assertRaises(ProviderError) as caught:
            self.call({'choices':[{'message':None}]})
        self.assertEqual(caught.exception.diagnostic['message_type'],'NoneType')
        self.assertFalse(caught.exception.retryable)

    def test_null_tools_and_reasoning_usage(self):
        msg, usage = self.call({'choices':[{'message':{'content':'42','tool_calls':None}}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':15},'cost':0.001}})
        self.assertEqual(msg['content'],'42')
        self.assertEqual(usage['reasoning_tokens'],15)
        self.assertEqual(usage['cost_usd'],0.001)

    def test_truncated_tool_not_executed(self):
        with self.assertRaises(ProviderError) as caught:
            self.call({'choices':[{'finish_reason':'length','message':{'tool_calls':[]}}]})
        self.assertFalse(caught.exception.retryable)
