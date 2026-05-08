# ASR runtime

Исходный файл: `src/infrastructure/asr_runtime.py`

Runtime-обёртки над локальными ASR backend-ами.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_QWEN_LANGUAGE_NAMES` = `{'ar': 'Arabic', 'arabic': 'Arabic', 'cs': 'Czech', 'czech': 'Czech', 'da': 'Danish', 'danish': 'Danish', 'de': 'German', 'german': 'German', 'el': 'Greek', 'greek': 'Greek', 'en': 'English', 'english': 'English', 'es': 'Spanish', 'spanish': 'Spanish', 'fa': 'Persian', 'persian': 'Persian', 'fi': 'Finnish', 'finnish': 'Finnish', 'fil': 'Filipino', 'filipino': 'Filipino', 'fr': 'French', 'french': 'French', 'hi': 'Hindi', 'hindi': 'Hindi', 'hu': 'Hungarian', 'hungarian': 'Hungarian', 'id': 'Indonesian', 'indonesian': 'Indonesian', 'it': 'Italian', 'italian': 'Italian', 'ja': 'Japanese', 'japanese': 'Japanese', 'ko': 'Korean', 'korean': 'Korean', 'mk': 'Macedonian', 'macedonian': 'Macedonian', 'ms': 'Malay', 'malay': 'Malay', 'nl': 'Dutch', 'dutch': 'Dutch', 'pl': 'Polish', 'polish': 'Polish', 'pt': 'Portuguese', 'portuguese': 'Portuguese', 'ro': 'Romanian', 'romanian': 'Romanian', 'ru': 'Russian', 'russian': 'Russian', 'sv': 'Swedish', 'swedish': 'Swedish', 'th': 'Thai', 'thai': 'Thai', 'tr': 'Turkish', 'turkish': 'Turkish', 'vi': 'Vietnamese', 'vietnamese': 'Vietnamese', 'yue': 'Cantonese', 'cantonese': 'Cantonese', 'zh': 'Chinese', 'zh-cn': 'Chinese', 'zh-hans': 'Chinese', 'zh-hant': 'Chinese', 'zh-tw': 'Chinese', 'chinese': 'Chinese'}`

## Публичные функции

### `is_qwen_asr_model`

```python
is_qwen_asr_model(model_name: str) -> bool
```

Определяет, что выбранная модель должна идти через mlx-audio.

### `run_whisper_transcription`

```python
run_whisper_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]
```

Запускает один проход mlx_whisper с фиксированными runtime-параметрами.

### `run_qwen_transcription`

```python
run_qwen_transcription(audio_data: Any, model_name: str, language: str | None, *, model_loader: Any | None = None) -> dict[str, Any]
```

Запускает один проход Qwen3-ASR через mlx-audio без промежуточного WAV.

### `run_asr_transcription`

```python
run_asr_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]
```

Выбирает подходящий локальный ASR backend по имени модели.

## Внутренние функции

### `_coerce_int`

```python
_coerce_int(value: object) -> int
```

_Внутренняя функция._

Преобразует вход в неотрицательное целое число.

### `_coerce_optional_text`

```python
_coerce_optional_text(value: object) -> str | None
```

_Внутренняя функция._

Преобразует произвольное значение в непустую строку.

### `_map_qwen_language`

```python
_map_qwen_language(language: str | None) -> str | None
```

_Внутренняя функция._

Преобразует языковой код приложения в имя языка для Qwen3-ASR.

### `_load_qwen_model_from_mlx_audio`

```python
_load_qwen_model_from_mlx_audio(model_name: str) -> Any
```

_Внутренняя функция._

Загружает Qwen3-ASR модель через mlx-audio.

### `_get_cached_qwen_model`

```python
_get_cached_qwen_model(model_name: str, model_loader: Any | None = None) -> Any
```

_Внутренняя функция._

Получает Qwen3-ASR модель через переданный или общий runtime-loader.

### `_normalize_qwen_segments`

```python
_normalize_qwen_segments(segments: object) -> list[dict[str, Any]]
```

_Внутренняя функция._

Приводит сегменты Qwen3-ASR к словарному формату приложения.
