# Runtime API

Этот раздел собирается автоматически по актуальной слоистой структуре проекта в каталоге `src/`.

## Что покрывает автогенерация

- точку входа приложения и CLI-аргументы;
- domain-правила, настройки и типы;
- запись звука, ASR/LLM/TTS runtime, hotkey runtime, разрешения macOS и menu bar UI;
- use case-сценарии распознавания, истории, Reader, LLM-пайплайна и Zipper;
- инфраструктуру Zipper: конфиг, память, allowlist CLI, MCP и агентский runtime.

## Карта runtime-модулей

- [CLI и запуск](entrypoint.md) — Приложение офлайн-диктовки для macOS на базе MLX Whisper.
- [Domain и настройки](modules/config.md) — Чистые константы и helper-функции приложения Dictator.
- [Аудио и микрофон](modules/audio.md) — Runtime-запись звука и перечисление устройств ввода через PyAudio.
- [ASR runtime](modules/asr_runtime.md) — Runtime-обёртки над локальными ASR backend-ами.
- [Model manager](modules/model_manager.md) — Централизованный менеджер локальных MLX-моделей.
- [Model runtime service](modules/model_runtime_service.md) — Единый runtime-сервис загруженных MLX-моделей.
- [Диагностика](modules/diagnostics.md) — Логирование и сохранение диагностических артефактов приложения.
- [История распознавания](modules/history.md) — Persistence истории распознанного текста через NSUserDefaults.
- [LLM runtime](modules/llm_runtime.md) — Runtime-адаптеры для генерации через локальные MLX LLM/VLM.
- [Глобальные хоткеи](modules/hotkeys.md) — Горячие клавиши и единый keyboard dispatcher приложения Dictator.
- [Разрешения macOS](modules/permissions.md) — Разрешения macOS и системные утилиты приложения Dictator.
- [Распознавание и вставка](modules/transcriber.md) — Use case распознавания речи, вставки текста и истории.
- [LLM-обработка](modules/llm.md) — Use case-сценарии LLM-пайплайна и загрузки модели.
- [Reader source](modules/reader_source.md) — Общие правила чтения источника reader-сценариев из буфера обмена.
- [Reader preprocessing](modules/reader_preprocessing.md) — Use case предобработки текста reader-модуля через локальную LLM.
- [Reader RSVP](modules/reader_rsvp.md) — Use case запуска RSVP-чтения текста из буфера обмена.
- [Reader TTS](modules/reader_tts.md) — Use case запуска ускоренного TTS из буфера обмена.
- [Zipper use case](modules/zipper.md) — Use case-сценарии голосового агента Zipper.
- [Zipper config](modules/zipper_config.md) — Загрузка и нормализация TOML-конфига Zipper.
- [Zipper runtime](modules/zipper_runtime.md) — Инфраструктурные адаптеры Zipper: память, инструменты, URL и агент.
- [Menu bar UI](modules/ui.md) — UI menu bar приложения Dictator.

## Как обновляется документация

Перед каждой сборкой MkDocs запускается `scripts/generate_docs.py`, который перечитывает текущий Python-код и перегенерирует страницы API в каталоге `docs/api/`.
