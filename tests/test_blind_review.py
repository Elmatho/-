import json
import tempfile
import unittest
from pathlib import Path
from bitrix_agents.blind_review import create_blind_sheet


class ArchiveStub:
    def get_task(self, task_id):
        return {'id': task_id, 'title': 'Тестовая задача', 'description': 'Описание'}


class BlindReviewTests(unittest.TestCase):
    def test_ignores_manifest_and_log_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'control_ids.json').write_text('{"task_ids":["1"]}', encoding='utf-8')
            (root / 'run_log.json').write_text('[]', encoding='utf-8')
            (root / '1.json').write_text(json.dumps({
                'task_id': '1', 'answers': {'raw': {'answer': 'Ответ 1'},
                'summary': {'answer': 'Ответ 2'},
                'verified_memory': {'answer': 'Ответ 3'}}}), encoding='utf-8')
            sheet = create_blind_sheet(ArchiveStub(), root, root)
            self.assertIn('Тестовая задача', sheet.read_text(encoding='utf-8'))
            items = json.loads((root / 'blind_items.json').read_text(encoding='utf-8'))
            self.assertEqual(len(items), 3)
            self.assertEqual({item['letter'] for item in items}, {'A', 'B', 'C'})
            self.assertTrue(all(set(item) == {'task_id', 'title', 'description', 'letter', 'answer'}
                                for item in items))


if __name__ == '__main__':
    unittest.main()
