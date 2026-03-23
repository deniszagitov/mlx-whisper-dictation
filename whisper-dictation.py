"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Модуль содержит menu bar приложение, которое записывает звук с микрофона,
распознает речь локально через MLX Whisper и вставляет результат в активное
поле ввода.
"""

import argparse
import logging
import platform
import threading
import time
from typing import Any, cast

import AppKit
import mlx_whisper
import numpy as np
import pyaudio
import rumps
from pynput import keyboard

DEFAULT_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
MIN_HOTKEY_PARTS = 2
DOUBLE_COMMAND_PRESS_INTERVAL = 0.5
LOGGER = logging.getLogger(__name__)


def notify_user(title, message):
    """Показывает системное уведомление macOS.

    Args:
        title: Заголовок уведомления.
        message: Основной текст уведомления.
    """
    try:
        rumps.notification(title, "", message)
    except Exception:
        LOGGER.exception("Не удалось показать системное уведомление macOS")


def parse_key(key_name):
    """Преобразует строковое имя клавиши в объект pynput.

    Args:
        key_name: Имя клавиши, например `cmd_l`, `alt` или `space`.

    Returns:
        Объект клавиши или код символа, который понимает pynput.
    """
    return getattr(keyboard.Key, key_name, keyboard.KeyCode(char=key_name))


def parse_key_combination(key_combination):
    """Разбирает строку с комбинацией клавиш.

    Args:
        key_combination: Строка вида `cmd_l+alt` или `cmd_l+shift+space`.

    Returns:
        Кортеж объектов клавиш в том порядке, в котором они указаны.

    Raises:
        ValueError: Если в комбинации меньше двух клавиш.
    """
    parts = [part.strip() for part in key_combination.split("+") if part.strip()]
    if len(parts) < MIN_HOTKEY_PARTS:
        raise ValueError("Комбинация клавиш должна содержать как минимум две клавиши.")
    return tuple(parse_key(part) for part in parts)


class SpeechTranscriber:
    """Распознает аудио и вставляет текст в активное приложение.

    Attributes:
        pykeyboard: Контроллер клавиатуры pynput для вставки текста.
        model_name: Имя или путь к модели MLX Whisper.
    """

    def __init__(self, model_name):
        """Создает объект распознавания.

        Args:
            model_name: Имя модели Hugging Face или локальный путь к модели.
        """
        self.pykeyboard = keyboard.Controller()
        self.model_name = model_name

    def _paste_text(self, text):
        """Вставляет текст через буфер обмена и Cmd+V.

        Args:
            text: Текст для вставки в активное поле ввода.
        """
        appkit = cast("Any", AppKit)
        pasteboard = appkit.NSPasteboard.generalPasteboard()
        previous_text = pasteboard.stringForType_(appkit.NSPasteboardTypeString)

        pasteboard.clearContents()
        pasteboard.setString_forType_(text, appkit.NSPasteboardTypeString)
        time.sleep(0.05)

        with self.pykeyboard.pressed(keyboard.Key.cmd):
            self.pykeyboard.press("v")
            self.pykeyboard.release("v")

        time.sleep(0.05)

        pasteboard.clearContents()
        if previous_text is not None:
            pasteboard.setString_forType_(
                previous_text,
                appkit.NSPasteboardTypeString,
            )

    def transcribe(self, audio_data, language=None):
        """Распознает аудио и вставляет результат в активное приложение.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.
        """
        try:
            result = mlx_whisper.transcribe(
                audio_data,
                language=language,
                path_or_hf_repo=self.model_name,
            )
        except Exception:
            LOGGER.exception("Ошибка распознавания")
            notify_user(
                "MLX Whisper Dictation",
                "Ошибка распознавания. Смотрите stderr.log.",
            )
            return

        text = str(result.get("text", "")).lstrip()
        LOGGER.info("Распознавание завершено, длина текста=%s", len(text))

        if not text:
            LOGGER.info("Результат распознавания пустой")
            return

        try:
            self._paste_text(text)
            LOGGER.info("Текст вставлен через буфер обмена")
        except Exception:
            LOGGER.exception("Не удалось вставить через буфер обмена, переключаюсь на ввод клавишами")
            try:
                self.pykeyboard.type(text)
                LOGGER.info("Текст вставлен через резервный ввод клавишами")
            except Exception:
                LOGGER.exception("Резервный ввод клавишами тоже завершился ошибкой")
                notify_user(
                    "MLX Whisper Dictation",
                    "Не удалось вставить текст. Проверьте Accessibility и Input Monitoring.",
                )


class Recorder:
    """Записывает звук с микрофона и передает его в распознавание.

    Attributes:
        recording: Флаг активной записи.
        transcriber: Объект распознавания, который обрабатывает аудио.
    """

    def __init__(self, transcriber):
        """Создает объект записи.

        Args:
            transcriber: Экземпляр SpeechTranscriber для обработки записанного аудио.
        """
        self.recording = False
        self.transcriber = transcriber

    def start(self, language=None):
        """Запускает запись в отдельном потоке.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        thread = threading.Thread(target=self._record_impl, args=(language,))
        thread.daemon = True
        thread.start()

    def stop(self):
        """Останавливает активную запись."""
        self.recording = False

    def _record_impl(self, language):
        """Выполняет запись, конвертацию аудио и запуск распознавания.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        self.recording = True
        frames_per_buffer = 1024
        audio_interface = pyaudio.PyAudio()
        stream = None
        frames = []

        try:
            stream = audio_interface.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=frames_per_buffer,
                input=True,
            )

            while self.recording:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(data)
        except Exception:
            LOGGER.exception("Ошибка записи")
            notify_user(
                "MLX Whisper Dictation",
                "Ошибка записи с микрофона. Смотрите stderr.log.",
            )
            return
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()

        if not frames:
            LOGGER.warning("Запись остановлена без захваченных аудиофреймов")
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        self.transcriber.transcribe(audio_data_fp32, language)


class GlobalKeyListener:
    """Обрабатывает глобальную комбинацию клавиш для запуска диктовки.

    Attributes:
        app: Экземпляр StatusBarApp, которым управляет listener.
        keys: Кортеж клавиш, которые образуют хоткей.
        pressed_keys: Набор клавиш, зажатых в текущий момент.
        triggered: Флаг, защищающий от повторного срабатывания при удержании.
    """

    def __init__(self, app, key_combination):
        """Создает listener для заданной комбинации клавиш.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
            key_combination: Строка с комбинацией клавиш.
        """
        self.app = app
        self.keys = parse_key_combination(key_combination)
        self.pressed_keys = set()
        self.triggered = False

    def on_key_press(self, key):
        """Обрабатывает нажатие клавиши.

        Args:
            key: Объект клавиши из pynput.
        """
        if key in self.keys:
            self.pressed_keys.add(key)

        if not self.triggered and all(hotkey in self.pressed_keys for hotkey in self.keys):
            self.triggered = True
            self.app.toggle()

    def on_key_release(self, key):
        """Обрабатывает отпускание клавиши.

        Args:
            key: Объект клавиши из pynput.
        """
        self.pressed_keys.discard(key)
        if key in self.keys:
            self.triggered = False


class DoubleCommandKeyListener:
    """Обрабатывает режим управления через правую клавишу Command.

    Attributes:
        app: Экземпляр приложения, у которого будет вызван toggle.
        key: Клавиша, используемая для переключения записи.
        last_press_time: Время предыдущего нажатия для определения двойного клика.
    """

    def __init__(self, app):
        """Создает listener для режима двойного нажатия Command.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
        """
        self.app = app
        self.key = keyboard.Key.cmd_r
        self.last_press_time = 0.0

    def on_key_press(self, key):
        """Обрабатывает нажатие правой клавиши Command.

        Args:
            key: Объект клавиши из pynput.
        """
        is_listening = self.app.started
        if key == self.key:
            current_time = time.time()
            if is_listening or current_time - self.last_press_time < DOUBLE_COMMAND_PRESS_INTERVAL:
                self.app.toggle()
            self.last_press_time = current_time

    def on_key_release(self, key):
        """Игнорирует отпускание клавиши в этом режиме.

        Args:
            key: Объект клавиши из pynput.
        """
        del key


class StatusBarApp(rumps.App):
    """Menu bar приложение для управления записью и распознаванием.

    Attributes:
        languages: Доступные языки распознавания или None.
        current_language: Текущий выбранный язык или None.
        started: Флаг активной записи.
        recorder: Объект записи аудио.
        max_time: Максимальная длительность записи в секундах.
        elapsed_time: Количество секунд с начала текущей записи.
        status_timer: Таймер обновления индикатора в строке меню.
    """

    def __init__(self, recorder, languages=None, max_time=None):
        """Создает menu bar приложение.

        Args:
            recorder: Объект Recorder для записи и распознавания.
            languages: Необязательный список доступных языков.
            max_time: Необязательный лимит длительности записи в секундах.
        """
        super().__init__("whisper", "⏯")
        self.languages = languages
        self.current_language = languages[0] if languages is not None else None

        menu = ["Начать запись", "Остановить запись", None]

        if languages is not None:
            for lang in languages:
                callback = self.change_language if lang != self.current_language else None
                menu.append(rumps.MenuItem(lang, callback=callback))
            menu.append(None)

        self.menu = menu
        self._menu_item("Остановить запись").set_callback(None)

        self.started = False
        self.recorder = recorder
        self.max_time = max_time
        self.elapsed_time = 0
        self.status_timer = rumps.Timer(self.on_status_tick, 1)
        self.status_timer.start()

    def _menu_item(self, title):
        """Возвращает пункт меню по заголовку.

        Args:
            title: Текст пункта меню.

        Returns:
            Объект пункта меню из rumps.
        """
        return cast("Any", self.menu)[title]

    def change_language(self, sender):
        """Переключает текущий язык распознавания.

        Args:
            sender: Пункт меню, выбранный пользователем.
        """
        if self.languages is None:
            return

        self.current_language = sender.title
        for lang in self.languages:
            self._menu_item(lang).set_callback(self.change_language if lang != self.current_language else None)

    @rumps.clicked("Начать запись")
    def start_app(self, _):
        """Запускает запись и обновляет состояние интерфейса.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        print("Слушаю...")
        LOGGER.info("Запись началась")
        self.started = True
        self._menu_item("Начать запись").set_callback(None)
        self._menu_item("Остановить запись").set_callback(self.stop_app)
        self.recorder.start(self.current_language)

        self.start_time = time.time()
        self.on_status_tick(None)

    @rumps.clicked("Остановить запись")
    def stop_app(self, _):
        """Останавливает запись и запускает этап распознавания.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        if not self.started:
            return

        print("Распознаю...")
        LOGGER.info("Запись остановлена, запускаю распознавание")
        self.title = "⏯"
        self.started = False
        self._menu_item("Остановить запись").set_callback(None)
        self._menu_item("Начать запись").set_callback(self.start_app)
        self.recorder.stop()
        print("Готово.\n")

    def on_status_tick(self, _):
        """Обновляет индикатор времени записи в строке меню.

        Args:
            _: Аргумент timer callback, который здесь не используется.
        """
        if not self.started:
            return

        self.elapsed_time = int(time.time() - self.start_time)
        minutes, seconds = divmod(self.elapsed_time, 60)
        self.title = f"({minutes:02d}:{seconds:02d}) 🔴"

        if self.max_time is not None and self.elapsed_time >= self.max_time:
            self.stop_app(None)

    def toggle(self):
        """Переключает приложение между состояниями записи и ожидания."""
        if self.started:
            self.stop_app(None)
        else:
            self.start_app(None)


def parse_args():
    """Разбирает аргументы командной строки.

    Returns:
        Пространство имен argparse с настройками запуска приложения.

    Raises:
        SystemExit: Если передана некорректная комбинация клавиш.
        ValueError: Если выбран несовместимый язык для модели с суффиксом `.en`.
    """
    parser = argparse.ArgumentParser(
        description=("Приложение диктовки на базе MLX Whisper. По умолчанию комбинация cmd+option запускает и останавливает диктовку.")
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="Локальный путь к модели MLX или Hugging Face repo для распознавания.",
    )
    parser.add_argument(
        "-k",
        "--key_combination",
        type=str,
        default="cmd_l+alt" if platform.system() == "Darwin" else "ctrl+alt",
        help=(
            "Комбинация клавиш для запуска и остановки приложения. "
            "Примеры: cmd_l+alt, cmd_l+shift+space, ctrl+alt. "
            "По умолчанию: cmd_l+alt на macOS и ctrl+alt на остальных платформах."
        ),
    )
    parser.add_argument(
        "--k_double_cmd",
        action="store_true",
        help=(
            "Если флаг включен, приложение использует двойное нажатие правой Command "
            "для старта записи и одиночное нажатие для остановки. "
            "Параметр --key_combination при этом игнорируется."
        ),
    )
    parser.add_argument(
        "-l",
        "--language",
        type=str,
        default=None,
        help=(
            'Двухбуквенный код языка, например "en" или "ru", который помогает '
            "улучшить точность распознавания. Это особенно полезно для более компактных моделей. "
            "Полный список языков есть в официальном списке Whisper: "
            "https://github.com/openai/whisper/blob/main/whisper/tokenizer.py."
        ),
    )
    parser.add_argument(
        "-t",
        "--max_time",
        type=float,
        default=30,
        help=(
            "Максимальная длительность записи в секундах. "
            "После этого времени приложение автоматически остановит запись. "
            "По умолчанию: 30 секунд."
        ),
    )

    args = parser.parse_args()

    if not args.k_double_cmd:
        try:
            parse_key_combination(args.key_combination)
        except ValueError as error:
            parser.error(str(error))

    if args.language is not None:
        args.language = args.language.split(",")

    if args.model.endswith(".en") and args.language is not None and any(lang != "en" for lang in args.language):
        raise ValueError("Для модели с суффиксом .en нельзя указывать язык, отличный от английского.")

    return args


def main():
    """Запускает приложение диктовки и глобальные обработчики клавиш."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args()

    transcriber = SpeechTranscriber(args.model)
    recorder = Recorder(transcriber)

    app = StatusBarApp(recorder, args.language, args.max_time)
    key_listener = DoubleCommandKeyListener(app) if args.k_double_cmd else GlobalKeyListener(app, args.key_combination)
    listener = keyboard.Listener(
        on_press=key_listener.on_key_press,
        on_release=key_listener.on_key_release,
    )
    listener.start()

    print(f"Запуск с моделью: {args.model}")
    if args.k_double_cmd:
        print("Хоткей: двойное нажатие правой Command для старта и одиночное для остановки")
    else:
        print(f"Хоткей: {args.key_combination}")
    app.run()


if __name__ == "__main__":
    main()
