"""Чтение одной задачи Битрикс24 и её чата через REST; без записи в портал."""
import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class BitrixReader:
    def __init__(self, webhook_url):
        parsed = urlparse(webhook_url)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.path.startswith('/rest/'):
            raise ValueError('Нужен HTTPS-адрес входящего вебхука Битрикс24')
        self._url = webhook_url.rstrip('/') + '/'
        self.portal = parsed.hostname

    def _call(self, method, params):
        request = Request(self._url + method + '.json',
                          data=json.dumps(params).encode('utf-8'),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read())
        except HTTPError as error:
            raise RuntimeError(f'Битрикс24: HTTP {error.code}. Проверьте доступ к методу.') from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError('Битрикс24: ошибка соединения или таймаут.') from None
        except (ValueError, TypeError):
            raise RuntimeError('Битрикс24: неверный JSON-ответ.') from None
        if not isinstance(data, dict) or data.get('error'):
            # Не выводим полный ответ: в нём могут быть детали портала.
            raise RuntimeError('Битрикс24: API отказал в доступе или вернул ошибку.')
        return data.get('result')

    def read_task(self, task_id):
        if not str(task_id).isdigit():
            raise ValueError('ID задачи должен быть целым числом')
        result = self._call('tasks.task.get', {'taskId': int(task_id),
                                               'select': ['ID','TITLE','DESCRIPTION','GROUP_ID',
                                                          'STATUS','CHAT_ID','CREATED_DATE']})
        task = result.get('task', {}) if isinstance(result, dict) else {}
        if not task or not task.get('chatId'):
            raise RuntimeError('Не получен чат задачи; проверьте тип карточки и права на чтение.')
        chat = self._call('im.dialog.messages.get', {'DIALOG_ID': 'chat' + str(task['chatId'])})
        if not isinstance(chat, dict) or not isinstance(chat.get('messages'), list):
            raise RuntimeError('Не получены сообщения чата задачи.')
        comments = [{'id': str(m['id']), 'created_at': str(m.get('date', '')),
                     'author': str(m.get('author_id', '')), 'text': str(m.get('text', ''))}
                    for m in chat['messages'] if isinstance(m, dict) and m.get('id') and m.get('text')]
        return {'id': str(task['id']), 'scope': self.portal + '/' + str(task.get('groupId', '')),
                'title': str(task.get('title', '')), 'description': str(task.get('description', '')),
                'status': str(task.get('status', '')), 'created_at': str(task.get('createdDate', '')),
                'comments': comments}
