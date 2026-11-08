"""Точка запуска: выбор демонстрации или работы агентов через YandexGPT."""
import argparse
import json
from dataclasses import asdict
from .core import Analyst, Executor, Memory, Orchestrator, Task
from .demo import DemoModel, history


def main():
    # Аргументы командной строки выбирают режим и файл с настройками API.
    parser = argparse.ArgumentParser(description='Демонстрационный шаблон двух агентов')
    parser.add_argument('command', choices=['demo', 'yandex', 'import', 'search', 'stats',
                                            'view', 'review', 'reviews', 'classify-review', 'evaluate', 'solve-local',
                                            'bitrix-read', 'prototype-preview', 'prototype-run', 'annotate-draft',
                                            'drafts', 'approve-draft', 'review-packet',
                                            'blind-review', 'review-gui'])
    parser.add_argument('--env-file', help='Путь к .env с настройками Yandex')
    parser.add_argument('--archive', help='Путь к ZIP выгрузки Битрикс24')
    parser.add_argument('--db', default='data/tasks.sqlite3', help='Локальная база SQLite')
    parser.add_argument('--query', help='Текст запроса для локального поиска')
    parser.add_argument('--scope', help='Необязательное ограничение по порталу и группе')
    parser.add_argument('--task-id', help='ID задачи из локальной базы')
    parser.add_argument('--comment', type=int, help='Номер комментария, подтверждающего действие')
    parser.add_argument('--action', help='Текст действия для ручной разметки')
    parser.add_argument('--outcome', choices=['proposed', 'succeeded', 'failed', 'unknown'])
    parser.add_argument('--reviewer', help='Имя проверяющего')
    parser.add_argument('--review-id', type=int, help='ID подтверждённой записи опыта')
    parser.add_argument('--kind', choices=['solution', 'administrative', 'unknown'],
                        help='Тип действия: решение, событие сопровождения или неясно')
    parser.add_argument('--draft-id', type=int, help='ID черновой записи модели')
    parser.add_argument('--cases', help='JSON-файл с экспертными тестовыми случаями')
    parser.add_argument('--k', type=int, default=5, help='Число найденных задач на один запрос')
    parser.add_argument('--before', help='Искать только задачи до этой даты YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--task-ids', nargs='+', help='ID контрольных задач для прототипа')
    parser.add_argument('--results-dir', default='data/prototype_v2', help='Локальная папка результатов прототипа')
    args = parser.parse_args()
    if args.command == 'review-gui':
        from .review_gui import launch
        launch(args.results_dir)
        return
    if args.command == 'bitrix-read':
        if not args.task_id:
            parser.error('Для bitrix-read укажите --task-id')
        import os
        from pathlib import Path
        from .bitrix_api import BitrixReader
        # Адрес вебхука читается из локального окружения; в вывод не включается.
        webhook = os.environ.get('BITRIX_WEBHOOK_URL', '')
        if not webhook:
            raise ValueError('Задайте BITRIX_WEBHOOK_URL в переменной окружения')
        task = BitrixReader(webhook).read_task(args.task_id)
        output = Path('data') / ('bitrix_task_' + str(args.task_id) + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Задача сохранена локально: {output}; комментариев: {len(task["comments"])}')
        return
    if args.command in {'import', 'search', 'stats', 'view', 'review', 'reviews', 'classify-review', 'evaluate', 'solve-local', 'prototype-preview', 'prototype-run', 'annotate-draft', 'drafts', 'approve-draft', 'review-packet', 'blind-review'}:
        from .local_archive import LocalArchive
        archive = LocalArchive(args.db)
        try:
            if args.command == 'import':
                if not args.archive:
                    parser.error('Для import укажите --archive')
                result = archive.import_zip(args.archive)
            elif args.command == 'search':
                if not args.query:
                    parser.error('Для search укажите --query')
                result = archive.search(args.query, scope=args.scope)
            elif args.command == 'view':
                if not args.task_id:
                    parser.error('Для view укажите --task-id')
                result = archive.get_task(args.task_id)
                result.pop('content_hash')
            elif args.command == 'review':
                if not all((args.task_id, args.comment, args.action, args.outcome, args.reviewer)):
                    parser.error('Для review укажите --task-id, --comment, --action, --outcome и --reviewer')
                archive.add_review(args.task_id, args.comment, args.action,
                                   args.outcome, args.reviewer)
                result = {'saved': True, 'task_id': args.task_id}
            elif args.command == 'reviews':
                result = archive.current_reviews(args.task_id) if args.task_id else archive.review_stats()
            elif args.command == 'classify-review':
                if not args.review_id or not args.kind or not args.reviewer:
                    parser.error('Для classify-review укажите --review-id, --kind и --reviewer')
                archive.classify_review(args.review_id, args.kind, args.reviewer)
                result = {'classified': args.review_id, 'kind': args.kind}
            elif args.command == 'evaluate':
                if not args.cases:
                    parser.error('Для evaluate укажите --cases')
                from pathlib import Path
                from .experiment import evaluate
                cases = json.loads(Path(args.cases).read_text(encoding='utf-8-sig'))
                result = evaluate(archive, cases, args.k)
            elif args.command == 'solve-local':
                if not args.query or not args.scope:
                    parser.error('Для solve-local укажите --query и --scope')
                from .workflow import LocalWorkflow
                result = LocalWorkflow(archive).solve(args.query, args.scope, args.before)
            elif args.command == 'prototype-preview':
                if not args.task_ids:
                    parser.error('Для prototype-preview укажите --task-ids')
                from .prototype import preview_prototype
                result = preview_prototype(archive, args.task_ids, 'data/prototype_preview', args.k)
            elif args.command == 'prototype-run':
                if not args.task_ids:
                    parser.error('Для prototype-run укажите --task-ids')
                from .prototype import run_prototype
                from .yandex import YandexModel
                result = run_prototype(archive, YandexModel.from_env(args.env_file),
                                       args.task_ids, args.results_dir, args.k)
            elif args.command == 'annotate-draft':
                if not args.task_ids:
                    parser.error('Для annotate-draft укажите --task-ids')
                from .draft_annotation import propose_actions
                from .yandex import YandexModel
                model = YandexModel.from_env(args.env_file)
                result = [propose_actions(archive, model, task_id) for task_id in args.task_ids]
            elif args.command == 'drafts':
                if not args.task_id:
                    parser.error('Для drafts укажите --task-id')
                result = archive.draft_actions(args.task_id)
            elif args.command == 'approve-draft':
                if not args.draft_id or not args.reviewer:
                    parser.error('Для approve-draft укажите --draft-id и --reviewer')
                archive.approve_draft(args.draft_id, args.reviewer)
                result = {'approved':args.draft_id, 'reviewer':args.reviewer}
            elif args.command == 'review-packet':
                if not args.task_ids:
                    parser.error('Для review-packet укажите --task-ids')
                from .draft_annotation import write_review_packet
                output = write_review_packet(archive, args.task_ids, 'data/review_packet.md')
                result = {'saved': str(output), 'tasks': len(args.task_ids)}
            elif args.command == 'blind-review':
                from .blind_review import create_blind_sheet
                output = create_blind_sheet(archive, args.results_dir, args.results_dir)
                result = {'saved': str(output)}
            else:
                result = archive.stats()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            archive.close()
        return
    if args.command == 'yandex':
        # Реальная модель анализирует встроенную вымышленную историю.
        from .yandex import YandexModel, YandexExecutor
        model = YandexModel.from_env(args.env_file)
        memory = Memory()
        analyst = Analyst(memory, model)
        case = analyst.learn(history())
        print('Карточка, извлечённая YandexGPT из синтетической истории:')
        print(json.dumps(asdict(case), ensure_ascii=False, indent=2))
        print('Проверьте соответствие исходным комментариям:')
        print(json.dumps(asdict(history()), ensure_ascii=False, indent=2))
        # Проверяющий сверяет вывод модели с оригиналом до использования опыта.
        if input('Подтвердить карточку? Введите да: ').strip().casefold() != 'да':
            print('Карточка не подтверждена; исполнитель не запускается.')
            return
        memory.review(case.key, 'local-operator', True)
        task = Task('102', 'demo/support', 'Нет доступа к отчету', ())
        result = Orchestrator(analyst, YandexExecutor(model)).solve(task)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return
    memory = Memory()
    analyst = Analyst(memory, DemoModel())
    case = analyst.learn(history())
    system = Orchestrator(analyst, Executor())
    task = Task('102', 'demo/support', 'Нет доступа к отчету', ())
    print('СИМУЛЯЦИЯ: без LLM и подключения к Битрикс24')
    print('\nДо проверки опыта:', system.solve(task).text)
    # Имитация ручного подтверждения только для демонстрации, не для рабочих данных.
    memory.review(case.key, 'demo-human-review', True)
    print('\nПосле СИМУЛЯЦИИ ручного подтверждения:')
    print(json.dumps(asdict(system.solve(task)), ensure_ascii=False, indent=2))
    print('\nОбмен между агентами:')
    print(json.dumps(system.journal, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
