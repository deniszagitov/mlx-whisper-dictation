# Menu bar UI

UI-слой теперь состоит из:

- `src/adapters/ui.py`
  - `StatusBarApp` для строки меню.
- `src/adapters/settings_window.py`
  - нативное AppKit-окно настроек с верхним toolbar, открываемое из пункта menu bar «Открыть Диктатор…».
- `src/adapters/overlay.py`
  - `RecordingOverlay`.
- `src/app.py`
  - тонкий координатор `DictationApp`, который публикует snapshot для UI.

## Что изменилось

- `StatusBarApp` больше не использует магию `__getattr__`/`__setattr__`.
- UI читает состояние через явные свойства и обновляется по `AppSnapshot`.
- Окно настроек читает тот же `AppSnapshot` и делегирует команды в `DictationApp`, не импортируя use cases или infrastructure.
- Скачиваемые STT/LLM/MLX TTS-модели отображаются через `DownloadableModelStatus`: UI показывает `загружено`, `не загружено`, `загрузка N%`, запускает загрузку при выборе отсутствующей модели и даёт удалить локальную Hugging Face копию.
- Каждый экран настроек содержит краткое описание раздела: STT, LLM, TTS и RSVP раскрываются прямо в UI.
- Вся пользовательская логика по-прежнему доступна из menu bar: запись, модель, хоткеи, лимит записи, права macOS, история и быстрые профили микрофона.
