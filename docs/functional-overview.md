# Функциональное описание

Эта страница описывает пользовательские сценарии Dictator: чем они запускаются,
какие данные принимают, как эти данные проходят через приложение и какой
результат получает пользователь.

Правильное название для «схемы входных и выходных данных» в этом проекте —
**диаграмма потоков данных**: DFD, Data Flow Diagram. Для практической
документации ниже используются две формы:

- **карта входов и выходов** — таблица контрактов сценариев;
- **DFD-схемы** — Mermaid-диаграммы, показывающие движение данных через
  runtime-слои.

## Карта сценариев

| Сценарий | Как запускается | Входные данные | Основная обработка | Выходные данные |
| --- | --- | --- | --- | --- |
| Обычная диктовка | Основной хоткей `cmd_l+alt`, дополнительный хоткей `ctrl+shift+alt+t` или пункт menu bar | Аудио с выбранного микрофона, язык, ASR-модель, настройки постобработки и методов вставки | Запись через PyAudio, post-roll, preprocessing до `float32 mono 16 kHz`, локальный ASR, текстовая постобработка | Текст в активном поле через CGEvent/AX/clipboard, история текста, fallback в clipboard при ошибке вставки |
| Whisper -> LLM | LLM-хоткей `ctrl+shift+alt+l` или пункт меню LLM | Аудио с микрофона, распознанный текст, выбранный системный prompt, опциональный текст из clipboard или Obsidian | ASR, выбор контекста, локальная MLX LLM, обработка ответа | LLM-ответ в clipboard и историю; для Obsidian-сценариев — заметка в vault |
| Reader RSVP | RSVP-хоткей `cmd_l+alt+r` или `📖 Reader -> 👀 Запустить RSVP` | Текстовый тип из системного буфера обмена, настройки wpm/chunk/font, флаг LLM-предобработки | Read-only чтение clipboard, ограничение длины, локальная LLM-предобработка или fallback, разбиение на RSVP-кадры с ORP | Borderless overlay для быстрого чтения; clipboard не меняется |
| Reader TTS | TTS-хоткей `cmd_l+alt+t` или `📖 Reader -> 🔊 Запустить TTS` | Текстовый тип из clipboard, backend Apple/MLX, голос, скорость, лимит длительности, флаг LLM-предобработки | Read-only чтение clipboard, LLM-предобработка или fallback, чистка markdown/URL/кода, ограничение длины | Локальное озвучивание через Apple AVSpeech или MLX Qwen3-TTS; clipboard не меняется |
| Zipper | Zipper-хоткей `ctrl+shift+alt+z` или `🧷 Zipper -> Запустить Zipper` | Аудио команды, конфиг Zipper, текущая MLX LLM, память, инструменты, clipboard/URL/CLI/MCP при явном вызове | ASR без автовставки, LangChain ReAct agent, allowlist-инструменты, сохранение событий и суммаризация памяти | Голосовой ответ, текстовое окно, debug-события, изменения только через выбранные инструменты |
| Настройки и обслуживание | Пункты menu bar | Пользовательские значения модели, языка, хоткеев, микрофона, лимитов, методов вставки, reader/TTS/Zipper-настроек | Валидация доменными правилами, сохранение в `NSUserDefaults` или файлы Application Support | Обновлённый snapshot UI, сохранённые настройки между запусками |

## Общий жизненный цикл

1. `main.py` читает CLI-аргументы и сохранённые настройки.
2. `main.py` создаёт concrete adapters: recorder, ASR/LLM/TTS runtime,
   clipboard/text-input adapters, persistence, menu bar UI и hotkey dispatcher.
3. `DictationApp` получает зависимости через конструктор и создаёт use case-слой.
4. `StatusBarApp` подписывается на snapshot приложения и показывает текущее
   состояние в menu bar.
5. `HotkeyDispatcher` принимает глобальные сочетания клавиш через `CGEventTap`.
6. Каждый пользовательский сценарий меняет state приложения и публикует новый
   snapshot для UI.
7. Ошибки сценариев должны заканчиваться понятным уведомлением и fallback-ом,
   а не потерей результата.

## Основные состояния

| Состояние | Что означает | Что видно пользователю |
| --- | --- | --- |
| `ожидание` | Нет активной записи или обработки | Иконка ожидания, меню доступно |
| `запись` | Recorder получает аудио с микрофона | Красный индикатор, таймер, optional overlay |
| `распознавание` | Аудио передано в ASR | Иконка обработки, запись уже остановлена |
| `LLM-обработка` | Распознанный текст передан локальной LLM | Статус LLM, возможна загрузка модели |
| `Zipper: обработка` | Агент выполняет reasoning и инструменты | Иконка Zipper, debug-панель при включении |
| `загрузка модели` | MLX-модель синхронно загружается в память | Статус модели и короткое имя модели |

## Горячие клавиши и dispatch

Все глобальные хоткеи проходят через `HotkeyDispatcher`:

| Хоткей по умолчанию | Callback | Сценарий |
| --- | --- | --- |
| `cmd_l+alt` | `DictationApp.toggle()` | Обычная диктовка |
| `ctrl+shift+alt+t` | `DictationApp.toggle()` | Дополнительный запуск обычной диктовки |
| `ctrl+shift+alt+l` | `DictationApp.toggle_llm()` | Whisper -> LLM |
| `ctrl+shift+alt+z` | `DictationApp.toggle_zipper()` | Zipper |
| `cmd_l+alt+r` | `DictationApp.toggle_rsvp()` | Reader RSVP |
| `cmd_l+alt+t` | `DictationApp.toggle_tts()` | Reader TTS |
| `Esc` | `handle_escape_keycode()` или reader handler | Отмена записи, закрытие RSVP или остановка TTS |

Если `CGEventTap` не поднялся из-за macOS-разрешений, запись всё равно должна
быть доступна из menu bar. При проблемах с хоткеями сначала проверяется
`Accessibility` и `Input Monitoring`.

## Контракт данных

### Аудио

| Этап | Формат |
| --- | --- |
| Capture | `RecordedAudio`: samples, sample rate, channels, sample format, profile |
| Preprocessing | `PreprocessedAudio`: `float32`, mono, `16 kHz`, diagnostics |
| ASR input | In-memory numpy array без обязательной записи WAV на диск |
| ASR output | `dict` с `text`, optional `segments`, token usage |

Диагностические WAV/JSON сохраняются только при включённой диагностике. Обычный
путь держит аудио в памяти.

### Текст

| Источник | Внутренний формат | Куда уходит |
| --- | --- | --- |
| ASR обычной диктовки | `str` после постобработки | Методы вставки, история, fallback clipboard |
| ASR LLM-сценария | `str` исходного запроса | LLM prompt + optional context |
| Clipboard reader | `ClipboardContent` -> `ReaderSourceText` -> `ProcessedText` | RSVP frames или TTS text |
| Zipper команда | `str` после ASR | LangChain agent input, память событий |
| Zipper tool output | `str`, обрезается до безопасного лимита для контекста | Agent observation, debug-панель, финальный ответ |

Reader-сценарии читают clipboard только через read-only порт и не записывают
обратно. Zipper может читать или писать clipboard только через явный инструмент
агента.

### Конфигурация

| Данные | Хранилище |
| --- | --- |
| Runtime-настройки, хоткеи, модель, методы вставки, reader-настройки | `NSUserDefaults` |
| История текста | `NSUserDefaults`, до 20 записей, кроме приватного режима |
| Zipper example config | `docs/zipper/zipper.example.toml` |
| Zipper dev config | `zipper.local.toml`, не коммитится |
| Zipper user config | `~/Library/Application Support/Dictator/zipper.toml` |
| Zipper память | `~/Library/Application Support/Dictator/zipper_memory.json` |
| Логи | `~/Library/Logs/whisper-dictation/` |

## Fallback-правила

- Обычная диктовка всегда добавляет распознанный текст в историю.
- Если включённый метод вставки падает, следующий метод пробуется автоматически.
- Если все методы вставки недоступны или выключены, текст сохраняется в
  clipboard fallback и истории.
- Если LLM в сценарии Whisper -> LLM недоступна или падает, исходный
  распознанный текст сохраняется в буфер обмена и историю.
- Если Reader LLM-предобработка падает, RSVP/TTS используют исходный текст после
  локальной очистки.
- Если MCP или инструмент Zipper недоступен, ошибка попадает в debug-поток и
  пользовательский вывод, но обычная диктовка, Reader и TTS продолжают работать.

