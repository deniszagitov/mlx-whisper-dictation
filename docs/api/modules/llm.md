# LLM-обработка

LLM-часть теперь разделена так:

- `src/domain/llm_processing.py`
  - Чистая обработка ответа модели и правила использования clipboard-context.
- `src/use_cases/llm_pipeline.py`
  - Сценарий `запись -> Whisper -> LLM`.
- `src/infrastructure/llm_runtime.py`
  - `LlmGateway` и concrete runtime для MLX LLM, загрузки модели и cleanup памяти.

## Поток

1. `main.py` создаёт `LlmGateway`.
2. `DictationApp` делегирует LLM-поведение в `LlmPipelineUseCases`.
3. Use case вызывает gateway только через абстрактный интерфейс и обновляет snapshot приложения.
