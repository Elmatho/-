"""Локальный импорт выгрузки Битрикс24 и поиск без сетевых запросов."""
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


TASK_PATH = re.compile(r'^tasks/(\d+)/task\.md$')
COMMENT_HEADING = re.compile(r'^### (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+[—-]\s+(.+)$')


@contextmanager
def _task_archives(path):
    """Принять исходный ZIP с вложенным ZIP либо прямую выгрузку задач."""
    with zipfile.ZipFile(path) as outer:
        if any(TASK_PATH.fullmatch(n) for n in outer.namelist()):
            yield outer
            return
        nested = [n for n in outer.namelist() if n.lower().endswith('.zip')]
        if len(nested) != 1:
            raise ValueError('Ожидался архив задач или один вложенный ZIP с tasks/*/task.md')
        with zipfile.ZipFile(io.BytesIO(outer.read(nested[0]))) as inner:
            yield inner


def parse_task(text, path):
    """Разобрать Markdown из архива; ID берём из пути, а не из текста задачи."""
    match = TASK_PATH.fullmatch(path)
    if not match:
        raise ValueError('Неверный путь задачи')
    lines = text.splitlines()
    title = lines[0][2:].strip() if lines and lines[0].startswith('# ') else ''
    metadata = {}
    for line in lines:
        m = re.match(r'^- \*\*(.+?):\*\*\s*(.*)$', line)
        if m:
            metadata[m.group(1)] = m.group(2)
    start = next((i for i, line in enumerate(lines) if line == '## Постановка задачи'), None)
    comments_start = next((i for i, line in enumerate(lines) if line.startswith('## Комментарии')), len(lines))
    if not title or start is None:
        raise ValueError(f'В {path} нет заголовка или постановки задачи')
    description = '\n'.join(lines[start + 1:comments_start]).strip()
    comments = []
    current = None
    for line in lines[comments_start + 1:]:
        m = COMMENT_HEADING.match(line)
        if m:
            if current:
                current['text'] = '\n'.join(current['lines']).strip()
                del current['lines']
                comments.append(current)
            current = {'ordinal': len(comments) + 1, 'created_at': m.group(1),
                       'author': m.group(2).strip(), 'lines': []}
        elif current:
            current['lines'].append(line)
    if current:
        current['text'] = '\n'.join(current['lines']).strip()
        del current['lines']
        comments.append(current)
    portal = urlparse(metadata.get('Ссылка', '')).hostname or 'unknown-portal'
    return {'id': match.group(1), 'scope': portal + '/' + metadata.get('Группа', '').strip(),
            'title': title, 'status': metadata.get('Статус', ''),
            'created_at': metadata.get('Создана', ''), 'completed_at': metadata.get('Завершена', ''),
            'url': metadata.get('Ссылка', ''), 'description': description, 'comments': comments}


class LocalArchive:
    """Постоянное хранилище. Содержимое и индекс остаются в локальном файле SQLite."""
    def __init__(self, database):
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, title TEXT NOT NULL,
                status TEXT, created_at TEXT, completed_at TEXT, url TEXT,
                description TEXT, comments_json TEXT NOT NULL, content_hash TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS task_search USING fts5(
                task_id UNINDEXED, title, description, comments_text, tokenize='unicode61'
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, source_hash TEXT NOT NULL,
                comment_ordinal INTEGER NOT NULL, action TEXT NOT NULL,
                outcome TEXT NOT NULL, reviewer TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'unknown',
                kind_reviewer TEXT NOT NULL DEFAULT '', kind_reviewed_at TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS draft_actions (
                id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, source_hash TEXT NOT NULL,
                comment_ordinal INTEGER NOT NULL, action TEXT NOT NULL,
                outcome TEXT NOT NULL, model_uri TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
        ''')
        # Старые базы получают новые поля без изменения исходной разметки.
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(reviews)')}
        for name, declaration in (
                ('kind', "TEXT NOT NULL DEFAULT 'unknown'"),
                ('kind_reviewer', "TEXT NOT NULL DEFAULT ''"),
                ('kind_reviewed_at', "TEXT NOT NULL DEFAULT ''")):
            if name not in columns:
                self.db.execute(f'ALTER TABLE reviews ADD COLUMN {name} {declaration}')

    def close(self):
        self.db.close()

    def import_zip(self, path):
        added = updated = unchanged = 0
        with _task_archives(path) as archive, self.db:
            for info in archive.infolist():
                if not TASK_PATH.fullmatch(info.filename):
                    continue  # Вложения не распаковываем и в API не отправляем.
                raw = archive.read(info).decode('utf-8-sig')
                task = parse_task(raw, info.filename)
                digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                old = self.db.execute('SELECT content_hash FROM tasks WHERE id=?', (task['id'],)).fetchone()
                if old and old[0] == digest:
                    unchanged += 1
                    continue
                self.db.execute('''INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET scope=excluded.scope, title=excluded.title,
                    status=excluded.status, created_at=excluded.created_at,
                    completed_at=excluded.completed_at, url=excluded.url,
                    description=excluded.description, comments_json=excluded.comments_json,
                    content_hash=excluded.content_hash''',
                    (task['id'], task['scope'], task['title'], task['status'], task['created_at'],
                     task['completed_at'], task['url'], task['description'],
                     json.dumps(task['comments'], ensure_ascii=False), digest))
                self.db.execute('DELETE FROM task_search WHERE task_id=?', (task['id'],))
                self.db.execute('INSERT INTO task_search VALUES (?,?,?,?)',
                                (task['id'], task['title'], task['description'],
                                 '\n'.join(c['text'] for c in task['comments'])))
                updated += bool(old)
                added += not bool(old)
        return {'added': added, 'updated': updated, 'unchanged': unchanged}

    def stats(self):
        rows = self.db.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status ORDER BY COUNT(*) DESC').fetchall()
        return {'tasks': sum(count for _, count in rows), 'statuses': dict(rows)}

    def get_task(self, task_id):
        row = self.db.execute('''SELECT id,scope,title,status,created_at,completed_at,url,
                                description,comments_json,content_hash FROM tasks WHERE id=?''',
                              (str(task_id),)).fetchone()
        if row is None:
            raise ValueError('Задача не найдена')
        data = dict(zip(('id','scope','title','status','created_at','completed_at','url',
                         'description','comments','content_hash'), row))
        data['comments'] = json.loads(data['comments'])
        return data

    def add_review(self, task_id, comment_ordinal, action, outcome, reviewer):
        """Сохранить решение проверяющего с привязкой к версии исходной задачи."""
        task = self.get_task(task_id)
        if outcome not in {'proposed', 'succeeded', 'failed', 'unknown'}:
            raise ValueError('Итог: proposed, succeeded, failed или unknown')
        if not action.strip() or not reviewer.strip():
            raise ValueError('Укажите действие и имя проверяющего')
        try:
            ordinal = int(comment_ordinal)
        except (ValueError, TypeError):
            raise ValueError('Укажите номер комментария') from None
        if ordinal not in {c['ordinal'] for c in task['comments']}:
            raise ValueError('Указанного комментария нет в задаче')
        with self.db:
            self.db.execute('''INSERT INTO reviews(task_id,source_hash,comment_ordinal,
                               action,outcome,reviewer) VALUES (?,?,?,?,?,?)''',
                            (task['id'], task['content_hash'], ordinal,
                             action.strip(), outcome, reviewer.strip()))

    def current_reviews(self, task_id):
        task = self.get_task(task_id)
        rows = self.db.execute('''SELECT id,comment_ordinal,action,outcome,reviewer,reviewed_at,
                                  kind,kind_reviewer,kind_reviewed_at
                                  FROM reviews WHERE task_id=? AND source_hash=? ORDER BY id''',
                               (task['id'], task['content_hash'])).fetchall()
        return [dict(zip(('id','comment_ordinal','action','outcome','reviewer','reviewed_at',
                          'kind','kind_reviewer','kind_reviewed_at'), row))
                for row in rows]

    def classify_review(self, review_id, kind, reviewer):
        """Отдельно подтвердить, является ли действие решением проблемы."""
        if kind not in {'solution', 'administrative', 'unknown'}:
            raise ValueError('Тип действия: solution, administrative или unknown')
        if not reviewer or not reviewer.strip():
            raise ValueError('Укажите проверяющего')
        row = self.db.execute('''SELECT r.source_hash,t.content_hash FROM reviews r
            JOIN tasks t ON t.id=r.task_id WHERE r.id=?''', (review_id,)).fetchone()
        if row is None or row[0] != row[1]:
            raise ValueError('Разметка не найдена или исходная задача изменилась')
        with self.db:
            self.db.execute('''UPDATE reviews SET kind=?,kind_reviewer=?,
                kind_reviewed_at=CURRENT_TIMESTAMP WHERE id=?''',
                (kind, reviewer.strip(), review_id))

    def review_stats(self):
        current = self.db.execute('''SELECT COUNT(*) FROM reviews r JOIN tasks t ON t.id=r.task_id
                                     WHERE r.source_hash=t.content_hash''').fetchone()[0]
        stale = self.db.execute('''SELECT COUNT(*) FROM reviews r JOIN tasks t ON t.id=r.task_id
                                   WHERE r.source_hash!=t.content_hash''').fetchone()[0]
        return {'current': current, 'stale': stale}

    def draft_actions(self, task_id):
        task = self.get_task(task_id)
        rows = self.db.execute('''SELECT id,comment_ordinal,action,outcome,model_uri,created_at
            FROM draft_actions WHERE task_id=? AND source_hash=? ORDER BY id''',
            (task['id'], task['content_hash'])).fetchall()
        return [dict(zip(('id','comment_ordinal','action','outcome','model_uri','created_at'),row))
                for row in rows]

    def approve_draft(self, draft_id, reviewer):
        """Перенос проверенной человеком записи в память только при текущем источнике."""
        row = self.db.execute('''SELECT d.task_id,d.source_hash,d.comment_ordinal,
            d.action,d.outcome,t.content_hash FROM draft_actions d
            JOIN tasks t ON t.id=d.task_id WHERE d.id=?''', (draft_id,)).fetchone()
        if row is None or row[1] != row[5]:
            raise ValueError('Черновик не найден или исходная задача изменилась')
        if not reviewer.strip():
            raise ValueError('Укажите имя проверяющего')
        self.add_review(row[0], row[2], row[3], row[4], reviewer)

    def search(self, query, limit=10, scope=None):
        if not query.strip():
            return []
        # FTS5 допускает операторы; экранируем пользовательские слова как фразы.
        words = re.findall(r'\w+', query, flags=re.UNICODE)
        if not words:
            return []
        expression = ' OR '.join('"' + word.replace('"', '') + '"' for word in words[:20])
        sql = '''SELECT t.id, t.scope, t.title, t.status, t.url,
                       snippet(task_search, 3, '[', ']', '…', 12) AS excerpt
                 FROM task_search JOIN tasks t ON t.id=task_search.task_id
                 WHERE task_search MATCH ?'''
        params = [expression]
        if scope:
            sql += ' AND t.scope=?'
            params.append(scope)
        sql += ' ORDER BY bm25(task_search) LIMIT ?'
        params.append(min(max(limit, 1), 100))
        return [dict(zip(('id','scope','title','status','url','excerpt'), row))
                for row in self.db.execute(sql, params)]
