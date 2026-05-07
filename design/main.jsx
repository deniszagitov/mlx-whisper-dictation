/* global React, ReactDOM, Icon, AppIcon, UI, Screens, useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakToggle, TweakSelect */
const { useState, useEffect, useMemo, useRef } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "glass": "medium",
  "density": "comfortable",
  "nav": "toolbar",
  "accent": "blue"
}/*EDITMODE-END*/;

const SECTIONS = [
  { id: "home", label: "Главная", icon: "home", group: 0 },
  { id: "recognition", label: "STT", icon: "mic", group: 1 },
  { id: "llm", label: "LLM", icon: "robot", group: 1 },
  { id: "reader", label: "TTS", icon: "speaker", group: 1 },
  { id: "rsvp", label: "RSVP", icon: "eye", group: 1 },
  { id: "input", label: "Ввод текста", icon: "text", group: 2 },
  { id: "hotkeys", label: "Хоткеи", icon: "keyboard", group: 2 },
  { id: "audio", label: "Аудио", icon: "wave", group: 2 },
  { id: "history", label: "История", icon: "history", group: 3 },
  { id: "permissions", label: "Доступы", icon: "shield", group: 3 },
  { id: "about", label: "О приложении", icon: "info", group: 3 },
];

const HOTKEY_LABELS = {
  primary: "Основная запись",
  secondary: "Дополнительная запись",
  llm: "LLM-пайплайн",
  rsvp: "RSVP",
  tts: "TTS",
};

function HotkeyRecorder({ open, title, onClose, onSave }) {
  const [keys, setKeys] = useState([]);
  useEffect(() => {
    if (!open) return;
    setKeys([]);
    const onDown = (e) => {
      e.preventDefault();
      const k = [];
      if (e.ctrlKey) k.push("⌃");
      if (e.altKey) k.push("⌥");
      if (e.shiftKey) k.push("⇧");
      if (e.metaKey) k.push("⌘");
      const main = e.key.length === 1 ? e.key.toUpperCase() : null;
      if (main && !["Control","Alt","Shift","Meta"].includes(e.key)) k.push(main);
      setKeys(k);
    };
    window.addEventListener("keydown", onDown);
    return () => window.removeEventListener("keydown", onDown);
  }, [open]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-icon"><Icon name="keyboard" size={22}/></div>
        <div className="modal-title">Запись хоткея</div>
        <div className="modal-sub">{title}</div>
        <div className="modal-keys">
          {keys.length === 0
            ? <span className="modal-keys-hint">Нажмите комбинацию клавиш…</span>
            : keys.map((k, i) => <span key={i} className="kbd kbd-large">{k}</span>)}
        </div>
        <div className="modal-actions">
          <UI.Button onClick={onClose}>Отмена</UI.Button>
          <UI.Button kind="primary" disabled={keys.length < 2} onClick={() => { onSave(keys); onClose(); }}>Сохранить</UI.Button>
        </div>
      </div>
    </div>
  );
}

function MenuBarMockup({ onOpenSettings, recording }) {
  return (
    <div className="menubar-mockup">
      <div className="menubar-strip">
        <div className="menubar-apple">􀣺</div>
        <div className="menubar-title">Pages</div>
        <div className="menubar-spacer"/>
        <div className="menubar-trayicon">{recording ? "🔴" : "⏯"}</div>
        <div className="menubar-trayicon">􀋙</div>
        <div className="menubar-trayicon">􀛨</div>
        <div className="menubar-clock">Чт 7 мая  14:32</div>
      </div>
      <div className="menubar-popover">
        <div className="mb-row mb-status"><span className="rec-dot-tiny"/>Готов слушать</div>
        <div className="mb-divider"/>
        <div className="mb-row mb-action"><span>Начать запись</span><span className="mb-kbd">⌘⌥</span></div>
        <div className="mb-row mb-action"><span>Запустить RSVP</span><span className="mb-kbd">⌃⇧⌥R</span></div>
        <div className="mb-row mb-action"><span>Запустить TTS</span><span className="mb-kbd">⌃⇧⌥S</span></div>
        <div className="mb-divider"/>
        <div className="mb-row mb-action mb-primary" onClick={onOpenSettings}><span>Открыть Диктатор…</span><span className="mb-kbd">⌘,</span></div>
        <div className="mb-divider"/>
        <div className="mb-row mb-action mb-quit"><span>Выйти</span><span className="mb-kbd">⌘Q</span></div>
      </div>
    </div>
  );
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  const [route, setRoute] = useState("home");
  const [search, setSearch] = useState("");
  const [hotkeyModal, setHotkeyModal] = useState({ open: false, id: null, title: "" });
  const [showMenuBar, setShowMenuBar] = useState(false);

  const [state, setState] = useState({
    recording: false,
    transcribing: false,
    elapsed: 0,
    model: "large-v3-turbo",
    language: "ru",
    maxTime: 30,
    performance: "balanced",
    cap: true,
    dropPeriod: true,
    chainDictation: true,
    readerLLM: true,
    wpm: 400,
    chunk: 2,
    fontSize: 64,
    ttsBackend: "apple",
    ttsModel: "qwen3-tts",
    ttsVoice: "auto",
    ttsRate: 1.0,
    ttsMax: 5,
    cgevent: true,
    ax: true,
    cmdv: true,
    privateMode: false,
    notifyStart: true,
    overlay: true,
    timeInMenuBar: false,
    mic: "macbook",
    audioProfile: "auto",
    normalize: true,
    autoclean: true,
    profiles: [
      { id: 1, name: "Дома · MacBook", desc: "MacBook Pro Microphone · MacBook HQ" },
      { id: 2, name: "Студия", desc: "Shure MV7 · Студийный профиль" },
    ],
    llmModel: "qwen2.5-3b",
    llmPrompt: "default",
    llmClipboard: false,
    permissions: { accessibility: true, input: true, microphone: true },
    history: [
      { id: 1, time: "14:21", words: 12, text: "Сделай ревью пулл-реквеста и оставь комментарии в Линеаре до пятницы." },
      { id: 2, time: "13:48", words: 6, text: "Запиши в обсидиан мысль про liquid glass." },
      { id: 3, time: "12:30", words: 24, text: "Привет, я думаю нам стоит перенести синк на четверг, потому что в среду я буду на конференции и не смогу нормально подключиться." },
      { id: 4, time: "11:05", words: 8, text: "Купить хлеб, молоко, яблоки и кофе по дороге домой." },
      { id: 5, time: "10:40", words: 4, text: "Начать новый проект диктатор." },
    ],
  });

  // обновляем таймер записи
  useEffect(() => {
    if (!state.recording) return;
    const iv = setInterval(() => setState((s) => ({ ...s, elapsed: s.elapsed + 1 })), 1000);
    return () => clearInterval(iv);
  }, [state.recording]);

  useEffect(() => {
    document.documentElement.dataset.theme = t.theme;
    document.documentElement.dataset.glass = t.glass;
    document.documentElement.dataset.density = t.density;
    document.documentElement.dataset.nav = t.nav;
    document.documentElement.dataset.accent = t.accent;
  }, [t.theme, t.glass, t.density, t.nav, t.accent]);

  const filteredSections = useMemo(() => {
    if (!search.trim()) return SECTIONS;
    const q = search.toLowerCase();
    return SECTIONS.filter((s) => s.label.toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [search]);

  const recordHotkey = (id, title) => setHotkeyModal({ open: true, id, title });

  const renderScreen = () => {
    const props = { state, setState, recordHotkey };
    switch (route) {
      case "home": return <Screens.HomeScreen {...props} setState={(s) => setState(s)}/>;
      case "recognition": return <Screens.RecognitionScreen {...props}/>;
      case "reader": return <Screens.TTSScreen {...props}/>;
      case "rsvp": return <Screens.RSVPScreen {...props}/>;
      case "input": return <Screens.TextInputScreen {...props}/>;
      case "hotkeys": return <Screens.HotkeysScreen {...props}/>;
      case "audio": return <Screens.AudioScreen {...props}/>;
      case "llm": return <Screens.LLMScreen {...props}/>;
      case "history": return <Screens.HistoryScreen {...props}/>;
      case "permissions": return <Screens.PermissionsScreen {...props}/>;
      case "about": return <Screens.AboutScreen/>;
      default: return null;
    }
  };

  // Прокси для setState из главного экрана с роутингом
  const setStateWithRoute = (next) => {
    if (next.route) {
      setRoute(next.route);
      const { route: _r, ...rest } = next;
      setState(rest);
    } else {
      setState(next);
    }
  };

  const currentSection = SECTIONS.find((s) => s.id === route);

  return (
    <div className="app-root" data-screen-label={"Settings · " + (currentSection?.label || "")}>
      {/* Декоративный фон обоев — для эффекта стекла */}
      <div className="wallpaper"/>

      <div className={"window window-" + t.nav}>
        {/* TRAFFIC LIGHTS */}
        <div className="traffic">
          <span className="tl tl-close"/>
          <span className="tl tl-min"/>
          <span className="tl tl-max"/>
        </div>

        {t.nav === "sidebar" ? (
          <>
            <aside className="sidebar">
              <div className="sidebar-top">
                <div className="search-mini">
                  <Icon name="search" size={12}/>
                  <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск"/>
                  <span className="search-mini-kbd">⌘F</span>
                </div>
              </div>
              <nav className="nav">
                {[0, 1, 2, 3].map((g) => {
                  const items = filteredSections.filter((s) => s.group === g);
                  if (items.length === 0) return null;
                  return (
                    <div key={g} className="nav-group">
                      {items.map((s) => (
                        <button key={s.id} className={"nav-item" + (route === s.id ? " active" : "")} onClick={() => setRoute(s.id)}>
                          <span className={"nav-icon nav-icon-" + s.id}><Icon name={s.icon} size={13}/></span>
                          <span className="nav-label">{s.label}</span>
                          {s.id === "permissions" && (!state.permissions.accessibility || !state.permissions.input) && (
                            <span className="nav-badge"/>
                          )}
                        </button>
                      ))}
                    </div>
                  );
                })}
              </nav>
              <div className="sidebar-foot" onClick={() => setShowMenuBar(true)}>
                <span className="sidebar-foot-icon">⌘</span>
                <div>
                  <div className="sidebar-foot-title">Иконка в menu bar</div>
                  <div className="sidebar-foot-sub">Посмотреть, что осталось</div>
                </div>
              </div>
            </aside>

            <main className="content">
              <header className="content-header">
                <div className="content-header-titles">
                  <h1 className="content-title">{currentSection?.label}</h1>
                </div>
              </header>
              <div className="content-scroll">
                {renderScreen()}
              </div>
            </main>
          </>
        ) : (
          <div className="window-toolbar-layout">
            <header className="toolbar">
              <div className="toolbar-tabs">
                {SECTIONS.map((s) => (
                  <button key={s.id} className={"toolbar-tab" + (route === s.id ? " active" : "")} onClick={() => setRoute(s.id)}>
                    <Icon name={s.icon} size={16}/>
                    <span>{s.label}</span>
                  </button>
                ))}
              </div>
            </header>
            <main className="content content-toolbar">
              <div className="content-scroll">
                <h1 className="content-title content-title-toolbar">{currentSection?.label}</h1>
                {renderScreen()}
              </div>
            </main>
          </div>
        )}
      </div>

      {/* Менюбар оверлей */}
      {showMenuBar && (
        <div className="menubar-overlay" onClick={() => setShowMenuBar(false)}>
          <MenuBarMockup onOpenSettings={() => setShowMenuBar(false)} recording={state.recording}/>
        </div>
      )}

      {/* Хоткей модал */}
      <HotkeyRecorder
        open={hotkeyModal.open}
        title={hotkeyModal.title}
        onClose={() => setHotkeyModal({ open: false, id: null, title: "" })}
        onSave={() => {}}
      />

      {/* Tweaks */}
      <TweaksPanel title="Tweaks">
        <TweakSection title="Внешний вид">
          <TweakRadio label="Тема" value={t.theme} onChange={(v) => setTweak("theme", v)} options={[
            { value: "light", label: "Светлая" },
            { value: "dark", label: "Тёмная" },
          ]}/>
          <TweakRadio label="Liquid Glass" value={t.glass} onChange={(v) => setTweak("glass", v)} options={[
            { value: "subtle", label: "Сдержанно" },
            { value: "medium", label: "Средне" },
            { value: "max", label: "Максимум" },
          ]}/>
          <TweakRadio label="Плотность" value={t.density} onChange={(v) => setTweak("density", v)} options={[
            { value: "comfortable", label: "Просторно" },
            { value: "compact", label: "Компактно" },
          ]}/>
        </TweakSection>
        <TweakSection title="Структура">
          <TweakRadio label="Навигация" value={t.nav} onChange={(v) => setTweak("nav", v)} options={[
            { value: "sidebar", label: "Sidebar" },
            { value: "toolbar", label: "Toolbar" },
          ]}/>
          <TweakSelect label="Акцент" value={t.accent} onChange={(v) => setTweak("accent", v)} options={[
            { value: "blue", label: "Синий (системный)" },
            { value: "purple", label: "Фиолетовый" },
            { value: "graphite", label: "Графит" },
            { value: "warm", label: "Тёплый" },
          ]}/>
        </TweakSection>
        <TweakSection title="Состояние">
          <TweakToggle label="Идёт запись" value={state.recording} onChange={(v) => setState({ ...state, recording: v, elapsed: 0 })}/>
          <TweakToggle label="Доступ Accessibility выдан" value={state.permissions.accessibility}
            onChange={(v) => setState({ ...state, permissions: { ...state.permissions, accessibility: v } })}/>
          <TweakToggle label="Доступ Input Monitoring выдан" value={state.permissions.input}
            onChange={(v) => setState({ ...state, permissions: { ...state.permissions, input: v } })}/>
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
