"""Создание локального листа слепой оценки ответов трёх методов."""
import json
import random
from pathlib import Path


def create_blind_sheet(archive, results_dir, output_dir, seed=17):
    results = []
    for path in sorted(Path(results_dir).glob('*.json')):
        if path.name.endswith('.partial.json'):
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(record, dict) and {'task_id', 'answers'} <= record.keys():
            results.append(record)
    if not results:
        raise ValueError('Не найдены результаты прототипа')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    lines = ['# Слепая оценка ответов', '',
             'Оцените ответы по исходным условиям контрольной задачи, не зная метода.',
             '0 — неверно, 1 — частично верно, 2 — верно. Отдельно отметьте',
             'неподтверждённые факты и применимость решения. Не подглядывайте в ключ.', '']
    key = {}
    items = []
    for record in results:
        task = archive.get_task(record['task_id'])
        lines += [f"## Контрольная задача {task['id']}", '', task['title'], '',
                  task['description'], '']
        variants = list(record['answers'].items())
        rng.shuffle(variants)
        key[task['id']] = {}
        for letter, (method, value) in zip('ABC', variants):
            key[task['id']][letter] = method
            items.append({'task_id': str(task['id']), 'title': task['title'],
                          'description': task['description'], 'letter': letter,
                          'answer': value['answer'] or '(нет ответа)'})
            lines += [f'### Ответ {letter}', '', value['answer'] or '(нет ответа)', '',
                      'Оценка 0/1/2: ___   Неподтверждённые факты да/нет: ___',
                      'Применимо да/нет/неясно: ___   Обоснование: ___', '']
    items_file = output / 'blind_items.json'
    ratings_file = output / 'blind_ratings.json'
    if ratings_file.exists() and items_file.exists():
        previous = json.loads(items_file.read_text(encoding='utf-8'))
        if previous != items:
            raise ValueError('Ответы изменились после начала оценки; сохраните прежнюю разметку отдельно')
    items_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    sheet = output / 'blind_review.md'
    sheet.write_text('\n'.join(lines), encoding='utf-8')
    (output / 'method_key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
    return sheet
