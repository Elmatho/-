import unittest

from bitrix_agents.core import Analyst, Executor, Memory, Orchestrator, Task
from bitrix_agents.demo import DemoModel, history


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.analyst = Analyst(self.memory, DemoModel())
        self.case = self.analyst.learn(history())
        self.system = Orchestrator(self.analyst, Executor())
        self.task = Task('new', 'demo/support', 'Нет доступа к отчету', ())

    def test_unverified_case_does_not_become_solution(self):
        self.assertEqual(self.system.solve(self.task).status, 'needs_information')

    def test_reviewed_case_returns_draft_and_sources(self):
        self.memory.review(self.case.key, 'teacher', True)
        result = self.system.solve(self.task)
        self.assertEqual(result.status, 'draft')
        self.assertIn('comment:3', result.sources)
        self.assertEqual([e['agent'] for e in self.system.journal], ['executor', 'analyst', 'executor'])

    def test_other_scope_cannot_read_case(self):
        self.memory.review(self.case.key, 'teacher', True)
        other = Task('new', 'other/team', self.task.title, ())
        self.assertEqual(self.system.solve(other).status, 'needs_information')

    def test_changed_source_invalidates_review(self):
        self.memory.review(self.case.key, 'teacher', True)
        original = history()
        self.analyst.learn(Task(original.id, original.scope, original.title + ' изменено', original.comments))
        self.assertEqual(self.memory.cases[self.case.key].trust, 'unverified')

    def test_unchanged_source_preserves_review(self):
        self.memory.review(self.case.key, 'teacher', True)
        self.analyst.learn(history())
        self.assertEqual(len(self.memory.cases), 1)
        self.assertEqual(self.memory.cases[self.case.key].trust, 'verified')

    def test_fabricated_source_rejected(self):
        class InvalidModel(DemoModel):
            def extract(self, task):
                result = super().extract(task)
                result['sources'] = ['comment:999']
                return result
        with self.assertRaises(ValueError):
            Analyst(Memory(), InvalidModel()).learn(history())

    def test_failed_action_excluded(self):
        self.memory.review(self.case.key, 'teacher', True)
        result = self.system.solve(self.task)
        self.assertNotIn('Перезапустить', result.text)


if __name__ == '__main__':
    unittest.main()
