"""Keep administrator code examples aligned with the shipped block assembler."""
import ast
import asyncio
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import types
import unittest
import yaml
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'llm-security-control-plane'
CONTROL = BASE / 'guided-control-center'
FREE = {'P01','P04','P05','P07','P09','P11','P12','P13','P14','P15','P16','P17','P18','P19','P20','P21','P22'}
CANONICAL = {
    'P02': ('embedding_model_id', 'embedding_dimensions', 's3', 'runtime', 'put', 'embed'),
    'P03': ('agent', 'runtime', 'job', 'knowledge_base_id', 'retrieval_count', 'retrieve'),
}


def fences(path):
    return [body.strip() for _, body in re.findall(r'```([^\n]*)\n(.*?)\n```', path.read_text(), re.S)]


class AdminAnswerAlignmentTest(unittest.TestCase):
    def test_ui_offers_every_server_approved_block(self):
        spec = importlib.util.spec_from_file_location('guided_block_submission', CONTROL / 'block_submission.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        js = (CONTROL / 'block-lab.js').read_text()
        for problem, approved in module.BLOCKS.items():
            section = re.search(r'  ' + problem + r': \{.*?\n    blocks: \[(.*?)\n    \],', js, re.S)
            self.assertIsNotNone(section, problem)
            offered = set(re.findall(r'\{id: "([^"]+)"', section.group(1)))
            self.assertEqual(offered, set(approved), problem)

    def test_p00_json_answer(self):
        examples = fences(CONTROL / 'admin-answers/P00.md')
        expected = {'message': '계정 보안을 위한 조언을 한 문장으로 알려 주세요.', 'max_tokens': 64}
        self.assertEqual(len(examples), 2)
        for example in examples:
            self.assertEqual(json.loads(example), expected)

    def test_all_block_answers(self):
        spec = importlib.util.spec_from_file_location('guided_block_submission', CONTROL / 'block_submission.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        containerfile = (CONTROL / 'Containerfile').read_text()
        js = (CONTROL / 'block-lab.js').read_text()
        section = js.split('const distractor', 1)[-1].split('const slotCountOverrides', 1)[0]
        traps = {name: set(re.findall(r'"([^"]+)"', ids)) for name, ids in re.findall(r'(P\d\d): new Set\(\[([^\]]*)\]\)', section)}
        with tempfile.TemporaryDirectory() as temporary:
            starters = Path(temporary) / 'block-starters'
            starters.mkdir()
            for source, target in re.findall(r'^COPY --chmod=0444 (\S+) /app/block-starters/(\S+)$', containerfile, re.M):
                shutil.copyfile(BASE / source, starters / target)
            with patch.object(module, 'ROOT', Path(temporary)):
                for number in range(1, 23):
                    problem = f'P{number:02d}'
                    ids = CANONICAL.get(problem) or [key for key in module.BLOCKS[problem] if key not in traps.get(problem, set())]
                    order = [f'{module.BLOCKS[problem][key][0]}:{key}' if problem in FREE else key for key in ids]
                    assembled = module.assemble(problem, order).strip()
                    answer = fences(CONTROL / 'admin-answers' / f'{problem}.md')
                    if problem == 'P20':
                        rules, _, dashboard = assembled.partition(module.P20_SEPARATOR)
                        self.assertEqual([rules.strip(), dashboard.strip()], answer[:2], problem)
                        self.assertIsInstance(yaml.safe_load(rules), dict)
                        self.assertIsInstance(json.loads(dashboard), dict)
                    else:
                        self.assertEqual(assembled, answer[0], problem)
                        if module.FILES[problem].endswith(('.yaml', '.yml')):
                            self.assertIsInstance(yaml.safe_load(assembled), dict, problem)
                    if problem == 'P02':
                        self.assertLess(assembled.index('s3 = session.client'), assembled.index('source = s3.put_object'))
                        self.assertLess(assembled.index('source = s3.put_object'), assembled.index('embedding_response = bedrock.invoke_model'))
                        self._run_p02(assembled)
                    if problem == 'P03':
                        self.assertLess(assembled.index('agent = session.client'), assembled.index('job_response = agent.get_ingestion_job'))
                        self.assertLess(assembled.index('runtime = session.client'), assembled.index('result = runtime.retrieve'))
                        self._run_p03(assembled)
                    if problem == 'P05':
                        self.assertIn('\n  bot refuse recovery code\n', assembled)
                    if problem == 'P15':
                        namespace = {}
                        exec(assembled, namespace)
                        self.assertEqual(namespace['attack_contract'](), {
                            'max_turns': 3, 'impact_marker': 'H15_POLICY_BYPASS_CANARY',
                            'sequential': True, 'http_error_is_err': True,
                        })

    def _run_p02(self, source):
        events = []
        class S3:
            def put_object(self, **kwargs):
                events.append('put')
                return {'ETag': 'saved'}
        class Runtime:
            def invoke_model(self, **kwargs):
                events.append('embed')
                return {'body': io.BytesIO(b'{"embedding":[1]}')}
        class Session:
            region_name = 'us-east-1'
            def client(self, name, **kwargs):
                events.append(name)
                return S3() if name == 's3' else Runtime()
        fake_auth = types.SimpleNamespace(load_aws_session=lambda aws: (Session(), 'bucket'))
        with patch.dict(sys.modules, {'aws_auth': fake_auth}):
            namespace = {}
            exec(source, namespace)
            result = asyncio.run(namespace['prepare_document']({'title': 'title', 'body': 'long enough text'}, 'id', object()))
        self.assertEqual(events, ['s3', 'bedrock-runtime', 'put', 'embed'])
        self.assertEqual(result['embedding'], {'embedding': [1]})

    def _run_p03(self, source):
        events = []
        binding = {'knowledgeBaseId': 'kb', 'dataSourceId': 'ds', 'ingestionJobId': 'job'}
        class Agent:
            def get_ingestion_job(self, **kwargs):
                events.append('job')
                return {'ingestionJob': {'ingestionJobId': 'job', 'status': 'COMPLETE'}}
        class Runtime:
            def retrieve(self, **kwargs):
                events.append('retrieve')
                return {'retrievalResults': []}
        class Session:
            region_name = 'us-east-1'
            def client(self, name, **kwargs):
                events.append(name)
                return Agent() if name == 'bedrock-agent' else Runtime()
        fake_auth = types.SimpleNamespace(load_aws_session=lambda aws: (Session(), binding))
        with patch.dict(sys.modules, {'aws_auth': fake_auth}):
            namespace = {}
            exec(source, namespace)
            result = asyncio.run(namespace['search_current']('exercise', types.SimpleNamespace(query='question')))
        self.assertEqual(events, ['bedrock-agent', 'bedrock-agent-runtime', 'job', 'retrieve'])
        self.assertEqual(result['status'], 'ready')

    def test_p23_answer_matches_native_assembler(self):
        model = BASE / 'guided-labs/h23-model-call'
        tree = ast.parse((model / 'server.py').read_text())
        blocks = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'BLOCK_CODE' for t in node.targets))
        starter = (model / 'learner-starter.py').read_text()
        before, marker, remainder = starter.partition('    try:\n')
        _, ending, after = remainder.partition('    except (BotoCoreError, ClientError) as exc:')
        order = ('client', 'model_id', 'output_tokens', 'converse')
        lines = '\n\n'.join('\n'.join('        ' + line for line in blocks[key].splitlines()) for key in order)
        assembled = before + marker + lines + '\n' + ending + after
        self.assertEqual(assembled.strip(), fences(CONTROL / 'admin-answers/P23.md')[0])


if __name__ == '__main__':
    unittest.main()
