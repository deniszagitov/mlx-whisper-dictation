/* global React, Icon, AppIcon */
const { useState, useRef, useEffect } = React;

// ============================================================
// ОБЩИЕ КОМПОНЕНТЫ
// ============================================================

const Section = ({ title, footer, children }) => (
  <section className="section">
    {title && <h3 className="section-title">{title}</h3>}
    <div className="section-card">{children}</div>
    {footer && <p className="section-footer">{footer}</p>}
  </section>
);

const Row = ({ icon, title, subtitle, children, onClick, last }) => (
  <div className={"row" + (onClick ? " row-clickable" : "") + (last ? " row-last" : "")} onClick={onClick}>
    {icon && <div className="row-icon">{icon}</div>}
    <div className="row-text">
      <div className="row-title">{title}</div>
      {subtitle && <div className="row-subtitle">{subtitle}</div>}
    </div>
    <div className="row-control">{children}</div>
  </div>
);

const Toggle = ({ on, onChange }) => (
  <button className={"toggle" + (on ? " on" : "")} onClick={(e) => { e.stopPropagation(); onChange?.(!on); }} aria-pressed={on}>
    <span className="toggle-thumb"/>
  </button>
);

const Pill = ({ value, options, onChange }) => (
  <div className="pill-group">
    {options.map((opt) => (
      <button key={opt.value} className={"pill" + (value === opt.value ? " on" : "")} onClick={() => onChange(opt.value)}>
        {opt.label}
      </button>
    ))}
  </div>
);

const Select = ({ value, options, onChange, width }) => (
  <div className="select-wrap" style={{ minWidth: width || 160 }}>
    <select value={value} onChange={(e) => onChange(e.target.value)} className="select">
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
    <Icon name="chevron" size={11}/>
  </div>
);

const Stepper = ({ value, label, onDec, onInc }) => (
  <div className="stepper">
    <button className="stepper-btn" onClick={onDec}><Icon name="minus" size={11}/></button>
    <span className="stepper-value">{label}</span>
    <button className="stepper-btn" onClick={onInc}><Icon name="plus" size={11}/></button>
  </div>
);

const KbdKey = ({ children }) => <span className="kbd">{children}</span>;

const Hotkey = ({ keys }) => (
  <span className="hotkey">{keys.map((k, i) => <KbdKey key={i}>{k}</KbdKey>)}</span>
);

const Status = ({ tone, children }) => (
  <span className={"status status-" + tone}>
    <span className="status-dot"/>{children}
  </span>
);

const Button = ({ kind = "secondary", icon, children, onClick, disabled }) => (
  <button className={"btn btn-" + kind} onClick={onClick} disabled={disabled}>
    {icon && <Icon name={icon} size={12}/>}
    {children}
  </button>
);

window.UI = { Section, Row, Toggle, Pill, Select, Stepper, KbdKey, Hotkey, Status, Button };

// ============================================================
// ЭКРАНЫ
// ============================================================

const HomeScreen = ({ state, setState }) => {
  const recording = state.recording;
  return (
    <>
      {(!state.permissions.accessibility || !state.permissions.input) && (
        <div className="banner">
          <div className="banner-icon"><Icon name="warn" size={14}/></div>
          <div className="banner-text">
            <strong>Не все разрешения предоставлены</strong>
            <span>Без них хоткеи и автовставка работать не будут.</span>
          </div>
          <Button kind="primary" onClick={() => setState({ ...state, route: "permissions" })}>Перейти к доступам</Button>
        </div>
      )}

      <div className="hero-card">
        <div className="hero-status">
          {recording ? (
            <>
              <span className="rec-dot"/>
              <span>Запись… <span className="hero-time">{state.elapsed}s</span></span>
            </>
          ) : state.transcribing ? (
            <><Icon name="robot" size={14}/><span>Распознавание…</span></>
          ) : (
            <><span className="idle-dot"/><span>Готов слушать</span></>
          )}
        </div>

        <button className={"record-btn" + (recording ? " recording" : "")} onClick={() => setState({ ...state, recording: !recording, elapsed: 0 })}>
          <span className="record-btn-icon">
            {recording ? <Icon name="stop" size={28}/> : <Icon name="mic" size={28}/>}
          </span>
          <span className="record-btn-label">{recording ? "Остановить" : "Начать запись"}</span>
          <span className="record-btn-hotkey"><KbdKey>⌘</KbdKey><KbdKey>⌥</KbdKey></span>
        </button>

        <div className="hero-meta">
          <div className="hero-meta-item">
            <span className="hero-meta-label">Модель</span>
            <span className="hero-meta-value">large-v3-turbo</span>
          </div>
          <div className="hero-meta-divider"/>
          <div className="hero-meta-item">
            <span className="hero-meta-label">Язык</span>
            <span className="hero-meta-value">Русский</span>
          </div>
          <div className="hero-meta-divider"/>
          <div className="hero-meta-item">
            <span className="hero-meta-label">Лимит</span>
            <span className="hero-meta-value">30 сек</span>
          </div>
        </div>
      </div>

      <Section title="Быстрые действия">
        <Row icon={<Icon name="eye"/>} title="Запустить RSVP" subtitle="Чтение из буфера обмена пословно">
          <Hotkey keys={["⌃","⇧","⌥","R"]}/>
          <Button icon="play" onClick={() => {}}>Запустить</Button>
        </Row>
        <Row icon={<Icon name="speaker"/>} title="Запустить TTS" subtitle="Озвучить текст из буфера">
          <Hotkey keys={["⌃","⇧","⌥","T"]}/>
          <Button icon="play" onClick={() => {}}>Запустить</Button>
        </Row>
        <Row icon={<Icon name="robot"/>} title="LLM-обработка диктовки" subtitle="Голос → Whisper → LLM → буфер" last>
          <Hotkey keys={["⌃","⇧","⌥","L"]}/>
        </Row>
      </Section>

      <Section title="Сегодня">
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-label">Распознано</span>
            <span className="stat-value">14</span>
            <span className="stat-sub">диктовок</span>
          </div>
          <div className="stat">
            <span className="stat-label">Слов вставлено</span>
            <span className="stat-value">1 248</span>
            <span className="stat-sub">≈ 8 минут речи</span>
          </div>
          <div className="stat">
            <span className="stat-label">Токены LLM</span>
            <span className="stat-value">23 410</span>
            <span className="stat-sub">локально</span>
          </div>
        </div>
      </Section>
    </>
  );
};

const RecognitionScreen = ({ state, setState }) => (
  <>
    <Section title="Модель" footer="Модели хранятся локально и не отправляют данные в облако.">
      <Row icon={<Icon name="robot"/>} title="Whisper-модель" subtitle="Качество ↑, скорость ↓ при увеличении">
        <Select value={state.model} onChange={(v) => setState({ ...state, model: v })} options={[
          { value: "tiny", label: "tiny" },
          { value: "base", label: "base" },
          { value: "small", label: "small" },
          { value: "medium", label: "medium" },
          { value: "large-v3", label: "large-v3" },
          { value: "large-v3-turbo", label: "large-v3-turbo" },
        ]}/>
      </Row>
      <Row icon={<Icon name="globe"/>} title="Язык распознавания">
        <Select value={state.language} onChange={(v) => setState({ ...state, language: v })} options={[
          { value: "auto", label: "Автоопределение" },
          { value: "ru", label: "Русский" },
          { value: "en", label: "Английский" },
          { value: "de", label: "Немецкий" },
          { value: "es", label: "Испанский" },
        ]}/>
      </Row>
      <Row icon={<Icon name="clock"/>} title="Длительность записи" subtitle="После лимита запись остановится автоматически" last>
        <Pill value={state.maxTime} onChange={(v) => setState({ ...state, maxTime: v })} options={[
          { value: 15, label: "15 с" },
          { value: 30, label: "30 с" },
          { value: 60, label: "1 мин" },
          { value: 120, label: "2 мин" },
          { value: 0, label: "∞" },
        ]}/>
      </Row>
    </Section>

    <Section title="Производительность">
      <Row title="Режим работы" subtitle="Балансирует точность и нагрузку на Apple Silicon" last>
        <Pill value={state.performance} onChange={(v) => setState({ ...state, performance: v })} options={[
          { value: "eco", label: "Эко" },
          { value: "balanced", label: "Баланс" },
          { value: "max", label: "Максимум" },
        ]}/>
      </Row>
    </Section>

    <Section title="Постобработка текста" footer="Применяется к распознанному тексту перед вставкой.">
      <Row title="Первая буква с заглавной">
        <Toggle on={state.cap} onChange={(v) => setState({ ...state, cap: v })}/>
      </Row>
      <Row title="Убирать точку в конце одного предложения" subtitle="Если диктовка из одного предложения">
        <Toggle on={state.dropPeriod} onChange={(v) => setState({ ...state, dropPeriod: v })}/>
      </Row>
      <Row title="Связывать диктовки в цепочку" subtitle="Восстанавливать точку, если следом ещё одна диктовка" last>
        <Toggle on={state.chainDictation} onChange={(v) => setState({ ...state, chainDictation: v })}/>
      </Row>
    </Section>
  </>
);

const TTSScreen = ({ state, setState }) => (
  <>
    <Section title="TTS — озвучивание" footer="Читает текст из системного буфера обмена. Содержимое буфера не изменяется.">
      <Row icon={<Icon name="speaker"/>} title="Запустить TTS" subtitle="Зачитать текст из буфера голосом">
        <Hotkey keys={["⌃","⇧","⌥","S"]}/>
        <Button icon="play">Запустить</Button>
      </Row>
      <Row icon={<Icon name="robot"/>} title="LLM-предобработка" subtitle="Чистит и нормализует текст перед чтением" last>
        <Toggle on={state.readerLLM} onChange={(v) => setState({ ...state, readerLLM: v })}/>
      </Row>
    </Section>

    <Section title="Голос">
      <Row title="Backend">
        <Pill value={state.ttsBackend} onChange={(v) => setState({ ...state, ttsBackend: v })} options={[
          { value: "apple", label: "Apple" },
          { value: "mlx", label: "MLX" },
        ]}/>
      </Row>
      {state.ttsBackend === "mlx" && (
        <Row title="MLX-модель" subtitle="Локальная модель синтеза">
          <Select width={220} value={state.ttsModel} onChange={(v) => setState({ ...state, ttsModel: v })} options={[
            { value: "qwen3-tts", label: "Qwen3-TTS-12Hz-1.7B" },
            { value: "kokoro", label: "Kokoro-82M" },
          ]}/>
        </Row>
      )}
      <Row title="Голос">
        <Select width={200} value={state.ttsVoice} onChange={(v) => setState({ ...state, ttsVoice: v })} options={[
          { value: "auto", label: "Авто (русский)" },
          { value: "milena", label: "Milena (ru-RU)" },
          { value: "yuri", label: "Yuri (ru-RU)" },
          { value: "samantha", label: "Samantha (en-US)" },
        ]}/>
      </Row>
      {state.ttsBackend === "mlx" && (
        <Row title="Описание MLX-голоса" subtitle="Текстовый промпт для нейросинтеза" last={false}>
          <Button icon="text">Изменить…</Button>
        </Row>
      )}
      <Row title="Скорость речи" last>
        <Stepper value={state.ttsRate} label={state.ttsRate.toFixed(2) + "×"}
          onDec={() => setState({ ...state, ttsRate: Math.max(0.5, +(state.ttsRate - 0.1).toFixed(2)) })}
          onInc={() => setState({ ...state, ttsRate: Math.min(2.0, +(state.ttsRate + 0.1).toFixed(2)) })}/>
      </Row>
    </Section>

    <Section title="Лимиты">
      <Row title="Максимальная длительность" subtitle="Принудительно остановить через" last>
        <Pill value={state.ttsMax} onChange={(v) => setState({ ...state, ttsMax: v })} options={[
          { value: 5, label: "5 мин" }, { value: 15, label: "15 мин" }, { value: 30, label: "30 мин" }, { value: 0, label: "∞" },
        ]}/>
      </Row>
    </Section>
  </>
);

const RSVPScreen = ({ state, setState }) => (
  <>
    <Section title="RSVP — пословное чтение" footer="Слова мелькают в центре экрана с фокусом на оптимальной точке распознавания. Текст берётся из буфера обмена.">
      <Row icon={<Icon name="eye"/>} title="Запустить RSVP" subtitle="Запустить чтение из буфера">
        <Hotkey keys={["⌃","⇧","⌥","R"]}/>
        <Button icon="play">Запустить</Button>
      </Row>
      <Row icon={<Icon name="robot"/>} title="LLM-предобработка" subtitle="Очищает разметку и сноски перед показом" last>
        <Toggle on={state.readerLLM} onChange={(v) => setState({ ...state, readerLLM: v })}/>
      </Row>
    </Section>

    <Section title="Параметры чтения">
      <Row title="Скорость чтения" subtitle="Слов в минуту">
        <Stepper value={state.wpm} label={state.wpm + " wpm"}
          onDec={() => setState({ ...state, wpm: Math.max(150, state.wpm - 50) })}
          onInc={() => setState({ ...state, wpm: Math.min(900, state.wpm + 50) })}/>
      </Row>
      <Row title="Размер chunk-а" subtitle="Сколько слов показывать одновременно">
        <Pill value={state.chunk} onChange={(v) => setState({ ...state, chunk: v })} options={[
          { value: 1, label: "1" }, { value: 2, label: "2" }, { value: 3, label: "3" }, { value: 4, label: "4" },
        ]}/>
      </Row>
      <Row title="Размер шрифта" last>
        <Pill value={state.fontSize} onChange={(v) => setState({ ...state, fontSize: v })} options={[
          { value: 48, label: "48" }, { value: 64, label: "64" }, { value: 80, label: "80" }, { value: 96, label: "96" },
        ]}/>
      </Row>
    </Section>
  </>
);

const HotkeysScreen = ({ state, setState, recordHotkey }) => (
  <Section title="Глобальные хоткеи" footer="Хоткеи работают, даже когда Диктатор не в фокусе. Требует разрешения Input Monitoring и Accessibility.">
    {[
      { id: "primary", title: "Основная запись", subtitle: "Старт и стоп диктовки", keys: ["⌘","⌥"] },
      { id: "secondary", title: "Дополнительная запись", subtitle: "На случай конфликтов с другими приложениями", keys: ["⌃","⇧","⌥","T"] },
      { id: "llm", title: "LLM-пайплайн", subtitle: "Голос → Whisper → LLM → буфер", keys: ["⌃","⇧","⌥","L"] },
      { id: "rsvp", title: "RSVP", subtitle: "Запустить пословное чтение из буфера", keys: ["⌃","⇧","⌥","R"] },
      { id: "tts", title: "TTS", subtitle: "Озвучить текст из буфера", keys: ["⌃","⇧","⌥","S"], last: true },
    ].map((h) => (
      <Row key={h.id} title={h.title} subtitle={h.subtitle} last={h.last}>
        <Hotkey keys={h.keys}/>
        <Button onClick={() => recordHotkey(h.id, h.title)}>Изменить…</Button>
      </Row>
    ))}
  </Section>
);

const TextInputScreen = ({ state, setState }) => (
  <>
    <Section title="Метод вставки" footer="Если первый метод не сработает, Диктатор перейдёт к следующему. Текст всегда сохраняется в буфер обмена.">
      <Row title="Прямой ввод" subtitle="CGEvent — печатает текст в активное поле">
        <Toggle on={state.cgevent} onChange={(v) => setState({ ...state, cgevent: v })}/>
      </Row>
      <Row title="Accessibility API" subtitle="Вставка через AX — самый надёжный способ">
        <Toggle on={state.ax} onChange={(v) => setState({ ...state, ax: v })}/>
      </Row>
      <Row title="Буфер обмена + ⌘V" subtitle="Резервный способ" last>
        <Toggle on={state.cmdv} onChange={(v) => setState({ ...state, cmdv: v })}/>
      </Row>
    </Section>

    <Section title="Приватность">
      <Row title="Приватный режим" subtitle="Не сохранять историю распознанного текста" last>
        <Toggle on={state.privateMode} onChange={(v) => setState({ ...state, privateMode: v })}/>
      </Row>
    </Section>

    <Section title="Индикация записи">
      <Row title="Уведомление о старте записи">
        <Toggle on={state.notifyStart} onChange={(v) => setState({ ...state, notifyStart: v })}/>
      </Row>
      <Row title="Индикатор у курсора" subtitle="Маленькая точка возле текущей точки ввода">
        <Toggle on={state.overlay} onChange={(v) => setState({ ...state, overlay: v })}/>
      </Row>
      <Row title="Время записи в menu bar" last>
        <Toggle on={state.timeInMenuBar} onChange={(v) => setState({ ...state, timeInMenuBar: v })}/>
      </Row>
    </Section>
  </>
);

const AudioScreen = ({ state, setState }) => (
  <>
    <Section title="Микрофон">
      <Row icon={<Icon name="mic"/>} title="Устройство ввода">
        <Select width={220} value={state.mic} onChange={(v) => setState({ ...state, mic: v })} options={[
          { value: "default", label: "Системный по умолчанию" },
          { value: "macbook", label: "MacBook Pro Microphone" },
          { value: "airpods", label: "AirPods Pro" },
          { value: "shure", label: "Shure MV7 (USB)" },
        ]}/>
      </Row>
      <Row title="Профиль" subtitle="Адаптация к типу микрофона" last>
        <Select width={180} value={state.audioProfile} onChange={(v) => setState({ ...state, audioProfile: v })} options={[
          { value: "auto", label: "Автоматически" },
          { value: "macbook_hq", label: "MacBook HQ" },
          { value: "studio", label: "Студийный" },
          { value: "headset", label: "Гарнитура" },
        ]}/>
      </Row>
    </Section>

    <Section title="Уровни">
      <Row title="Бережная нормализация" subtitle="Подтягивает тихую речь, не ломая громкую">
        <Toggle on={state.normalize} onChange={(v) => setState({ ...state, normalize: v })}/>
      </Row>
      <Row title="Voice Isolation" subtitle="Включается вручную в Control Center macOS" last>
        <span className="hint-text">Системная настройка</span>
      </Row>
    </Section>

    <Section title="Файлы записей" footer="WAV-записи хранятся локально для диагностики и могут пригодиться при отладке.">
      <Row title="Автоочистка через 24 часа">
        <Toggle on={state.autoclean} onChange={(v) => setState({ ...state, autoclean: v })}/>
      </Row>
      <Row title="Папка WAV-записей" last>
        <Button icon="external">Открыть в Finder</Button>
      </Row>
    </Section>

    <Section title="Быстрые профили" footer="Сохранить текущий микрофон + настройки как профиль для быстрого переключения.">
      {state.profiles.map((p, i) => (
        <Row key={p.id} title={p.name} subtitle={p.desc} last={i === state.profiles.length - 1 && !state.profiles.length}>
          <Button>Применить</Button>
          <button className="icon-btn"><Icon name="trash" size={13}/></button>
        </Row>
      ))}
      <Row title="Добавить текущий профиль" last>
        <Button icon="plus">Добавить…</Button>
      </Row>
    </Section>
  </>
);

const LLMScreen = ({ state, setState }) => (
  <>
    <Section title="Модель LLM" footer="Локальная LLM используется для постобработки диктовки и предобработки Reader.">
      <Row icon={<Icon name="robot"/>} title="Активная модель">
        <Select width={240} value={state.llmModel} onChange={(v) => setState({ ...state, llmModel: v })} options={[
          { value: "qwen2.5-3b", label: "Qwen2.5-3B-Instruct (4-bit)" },
          { value: "qwen2.5-7b", label: "Qwen2.5-7B-Instruct (4-bit)" },
          { value: "llama-3.2-3b", label: "Llama-3.2-3B-Instruct" },
          { value: "phi-3.5-mini", label: "Phi-3.5-mini" },
        ]}/>
      </Row>
      <Row title="Системный промпт">
        <Select width={200} value={state.llmPrompt} onChange={(v) => setState({ ...state, llmPrompt: v })} options={[
          { value: "default", label: "По умолчанию" },
          { value: "email", label: "Деловое письмо" },
          { value: "code", label: "Технический текст" },
          { value: "translate-en", label: "Перевод на английский" },
          { value: "custom", label: "Свой…" },
        ]}/>
      </Row>
      <Row title="Использовать буфер обмена" subtitle="Передавать LLM содержимое буфера как контекст" last>
        <Toggle on={state.llmClipboard} onChange={(v) => setState({ ...state, llmClipboard: v })}/>
      </Row>
    </Section>

    <Section title="Загрузка">
      <Row title="Qwen2.5-3B-Instruct" subtitle="Загружено локально">
        <Status tone="ok">2.1 ГБ • готово</Status>
      </Row>
      <Row title="Qwen2.5-7B-Instruct" subtitle="Не загружено" last>
        <Button icon="external">Скачать (4.5 ГБ)</Button>
      </Row>
    </Section>

    <Section title="Расход токенов">
      <div className="tokens-card">
        <div className="tokens-big">23 410</div>
        <div className="tokens-sub">токенов обработано локально за всё время</div>
        <div className="tokens-bars">
          <div className="tokens-bar">
            <span>Сегодня</span>
            <div className="tokens-bar-track"><div style={{ width: "24%" }}/></div>
            <span>5 612</span>
          </div>
          <div className="tokens-bar">
            <span>На неделе</span>
            <div className="tokens-bar-track"><div style={{ width: "62%" }}/></div>
            <span>14 480</span>
          </div>
          <div className="tokens-bar">
            <span>Этот месяц</span>
            <div className="tokens-bar-track"><div style={{ width: "100%" }}/></div>
            <span>23 410</span>
          </div>
        </div>
      </div>
    </Section>
  </>
);

const HistoryScreen = ({ state, setState }) => {
  const [query, setQuery] = useState("");
  const items = state.history.filter(h => h.text.toLowerCase().includes(query.toLowerCase()));
  return (
    <>
      <div className="search-bar">
        <Icon name="search" size={13}/>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по истории…"/>
        {query && <button className="search-clear" onClick={() => setQuery("")}>✕</button>}
      </div>
      <Section footer="История хранится локально 7 дней и автоматически очищается. В приватном режиме история не пишется.">
        {items.length === 0 ? (
          <div className="empty">
            <div className="empty-icon"><Icon name="history" size={28}/></div>
            <div className="empty-title">Ничего не найдено</div>
            <div className="empty-sub">Попробуйте изменить запрос</div>
          </div>
        ) : items.map((h, i) => (
          <Row key={h.id} title={h.text} subtitle={h.time + " · " + h.words + " слов"} last={i === items.length - 1}>
            <button className="icon-btn" title="Скопировать"><Icon name="copy" size={13}/></button>
            <button className="icon-btn" title="Удалить"><Icon name="trash" size={13}/></button>
          </Row>
        ))}
      </Section>
    </>
  );
};

const PermissionsScreen = ({ state, setState }) => {
  const setPerm = (k, v) => setState({ ...state, permissions: { ...state.permissions, [k]: v } });
  const items = [
    { id: "accessibility", title: "Accessibility", desc: "Нужен для автовставки текста в активное поле и работы хоткеев.", panel: "Privacy & Security → Accessibility" },
    { id: "input", title: "Input Monitoring", desc: "Позволяет отслеживать глобальные сочетания клавиш.", panel: "Privacy & Security → Input Monitoring" },
    { id: "microphone", title: "Microphone", desc: "Без доступа к микрофону диктовка работать не будет.", panel: "Privacy & Security → Microphone" },
  ];
  return (
    <>
      <Section title="Разрешения macOS" footer="Все разрешения настраиваются в System Settings. Диктатор только просит и проверяет статус.">
        {items.map((p, i) => (
          <Row key={p.id} title={p.title} subtitle={p.desc} last={i === items.length - 1}>
            {state.permissions[p.id]
              ? <Status tone="ok">Предоставлено</Status>
              : <Status tone="warn">Не предоставлено</Status>}
            <Button onClick={() => setPerm(p.id, !state.permissions[p.id])}>
              {state.permissions[p.id] ? "Открыть…" : "Запросить…"}
            </Button>
          </Row>
        ))}
      </Section>

      <Section title="Если хоткей не работает" footer="Чаще всего после обновления .app нужно снять и заново выдать разрешения. Это известное поведение macOS.">
        <Row title="Снять и заново выдать разрешения" subtitle="Удаляет Диктатор из списков и просит macOS заново">
          <Button>Сбросить…</Button>
        </Row>
        <Row title="Открыть System Settings" last>
          <Button icon="external">Открыть</Button>
        </Row>
      </Section>
    </>
  );
};

const AboutScreen = () => (
  <>
    <div className="about-hero">
      <AppIcon size={84}/>
      <div className="about-name">Диктатор</div>
      <div className="about-tagline">Локальная диктовка для macOS на MLX Whisper</div>
      <div className="about-version">Версия 0.9.2 · Apple Silicon</div>
    </div>

    <Section title="О приложении">
      <Row title="Локальное распознавание" subtitle="MLX Whisper — без облака и без отправки данных">
        <Status tone="ok">Офлайн</Status>
      </Row>
      <Row title="Открытый исходный код" subtitle="github.com/deniszagitov/mlx-whisper-dictation">
        <Button icon="external">Открыть</Button>
      </Row>
      <Row title="Лицензия" last>
        <span className="hint-text">MIT</span>
      </Row>
    </Section>

    <Section title="Диагностика">
      <Row title="Открыть логи" subtitle="~/Library/Logs/whisper-dictation/">
        <Button icon="external">Открыть</Button>
      </Row>
      <Row title="Скопировать системную информацию" subtitle="Версии MLX, модели, разрешения" last>
        <Button icon="copy">Скопировать</Button>
      </Row>
    </Section>
  </>
);

window.Screens = { HomeScreen, RecognitionScreen, TTSScreen, RSVPScreen, HotkeysScreen, TextInputScreen, AudioScreen, LLMScreen, HistoryScreen, PermissionsScreen, AboutScreen };
