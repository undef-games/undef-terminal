/**
 * UndefTerminal - Embeddable xterm.js WebSocket terminal widget.
 *
 * Usage:
 *   const term = new UndefTerminal(containerEl, { wsUrl: '/ws/terminal' });
 *   term.connect();    // open WS (called automatically on construction)
 *   term.disconnect(); // close WS
 *   term.dispose();    // tear down entirely
 */
'use strict';

// ── Module-level guards ───────────────────────────────────────────────────────
let _cssInjected = false;
let _instanceCount = 0;

// ── Defaults ─────────────────────────────────────────────────────────────────
const DEFAULTS = {
  theme: 'crt',
  cols: 80,
  rows: 25,
  fontSize: 14,
  pageBg: '#0a0a0a',
  termBg: '#0a0a0a',
  scanlines: true,
  vignette: true,
  glow: false,
  storageKey: 'undef-terminal-settings',
  title: null,
};

// Theme-specific default effects
const THEME_DEFAULTS = {
  crt:   { scanlines: true,  vignette: true,  glow: false },
  bbs:   { scanlines: false, vignette: false, glow: false },
  glass: { scanlines: false, vignette: false, glow: true },
};

// ── CSS (injected once into <head> on first instantiation) ────────────────────
const TERMINAL_CSS = `
.undef-terminal, .undef-terminal * { box-sizing: border-box; }

.undef-terminal {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  overscroll-behavior: none;
  font-family: 'Fira Code', 'Consolas', monospace;
  color: #e2e8f0;
  --bg-page: #0a0a0a;
  --bg-terminal: #0a0a0a;
  --green-base: #22c55e;
  --green-bright: #4ade80;
  --text-primary: #e2e8f0;
  --text-dim: #64748b;
}

/* ── Page Layout ── */
.undef-terminal .page-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  width: 100%;
  padding: 20px;
  position: relative;
}

/* ── Gear Icon ── */
.undef-terminal .gear-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 2000;
  background: rgba(30, 30, 30, 0.8);
  border: 1px solid #444;
  border-radius: 8px;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  color: #888;
  font-size: 24px;
  line-height: 1;
}
.undef-terminal .gear-btn:hover { border-color: var(--green-base); color: var(--green-base); }
.undef-terminal .gear-btn svg { width: 24px; height: 24px; fill: currentColor; }

/* ── Settings Panel ── */
.undef-terminal .settings-overlay {
  display: none;
  position: absolute;
  inset: 0;
  z-index: 1999;
}
.undef-terminal .settings-overlay.open { display: block; }

.undef-terminal .settings-panel {
  position: absolute;
  top: 68px;
  right: 16px;
  z-index: 2001;
  width: 300px;
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 10px;
  padding: 20px;
  display: none;
  max-height: calc(100% - 90px);
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0,0,0,0.6);
}
.undef-terminal .settings-panel.open { display: block; }

.undef-terminal .settings-panel h3 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--text-dim);
  margin: 16px 0 8px 0;
}
.undef-terminal .settings-panel h3:first-child { margin-top: 0; }

.undef-terminal .theme-options {
  display: flex;
  gap: 6px;
}
.undef-terminal .theme-btn {
  flex: 1;
  padding: 8px 4px;
  background: #111;
  border: 2px solid #333;
  border-radius: 6px;
  color: #aaa;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.undef-terminal .theme-btn:hover { border-color: #666; }
.undef-terminal .theme-btn.active { border-color: var(--green-base); color: var(--green-base); }

.undef-terminal .setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0;
}
.undef-terminal .setting-row label {
  font-size: 12px;
  color: #ccc;
}
.undef-terminal .setting-row input[type="range"] {
  width: 120px;
  accent-color: var(--green-base);
}
.undef-terminal .setting-row .val {
  font-size: 11px;
  color: var(--green-base);
  min-width: 32px;
  text-align: right;
}
.undef-terminal .setting-row input[type="color"] {
  width: 32px;
  height: 24px;
  border: 1px solid #444;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  padding: 0;
}
.undef-terminal .setting-row input[type="checkbox"] {
  accent-color: var(--green-base);
  width: 16px;
  height: 16px;
}

/* ── Frame: Common ── */
/* Height chain: page-wrapper → frame-root → terminal-frame → screen-inset → terminal-div
   Must flow all the way down for FitAddon to measure both dimensions. */
.undef-terminal .frame-root {
  width: 100%;
  max-width: 1100px;
  height: 100%;
}

.undef-terminal .terminal-frame {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.undef-terminal .screen-inset {
  flex: 1;
  min-height: 0;
}

.undef-terminal .terminal-div {
  overflow: hidden;
  height: 100%;
}

.undef-terminal .xterm { padding: 0; }

/* ── Connection Status (inside frame) ── */
.undef-terminal .frame-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-dim);
}
.undef-terminal .status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #555;
  display: inline-block;
}
.undef-terminal .status-dot.connected {
  background: var(--green-base);
  box-shadow: 0 0 6px var(--green-base);
}

/* ══════════════════════════════════════
   Theme A: CRT Monitor
   ══════════════════════════════════════ */
.undef-terminal.theme-crt .terminal-frame {
  background: linear-gradient(145deg, #111 0%, #0d0d0d 50%, #111 100%);
  border-radius: 18px;
  padding: 28px 28px 12px 28px;
  box-shadow:
    0 0 0 2px #111,
    0 4px 20px rgba(0,0,0,0.8),
    inset 0 2px 4px rgba(255,255,255,0.05);
}
.undef-terminal.theme-crt .screen-inset {
  background: #000;
  border-radius: 8px;
  padding: 6px;
  box-shadow: inset 0 0 20px rgba(0,0,0,0.9), inset 0 0 4px rgba(0,0,0,0.5);
  position: relative;
  overflow: hidden;
}
.undef-terminal.theme-crt .frame-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 6px 2px 6px;
}
.undef-terminal.theme-crt .frame-label {
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #555;
}
.undef-terminal.theme-crt .led {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #333;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.5);
}
.undef-terminal.theme-crt .led.on {
  background: var(--green-base);
  box-shadow: 0 0 4px var(--green-base), 0 0 8px var(--green-base);
}

/* CRT scanlines */
.undef-terminal.theme-crt.fx-scanlines .screen-inset::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.15) 2px, rgba(0,0,0,0.15) 4px
  );
  pointer-events: none;
  z-index: 10;
}
/* CRT vignette */
.undef-terminal.theme-crt.fx-vignette .screen-inset::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%);
  pointer-events: none;
  z-index: 10;
  border-radius: 8px;
}

/* ══════════════════════════════════════
   Theme B: BBS/DOS Frame
   ══════════════════════════════════════ */
.undef-terminal.theme-bbs .terminal-frame {
  border: 2px solid #444;
  background: #111;
}
.undef-terminal.theme-bbs .frame-header {
  background: linear-gradient(90deg, #000080, #0000b0);
  padding: 4px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.undef-terminal.theme-bbs .frame-header-title {
  font-size: 12px;
  font-weight: bold;
  color: #fff;
  letter-spacing: 1px;
}
.undef-terminal.theme-bbs .screen-inset {
  position: relative;
  overflow: hidden;
}
.undef-terminal.theme-bbs .frame-statusbar {
  background: linear-gradient(90deg, #000080, #0000a0);
  padding: 3px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #aaa;
}

/* BBS scanlines */
.undef-terminal.theme-bbs.fx-scanlines .screen-inset::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.1) 2px, rgba(0,0,0,0.1) 4px
  );
  pointer-events: none;
  z-index: 10;
}

/* ══════════════════════════════════════
   Theme C: Floating Glass
   ══════════════════════════════════════ */
.undef-terminal.theme-glass .terminal-frame {
  border-radius: 12px;
  background: rgba(20, 20, 30, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  overflow: hidden;
}
.undef-terminal.theme-glass .frame-titlebar {
  padding: 8px 14px;
  text-align: center;
  font-size: 11px;
  color: #777;
  letter-spacing: 1px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.undef-terminal.theme-glass .screen-inset {
  position: relative;
  overflow: hidden;
}
.undef-terminal.theme-glass .frame-statusbar {
  padding: 4px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #555;
  border-top: 1px solid rgba(255,255,255,0.05);
}

/* Glass glow */
.undef-terminal.theme-glass.fx-glow .terminal-frame {
  box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 40px rgba(34,197,94,0.06);
}

/* Glass scanlines */
.undef-terminal.theme-glass.fx-scanlines .screen-inset::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px
  );
  pointer-events: none;
  z-index: 10;
}

/* ── Loading Overlay ── */
.undef-terminal .loading {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(13, 17, 23, 0.95);
  padding: 30px 50px;
  border: 2px solid var(--green-base);
  border-radius: 8px;
  text-align: center;
  z-index: 100;
  font-size: 13px;
}
.undef-terminal .loading-spinner {
  display: inline-block;
  width: 20px; height: 20px;
  border: 2px solid var(--text-dim);
  border-top-color: var(--green-base);
  border-radius: 50%;
  animation: undef-spin 0.8s linear infinite;
  margin-right: 10px;
}
@keyframes undef-spin { to { transform: rotate(360deg); } }

/* ── Scrollbar styling for settings panel ── */
.undef-terminal .settings-panel::-webkit-scrollbar { width: 6px; }
.undef-terminal .settings-panel::-webkit-scrollbar-track { background: transparent; }
.undef-terminal .settings-panel::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }

/* ══════════════════════════════════════
   Mobile / Responsive Adjustments
   ══════════════════════════════════════ */
@media (max-width: 768px), (max-height: 600px) {
  .undef-terminal .page-wrapper {
    padding: 0;
    align-items: flex-start;
  }

  .undef-terminal .frame-root {
    width: 100%;
    height: 100%;
  }

  .undef-terminal .terminal-frame {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    border-radius: 0 !important;
    border: none !important;
    padding: 4px !important;
    box-shadow: none !important;
  }

  /* Force flex child to calculate height from parent, not content */
  .undef-terminal .screen-inset,
  .undef-terminal.theme-crt .screen-inset,
  .undef-terminal.theme-bbs .screen-inset,
  .undef-terminal.theme-glass .screen-inset {
    flex: 1;
    height: 0;
    border-radius: 0 !important;
  }

  .undef-terminal .terminal-div { height: 100%; }

  /* Gradient at the bottom edge of the terminal */
  .undef-terminal .screen-inset { position: relative; }
  .undef-terminal .screen-inset::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 40px;
    background: linear-gradient(to bottom, transparent, var(--bg-terminal, #0a0a0a));
    pointer-events: none;
    z-index: 10;
  }

  /* Hide decorative chrome */
  .undef-terminal .frame-bottom, .undef-terminal.theme-crt .frame-bottom,
  .undef-terminal .frame-header, .undef-terminal.theme-bbs .frame-header,
  .undef-terminal .frame-statusbar, .undef-terminal.theme-bbs .frame-statusbar,
  .undef-terminal.theme-glass .frame-statusbar,
  .undef-terminal .frame-titlebar, .undef-terminal.theme-glass .frame-titlebar {
    display: none !important;
  }

  .undef-terminal .gear-btn {
    top: 4px;
    right: 4px;
    width: 32px;
    height: 32px;
    background: rgba(0, 0, 0, 0.6);
  }
  .undef-terminal .gear-btn svg { width: 18px; height: 18px; }
}
`;

// ── CSS injection ─────────────────────────────────────────────────────────────
function _injectCSS() {
  if (_cssInjected) return;
  _cssInjected = true;
  const style = document.createElement('style');
  style.textContent = TERMINAL_CSS;
  document.head.appendChild(style);
}

// ── UndefTerminal class ───────────────────────────────────────────────────────
class UndefTerminal {
  /**
   * Create an embeddable terminal widget.
   *
   * @param {HTMLElement} container - Element to mount the terminal into.
   * @param {object} [config={}] - Configuration options.
   * @param {string} [config.wsUrl] - WebSocket endpoint. Defaults to auto-detect.
   * @param {string} [config.theme='crt'] - 'crt' | 'bbs' | 'glass'
   * @param {number} [config.cols=80]
   * @param {number} [config.rows=25]
   * @param {number} [config.fontSize=14]
   * @param {string} [config.pageBg='#0a0a0a']
   * @param {string} [config.termBg='#0a0a0a']
   * @param {boolean} [config.scanlines=true]
   * @param {boolean} [config.vignette=true]
   * @param {boolean} [config.glow=false]
   * @param {string} [config.storageKey='undef-terminal-settings']
   * @param {string|null} [config.title=null] - Override frame branding text.
   */
  constructor(container, config = {}) {
    this._container = container;
    this._config = { ...DEFAULTS, ...config };
    this._uid = ++_instanceCount;

    // Instance state
    this._term = null;
    this._fitAddon = null;
    this._ws = null;
    this._connected = false;
    this._waitingForReconnect = false;
    this._settings = {};
    this._root = null;
    this._ro = null;

    _injectCSS();
    this._buildDOM();
    this._loadSettings();
    this._bindSettingsEvents();
    this._createTerminal();
    this.connect();

    // Re-fit once web fonts load — initial fit may have used fallback font metrics
    document.fonts.ready.then(() =>
      requestAnimationFrame(() => this._fitWithMinCols(this._settings.cols || 80))
    );
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Open the WebSocket connection. Called automatically on construction. */
  connect() {
    this._connectWebSocket();
  }

  /** Close the WebSocket connection. */
  disconnect() {
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  }

  /** Tear down entirely: xterm, WebSocket, ResizeObserver, and DOM. */
  dispose() {
    this.disconnect();
    if (this._ro) { this._ro.disconnect(); this._ro = null; }
    if (this._term) { this._term.dispose(); this._term = null; }
    this._fitAddon = null;
    if (this._root && this._root.parentNode) {
      this._root.parentNode.removeChild(this._root);
    }
    this._root = null;
  }

  // ── Internal helpers ────────────────────────────────────────────────────────

  /** Query by ID within this instance's root (IDs are suffixed with uid). */
  _q(id) {
    return this._root.querySelector('#' + id + '-' + this._uid);
  }

  // ── DOM Construction ────────────────────────────────────────────────────────

  _buildDOM() {
    const uid = this._uid;
    const GEAR_SVG = `<svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1112 8.4a3.6 3.6 0 010 7.2z"/></svg>`;

    const root = document.createElement('div');
    root.className = 'undef-terminal';
    root.innerHTML = `
      <button class="gear-btn" id="gearBtn-${uid}" title="Settings">${GEAR_SVG}</button>
      <div class="settings-overlay" id="settingsOverlay-${uid}"></div>
      <div class="settings-panel" id="settingsPanel-${uid}">
        <h3>Theme</h3>
        <div class="theme-options">
          <button class="theme-btn" data-theme="crt">CRT</button>
          <button class="theme-btn" data-theme="bbs">BBS/DOS</button>
          <button class="theme-btn" data-theme="glass">Glass</button>
        </div>
        <h3>Terminal Size</h3>
        <div class="setting-row">
          <label>Columns</label>
          <input type="range" id="setCols-${uid}" min="80" max="120" value="80">
          <span class="val" id="valCols-${uid}">80</span>
        </div>
        <div class="setting-row">
          <label>Rows</label>
          <input type="range" id="setRows-${uid}" min="25" max="40" value="25">
          <span class="val" id="valRows-${uid}">25</span>
        </div>
        <div class="setting-row">
          <label>Font Size</label>
          <input type="range" id="setFontSize-${uid}" min="11" max="18" value="14">
          <span class="val" id="valFontSize-${uid}">14px</span>
        </div>
        <h3>Colors</h3>
        <div class="setting-row">
          <label>Page Background</label>
          <input type="color" id="setPageBg-${uid}" value="#0a0a0a">
        </div>
        <div class="setting-row">
          <label>Terminal Background</label>
          <input type="color" id="setTermBg-${uid}" value="#0a0a0a">
        </div>
        <h3>Effects</h3>
        <div class="setting-row">
          <label>Scanlines</label>
          <input type="checkbox" id="fxScanlines-${uid}">
        </div>
        <div class="setting-row">
          <label>Vignette</label>
          <input type="checkbox" id="fxVignette-${uid}">
        </div>
        <div class="setting-row">
          <label>Glow</label>
          <input type="checkbox" id="fxGlow-${uid}">
        </div>
      </div>
      <div class="page-wrapper" id="pageWrapper-${uid}">
        <div class="frame-root" id="frameRoot-${uid}"></div>
        <div class="loading" id="loadingScreen-${uid}">
          <div>
            <div class="loading-spinner"></div>
            Initializing Terminal Connection...
          </div>
        </div>
      </div>
    `;

    this._root = root;
    this._container.appendChild(root);
  }

  // ── Frame Builders ────────────────────────────────────────────────────────

  _buildCRTFrame() {
    const uid = this._uid;
    const label = this._config.title || 'Warp Agent Runtime Platform';
    return `
      <div class="terminal-frame">
        <div class="screen-inset">
          <div class="terminal-div" id="terminalDiv-${uid}"></div>
        </div>
        <div class="frame-bottom">
          <span class="frame-label">${label}</span>
          <div style="display:flex;align-items:center;gap:10px;">
            <div class="frame-status">
              <span class="status-dot" id="statusDot-${uid}"></span>
              <span id="statusText-${uid}">Connecting...</span>
            </div>
            <div class="led" id="ledIndicator-${uid}"></div>
          </div>
        </div>
      </div>`;
  }

  _buildBBSFrame() {
    const uid = this._uid;
    const title = (this._config.title || 'Warp Agent Runtime Platform').toUpperCase();
    return `
      <div class="terminal-frame">
        <div class="frame-header">
          <span class="frame-header-title">${title}</span>
          <div class="frame-status">
            <span class="status-dot" id="statusDot-${uid}"></span>
            <span id="statusText-${uid}">Connecting...</span>
          </div>
        </div>
        <div class="screen-inset">
          <div class="terminal-div" id="terminalDiv-${uid}"></div>
        </div>
        <div class="frame-statusbar">
          <span>ANSI Terminal</span>
          <span id="connectionInfo-${uid}">${this._settings.cols}×${this._settings.rows}</span>
        </div>
      </div>`;
  }

  _buildGlassFrame() {
    const uid = this._uid;
    const title = (this._config.title || 'Warp Agent Runtime Platform').toUpperCase();
    return `
      <div class="terminal-frame">
        <div class="frame-titlebar">${title}</div>
        <div class="screen-inset">
          <div class="terminal-div" id="terminalDiv-${uid}"></div>
        </div>
        <div class="frame-statusbar">
          <div class="frame-status">
            <span class="status-dot" id="statusDot-${uid}"></span>
            <span id="statusText-${uid}">Connecting...</span>
          </div>
          <span id="connectionInfo-${uid}">${this._settings.cols}×${this._settings.rows}</span>
        </div>
      </div>`;
  }

  // ── Settings Persistence ─────────────────────────────────────────────────

  _loadSettings() {
    const key = this._config.storageKey;
    // Base: DEFAULTS overridden by any UI-relevant constructor config
    const base = { ...DEFAULTS, ...this._config };
    try {
      const saved = localStorage.getItem(key);
      this._settings = saved ? { ...base, ...JSON.parse(saved) } : { ...base };
    } catch {
      this._settings = { ...base };
    }
  }

  _saveSettings() {
    try {
      localStorage.setItem(this._config.storageKey, JSON.stringify(this._settings));
    } catch {
      // localStorage might be unavailable
    }
  }

  // ── Apply Settings to DOM ─────────────────────────────────────────────────

  _applyThemeClasses() {
    const root = this._root;
    root.classList.remove('theme-crt', 'theme-bbs', 'theme-glass');
    root.classList.remove('fx-scanlines', 'fx-vignette', 'fx-glow');
    root.classList.add('theme-' + this._settings.theme);
    if (this._settings.scanlines) root.classList.add('fx-scanlines');
    if (this._settings.vignette) root.classList.add('fx-vignette');
    if (this._settings.glow) root.classList.add('fx-glow');
  }

  _applyColors() {
    this._root.style.setProperty('--bg-page', this._settings.pageBg);
    this._root.style.setProperty('--bg-terminal', this._settings.termBg);
    this._root.style.background = this._settings.pageBg;
  }

  _applySettingsToUI() {
    this._root.querySelectorAll('.theme-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === this._settings.theme);
    });
    this._q('setCols').value = this._settings.cols;
    this._q('valCols').textContent = this._settings.cols;
    this._q('setRows').value = this._settings.rows;
    this._q('valRows').textContent = this._settings.rows;
    this._q('setFontSize').value = this._settings.fontSize;
    this._q('valFontSize').textContent = this._settings.fontSize + 'px';
    this._q('setPageBg').value = this._settings.pageBg;
    this._q('setTermBg').value = this._settings.termBg;
    this._q('fxScanlines').checked = this._settings.scanlines;
    this._q('fxVignette').checked = this._settings.vignette;
    this._q('fxGlow').checked = this._settings.glow;
  }

  // ── Terminal Creation ─────────────────────────────────────────────────────

  /**
   * Scale font down if needed so xterm renders at least minCols columns,
   * then fit the terminal to the container.
   */
  _fitWithMinCols(minCols) {
    if (!this._fitAddon || !this._term) return;
    const proposed = this._fitAddon.proposeDimensions();
    if (!proposed || proposed.cols <= 0) return;
    if (proposed.cols < minCols) {
      const newSize = Math.max(6, Math.floor(this._term.options.fontSize * proposed.cols / minCols));
      this._term.options.fontSize = newSize;
    }
    this._fitAddon.fit();
  }

  _createTerminal() {
    const frameRoot = this._q('frameRoot');
    const builders = {
      crt:   () => this._buildCRTFrame(),
      bbs:   () => this._buildBBSFrame(),
      glass: () => this._buildGlassFrame(),
    };
    frameRoot.innerHTML = (builders[this._settings.theme] || builders.crt)();

    this._applyThemeClasses();
    this._applyColors();

    const fontFamily = "'Fira Code', 'DejaVu Sans Mono', 'Consolas', monospace";

    this._term = new Terminal({
      theme: {
        background: this._settings.termBg,
        foreground: '#e2e8f0',
        cursor: '#22c55e',
        cursorAccent: this._settings.termBg,
        selection: 'rgba(34, 197, 94, 0.15)',
        black: '#000000',
      },
      fontFamily,
      fontSize: this._settings.fontSize,
      fontWeight: 'normal',
      letterSpacing: 0,
      lineHeight: 1.2,
      allowTransparency: true,
    });

    const terminalDiv = this._q('terminalDiv');
    this._term.open(terminalDiv);

    this._fitAddon = new FitAddon.FitAddon();
    this._term.loadAddon(this._fitAddon);

    requestAnimationFrame(() => this._fitWithMinCols(this._settings.cols || 80));

    // Re-fit with font scale on every container resize
    if (this._ro) this._ro.disconnect();
    this._ro = new ResizeObserver(() => this._fitWithMinCols(this._settings.cols || 80));
    this._ro.observe(terminalDiv);

    this._term.focus();
    this._term.onData((data) => this._handleTerminalInput(data));

    // Ctrl key passthrough
    this._term.attachCustomKeyEventHandler((event) => {
      if (event.ctrlKey || event.metaKey) return false;
      return true;
    });

    // Hide loading screen on first data received
    const loadingScreen = this._q('loadingScreen');
    if (loadingScreen) loadingScreen.style.removeProperty('display');
    let firstData = false;
    const originalWrite = this._term.write.bind(this._term);
    this._term.write = (...args) => {
      if (!firstData) {
        if (loadingScreen) loadingScreen.style.display = 'none';
        firstData = true;
      }
      return originalWrite(...args);
    };

    this._updateStatus(this._connected);
  }

  _recreateTerminal() {
    if (this._term) { this._term.dispose(); this._term = null; }
    this._fitAddon = null;
    this._createTerminal();
    // Hide loading immediately on recreation (already connected)
    const loadingScreen = this._q('loadingScreen');
    if (loadingScreen) loadingScreen.style.display = 'none';
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._updateStatus(true);
    }
  }

  // ── Settings Panel ────────────────────────────────────────────────────────

  _openSettings() {
    this._q('settingsPanel').classList.add('open');
    this._q('settingsOverlay').classList.add('open');
    this._applySettingsToUI();
  }

  _closeSettings() {
    this._q('settingsPanel').classList.remove('open');
    this._q('settingsOverlay').classList.remove('open');
    if (this._term) this._term.focus();
  }

  _toggleSettings() {
    if (this._q('settingsPanel').classList.contains('open')) {
      this._closeSettings();
    } else {
      this._openSettings();
    }
  }

  _bindSettingsEvents() {
    this._q('gearBtn').addEventListener('click', () => this._toggleSettings());
    this._q('settingsOverlay').addEventListener('click', () => this._closeSettings());

    // Theme buttons
    this._root.querySelectorAll('.theme-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const newTheme = btn.dataset.theme;
        if (newTheme !== this._settings.theme) {
          const fx = THEME_DEFAULTS[newTheme] || {};
          this._settings.theme = newTheme;
          this._settings.scanlines = fx.scanlines;
          this._settings.vignette = fx.vignette;
          this._settings.glow = fx.glow;
          this._saveSettings();
          this._recreateTerminal();
          this._applySettingsToUI();
        }
      });
    });

    // Sliders
    const colsSlider = this._q('setCols');
    const rowsSlider = this._q('setRows');
    const fontSlider = this._q('setFontSize');

    colsSlider.addEventListener('input', () => {
      this._q('valCols').textContent = colsSlider.value;
    });
    colsSlider.addEventListener('change', () => {
      this._settings.cols = parseInt(colsSlider.value);
      this._saveSettings();
      this._recreateTerminal();
    });

    rowsSlider.addEventListener('input', () => {
      this._q('valRows').textContent = rowsSlider.value;
    });
    rowsSlider.addEventListener('change', () => {
      this._settings.rows = parseInt(rowsSlider.value);
      this._saveSettings();
      this._recreateTerminal();
    });

    fontSlider.addEventListener('input', () => {
      this._q('valFontSize').textContent = fontSlider.value + 'px';
    });
    fontSlider.addEventListener('change', () => {
      this._settings.fontSize = parseInt(fontSlider.value);
      this._saveSettings();
      this._recreateTerminal();
    });

    // Color pickers
    this._q('setPageBg').addEventListener('input', (e) => {
      this._settings.pageBg = e.target.value;
      this._applyColors();
      this._saveSettings();
    });
    this._q('setTermBg').addEventListener('input', (e) => {
      this._settings.termBg = e.target.value;
      this._saveSettings();
      if (this._term) {
        this._term.options.theme = {
          ...this._term.options.theme,
          background: this._settings.termBg,
          cursorAccent: this._settings.termBg,
        };
      }
    });

    // Effect checkboxes
    this._q('fxScanlines').addEventListener('change', (e) => {
      this._settings.scanlines = e.target.checked;
      this._applyThemeClasses();
      this._saveSettings();
    });
    this._q('fxVignette').addEventListener('change', (e) => {
      this._settings.vignette = e.target.checked;
      this._applyThemeClasses();
      this._saveSettings();
    });
    this._q('fxGlow').addEventListener('change', (e) => {
      this._settings.glow = e.target.checked;
      this._applyThemeClasses();
      this._saveSettings();
    });
  }

  // ── WebSocket Connection ─────────────────────────────────────────────────

  _resolveWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = this._config.wsUrl;
    if (!url) return `${proto}//${location.host}/ws`;
    if (url.startsWith('/')) return `${proto}//${location.host}${url}`;
    return url; // already absolute ws:// or wss://
  }

  _connectWebSocket() {
    try {
      const wsUrl = this._resolveWsUrl();
      this._ws = new WebSocket(wsUrl);
      this._ws.binaryType = 'arraybuffer';

      this._ws.onopen = () => {
        this._connected = true;
        this._updateStatus(true);
      };

      this._ws.onmessage = (event) => {
        try {
          const data = event.data;
          if (data instanceof ArrayBuffer) {
            const view = new Uint8Array(data);
            const text = String.fromCharCode.apply(null, view);
            this._term.write(text);
          } else {
            this._term.write(data);
          }
        } catch (e) {
          console.error('Error handling message:', e);
        }
      };

      this._ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        if (this._term) this._term.write('\x1b[31m✗ WebSocket error\x1b[0m\r\n');
      };

      this._ws.onclose = () => {
        this._connected = false;
        this._updateStatus(false);
        if (this._term) {
          this._term.write('\r\n\x1b[31m✗ Connection closed\x1b[0m\r\n');
          this._term.write('\x1b[33mPress any key to reconnect...\x1b[0m');
          this._waitingForReconnect = true;
        }
      };
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      if (this._term) this._term.write(`\x1b[31m✗ Failed to connect: ${e.message}\x1b[0m\r\n`);
    }
  }

  // ── Terminal Input Handler ────────────────────────────────────────────────

  _handleTerminalInput(data) {
    if (this._waitingForReconnect) {
      this._waitingForReconnect = false;
      if (this._term) this._term.write('\r\n\x1b[33m⟳ Reconnecting...\x1b[0m\r\n');
      this._connectWebSocket();
      return;
    }
    if (!this._connected || !this._ws) return;
    try {
      this._ws.send(data);
    } catch (e) {
      console.error('Failed to send data:', e);
      if (this._term) this._term.write(`\x1b[31m✗ Failed to send input: ${e.message}\x1b[0m\r\n`);
    }
  }

  // ── Status Updates ────────────────────────────────────────────────────────

  _updateStatus(isConnected) {
    const dot  = this._q('statusDot');
    const text = this._q('statusText');
    const led  = this._q('ledIndicator');
    const info = this._q('connectionInfo');

    if (dot)  dot.classList.toggle('connected', isConnected);
    if (text) text.textContent = isConnected ? 'Connected' : 'Disconnected';
    if (led)  led.classList.toggle('on', isConnected);
    if (info) info.textContent = `${this._settings.cols}×${this._settings.rows}`;
  }
}

// ── Global exposure for CDN / script-tag use ──────────────────────────────────
if (typeof window !== 'undefined') window.UndefTerminal = UndefTerminal;
