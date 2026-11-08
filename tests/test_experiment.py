import json
import tempfile
import unittest
from pathlib import Path
from bitrix_agents.local_archive import LocalArchive
from bitrix_agents.experiment import evaluate


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = LocalArchive(Path(self.tmp.name) / 'db.sqlite3')
        self.addCleanup(self.archive.close)
        with self.archive.db:
            for task_id, created, status in [('1','2025-01-01','Завершена'),
                                             ('2','2025-01-02','Завершена'),
                                             ('3','2025-02-01','Завершена')]:
                self.archive.db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (task_id,'portal/team','Доступ к отчету',status,created,created,'','',
                     json.dumps([{'ordinal':1,'text':'Проверен результат'}]),task_id+'hash'))
                self.archive.db.execute('INSERT INTO task_search VALUES (?,?,?,?)',
                                        (task_id,'Доступ к отчету','',''))
        self.archive.add_review('1',1,'Перезапуск','failed','Эксперт')
        self.archive.add_review('2',1,'Выдать роль','succeeded','Эксперт')

    def test_temporal_split_and_success_filter(self):
        review_id = self.archive.current_reviews('2')[0]['id']
        self.archive.classify_review(review_id, 'solution', 'Эксперт')
        result = evaluate(self.archive,[{'id':'q1','query':'Доступ к отчету','scope':'portal/team',
            'created_at':'2025-01-15','relevant_task_ids':['2'],'forbidden_task_ids':['1']}], k=3)
        row = result['cases'][0]
        self.assertEqual(set(row['raw_ids']), {'1','2'})
        self.assertEqual(row['verified_ids'], ['2'])
        self.assertEqual(result['summary']['verified']['hit_at_k'], 1.0)
        self.assertEqual(result['summary']['verified']['forbidden_at_k'], 0.0)

    def test_unclassified_action_is_not_counted_as_verified(self):
        result = evaluate(self.archive,[{'id':'q1','query':'Доступ к отчету','scope':'portal/team',
            'created_at':'2025-01-15','relevant_task_ids':['2'],'forbidden_task_ids':[]}], k=3)
        self.assertEqual(result['cases'][0]['verified_ids'], [])

    def test_no_future_or_same_task_leakage(self):
        result = evaluate(self.archive,[{'id':'2','query':'Доступ к отчету','scope':'portal/team',
            'created_at':'2025-01-02','relevant_task_ids':[],'forbidden_task_ids':[]}], k=3)
        self.assertEqual(result['cases'][0]['raw_ids'], ['1'])
        self.assertEqual(result['cases'][0]['verified_ids'], [])

    def test_empty_cases_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.archive, [])


if __name__ == '__main__':
    unittest.main()
