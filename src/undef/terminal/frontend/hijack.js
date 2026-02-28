/**
 * UndefHijack - Embeddable terminal hijack control widget.
 *
 * Connects to the TermHub browser WebSocket endpoint (/ws/bot/{botId}/term)
 * and provides live terminal viewing plus hijack controls (pause/step/release).
 *
 * Usage:
 *   const w = new UndefHijack(containerEl, { botId: 'mybot' });
 *   w.connect();    // called automatically on construction
 *   w.disconnect(); // close WS
 *   w.dispose();    // tear down entirely
 */
'use strict';

// ── Module-level guards ───────────────────────────────────────────────────────
let _hijackCssInjected = false;
let _hijackInstanceCount = 0;

// ── CSS (injected once into <head>) ───────────────────────────────────────────
const HIJACK_CSS = `
.undef-hijack, .undef-hijack * { box-sizing: border-box; }

.undef-hijack {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  background: #0b0f14;
  color: #e2e8f0;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 13px;
  overflow: hidden;
}

/* ── Toolbar ── */
.undef-hijack .hijack-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #141920;
  border-bottom: 1px solid #1e2530;
  flex-shrink: 0;
  flex-wrap: wrap;
  min-height: 38px;
}

.undef-hijack .hijack-status {
  font-size: 12px;
  min-width: 150px;
  display: flex;
  align-items: center;
  gap: 5px;
}
.undef-hijack .hijack-status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #444;
  flex-shrink: 0;
}
.undef-hijack .hijack-status-dot.live { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
.undef-hijack .hijack-status-dot.warn { background: #f59e0b; box-shadow: 0 0 4px #f59e0b; }
.undef-hijack .hijack-status-dot.bad  { background: #ef4444; box-shadow: 0 0 4px #ef4444; }

.undef-hijack .hijack-controls {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}

.undef-hijack .hbtn {
  padding: 3px 10px;
  border-radius: 5px;
  border: 1px solid #2a3040;
  background: #1e2530;
  color: #ccc;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  line-height: 1.5;
}
.undef-hijack .hbtn:hover:not(:disabled) { border-color: #3a4555; background: #253040; color: #fff; }
.undef-hijack .hbtn:disabled { opacity: 0.35; cursor: not-allowed; }
.undef-hijack .hbtn.primary { border-color: #22c55e55; color: #22c55e; }
.undef-hijack .hbtn.primary:hover:not(:disabled) { background: #22c55e22; border-color: #22c55e; }
.undef-hijack .hbtn.danger { border-color: #ef444455; color: #ef4444; }
.undef-hijack .hbtn.danger:hover:not(:disabled) { background: #ef444422; border-color: #ef4444; }

.undef-hijack .hijack-prompt {
  margin-left: auto;
  font-size: 11px;
  color: #4a6080;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

/* ── Terminal area ── */
.undef-hijack .hijack-terminal {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

/* ── Text input row (visible when hijacked by me) ── */
.undef-hijack .hijack-input-row {
  display: none;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  background: #141920;
  border-top: 1px solid #1e2530;
  flex-shrink: 0;
}
.undef-hijack .hijack-input-row.visible { display: flex; }
.undef-hijack .hijack-input-field {
  flex: 1;
  background: #0d1117;
  border: 1px solid #2a3040;
  border-radius: 4px;
  color: #e2e8f0;
  font-family: 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12px;
  padding: 3px 8px;
  outline: none;
}
.undef-hijack .hijack-input-field:focus { border-color: #22c55e66; }
.undef-hijack .hijack-input-send {
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid #22c55e55;
  background: #22c55e22;
  color: #22c55e;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.undef-hijack .hijack-input-send:hover { background: #22c55e33; border-color: #22c55e; }

/* ── Analysis panel ── */
.undef-hijack .hijack-analysis {
  border-top: 1px solid #1e2530;
  flex-shrink: 0;
  max-height: 130px;
  overflow-y: auto;
  background: #0d1117;
}
.undef-hijack .hijack-analysis summary {
  padding: 4px 10px;
  font-size: 11px;
  color: #4a6080;
  cursor: pointer;
  user-select: none;
  background: #141920;
  border-bottom: 1px solid #1e2530;
  list-style: none;
}
.undef-hijack .hijack-analysis summary::-webkit-details-marker { display: none; }
.undef-hijack .hijack-analysis summary::before { content: '▶ '; font-size: 9px; }
.undef-hijack .hijack-analysis[open] summary::before { content: '▼ '; font-size: 9px; }
.undef-hijack .hijack-analysis summary:hover { color: #8899aa; }
.undef-hijack .hijack-analysis pre {
  margin: 0;
  padding: 6px 10px;
  font-size: 11px;
  color: #8899aa;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Fira Code', 'Cascadia Code', monospace;
}

/* ── Scrollbar ── */
.undef-hijack .hijack-analysis::-webkit-scrollbar { width: 5px; }
.undef-hijack .hijack-analysis::-webkit-scrollbar-track { background: transparent; }
.undef-hijack .hijack-analysis::-webkit-scrollbar-thumb { background: #2a3040; border-radius: 3px; }
`;

// ── CSS injection ─────────────────────────────────────────────────────────────
function _injectHijackCSS() {
  if (_hijackCssInjected) return;
  _hijackCssInjected = true;
  const style = document.createElement('style');
  style.textContent = HIJACK_CSS;
  document.head.appendChild(style);
}

// ── UndefHijack class ─────────────────────────────────────────────────────────
class UndefHijack {
  /**
   * Create an embeddable hijack control widget.
   *
   * @param {HTMLElement} container - Element to mount the widget into.
   * @param {object} [config={}] - Configuration options.
   * @param {string} [config.wsUrl] - Full WS URL. If omitted, auto-built from botId.
   * @param {string} [config.botId] - Bot ID (used in auto URL and display title).
   * @param {string} [config.wsPathPrefix='/ws/bot'] - Path prefix for auto URL construction.
   * @param {string|null} [config.title] - Override toolbar title text.
   * @param {boolean} [config.showInput=true] - Show text-input bar when hijacked.
   * @param {boolean} [config.showAnalysis=true] - Show collapsible analysis panel.
   * @param {number} [config.heartbeatInterval=5000] - Heartbeat interval (ms) when hijacked.
   */
  constructor(container, config = {}) {
    this._container = container;
    this._config = {
      wsPathPrefix: '/ws/bot',
      showInput: true,
      showAnalysis: true,
      heartbeatInterval: 5000,
      ...config,
    };
    this._uid = ++_hijackInstanceCount;

    // Instance state
    this._ws = null;
    this._term = null;
    this._fitAddon = null;
    this._ro = null;
    this._heartbeatTimer = null;
    this._hijacked = false;
    this._hijackedByMe = false;
    this._root = null;

    _injectHijackCSS();
    this._buildDOM();
    this.connect();
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Open the WebSocket connection. Called automatically on construction. */
  connect() {
    this._connectWs();
  }

  /** Close the WebSocket connection. */
  disconnect() {
    this._clearHeartbeat();
    if (this._ws) {
      try { this._ws.close(); } catch (_) {}
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

  /** Query by ID within this instance's root (IDs are prefixed with h-{uid}-). */
  _q(id) {
    return this._root.querySelector('#h-' + this._uid + '-' + id);
  }

  _resolveWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = this._config.wsUrl;
    if (url) {
      if (url.startsWith('/')) return `${proto}//${location.host}${url}`;
      return url; // already absolute ws:// or wss://
    }
    const botId = encodeURIComponent(this._config.botId || 'default');
    const prefix = this._config.wsPathPrefix || '/ws/bot';
    return `${proto}//${location.host}${prefix}/${botId}/term`;
  }

  // ── DOM Construction ────────────────────────────────────────────────────────

  _buildDOM() {
    const p = (id) => `h-${this._uid}-${id}`; // ID prefix helper
    const botId = this._config.botId || '';
    const title = this._config.title || (botId ? `Terminal: ${botId}` : 'Terminal');
    const showAnalysis = this._config.showAnalysis !== false;

    const root = document.createElement('div');
    root.className = 'undef-hijack';
    root.innerHTML = `
      <div class="hijack-toolbar">
        <span class="hijack-status">
          <span class="hijack-status-dot" id="${p('dot')}"></span>
          <span id="${p('statustext')}">Connecting…</span>
        </span>
        <div class="hijack-controls">
          <button class="hbtn primary" id="${p('hijack')}" disabled>Hijack</button>
          <button class="hbtn" id="${p('step')}" disabled>Step</button>
          <button class="hbtn danger" id="${p('release')}" disabled>Release</button>
          <button class="hbtn" id="${p('resync')}" disabled title="Request snapshot">⟳ Resync</button>
          <button class="hbtn" id="${p('analyze')}" disabled>Analyze</button>
        </div>
        <span class="hijack-prompt" id="${p('prompt')}" title="Current prompt ID"></span>
      </div>
      <div class="hijack-terminal" id="${p('terminal')}"></div>
      <div class="hijack-input-row" id="${p('inputrow')}">
        <input class="hijack-input-field" id="${p('inputfield')}"
          placeholder="Send keys… (Enter to send, e.g. \\r for Return)"
          autocomplete="off" spellcheck="false">
        <button class="hijack-input-send" id="${p('inputsend')}">Send</button>
      </div>
      ${showAnalysis ? `
      <details class="hijack-analysis" id="${p('analysis')}">
        <summary>Analysis</summary>
        <pre id="${p('analysistext')}"></pre>
      </details>` : ''}
    `;

    this._root = root;
    this._container.appendChild(root);
    this._bindEvents();
  }

  // ── xterm ─────────────────────────────────────────────────────────────────

  _ensureTerm() {
    if (this._term) return this._term;
    if (!window.Terminal) throw new Error('xterm.js not loaded');

    const termDiv = this._q('terminal');
    this._term = new window.Terminal({
      convertEol: true,
      cursorBlink: true,
      fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace",
      fontSize: 13,
      theme: { background: '#0b0f14' },
      allowTransparency: true,
    });
    this._term.open(termDiv);
    this._term.focus();

    if (window.FitAddon) {
      this._fitAddon = new FitAddon.FitAddon();
      this._term.loadAddon(this._fitAddon);
      requestAnimationFrame(() => { try { this._fitAddon.fit(); } catch (_) {} });
      this._ro = new ResizeObserver(() => { try { this._fitAddon.fit(); } catch (_) {} });
      this._ro.observe(termDiv);
    }

    // Forward keyboard input to WS when hijacked
    this._term.onData((data) => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      if (!this._hijackedByMe) return;
      this._wsSend({ type: 'input', data });
    });

    return this._term;
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────

  _wsSend(obj) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(obj));
    }
  }

  _clearHeartbeat() {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
  }

  _startHeartbeat() {
    this._clearHeartbeat();
    this._heartbeatTimer = setInterval(() => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      if (!this._hijackedByMe) return;
      this._wsSend({ type: 'heartbeat' });
    }, this._config.heartbeatInterval || 5000);
  }

  _connectWs() {
    if (this._ws) {
      try { this._ws.close(); } catch (_) {}
      this._ws = null;
    }
    this._hijacked = false;
    this._hijackedByMe = false;

    let ws;
    try {
      ws = new WebSocket(this._resolveWsUrl());
    } catch (e) {
      this._setStatus('bad', `Failed: ${e.message}`);
      return;
    }
    this._ws = ws;

    ws.onopen = () => {
      this._setStatus('live', 'Connected (watching)');
      this._updateButtons();
      this._wsSend({ type: 'snapshot_req' });
      this._startHeartbeat();
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (!msg || !msg.type) return;
      this._handleMessage(msg);
    };

    ws.onclose = () => {
      if (ws !== this._ws) return; // stale handler from a replaced socket
      this._clearHeartbeat();
      this._hijacked = false;
      this._hijackedByMe = false;
      this._setStatus('bad', 'Disconnected');
      this._updateButtons();
      this._ws = null;
    };

    ws.onerror = () => {
      try { ws.close(); } catch (_) {}
    };
  }

  // ── Message dispatch ──────────────────────────────────────────────────────

  _handleMessage(msg) {
    switch (msg.type) {

      case 'term':
        if (msg.data) {
          try { this._ensureTerm().write(msg.data); } catch (_) {}
        }
        break;

      case 'snapshot': {
        const promptId = msg.prompt_detected && msg.prompt_detected.prompt_id;
        this._setPromptId(promptId || '');
        try {
          const t = this._ensureTerm();
          t.reset();
          t.write('\u001b[2J\u001b[H');
          t.write((msg.screen || '').replace(/\n/g, '\r\n'));
        } catch (_) {}
        break;
      }

      case 'analysis': {
        const pre = this._q('analysistext');
        if (pre) {
          pre.textContent = msg.formatted || '(no analysis)';
          const details = this._q('analysis');
          if (details) details.open = true;
        }
        break;
      }

      case 'hello':
        // {type, bot_id, can_hijack, hijacked, hijacked_by_me}
        this._hijacked = !!msg.hijacked;
        this._hijackedByMe = !!msg.hijacked_by_me;
        this._updateStatus();
        this._updateButtons();
        break;

      case 'hijack_state':
        // {type, hijacked, owner: "me"|"other"|null, lease_expires_at}
        this._hijacked = !!msg.hijacked;
        this._hijackedByMe = msg.owner === 'me';
        this._updateStatus();
        this._updateButtons();
        break;

      case 'heartbeat_ack':
        break; // lease refreshed — no visible change needed

      case 'error':
        this._setStatus('bad', `Error: ${msg.message || 'unknown'}`);
        break;
    }
  }

  // ── UI State ──────────────────────────────────────────────────────────────

  _setStatus(level, text) {
    const dot = this._q('dot');
    const txt = this._q('statustext');
    if (dot) {
      dot.className = 'hijack-status-dot ' + level;
    }
    if (txt) txt.textContent = text;
  }

  _updateStatus() {
    const connected = !!(this._ws && this._ws.readyState === WebSocket.OPEN);
    if (!connected) {
      this._setStatus('bad', 'Disconnected');
    } else if (this._hijackedByMe) {
      this._setStatus('warn', 'Hijacked (you)');
    } else if (this._hijacked) {
      this._setStatus('bad', 'Hijacked (other)');
    } else {
      this._setStatus('live', 'Connected (watching)');
    }

    // Show/hide text-input row based on whether we hold the hijack
    if (this._config.showInput !== false) {
      const row = this._q('inputrow');
      if (row) row.classList.toggle('visible', connected && this._hijackedByMe);
    }
  }

  _updateButtons() {
    const connected = !!(this._ws && this._ws.readyState === WebSocket.OPEN);
    const hijackBtn  = this._q('hijack');
    const stepBtn    = this._q('step');
    const releaseBtn = this._q('release');
    const resyncBtn  = this._q('resync');
    const analyzeBtn = this._q('analyze');

    if (!connected) {
      [hijackBtn, stepBtn, releaseBtn, resyncBtn, analyzeBtn]
        .forEach(b => { if (b) b.disabled = true; });
      return;
    }
    if (hijackBtn)  hijackBtn.disabled  = this._hijacked;
    if (stepBtn)    stepBtn.disabled    = !this._hijackedByMe;
    if (releaseBtn) releaseBtn.disabled = !this._hijackedByMe;
    if (resyncBtn)  resyncBtn.disabled  = false;
    if (analyzeBtn) analyzeBtn.disabled = false;
  }

  _setPromptId(id) {
    const el = this._q('prompt');
    if (el) el.textContent = id ? `prompt: ${id}` : '';
  }

  // ── Event Binding ─────────────────────────────────────────────────────────

  _bindEvents() {
    this._q('hijack').addEventListener('click', () => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      this._wsSend({ type: 'hijack_request' });
    });

    this._q('step').addEventListener('click', () => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      if (!this._hijackedByMe) return;
      this._wsSend({ type: 'hijack_step' });
      // Request snapshot + analysis shortly after the worker acts
      for (const ms of [250, 1000]) {
        setTimeout(() => {
          if (this._ws && this._ws.readyState === WebSocket.OPEN)
            this._wsSend({ type: 'snapshot_req' });
        }, ms);
      }
      for (const ms of [450, 1200]) {
        setTimeout(() => {
          if (this._ws && this._ws.readyState === WebSocket.OPEN)
            this._wsSend({ type: 'analyze_req' });
        }, ms);
      }
    });

    this._q('release').addEventListener('click', () => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      this._wsSend({ type: 'hijack_release' });
    });

    this._q('resync').addEventListener('click', () => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      this._wsSend({ type: 'snapshot_req' });
    });

    this._q('analyze').addEventListener('click', () => {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      this._wsSend({ type: 'analyze_req' });
    });

    // Text input send — for pasting strings or escape sequences when hijacked
    const inputField = this._q('inputfield');
    const inputSend  = this._q('inputsend');
    if (inputField) {
      const doSend = () => {
        const raw = inputField.value;
        if (!raw || !this._hijackedByMe) return;
        if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
        // Unescape \\r → \r, \\n → \n, \\t → \t, \\e → ESC
        const data = raw
          .replace(/\\r/g, '\r')
          .replace(/\\n/g, '\n')
          .replace(/\\t/g, '\t')
          .replace(/\\e/g, '\x1b');
        this._wsSend({ type: 'input', data });
        inputField.value = '';
        try { this._ensureTerm().focus(); } catch (_) {}
      };
      inputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); doSend(); }
      });
      if (inputSend) inputSend.addEventListener('click', doSend);
    }
  }
}

// ── Global exposure for CDN / script-tag use ──────────────────────────────────
if (typeof window !== 'undefined') window.UndefHijack = UndefHijack;
