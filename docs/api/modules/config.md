# Domain и настройки

Старый `src/config.py` разделён на несколько модулей по слоям:

- `src/domain/constants.py`
  - Константы, пресеты моделей, лимитов записи и статусов UI.
- `src/domain/types.py`
  - `HistoryRecord`, `AudioDeviceInfo`, `MicrophoneProfile`, `AudioDiagnostics`.
- `src/domain/ports.py`
  - Протоколы внешних зависимостей: recorder, overlay, persistence, clipboard, system integration, LLM.
- `src/infrastructure/persistence/defaults.py`
  - Concrete-обёртка над `NSUserDefaults`.

## Что важно

- `domain` больше не импортирует `Foundation`.
- `Defaults` больше не протекает транзитивно через общий модуль конфигурации.
- Use-case слой работает через `SettingsStoreProtocol`, а concrete `Defaults` создаётся только в `main.py`.
