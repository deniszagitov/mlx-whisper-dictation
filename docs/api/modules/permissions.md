# Разрешения macOS

Исходный runtime-модуль: `src/infrastructure/permissions.py`

Проверка и повторный запрос:

- `Accessibility`
- `Input Monitoring`
- системных уведомлений
- информации об активном приложении

## Архитектурная роль

- Concrete вызовы macOS остаются в infrastructure.
- `DictationApp` и use cases получают их через `SystemIntegrationService`.
- При проблемах с хоткеями или автовставкой этот слой остаётся первым местом для диагностики.
