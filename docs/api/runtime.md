# Runtime API

Этот раздел описывает runtime-часть после перехода на Clean Architecture.

## Что покрывает раздел

- composition root в `main.py`;
- слой `domain` с чистыми правилами и типами;
- слой `use_cases` со сценариями приложения;
- adapters для menu bar UI и overlay;
- infrastructure для macOS runtime, MLX, persistence и хоткеев.

## Карта runtime-модулей

- [CLI и запуск](entrypoint.md) — Приложение офлайн-диктовки для macOS на базе MLX Whisper.
- [Domain и настройки](modules/config.md) — Константы, типы, порты и NSUserDefaults adapter.
- [Аудио и микрофон](modules/audio.md) — Domain-утилиты микрофона и runtime-запись через PyAudio.
- [Диагностика](modules/diagnostics.md) — Логирование и сохранение диагностических артефактов приложения.
- [История распознавания](modules/history.md) — Persistence истории распознанного текста через NSUserDefaults.
- [LLM runtime](modules/llm_runtime.md) — Runtime-адаптеры для загрузки, генерации и выгрузки MLX LLM.
- [Горячие клавиши](modules/hotkeys.md) — Domain-правила, runtime-listener'ы и UI-захват комбинаций.
- [Разрешения macOS](modules/permissions.md) — Разрешения macOS и системные утилиты приложения.
- [Распознавание и вставка](modules/transcriber.md) — Domain-правила и `TranscriptionUseCases`.
- [LLM-обработка](modules/llm.md) — Domain-обработка, LLM pipeline и `LlmGateway`.
- [Menu bar UI](modules/ui.md) — `StatusBarApp`, `RecordingOverlay` и `DictationApp`.

## Как обновляется документация

Страницы в `docs/api/` синхронизируются вместе с кодом при архитектурных и пользовательских изменениях. Для текущего refactor-а они обновлены вручную под новую слоистую структуру.
