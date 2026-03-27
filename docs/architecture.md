# Архитектура

Ниже показан текущий поток данных и управления в приложении после декомпозиции runtime-кода на отдельные модули в `src/`.

```mermaid
flowchart TD
    User[Пользователь] --> UI[ui.py\nStatusBarApp]
    User --> Hotkeys[hotkeys.py\nGlobalKeyListener / MultiHotkeyListener / DoubleCommandKeyListener]
    Hotkeys --> UI
    UI --> Audio[audio.py\nRecorder]
    Audio --> Mic[PyAudio / микрофон]
    Audio --> Transcriber[transcriber.py\nSpeechTranscriber]
    Audio --> LLM[llm.py\nLLMProcessor]
    UI --> Permissions[permissions.py\nAccessibility / Input Monitoring / Microphone]
    UI --> Config[config.py\nNSUserDefaults и пресеты]
    Transcriber --> Whisper[mlx_whisper.transcribe]
    Transcriber --> History[История текста]
    Transcriber --> Diagnostics[diagnostics.py\nDiagnosticsStore]
    Diagnostics --> Logs[~/Library/Logs/whisper-dictation]
    Transcriber --> Paste{Цепочка методов вставки}
    Paste --> CGEvent[CGEvent Unicode]
    Paste --> AX[Accessibility API]
    Paste --> Clipboard[Буфер обмена c восстановлением]
    CGEvent --> Target[Активное поле ввода]
    AX --> Target
    Clipboard --> Target
    LLM --> ClipboardContext[Опциональный контекст из буфера обмена]
    ClipboardContext --> LLM
    LLM --> Target
```

## Что видно по диаграмме

- orchestration больше не сосредоточен в одном файле: entrypoint только связывает CLI, menu bar и runtime-модули;
- модуль `transcriber.py` отвечает не только за Whisper, но и за историю текста, цепочку методов вставки и LLM-delivery;
- `config.py`, `permissions.py` и `diagnostics.py` вынесены в отдельные слои, поэтому документацию теперь можно генерировать по модулям, а не по одному монолиту;
- fallback-поведение осталось надёжным: если вставка недоступна, текст сохраняется в историю, а при включённом методе clipboard проходит через буфер обмена с восстановлением.