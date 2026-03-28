# Горячие клавиши

Hotkey-логика теперь распределена по трём модулям:

- `src/domain/hotkeys.py`
  - Чистая нормализация и форматирование комбинаций.
- `src/infrastructure/hotkeys.py`
  - Глобальные listener'ы и macOS keyboard runtime.
- `src/adapters/hotkey_dialog.py`
  - NSAlert-диалог захвата новой комбинации.

## Роли

- `DictationApp` только хранит текущие комбинации и делегирует операции.
- `HotkeyManagementUseCases` меняет хоткеи и работает через injected factory listener'ов.
- `main.py` связывает concrete `GlobalKeyListener`/`MultiHotkeyListener` с use-case слоем.
