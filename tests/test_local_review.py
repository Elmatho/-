import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from bitrix_agents.local_archive import LocalArchive


def archive(path, comment='Доступ восстановлен'):
    md = ('# Доступ к отчету\n- **Статус:** Завершена\n- **Группа:** Поддержка\n'
          '- **Ссылка:** https://example.test/tasks/1\n## Постановка задачи\nНет доступа.\n'
          '## Комментарии (1)\n### 2025-01-01 12:00:00 — Сотрудник\n\n' + comment + '\n')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('tasks/1/task.md', md)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.zip = Path(self.tmp.name) / 'tasks.zip'
        self.db = LocalArchive(Path(self.tmp.name) / 'tasks.sqlite3')
        self.addCleanup(self.db.close)
        archive(self.zip)
        self.db.import_zip(self.zip)

    def test_review_requires_existing_comment_and_explicit_outcome(self):
        with self.assertRaises(ValueError):
            self.db.add_review('1', 2, 'Выдать доступ', 'succeeded', 'Эксперт')
        with self.assertRaises(ValueError):
            self.db.add_review('1', 1, 'Выдать доступ', 'done', 'Эксперт')
        self.assertEqual(self.db.review_stats()['current'], 0)

    def test_review_persists_and_source_change_invalidates_it(self):
        self.db.add_review('1', 1, 'Проверить роль', 'succeeded', 'Эксперт')
        self.assertEqual(self.db.review_stats()['current'], 1)
        self.assertEqual(len(self.db.current_reviews('1')), 1)
        archive(self.zip, 'После проверки роль не помогла')
        self.db.import_zip(self.zip)
        self.assertEqual(self.db.review_stats()['current'], 0)
        self.assertEqual(self.db.current_reviews('1'), [])
        self.assertEqual(self.db.review_stats()['stale'], 1)

    def test_completed_task_is_not_automatically_reviewed(self):
        self.assertEqual(self.db.get_task('1')['status'], 'Завершена')
        self.assertEqual(self.db.current_reviews('1'), [])

    def test_action_kind_requires_separate_review_and_stale_source_is_rejected(self):
        self.db.add_review('1', 1, 'Исправили права, доступ восстановлен',
                           'succeeded', 'Эксперт')
        review = self.db.current_reviews('1')[0]
        self.assertEqual(review['kind'], 'unknown')
        with self.assertRaises(ValueError):
            self.db.classify_review(review['id'], 'successful', 'Эксперт')
        self.db.classify_review(review['id'], 'solution', 'Эксперт')
        self.assertEqual(self.db.current_reviews('1')[0]['kind'], 'solution')
        archive(self.zip, 'Исходный комментарий изменён')
        self.db.import_zip(self.zip)
        with self.assertRaises(ValueError):
            self.db.classify_review(review['id'], 'solution', 'Эксперт')

    def test_existing_database_gets_action_kind_column(self):
        path = Path(self.tmp.name) / 'old.sqlite3'
        db = sqlite3.connect(path)
        db.execute('''CREATE TABLE reviews (id INTEGER PRIMARY KEY, task_id TEXT,
            source_hash TEXT, comment_ordinal INTEGER, action TEXT, outcome TEXT,
            reviewer TEXT, reviewed_at TEXT)''')
        db.close()
        upgraded = LocalArchive(path)
        try:
            columns = {row[1] for row in upgraded.db.execute('PRAGMA table_info(reviews)')}
            self.assertTrue({'kind', 'kind_reviewer', 'kind_reviewed_at'} <= columns)
        finally:
            upgraded.close()


if __name__ == '__main__':
    unittest.main()
