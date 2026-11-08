"""Черновая разметка реальных задач моделью без автоматического подтверждения."""
from .core import Analyst, Comment, Memory, Task
from .prototype import redact
from pathlib import Path


def propose_actions(archive, model, task_id):
    original = archive.get_task(task_id)
    if not original['comments']:
        raise ValueError('Нет комментариев для разметки')
    # Авторы, ссылки и вложения не входят в запрос к модели.
    task = Task(original['id'], original['scope'], redact(original['title']),
                tuple(Comment(str(c['ordinal']), redact(c['text'])[:3000])
                      for c in original['comments']))
    case = Analyst(Memory(), model).learn(task)
    if not case.actions:
        return {'task_id':task_id,'draft_count':0}
    with archive.db:
        archive.db.execute('DELETE FROM draft_actions WHERE task_id=? AND source_hash=?',
                           (original['id'], original['content_hash']))
        for action in case.actions:
            ordinal = int(action.source.split(':', 1)[1])
            archive.db.execute('''INSERT INTO draft_actions
                (task_id,source_hash,comment_ordinal,action,outcome,model_uri)
                VALUES (?,?,?,?,?,?)''',
                (original['id'],original['content_hash'],ordinal,
                 action.text,action.status,model.model_uri))
    return {'task_id':task_id,'draft_count':len(case.actions)}


def write_review_packet(archive, task_ids, path):
    """Локальный лист сверки черновиков с полным контекстом исходных комментариев."""
    lines = ['# Проверка разметки опыта', '',
             'Черновики предложены моделью. Отметьте только те действия и исходы,',
             'которые подтверждаются историей задачи. Номер комментария — локальный.', '']
    for task_id in task_ids:
        task = archive.get_task(task_id)
        lines += [f"## Задача {task_id}", '', task['title'], '',
                  'Описание:', task['description'], '', '### Комментарии', '']
        for comment in task['comments']:
            lines += [f"**{comment['ordinal']}. {comment['created_at']} — {comment['author']}**",
                      comment['text'], '']
        lines += ['### Предложения модели', '']
        for draft in archive.draft_actions(task_id):
            lines += [f"- [ ] Черновик {draft['id']}: {draft['action']} — "
                      f"{draft['outcome']} (комментарий {draft['comment_ordinal']})", '']
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
    return output
