# Menu bar UI

UI-слой теперь состоит из:

- `src/adapters/ui.py`
  - `StatusBarApp` для строки меню.
- `src/adapters/overlay.py`
  - `RecordingOverlay`.
- `src/app.py`
  - тонкий координатор `DictationApp`, который публикует snapshot для UI.

## Что изменилось

- `StatusBarApp` больше не использует магию `__getattr__`/`__setattr__`.
- UI читает состояние через явные свойства и обновляется по `AppSnapshot`.
- Вся пользовательская логика по-прежнему доступна из menu bar: запись, модель, хоткеи, лимит записи, права macOS, история и быстрые профили микрофона.
