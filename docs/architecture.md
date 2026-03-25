# Архитектура

Ниже показан текущий поток данных и управления в приложении. Диаграмма отражает существующую структуру кода в runtime-модуле и нужна как быстрый ориентир перед дальнейшей декомпозицией на модули.

```mermaid
flowchart TD
    User[Пользователь] --> Menu[StatusBarApp\nmenu bar UI]
    User --> Hotkey[GlobalKeyListener /\nMultiHotkeyListener /\nDoubleCommandKeyListener]
    Hotkey --> Menu
    Menu --> Recorder[Recorder]
    Recorder --> Mic[PyAudio / микрофон]
    Recorder --> Transcriber[SpeechTranscriber]
    Transcriber --> Whisper[mlx_whisper.transcribe]
    Transcriber --> Clipboard[Буфер обмена macOS]
    Transcriber --> Diagnostics[DiagnosticsStore]
    Diagnostics --> Logs[Логи и артефакты\n~/Library/Logs/whisper-dictation]
    Clipboard --> Paste{Есть права\nAccessibility и\nInput Monitoring?}
    Paste -->|Да| AutoPaste[Cmd+V через Quartz]
    Paste -->|Fallback| Keyboard[pynput keyboard.type]
    AutoPaste --> Target[Активное поле ввода]
    Keyboard --> Target
    Menu --> Permissions[Проверка разрешений macOS]
    Permissions --> Transcriber
```

## Что видно по диаграмме

- Главный orchestration-слой сейчас сосредоточен в одном файле: приложение, слушатели хоткеев, запись, распознавание и часть permission-логики связаны напрямую.
- Надежный fallback уже встроен в поток распознавания: даже при неудачной автовставке текст сначала попадает в буфер обмена.
- Диагностика изолирована в `DiagnosticsStore`, поэтому это уже хорошая точка для дальнейшей модульной декомпозиции.
- Для будущего сайта это полезно как стартовая карта архитектуры, даже до появления более подробных ручных страниц.