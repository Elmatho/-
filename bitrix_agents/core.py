"""Структуры данных, память и взаимодействие двух агентов без внешних библиотек."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Protocol


@dataclass(frozen=True)
class Comment:
    """Исходный комментарий сотрудника; ID позволяет сослаться на доказательство."""
    id: str
    text: str


@dataclass(frozen=True)
class Task:
    """Задача и её обсуждение, полученные из одного портала и группы."""
    id: str
    scope: str  # Портал/группа: значение должен назначать доверенный коннектор.
    title: str
    comments: tuple[Comment, ...]


@dataclass(frozen=True)
class Action:
    """Действие из истории задачи со статусом результата и ссылкой на комментарий."""
    text: str
    status: str  # proposed — предложено; succeeded — помогло; failed — не помогло.
    source: str


@dataclass(frozen=True)
class Case:
    """Карточка опыта: ключ (область, ID задачи), версия источника и результат проверки."""
    key: tuple[str, str]
    fingerprint: str
    problem: str
    actions: tuple[Action, ...]
    sources: tuple[str, ...]
    trust: str = 'unverified'
    reviewer: str = ''


@dataclass(frozen=True)
class Solution:
    """Черновик решения или запрос уточнений; сам по себе не означает выполнение задачи."""
    status: str
    text: str
    sources: tuple[str, ...] = ()


class ExtractionModel(Protocol):
    def extract(self, task: Task) -> dict:
        """Вернуть проблему, действия [{text, status, source}] и список источников.

        Комментарии сотрудников — данные, а не системные инструкции.
        Реальный адаптер модели должен проверять структуру JSON и обрабатывать ошибки.
        """
        ...


class TaskSource(Protocol):
    def completed_tasks(self, scope: str) -> list[Task]:
        """Прочитать задачи и комментарии из разрешённого портала/группы."""
        ...


class Memory:
    """Память в оперативной памяти: после завершения программы карточки исчезают."""
    def __init__(self):
        self.cases: dict[tuple[str, str], Case] = {}

    def review(self, key: tuple[str, str], reviewer: str, approved: bool):
        """Зафиксировать решение проверяющего; аутентификация пока не реализована."""
        from dataclasses import replace
        if not reviewer.strip():
            raise ValueError('Reviewer is required')
        self.cases[key] = replace(self.cases[key],
                                  trust='verified' if approved else 'rejected',
                                  reviewer=reviewer)

    def search(self, task: Task, limit: int = 3) -> list[Case]:
        """Найти подтверждённый опыт по общим словам, без семантического поиска."""
        def tokens(text):
            return set(re.findall(r'\w+', text.casefold()))
        query = tokens(task.title)
        candidates = []
        for case in self.cases.values():
            # Чужая область и неподтверждённый опыт не передаются исполнителю.
            if case.key[0] != task.scope or case.trust != 'verified':
                continue
            score = len(query & tokens(case.problem))
            if score:
                candidates.append((score, case))
        return [case for _, case in sorted(candidates, key=lambda x: -x[0])[:limit]]


class Analyst:
    """Первый агент: извлекает опыт из истории и отвечает на запросы исполнителя."""
    def __init__(self, memory: Memory, model: ExtractionModel):
        self.memory, self.model = memory, model

    def learn(self, task: Task) -> Case:
        # Хеш позволяет заметить изменения задачи и не анализировать дубликат повторно.
        fingerprint = hashlib.sha256(json.dumps(asdict(task), sort_keys=True,
                                               ensure_ascii=False).encode()).hexdigest()
        key = (task.scope, task.id)
        previous = self.memory.cases.get(key)
        if previous and previous.fingerprint == fingerprint:
            return previous
        # Удаляем старое подтверждение до анализа: при ошибке модели оно не восстановится.
        self.memory.cases.pop(key, None)
        payload = self.model.extract(task)
        valid_sources = {f'comment:{c.id}' for c in task.comments}
        # Проверяем наличие источников, но не смысловую истинность выводов модели.
        sources = payload['sources']
        if not sources or not set(sources) <= valid_sources:
            raise ValueError('Unknown or empty evidence references')
        actions = tuple(Action(**a) for a in payload['actions'])
        if not isinstance(payload['problem'], str) or not payload['problem'].strip():
            raise ValueError('Problem must be nonempty text')
        for action in actions:
            if action.status not in {'proposed', 'succeeded', 'failed'}:
                raise ValueError('Invalid action status')
            if action.source not in sources or not isinstance(action.text, str) or not action.text.strip():
                raise ValueError('Action requires text and evidence')
        case = Case(key, fingerprint, payload['problem'], actions, tuple(sources))
        self.memory.cases[key] = case
        return case

    def retrieve(self, task: Task) -> list[Case]:
        return self.memory.search(task)


class Executor:
    """Второй агент: базовая сборка черновика без LLM, на основе успешных действий."""
    def solve(self, task: Task, cases: list[Case]) -> Solution:
        eligible = [c for c in cases if c.trust == 'verified' and c.key[0] == task.scope]
        for case in eligible:
            successful = [a for a in case.actions if a.status == 'succeeded']
            if successful:
                text = 'Черновик по похожей задаче. Проверьте применимость условий:\n'
                text += '\n'.join(f'{i}. {a.text}' for i, a in enumerate(successful, 1))
                text += '\nПосле выполнения проверьте результат. Действия автоматически не выполнены.'
                return Solution('draft', text, tuple(a.source for a in successful))
        return Solution('needs_information',
                        'Подтверждённого решения не найдено. Уточните условия задачи и обратитесь к специалисту.')


class Orchestrator:
    """Координатор: передаёт запрос аналитику, опыт исполнителю и сохраняет журнал."""
    def __init__(self, analyst: Analyst, executor: Executor):
        self.analyst, self.executor = analyst, executor
        self.journal: list[dict] = []

    def solve(self, task: Task) -> Solution:
        # Один запрос к аналитику. Журнал не становится подтверждённым опытом автоматически.
        self.journal.append({'agent': 'executor', 'event': 'request_experience', 'task': task.id})
        cases = self.analyst.retrieve(task)
        self.journal.append({'agent': 'analyst', 'event': 'return_experience',
                             'cases': [list(c.key) for c in cases]})
        result = self.executor.solve(task, cases)
        self.journal.append({'agent': 'executor', 'event': 'draft_solution', 'status': result.status})
        return result
