import json
import tempfile
import unittest
from pathlib import Path

from bitrix_agents.local_archive import LocalArchive
from bitrix_agents.workflow import LocalWorkflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = LocalArchive(Path(self.tmp.name) / 'db.sqlite3')
        self.addCleanup(self.db.close)
        with self.db.db:
            for task_id, scope, title, date in [
                ('1', 'portal/team', 'Нет доступа к отчету', '2025-01-01 10:00:00'),
                ('2', 'portal/other', 'Нет доступа к отчету', '2025-01-01 10:00:00'),
                ('3', 'portal/team', 'Нет доступа к отчету', '2025-03-01 10:00:00')]:
                self.db.db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (task_id, scope, title, 'Завершена', date, date, '', '',
                     json.dumps([{'ordinal': 1, 'created_at': date,
                                  'author': 'А', 'text': 'Выдали роль; помогло'}]), task_id+'hash'))
                self.db.db.execute('INSERT INTO task_search VALUES (?,?,?,?)',
                                   (task_id, title, '', ''))
        self.db.add_review('1', 1, 'Выдать роль', 'succeeded', 'Эксперт')
        self.db.add_review('1', 1, 'Перезапустить', 'failed', 'Эксперт')
        self.db.add_review('2', 1, 'Сменить пароль', 'succeeded', 'Эксперт')
        self.db.add_review('3', 1, 'Поздний совет', 'succeeded', 'Эксперт')

    def test_solution_only_uses_verified_current_past_scope(self):
        review_id = next(r['id'] for r in self.db.current_reviews('1') if r['action'] == 'Выдать роль')
        self.db.classify_review(review_id, 'solution', 'Эксперт')
        result = LocalWorkflow(self.db).solve('Нет доступа к отчету', 'portal/team',
                                               before='2025-02-01 00:00:00')
        self.assertEqual(result['status'], 'draft')
        self.assertEqual(result['actions'], ['Выдать роль'])
        self.assertEqual(result['sources'], ['task:1/comment:1'])
        self.assertEqual([x['agent'] for x in result['journal']], ['executor', 'analyst', 'executor'])

    def test_unknown_action_kind_is_not_reused(self):
        result = LocalWorkflow(self.db).solve('Нет доступа к отчету', 'portal/team',
                                              before='2025-02-01 00:00:00')
        self.assertEqual(result['status'], 'needs_information')

    def test_stale_review_is_not_reused(self):
        self.db.db.execute("UPDATE tasks SET content_hash='changed' WHERE id='1'")
        result = LocalWorkflow(self.db).solve('Нет доступа к отчету', 'portal/team',
                                               before='2025-02-01 00:00:00')
        self.assertEqual(result['status'], 'needs_information')

    def test_no_review_does_not_claim_success(self):
        result = LocalWorkflow(self.db).solve('Другая проблема', 'portal/team')
        self.assertEqual(result['status'], 'needs_information')


if __name__ == '__main__':
    unittest.main()
