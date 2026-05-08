# Model manager

Исходный файл: `src/infrastructure/model_manager.py`

Централизованный менеджер локальных MLX-моделей.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `DOWNLOAD_SPEED_WINDOW_SECONDS` = `8.0`
- `DOWNLOAD_MIN_SPEED_WINDOW_SECONDS` = `1.0`
- `DOWNLOAD_MIN_SPEED_SAMPLES` = `2`
- `DOWNLOAD_TQDM_MIN_INTERVAL_SECONDS` = `0.5`
- `DOWNLOAD_TQDM_SMOOTHING` = `0.05`
- `DOWNLOAD_MAX_WORKERS` = `4`
- `DOWNLOAD_MIN_SPEED_BYTES_PER_SECOND` = `2 * 1024 * 1024`
- `DOWNLOAD_SLOW_SPEED_GRACE_SECONDS` = `30.0`
- `DOWNLOAD_STALL_TIMEOUT_SECONDS` = `60.0`
- `DOWNLOAD_HEALTH_MONITOR_INTERVAL_SECONDS` = `5.0`

## Классы

## `ModelDownloadHealthError`

Ошибка здоровья загрузки модели.

## `ModelDownloadTooSlowError`

Загрузка слишком долго идёт ниже минимальной скорости.

## `ModelDownloadStalledError`

Загрузка слишком долго не получает новые байты.

## `ModelDownloaderProtocol`

Минимальный контракт downloader-а для ModelManager.

### Методы

#### `is_model_cached`

```python
is_model_cached(model_name: str) -> bool
```

Проверяет наличие модели в локальном cache.

#### `ensure_downloaded`

```python
ensure_downloaded(model_name: str, *, label: str, progress_callback: ProgressCallback | None = None) -> None
```

Скачивает модель при необходимости.

## `HuggingFaceModelDownloader`

Единый downloader Hugging Face моделей с консольным и UI-прогрессом.

### Методы

#### `__init__`

```python
__init__(*, snapshot_downloader: Callable[..., str] | None = None, cache_checker: Callable[[str, str], Any] | None = None, clock: Callable[[], float] | None = None, min_emit_interval_seconds: float = 0.25, max_workers: int = DOWNLOAD_MAX_WORKERS, min_speed_bytes_per_second: float = DOWNLOAD_MIN_SPEED_BYTES_PER_SECOND, slow_speed_grace_seconds: float = DOWNLOAD_SLOW_SPEED_GRACE_SECONDS, stall_timeout_seconds: float = DOWNLOAD_STALL_TIMEOUT_SECONDS, health_monitor_interval_seconds: float = DOWNLOAD_HEALTH_MONITOR_INTERVAL_SECONDS) -> None
```

Конструктор класса.

#### `is_model_cached`

```python
is_model_cached(model_name: str) -> bool
```

Проверяет, есть ли модель в локальном cache Hugging Face.

#### `get_local_model_path`

```python
get_local_model_path(model_name: str) -> str | None
```

Возвращает локальный snapshot модели Hugging Face без обращения к сети.

#### `_local_path_from_cached_config`

```python
_local_path_from_cached_config(model_name: str) -> str | None
```

_Внутренняя функция._

Проверяет cache старым способом, не запуская сетевую загрузку.

#### `ensure_downloaded`

```python
ensure_downloaded(model_name: str, *, label: str, progress_callback: ProgressCallback | None = None) -> None
```

Скачивает модель через общий механизм с progress bar и событиями.

#### `_build_tqdm_class`

```python
_build_tqdm_class(label: str, model_name: str, progress_callback: ProgressCallback | None) -> type[Any]
```

_Внутренняя функция._

Создаёт tqdm-класс, который одновременно пишет в консоль и callback.

#### `_is_completed_in_process`

```python
_is_completed_in_process(model_name: str) -> bool
```

_Внутренняя функция._

Проверяет, была ли модель уже успешно скачана в текущем запуске.

#### `_mark_completed_in_process`

```python
_mark_completed_in_process(model_name: str) -> None
```

_Внутренняя функция._

Запоминает успешную проверку модели до завершения процесса.

#### `_remember_local_model_path`

```python
_remember_local_model_path(model_name: str, local_path: str) -> None
```

_Внутренняя функция._

Запоминает локальный snapshot path для runtime-loader-ов.

#### `_emit`

```python
_emit(progress_callback: ProgressCallback | None, progress: ModelDownloadProgress) -> None
```

_Внутренняя функция._

Отправляет событие прогресса, изолируя ошибки подписчика.

## `ModelManager`

Единая точка скачивания и загрузки ASR, LLM/VLM и MLX TTS моделей.

### Методы

#### `__init__`

```python
__init__(*, downloader: ModelDownloaderProtocol | None = None, progress_callback: ProgressCallback | None = None, lm_loader: Callable[[str], tuple[Any, Any]] | None = None, vlm_loader: Callable[[str], tuple[Any, Any]] | None = None, qwen_asr_loader: Callable[[str], Any] | None = None, tts_loader: Callable[[str], Any] | None = None, whisper_loader: Callable[[str], Any] | None = None, runtime_service: ModelRuntimeService | None = None) -> None
```

Конструктор класса.

#### `set_progress_callback`

```python
set_progress_callback(callback: ProgressCallback | None) -> None
```

Назначает callback для публикации прогресса в приложение.

#### `is_model_cached`

```python
is_model_cached(model_name: str) -> bool
```

Проверяет, доступна ли модель локально.

#### `is_model_ready`

```python
is_model_ready(model_name: str) -> bool
```

Проверяет, была ли модель подтверждена для runtime в текущем запуске.

#### `require_model_ready`

```python
require_model_ready(model_name: str, *, label: str) -> None
```

Разрешает runtime-загрузку только для локально доступной модели.

#### `ensure_model_downloaded`

```python
ensure_model_downloaded(model_name: str, *, label: str, progress_callback: LegacyProgressCallback | None = None) -> None
```

Скачивает модель через общий downloader и старый LLM callback.

#### `ensure_llm_model_downloaded`

```python
ensure_llm_model_downloaded(model_name: str, progress_callback: LegacyProgressCallback | None = None) -> None
```

Скачивает LLM-модель через общий менеджер.

#### `load_llm_runtime_objects`

```python
load_llm_runtime_objects(model_name: str) -> tuple[Any, Any]
```

Возвращает MLX LLM-модель из единого runtime-cache.

#### `_load_llm_runtime_objects_uncached`

```python
_load_llm_runtime_objects_uncached(model_name: str) -> tuple[Any, Any]
```

_Внутренняя функция._

Загружает MLX LLM-модель после проверки общим downloader-ом.

#### `load_vlm_runtime_objects`

```python
load_vlm_runtime_objects(model_name: str) -> tuple[Any, Any]
```

Возвращает MLX VLM-модель из единого runtime-cache.

#### `_load_vlm_runtime_objects_uncached`

```python
_load_vlm_runtime_objects_uncached(model_name: str) -> tuple[Any, Any]
```

_Внутренняя функция._

Загружает MLX VLM-модель после проверки общим downloader-ом.

#### `load_qwen_asr_model`

```python
load_qwen_asr_model(model_name: str) -> Any
```

Возвращает Qwen3-ASR модель из единого runtime-cache.

#### `_load_qwen_asr_model_uncached`

```python
_load_qwen_asr_model_uncached(model_name: str) -> Any
```

_Внутренняя функция._

Скачивает и загружает Qwen3-ASR модель через mlx-audio.

#### `load_tts_model`

```python
load_tts_model(model_name: str) -> Any
```

Возвращает streaming MLX TTS-модель из единого runtime-cache.

#### `_load_tts_model_uncached`

```python
_load_tts_model_uncached(model_name: str) -> Any
```

_Внутренняя функция._

Загружает streaming MLX TTS-модель после проверки общим downloader-ом.

#### `load_whisper_model`

```python
load_whisper_model(model_name: str) -> Any
```

Возвращает Whisper-модель из единого runtime-cache и заполняет ModelHolder.

#### `_load_whisper_model_uncached`

```python
_load_whisper_model_uncached(model_name: str) -> Any
```

_Внутренняя функция._

Загружает Whisper-модель в ModelHolder после проверки downloader-а.

#### `run_asr_transcription`

```python
run_asr_transcription(audio_data: npt.NDArray[np.float32], model_name: str, language: str | None) -> dict[str, Any]
```

Скачивает ASR-модель и запускает подходящий backend.

#### `preload_selected_models`

```python
preload_selected_models(*, asr_model: str | None = None, llm_model: str | None = None, tts_model: str | None = None) -> None
```

Запускает безопасный фоновый прогрев выбранных runtime-моделей.

#### `preload_asr_model`

```python
preload_asr_model(model_name: str) -> None
```

Прогревает выбранную ASR-модель, если её snapshot уже доступен локально.

#### `preload_llm_model`

```python
preload_llm_model(model_name: str) -> None
```

Прогревает выбранную LLM/VLM-модель, если её snapshot уже доступен локально.

#### `preload_tts_model`

```python
preload_tts_model(model_name: str) -> None
```

Прогревает выбранную MLX TTS-модель, если её snapshot уже доступен локально.

#### `release_model`

```python
release_model(model_name: str) -> None
```

Освобождает runtime-экземпляры указанной модели.

#### `shutdown`

```python
shutdown() -> None
```

Очищает единый runtime-cache моделей при выходе.

#### `_mark_model_ready`

```python
_mark_model_ready(model_name: str) -> None
```

_Внутренняя функция._

Запоминает успешную проверку модели для последующих runtime-load вызовов.

#### `_runtime_model_name`

```python
_runtime_model_name(model_name: str) -> str
```

_Внутренняя функция._

Подменяет HF repo id на локальный snapshot path, если он уже есть в cache.

#### `_set_whisper_model_holder`

```python
_set_whisper_model_holder(model_path: str, model: Any) -> None
```

_Внутренняя функция._

Заполняет singleton ModelHolder библиотеки mlx_whisper.

## Публичные функции

### `default_model_manager`

```python
default_model_manager() -> ModelManager
```

Возвращает общий менеджер моделей для legacy runtime-функций.

## Внутренние функции

### `_is_local_model_path`

```python
_is_local_model_path(model_name: str) -> bool
```

_Внутренняя функция._

Проверяет, похож ли идентификатор модели на локальный путь.

### `_coerce_total`

```python
_coerce_total(value: object) -> int
```

_Внутренняя функция._

Преобразует total progress bar в неотрицательное число байт.

### `_emit_legacy_progress`

```python
_emit_legacy_progress(callback: LegacyProgressCallback | None, progress: ModelDownloadProgress) -> None
```

_Внутренняя функция._

Пробрасывает новое событие в старый callback загрузки LLM.
