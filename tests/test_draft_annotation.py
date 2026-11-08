import json
import tempfile
import unittest
from pathlib import Path
from bitrix_agents.local_archive import LocalArchive
from bitrix_agents.draft_annotation import propose_actions


class DraftAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = LocalArchive(Path(self.tmp.name) / 'db.sqlite3')
        self.addCleanup(self.db.close)
        with self.db.db:
            self.db.db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)',
                ('1','portal/team','Нет доступа','Завершена','2025-01-01','2025-01-02',
                 '', 'Описание', json.dumps([{'ordinal':1,'text':'Исправили права'}]), 'hash1'))

    def test_draft_is_not_verified(self):
        class Model:
            model_uri = 'test'
            def extract(self, task):
                return {'problem':task.title, 'sources':['comment:1'],
                        'actions':[{'text':'Проверить права','status':'succeeded',
                                    'source':'comment:1'}]}
        result = propose_actions(self.db, Model(), '1')
        self.assertEqual(result['draft_count'],1)
        self.assertEqual(self.db.review_stats()['current'],0)
        self.assertEqual(self.db.current_reviews('1'),[])
        draft = self.db.draft_actions('1')[0]
        self.db.approve_draft(draft['id'], 'Эксперт')
        self.assertEqual(self.db.review_stats()['current'],1)
        self.assertEqual(self.db.current_reviews('1')[0]['kind'], 'unknown')

    def test_stale_draft_cannot_be_approved(self):
        class Model:
            model_uri = 'test'
            def extract(self, task):
                return {'problem':task.title, 'sources':['comment:1'],
                        'actions':[{'text':'Проверить права','status':'succeeded',
                                    'source':'comment:1'}]}
        propose_actions(self.db, Model(), '1')
        draft_id = self.db.draft_actions('1')[0]['id']
        self.db.db.execute("UPDATE tasks SET content_hash='changed' WHERE id='1'")
        with self.assertRaises(ValueError):
            self.db.approve_draft(draft_id, 'Эксперт')

    def test_unknown_comment_is_rejected(self):
        class Model:
            model_uri = 'test'
            def extract(self, task):
                return {'problem':task.title,'sources':['comment:99'],
                        'actions':[{'text':'Выдать роль','status':'succeeded',
                                    'source':'comment:99'}]}
        with self.assertRaises(ValueError):
            propose_actions(self.db, Model(), '1')
        self.assertEqual(self.db.draft_actions('1'),[])
