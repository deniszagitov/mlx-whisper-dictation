# MLX Whisper Dictation

Офлайн-диктовка для macOS на Apple Silicon. Приложение живет в строке меню, записывает звук с микрофона, расшифровывает речь через MLX Whisper и вставляет результат в текущее активное поле ввода.

Проект ориентирован на локальный запуск на Mac и упаковывается в `.app` через `py2app`.

## Как это работает

1. Приложение запускается как menu bar app.
2. По глобальному хоткею начинается запись с микрофона.
3. После остановки записи аудио передается в `mlx_whisper.transcribe(...)`.
4. Распознанный текст вставляется в активное приложение.
5. Для вставки используется буфер обмена и `Cmd+V`, поэтому результат не зависит от текущей раскладки клавиатуры.

# TODO: придумать как сделать стриминг слов и может даже исправление голосом

Приложение не использует облачную диктовку macOS и не отправляет звук во внешний сервис. Расшифровка идет локально на машине.

## Что нужно для работы

- macOS на Apple Silicon.
- Homebrew.
- Homebrew Python 3.11.
- `portaudio`.
- Доступы `Microphone` и `Accessibility`.
- Иногда дополнительно нужен `Input Monitoring`, если macOS блокирует глобальные хоткеи или синтетический ввод.

## Локальная сборка приложения

Надежный локальный путь для этого проекта сейчас такой: собрать alias `.app` через `py2app -A`. Это обычный `.app`, но он использует текущее окружение проекта вместо полной standalone-заморозки всех зависимостей.

```bash
brew install portaudio
pyenv local 3.11.14
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install py2app==0.28.10 modulegraph
pip install -r requirements.txt
python setup.py py2app -A
```

После сборки приложение появится здесь:

```bash
dist/MLX Whisper Dictation.app
```

Запуск:

```bash
open "dist/MLX Whisper Dictation.app"
```

Если нужен запуск с выводом логов в терминал:

```bash
./dist/MLX\ Whisper\ Dictation.app/Contents/MacOS/MLX\ Whisper\ Dictation
```

## Почему именно Python 3.11

- В проекте зафиксирована `.python-version = 3.11.14`.
- Homebrew Python 3.11 является framework build, а это заметно лучше работает с `py2app` на macOS.
- Ранее `pyenv` Python 3.12 без framework давал менее пригодный результат для app bundle.

Если `.venv` уже был создан на другой версии Python, его лучше пересоздать перед сборкой.

## Запуск без упаковки

Если хотите сначала проверить приложение как обычный Python-скрипт:

```bash
source .venv/bin/activate
python whisper-dictation.py
```

## Хоткеи

По умолчанию на macOS используется:

```bash
cmd_l+alt
```

Поддерживаются комбинации из двух и более клавиш. Примеры:

```bash
python whisper-dictation.py -k cmd_l+shift+space
python whisper-dictation.py -k cmd_r+shift
python whisper-dictation.py -k ctrl+alt
```

Также можно включить режим по правой клавише Command:

```bash
python whisper-dictation.py --k_double_cmd
```

В этом режиме:

- двойное нажатие правой `Command` начинает запись
- одиночное нажатие правой `Command` останавливает запись

Если используете этот режим, отключите системный shortcut встроенной диктовки macOS, чтобы они не конфликтовали.

## Выбор модели

Текущий рекомендуемый вариант по умолчанию:

```bash
mlx-community/whisper-large-v3-turbo
```

Практические варианты для M3:

- `mlx-community/whisper-large-v3-turbo` как основной баланс качества и скорости
- `mlx-community/whisper-large-v3-mlx`, если качество важнее задержки
- `mlx-community/whisper-turbo`, если нужна минимальная задержка и допустима более слабая точность

Пример запуска:

```bash
python whisper-dictation.py -m mlx-community/whisper-large-v3-mlx -l ru
```

## Доступы macOS

Для собранного `.app` проверьте доступы:

- `Microphone`
- `Accessibility`

Если хоткей не реагирует или текст не вставляется, дополнительно проверьте:

- `Input Monitoring`

Важно: после переноса `.app` в другую папку macOS может считать его новым приложением. В этом случае доступы иногда нужно выдать заново.

## Автозапуск при входе

Если приложение уже собрано и работает, добавьте его в `Login Items`:

1. Откройте `System Settings`.
2. Перейдите в `General`.
3. Откройте `Login Items & Extensions`.
4. Добавьте `dist/MLX Whisper Dictation.app` или ту копию `.app`, которую вы перенесли в постоянную папку.

## Где смотреть логи

У приложения есть простые пользовательские логи:

```bash
~/Library/Logs/whisper-dictation/stdout.log
~/Library/Logs/whisper-dictation/stderr.log
```

Они полезны, если приложение запускается, но не вставляет текст или не видно ошибок в интерфейсе.

## Сборка в GitHub Actions

В репозитории есть workflow [ .github/workflows/build-macos-app.yml ](.github/workflows/build-macos-app.yml).

Он:

- запускается на `macos-14`
- ставит `portaudio`
- устанавливает Python-зависимости и `py2app`
- собирает `.app`
- загружает артефакт сборки

## Техническая основа

Проект держится близко к MLX Whisper API:

- используется прямой вызов `mlx_whisper.transcribe(audio, path_or_hf_repo=...)`
- модель задается как Hugging Face repo или локальный путь
- аудио пишется через `PyAudio`
- горячие клавиши и вставка реализованы через `pynput`
- приложение в строке меню реализовано через `rumps`
