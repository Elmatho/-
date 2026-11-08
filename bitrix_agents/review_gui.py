"""Локальный интерфейс слепой оценки без доступа к ключу методов."""

import json
from pathlib import Path


def _item_key(item):
    return f"{item['task_id']}:{item['letter']}"


def load_items(results_dir):
    """Загрузить только обезличенные по методу варианты ответов."""
    path = Path(results_dir) / 'blind_items.json'
    if not path.exists():
        raise ValueError('Нет blind_items.json. Сначала запустите команду blind-review')
    items = json.loads(path.read_text(encoding='utf-8'))
    required = {'task_id', 'title', 'description', 'letter', 'answer'}
    if not isinstance(items, list) or not items or any(
            not isinstance(item, dict) or set(item) != required for item in items):
        raise ValueError('Неверный формат blind_items.json')
    if len({_item_key(item) for item in items}) != len(items):
        raise ValueError('В листе оценки повторяются идентификаторы ответов')
    return items


def load_ratings(results_dir):
    """Считать сохранённые оценки; при первом запуске вернуть пустой словарь."""
    path = Path(results_dir) / 'blind_ratings.json'
    if not path.exists():
        return {}
    ratings = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(ratings, dict):
        raise ValueError('Неверный формат blind_ratings.json')
    return ratings


def save_rating(results_dir, item, score, unsupported, applicability, rationale):
    """Проверить поля и атомарно сохранить оценку одного ответа."""
    if score not in (0, 1, 2) or type(score) is not int:
        raise ValueError('Выберите оценку 0, 1 или 2')
    if type(unsupported) is not bool:
        raise ValueError('Укажите, есть ли неподтверждённый факт')
    if applicability not in ('да', 'нет', 'неясно'):
        raise ValueError('Укажите применимость ответа')
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError('Добавьте краткое обоснование оценки')
    valid_keys = {_item_key(record) for record in load_items(results_dir)}
    key = _item_key(item)
    if key not in valid_keys:
        raise ValueError('Ответ не найден в текущем листе оценки')
    ratings = load_ratings(results_dir)
    ratings[key] = {'score': score, 'unsupported': unsupported,
                    'applicability': applicability, 'rationale': rationale.strip()}
    path = Path(results_dir) / 'blind_ratings.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(ratings, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return len(ratings)


def launch(results_dir):
    """Показать по одному ответу, сохраняя прогресс после каждой оценки."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    folder = Path(results_dir)
    items = load_items(folder)
    ratings = load_ratings(folder)
    root = tk.Tk()
    root.title('Слепая оценка ответов прототипа')
    root.geometry('1000x790')
    root.minsize(760, 610)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)
    frame.rowconfigure(4, weight=2)

    progress = ttk.Label(frame, font=('Segoe UI', 11, 'bold'))
    progress.grid(row=0, column=0, sticky='w', pady=(0, 8))
    ttk.Label(frame, text='Условия контрольной задачи').grid(row=1, column=0, sticky='w')
    task_text = ScrolledText(frame, height=9, wrap='word', font=('Segoe UI', 10))
    task_text.grid(row=2, column=0, sticky='nsew', pady=(4, 10))
    ttk.Label(frame, text='Ответ без указания метода').grid(row=3, column=0, sticky='w')
    answer_text = ScrolledText(frame, height=15, wrap='word', font=('Segoe UI', 10))
    answer_text.grid(row=4, column=0, sticky='nsew', pady=(4, 10))

    controls = ttk.Frame(frame)
    controls.grid(row=5, column=0, sticky='ew')
    score = tk.IntVar(value=-1)
    unsupported = tk.StringVar(value='')
    applicability = tk.StringVar(value='')
    ttk.Label(controls, text='Корректность:').grid(row=0, column=0, sticky='w')
    for col, (value, label) in enumerate(((0, '0 — неверно'), (1, '1 — частично'), (2, '2 — верно')), 1):
        ttk.Radiobutton(controls, text=label, variable=score, value=value).grid(row=0, column=col, padx=8)
    ttk.Label(controls, text='Неподтверждённый факт:').grid(row=1, column=0, sticky='w', pady=5)
    for col, value in enumerate(('да', 'нет'), 1):
        ttk.Radiobutton(controls, text=value, variable=unsupported, value=value).grid(row=1, column=col)
    ttk.Label(controls, text='Применимость:').grid(row=2, column=0, sticky='w')
    for col, value in enumerate(('да', 'нет', 'неясно'), 1):
        ttk.Radiobutton(controls, text=value, variable=applicability, value=value).grid(row=2, column=col)

    ttk.Label(frame, text='Обоснование (какое действие подтверждается или что вызывает сомнение)').grid(
        row=6, column=0, sticky='w', pady=(10, 2))
    rationale = ScrolledText(frame, height=4, wrap='word', font=('Segoe UI', 10))
    rationale.grid(row=7, column=0, sticky='ew')
    buttons = ttk.Frame(frame)
    buttons.grid(row=8, column=0, sticky='ew', pady=(12, 0))

    def set_readonly(widget, value):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', value)
        widget.configure(state='disabled')

    position = next((i for i, item in enumerate(items) if _item_key(item) not in ratings), 0)

    def show(index):
        nonlocal position, ratings
        position = index
        ratings = load_ratings(folder)
        item = items[position]
        progress.configure(text=f"Ответ {position + 1} из {len(items)}  •  Оценено {len(ratings)} из {len(items)}  •  Задача {item['task_id']}, вариант {item['letter']}")
        set_readonly(task_text, item['title'] + '\n\n' + item['description'])
        set_readonly(answer_text, item['answer'])
        saved = ratings.get(_item_key(item), {})
        score.set(saved.get('score', -1))
        unsupported.set('да' if saved.get('unsupported') is True else 'нет' if saved.get('unsupported') is False else '')
        applicability.set(saved.get('applicability', ''))
        rationale.delete('1.0', 'end')
        rationale.insert('1.0', saved.get('rationale', ''))
        previous_button.configure(state='normal' if position > 0 else 'disabled')
        next_button.configure(state='normal' if position + 1 < len(items) else 'disabled')

    def save_and_next():
        try:
            save_rating(folder, items[position], score.get(),
                        True if unsupported.get() == 'да' else False if unsupported.get() == 'нет' else None,
                        applicability.get(), rationale.get('1.0', 'end').strip())
        except ValueError as error:
            messagebox.showerror('Оценка не сохранена', str(error), parent=root)
            return
        if position + 1 < len(items):
            show(position + 1)
        else:
            show(position)
            messagebox.showinfo('Готово', 'Последняя оценка сохранена.', parent=root)

    previous_button = ttk.Button(buttons, text='Предыдущий', command=lambda: show(position - 1))
    previous_button.pack(side='left')
    next_button = ttk.Button(buttons, text='Пропустить', command=lambda: show(position + 1))
    next_button.pack(side='left', padx=8)
    ttk.Button(buttons, text='Сохранить и далее', command=save_and_next).pack(side='right')
    ttk.Label(buttons, text='При переходе без сохранения введённые поля сбрасываются.').pack(side='right', padx=12)

    show(position)
    root.mainloop()
