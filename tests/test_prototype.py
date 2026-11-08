import unittest
import json
import tempfile
from pathlib import Path
from bitrix_agents.prototype import redact, select_context, verified_context, run_prototype


class PrototypeTests(unittest.TestCase):
    def test_redact_removes_direct_contacts(self):
        cleaned = redact('Пишите на person@example.org, звоните +7 999 123 45 67. https://corp.test/22')
        self.assertNotIn('person@example.org', cleaned)
        self.assertNotIn('999 123', cleaned)
        self.assertNotIn('corp.test', cleaned)

    def test_context_omits_comment_authors(self):
        task = {'title': 'Проблема', 'description': 'Описание',
                'comments': [{'ordinal': 1, 'author': 'Сотрудник', 'text': 'Проверено'}]}
        self.assertNotIn('Сотрудник', select_context(task))

    def test_verified_context_excludes_administrative_and_unknown_actions(self):
        class Archive:
            def current_reviews(self, task_id):
                return [
                    {'outcome': 'succeeded', 'kind': 'administrative',
                     'action': 'Назначение исполнителя', 'comment_ordinal': 1},
                    {'outcome': 'succeeded', 'kind': 'unknown',
                     'action': 'Завершение задачи', 'comment_ordinal': 2},
                    {'outcome': 'failed', 'kind': 'solution',
                     'action': 'Перезапуск не помог', 'comment_ordinal': 3},
                    {'outcome': 'succeeded', 'kind': 'solution',
                     'action': 'Исправили права, доступ восстановлен', 'comment_ordinal': 4},
                ]

        result = verified_context(Archive(), [{'id': '11'}])
        self.assertIn('Исправили права', result)
        self.assertNotIn('Назначение', result)
        self.assertNotIn('Завершение', result)
        self.assertNotIn('Перезапуск', result)

    def test_old_checkpoint_is_not_reused_after_method_change(self):
        class Model:
            model_uri = 'gpt://test/model'

        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '1.json').write_text(json.dumps({'task_id': '1',
                'model_uri': 'gpt://test/model', 'answers': {}}), encoding='utf-8')
            with self.assertRaises(ValueError):
                run_prototype(None, Model(), ['1'], folder)


if __name__ == '__main__':
    unittest.main()
