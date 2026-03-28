# Аудио и микрофон

Аудио-часть теперь разделена на два уровня:

- `src/domain/audio.py`
  - Чистые функции форматирования и представления микрофонов для UI.
- `src/infrastructure/audio_runtime.py`
  - `Recorder`, перечисление устройств ввода и работа с PyAudio.

## Поток

1. `main.py` создаёт `Recorder`.
2. `DictationApp` получает каталог устройств через injected `InputDeviceCatalogService`.
3. `RecordingUseCases` управляет жизненным циклом записи.

Так orchestration и UI больше не зависят напрямую от PyAudio runtime.
