import json
import tempfile
import unittest
from pathlib import Path

from bitrix_agents.review_gui import load_items, load_ratings, save_rating


class ReviewGuiTests(unittest.TestCase):
    def test_save_and_resume_without_method_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'blind_items.json').write_text(json.dumps([
                {'task_id': '1', 'title': 'Задача', 'description': 'Описание',
                 'letter': 'A', 'answer': 'Черновик'}], ensure_ascii=False), encoding='utf-8')
            (root / 'method_key.json').write_text('{"1":{"A":"raw"}}', encoding='utf-8')
            item = load_items(root)[0]
            save_rating(root, item, 2, False, 'да', 'Действие подтверждено')
            rating = load_ratings(root)['1:A']
            self.assertEqual(rating['score'], 2)
            self.assertEqual(rating['rationale'], 'Действие подтверждено')
            self.assertNotIn('raw', json.dumps(rating))

    def test_rejects_incomplete_rating(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            item = {'task_id': '1', 'letter': 'A'}
            with self.assertRaises(ValueError):
                save_rating(root, item, 3, False, 'да', 'Причина')
            with self.assertRaises(ValueError):
                save_rating(root, item, 1, False, 'да', '')


if __name__ == '__main__':
    unittest.main()
