# Распознавание и вставка

Старый `src/transcriber.py` заменён на два уровня:

- `src/domain/transcription.py`
  - Чистые правила: детекция галлюцинаций, нормализация истории, сбор аудио-диагностики, подсчёт токенов.
- `src/use_cases/transcription.py`
  - `TranscriptionUseCases`: orchestration распознавания, вставки текста, истории и fallback-сценариев.

## Важные свойства

- Use-case слой не импортирует `infrastructure`.
- Whisper runtime, clipboard, AX/CGEvent и persistence передаются через injected callables/adapters.
- При любой неудачной автовставке текст не теряется: остаётся в истории и может попасть в буфер обмена.
