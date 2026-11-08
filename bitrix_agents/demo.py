"""Вымышленная история и заранее заданный ответ для демонстрации без LLM."""
from .core import Comment, Task


def history():
    """Пример: перезапуск не помог, а выдача согласованной роли решила проблему."""
    return Task('101', 'demo/support', 'Нет доступа к отчету', (
        Comment('1', 'Предлагаю перезапустить приложение.'),
        Comment('2', 'Перезапустили, ошибка доступа осталась.'),
        Comment('3', 'Администратор выдал согласованную роль, отчет стал доступен.'),
    ))


class DemoModel:
    """Замена модели для тестов: поддерживает только встроенную историю."""
    def extract(self, task):
        if task.id != '101' or task.comments != history().comments:
            raise NotImplementedError('DemoModel supports only the bundled synthetic history')
        return {
            'problem': task.title,
            'actions': [
                {'text': 'Перезапустить приложение', 'status': 'failed', 'source': 'comment:2'},
                {'text': 'Запросить у администратора проверку и выдачу согласованной роли',
                 'status': 'succeeded', 'source': 'comment:3'},
            ],
            'sources': ['comment:1', 'comment:2', 'comment:3'],
        }
