/* global React, ReactDOM */
const { useState, useEffect, useRef, useMemo } = React;

// ============================================================
// ИКОНКИ — все нарисованы вручную, простые SVG, без растровых картинок
// ============================================================

const Icon = ({ name, size = 16 }) => {
  const props = { width: size, height: size, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "home":
      return <svg {...props}><path d="M2.5 7L8 2.5 13.5 7v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1V7z"/><path d="M6.5 14V9.5h3V14"/></svg>;
    case "mic":
      return <svg {...props}><rect x="6" y="2" width="4" height="8" rx="2"/><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14M5.5 14h5"/></svg>;
    case "book":
      return <svg {...props}><path d="M2.5 3a1 1 0 0 1 1-1H7v12H3.5a1 1 0 0 1-1-1V3z"/><path d="M13.5 3a1 1 0 0 0-1-1H9v12h3.5a1 1 0 0 0 1-1V3z"/></svg>;
    case "keyboard":
      return <svg {...props}><rect x="1.5" y="4" width="13" height="8" rx="1.5"/><path d="M4 7h.01M6.5 7h.01M9 7h.01M11.5 7h.01M4 9.5h8"/></svg>;
    case "wave":
      return <svg {...props}><path d="M2 8h1.5M4.5 5.5v5M6.5 3v10M8.5 5.5v5M10.5 6.5v3M12.5 7.5v1M14 8h.5"/></svg>;
    case "robot":
      return <svg {...props}><rect x="3" y="5" width="10" height="8" rx="1.5"/><path d="M8 2v3M5.5 8.5h.01M10.5 8.5h.01M6 11.5h4"/><path d="M3 9H1.5M14.5 9H13"/></svg>;
    case "clock":
      return <svg {...props}><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1.5"/></svg>;
    case "shield":
      return <svg {...props}><path d="M8 1.5l5.5 2v4c0 3.5-2.5 6-5.5 7-3-1-5.5-3.5-5.5-7v-4l5.5-2z"/><path d="M5.5 8l2 2 3-3.5"/></svg>;
    case "info":
      return <svg {...props}><circle cx="8" cy="8" r="6"/><path d="M8 7.5v4M8 5.5v.01"/></svg>;
    case "text":
      return <svg {...props}><path d="M3 4.5V3h10v1.5M8 3v10M5.5 13h5"/></svg>;
    case "search":
      return <svg {...props}><circle cx="7" cy="7" r="4"/><path d="M10 10l3.5 3.5"/></svg>;
    case "play":
      return <svg {...props} fill="currentColor" stroke="none"><path d="M5 3.5L12 8l-7 4.5z"/></svg>;
    case "stop":
      return <svg {...props} fill="currentColor" stroke="none"><rect x="4" y="4" width="8" height="8" rx="1"/></svg>;
    case "check":
      return <svg {...props}><path d="M3 8l3.5 3.5 7-7"/></svg>;
    case "warn":
      return <svg {...props}><path d="M8 2L14.5 13.5h-13z"/><path d="M8 6.5v3M8 11.5v.01"/></svg>;
    case "chevron":
      return <svg {...props}><path d="M6 4l4 4-4 4"/></svg>;
    case "external":
      return <svg {...props}><path d="M9 3h4v4M13 3L7.5 8.5"/><path d="M11 9.5V13H3V5h3.5"/></svg>;
    case "copy":
      return <svg {...props}><rect x="5.5" y="5.5" width="8" height="8" rx="1"/><path d="M3 10.5V3.5a1 1 0 0 1 1-1h7"/></svg>;
    case "plus":
      return <svg {...props}><path d="M8 3.5v9M3.5 8h9"/></svg>;
    case "minus":
      return <svg {...props}><path d="M3.5 8h9"/></svg>;
    case "trash":
      return <svg {...props}><path d="M3 4.5h10M6 4.5V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5M4.5 4.5l.5 8a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1l.5-8"/></svg>;
    case "settings":
      return <svg {...props}><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M1.5 8h2M12.5 8h2M3.5 12.5l1.5-1.5M11 5l1.5-1.5"/></svg>;
    case "history":
      return <svg {...props}><path d="M3 8a5 5 0 1 0 1.5-3.5L3 6"/><path d="M3 3v3h3M8 5.5V8l2 1.5"/></svg>;
    case "globe":
      return <svg {...props}><circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/></svg>;
    case "speaker":
      return <svg {...props}><path d="M3 6h2.5L9 3v10L5.5 10H3z"/><path d="M11 6.5a2 2 0 0 1 0 3M12.5 4.5a4.5 4.5 0 0 1 0 7"/></svg>;
    case "eye":
      return <svg {...props}><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="1.5"/></svg>;
    default:
      return <svg {...props}><circle cx="8" cy="8" r="3"/></svg>;
  }
};

// Большая иконка приложения "Диктатор" — стилизованный микрофон в круге
const AppIcon = ({ size = 56 }) => (
  <svg width={size} height={size} viewBox="0 0 56 56" fill="none">
    <defs>
      <linearGradient id="appicon" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#5A9CFF"/>
        <stop offset="1" stopColor="#0A66E0"/>
      </linearGradient>
      <linearGradient id="appiconShine" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="rgba(255,255,255,0.45)"/>
        <stop offset="0.5" stopColor="rgba(255,255,255,0)"/>
      </linearGradient>
    </defs>
    <rect x="2" y="2" width="52" height="52" rx="13" fill="url(#appicon)"/>
    <rect x="2" y="2" width="52" height="22" rx="13" fill="url(#appiconShine)"/>
    <rect x="23" y="14" width="10" height="20" rx="5" fill="white"/>
    <path d="M17 27a11 11 0 0 0 22 0M28 38v5M22 43h12" stroke="white" strokeWidth="2.4" strokeLinecap="round" fill="none"/>
  </svg>
);

window.Icon = Icon;
window.AppIcon = AppIcon;
