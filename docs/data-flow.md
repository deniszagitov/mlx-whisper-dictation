# Диаграммы потоков данных

Эти схемы являются **DFD: Data Flow Diagram**, то есть диаграммами потоков
данных. Они показывают не классы и не вызовы функций, а движение данных между
пользователем, macOS, use case-слоем, MLX runtime, persistence и UI.

## Контекстная DFD

```mermaid
flowchart LR
    User["Пользователь"] -->|хоткеи / menu bar| UI["Menu bar UI"]
    User -->|голос| Mic["Микрофон macOS"]
    User -->|Cmd+C вне приложения| Clipboard["Системный буфер обмена"]

    UI --> App["DictationApp"]
    Hotkeys["CGEventTap HotkeyDispatcher"] --> App
    Mic --> Recorder["Recorder / PyAudio"]
    Recorder --> App

    App --> ASR["Локальный ASR<br/>mlx_whisper / mlx-audio"]
    App --> LLM["Локальная MLX LLM"]
    App --> TTS["Apple AVSpeech / MLX TTS"]
    App --> TextInput["CGEvent / AX / Cmd+V"]
    App --> Clipboard
    App --> Store["NSUserDefaults<br/>Application Support<br/>Logs"]

    ASR --> App
    LLM --> App
    App --> UI
    TextInput --> ActiveApp["Активное приложение"]
    TTS --> User
```

## Обычная диктовка

```mermaid
flowchart TD
    Start["Основной/дополнительный хоткей<br/>или пункт menu bar"] --> Prepare["prepare_recording()<br/>обновить микрофоны"]
    Prepare -->|нет микрофона| NotifyNoMic["Уведомление<br/>запись не началась"]
    Prepare -->|микрофон доступен| Record["Recorder.start()<br/>аудио capture"]
    Record --> Stop["Повторный хоткей / menu bar / max_time"]
    Stop --> PostRoll["Recorder.stop()<br/>post-roll 300 ms"]
    PostRoll --> Preprocess["preprocess_recorded_audio()<br/>float32 mono 16 kHz"]
    Preprocess --> ASR["ASR runtime<br/>mlx_whisper или mlx-audio"]
    ASR --> Postprocess["Постобработка текста<br/>заглавная буква, точка, цепочка"]
    Postprocess --> History["История текста<br/>до 20 записей"]
    Postprocess --> Insert{"Включённый метод вставки"}
    Insert --> CG["CGEvent Unicode"]
    CG -->|ошибка| AX["Accessibility API"]
    AX -->|ошибка| Paste["Clipboard + Cmd+V<br/>с восстановлением"]
    Paste -->|ошибка| Fallback["Fallback: текст в истории<br/>и системном clipboard"]
    CG -->|успех| Active["Активное поле ввода"]
    AX -->|успех| Active
    Paste -->|успех| Active
```

## Whisper -> LLM

```mermaid
flowchart TD
    Hotkey["LLM-хоткей<br/>ctrl+shift+alt+l"] --> Cached{"LLM-модель<br/>есть в HF cache?"}
    Cached -->|нет| Download["Единый downloader моделей<br/>уведомление и прогресс в menu bar"]
    Cached -->|да| Record["Запись через Recorder"]
    Record --> ASR["transcribe_to_text()<br/>ASR без автовставки"]
    ASR --> Context{"Нужен контекст?"}
    Context -->|clipboard подходит| Clipboard["read_clipboard()"]
    Context -->|Obsidian remind| ObsidianSearch["search_obsidian_notes()"]
    Context -->|нет| Prompt["System prompt из меню"]
    Clipboard --> Prompt
    ObsidianSearch --> Prompt
    Prompt --> LLM["LlmGateway.process_text()<br/>локальная MLX LLM"]
    LLM -->|ошибка / нужна модель| SourceFallback["Исходный ASR-текст<br/>в clipboard и историю"]
    LLM -->|ответ| Route{"Prompt Obsidian?"}
    Route -->|write note| Note["write_obsidian_note()"]
    Route -->|обычный| Output["LLM-ответ<br/>в clipboard и историю"]
    Note --> Notify["Уведомление"]
    Output --> Notify
```

## Reader RSVP

```mermaid
flowchart TD
    Trigger["RSVP-хоткей cmd_l+alt+r<br/>или пункт Reader"] --> Running{"Overlay уже открыт?"}
    Running -->|да| Close["Закрыть overlay"]
    Running -->|нет| Read["PasteboardReader.read_content()<br/>read-only clipboard"]
    Read --> Valid{"Есть текстовый тип?"}
    Valid -->|нет| Notify["Уведомление"]
    Valid -->|да| Limit["Обрезка до лимита<br/>10 000 символов"]
    Limit --> Preprocess{"LLM-предобработка<br/>включена и модель в cache?"}
    Preprocess -->|да| LLM["Локальная MLX LLM<br/>RSVP prompt"]
    Preprocess -->|нет / ошибка| Cleanup["Локальная очистка RSVP"]
    LLM --> Cleanup
    Cleanup --> Frames["build_rsvp_frames()<br/>chunk + ORP"]
    Frames --> Overlay["RSVPOverlay.show_frames()"]
    Overlay --> Keys["Space / Esc / стрелки<br/>управление показом"]
```

## Reader TTS

```mermaid
flowchart TD
    Trigger["TTS-хоткей cmd_l+alt+t<br/>или пункт Reader"] --> Speaking{"TTS уже говорит?"}
    Speaking -->|да| Stop["speaker.stop()"]
    Speaking -->|нет| Read["PasteboardReader.read_content()<br/>read-only clipboard"]
    Read --> Valid{"Есть текст?"}
    Valid -->|нет| Notify["Уведомление"]
    Valid -->|да| Limit["Обрезка источника<br/>10 000 символов"]
    Limit --> Preprocess{"LLM-предобработка<br/>включена и модель в cache?"}
    Preprocess -->|да| LLM["Локальная MLX LLM<br/>TTS prompt"]
    Preprocess -->|нет / ошибка| Normalize["Локальная нормализация<br/>markdown, URL, code"]
    LLM --> Normalize
    Normalize --> Duration["Лимит длительности<br/>по словам и rate"]
    Duration --> Backend{"Backend"}
    Backend --> Apple["Apple AVSpeechSynthesizer"]
    Backend --> MLX["MLX Qwen3-TTS streaming"]
    Apple --> Audio["Локальное аудио"]
    MLX --> Audio
```

## Zipper

```mermaid
flowchart TD
    Trigger["Zipper-хоткей ctrl+shift+alt+z<br/>или пункт menu bar"] --> Enabled{"Zipper включён?"}
    Enabled -->|нет| ErrorOff["Окно и уведомление"]
    Enabled -->|да| Cached{"LLM-модель<br/>есть в HF cache?"}
    Cached -->|нет| Download["Единый downloader<br/>повторить команду после загрузки"]
    Cached -->|да| Record["Запись голосовой команды"]
    Record --> ASR["transcribe_to_text()<br/>без автовставки"]
    ASR --> AgentInput["agent_input event<br/>команда + память + инструменты"]
    AgentInput --> Tools["Сбор инструментов:<br/>built-in, CLI allowlist, custom, MCP"]
    Tools --> Agent["Агентский runtime<br/>Qwen Hermes tools / ReAct"]
    Agent --> ToolCall{"Нужен инструмент?"}
    ToolCall -->|clipboard| Clipboard["get/set clipboard"]
    ToolCall -->|URL| URL["open_url http/https"]
    ToolCall -->|CLI| CLI["subprocess.run без shell<br/>только command из allowlist"]
    ToolCall -->|MCP/custom| ExternalTools["MCP/custom tools<br/>ошибки в debug"]
    Clipboard --> Agent
    URL --> Agent
    CLI --> Agent
    ExternalTools --> Agent
    ToolCall -->|нет| Result["ZipperAgentResult<br/>text + output_mode"]
    Agent --> Result
    Result --> Output{"output_mode"}
    Output --> Voice["Голосовой ответ"]
    Output --> Window["Текстовое окно"]
    Output --> Both["Голос + окно"]
    Voice --> Memory["События в память"]
    Window --> Memory
    Both --> Memory
    Memory --> Summarize{"Превышены лимиты<br/>events/tokens?"}
    Summarize -->|да| Summary["Суммаризация старых событий<br/>в постоянную память"]
    Summarize -->|нет| Idle["Статус ожидания"]
    Summary --> Idle
```

## Загрузка моделей

```mermaid
flowchart TD
    Request["ASR / LLM / TTS / Zipper<br/>запрос модели"] --> Cached{"Snapshot есть<br/>в Hugging Face cache?"}
    Cached -->|да| Memory["Синхронная загрузка<br/>модели в память"]
    Memory --> Status["Menu bar:<br/>загрузка модели в память"]
    Status --> Runtime["Runtime продолжает сценарий"]
    Cached -->|нет| Downloader["ModelManager.ensure_downloaded()<br/>4 воркера HF"]
    Downloader --> Progress["Menu bar progress:<br/>процент, объём, скорость, ETA"]
    Progress --> Slow{"Пауза или скорость<br/>ниже порога?"}
    Slow -->|да| Warning["Предупреждение / ошибка загрузки"]
    Slow -->|нет| Ready["Модель скачана"]
    Ready --> Retry["Пользователь повторяет действие"]
```
