"""Локальное взаимодействие аналитика и исполнителя на проверенной памяти."""
from datetime import datetime
from .experiment import _candidates


class LocalWorkflow:
    """Составляет проверяемый черновик без отправки корпоративных данных в сеть."""
    def __init__(self, archive):
        self.archive = archive

    def solve(self, query, scope, before=None, limit=3):
        if not query.strip() or not scope.strip():
            raise ValueError('Укажите задачу и область доступа')
        if not 1 <= limit <= 10:
            raise ValueError('limit должен быть от 1 до 10')
        before = before or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        journal = [{'agent': 'executor', 'event': 'request_experience', 'query': query}]
        candidate_ids = _candidates(self.archive, query, scope, before, '', 100)
        evidence = []
        for task_id in candidate_ids:
            task = self.archive.get_task(task_id)
            comments = {c['ordinal']: c for c in task['comments']}
            successful = [r for r in self.archive.current_reviews(task_id)
                          if r['outcome'] == 'succeeded' and r.get('kind') == 'solution'
                          and r['comment_ordinal'] in comments]
            for review in successful:
                evidence.append({'action': review['action'], 'source':
                                 f"task:{task_id}/comment:{review['comment_ordinal']}",
                                 'task_title': task['title'], 'task_url': task['url'],
                                 'source_timestamp': comments[review['comment_ordinal']]['created_at'],
                                 'reviewer': review['reviewer']})
            if len(evidence) >= limit:
                break
        evidence = evidence[:limit]
        journal.append({'agent': 'analyst', 'event': 'return_experience',
                        'source_ids': [e['source'] for e in evidence]})
        if evidence:
            actions = list(dict.fromkeys(e['action'] for e in evidence))
            text = ('Проверьте применимость условий похожих задач. Возможные действия:\n' +
                    '\n'.join(f'{i}. {action}' for i, action in enumerate(actions, 1)) +
                    '\nЭто черновик; действия ещё не выполнены.')
            status = 'draft'
        else:
            actions = []
            text = 'Нет подходящего подтверждённого опыта. Уточните условия и обратитесь к специалисту.'
            status = 'needs_information'
        journal.append({'agent': 'executor', 'event': 'draft_solution', 'status': status})
        return {'status': status, 'text': text, 'actions': actions,
                'sources': [e['source'] for e in evidence], 'evidence': evidence,
                'journal': journal}
