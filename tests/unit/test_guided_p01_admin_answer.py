"""Keep the Gateway admin answer identical to the code built from answer blocks."""

import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "llm-security-control-plane/guided-control-center"


class P01AdminAnswerTest(unittest.TestCase):
    def test_admin_code_matches_answer_blocks_and_starter(self):
        spec = importlib.util.spec_from_file_location("guided_block_submission", CONTROL / "block_submission.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        starter = ROOT / "llm-security-control-plane/guided-labs/h01-bedrock-gateway/learner.py"
        with tempfile.TemporaryDirectory() as temporary:
            source_dir = Path(temporary) / "block-starters"
            source_dir.mkdir()
            shutil.copyfile(starter, source_dir / "P01.py")
            with patch.object(module, "ROOT", Path(temporary)):
                assembled = module.assemble("P01", [
                    "cap:limit", "reserve:reserve", "call:model", "settle:settle",
                ])
        answer = (CONTROL / "admin-answers/P01.md").read_text(encoding="utf-8")
        fence = re.search(r"```python\n(.*?)\n```", answer, re.DOTALL)
        self.assertIsNotNone(fence)
        self.assertEqual(assembled.strip(), fence.group(1).strip())


if __name__ == "__main__":
    unittest.main()
