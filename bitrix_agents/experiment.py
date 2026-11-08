"""Локальная оценка поиска по размеченным контрольным задачам."""
import re


def _candidates(archive, query, scope, created_at, exclude_id, limit):
    words = re.findall(r'\w+', query, flags=re.UNICODE)[:20]
    if not words:
        return []
    expression = ' OR '.join('"' + word + '"' for word in words)
    return [row[0] for row in archive.db.execute('''
        SELECT t.id FROM task_search s JOIN tasks t ON t.id=s.task_id
        WHERE task_search MATCH ? AND t.scope=? AND t.created_at<?
          AND t.completed_at!='' AND t.completed_at<? AND t.id<>?
        ORDER BY bm25(task_search) LIMIT ?''',
        (expression, scope, created_at, created_at, str(exclude_id), limit))]


def _score(rows, field):
    total = len(rows)
    return {
        'hit_at_k': sum(bool(set(row[field]) & set(row['relevant_task_ids'])) for row in rows) / total,
        'forbidden_at_k': sum(bool(set(row[field]) & set(row['forbidden_task_ids'])) for row in rows) / total,
        'abstention_rate': sum(not row[field] for row in rows) / total,
    }


def evaluate(archive, cases, k=5):
    """Сравнить текстовый поиск и отбор подтверждённо успешных прошлых задач.

    Контрольные метки задаёт эксперт. Запросу доступны только более ранние задачи.
    Метрики описывают поиск источника, не качество финального ответа агента.
    """
    if not cases or not 1 <= k <= 100:
        raise ValueError('Нужен хотя бы один тестовый случай и k от 1 до 100')
    rows = []
    for case in cases:
        required = {'id','query','scope','created_at','relevant_task_ids','forbidden_task_ids'}
        if not isinstance(case, dict) or not required <= case.keys():
            raise ValueError('Неверный формат тестового случая')
        raw = _candidates(archive, case['query'], case['scope'], case['created_at'], case['id'], k)
        # Берём тот же лексический ранг; меняется только допуск подтверждённого опыта.
        pool = _candidates(archive, case['query'], case['scope'], case['created_at'], case['id'], 100)
        verified = [task_id for task_id in pool
                    if any(r['outcome'] == 'succeeded' and r.get('kind') == 'solution'
                           for r in archive.current_reviews(task_id))][:k]
        rows.append({'id': case['id'], 'raw_ids': raw, 'verified_ids': verified,
                     'relevant_task_ids': case['relevant_task_ids'],
                     'forbidden_task_ids': case['forbidden_task_ids']})
    return {'n': len(rows), 'k': k,
            'summary': {'raw': _score(rows, 'raw_ids'),
                        'verified': _score(rows, 'verified_ids')},
            'cases': rows}
