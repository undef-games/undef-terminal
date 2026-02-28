/**
 * UndefTerminal — settings panel, WebSocket, input, and status methods.
 * Extends UndefTerminal.prototype. Must be loaded after terminal.js.
 */
'use strict';

Object.assign(UndefTerminal.prototype, {
  // ── Settings Panel ────────────────────────────────────────────────────────

  _openSettings() {
    this._q('settingsPanel').classList.add('open');
    this._q('settingsOverlay').classList.add('open');
    this._applySettingsToUI();
  },

  _closeSettings() {
    this._q('settingsPanel').classList.remove('open');
    this._q('settingsOverlay').classList.remove('open');
    if (this._term) this._term.focus();
  },

  _toggleSettings() {
    if (this._q('settingsPanel').classList.contains('open')) {
      this._closeSettings();
    } else {
      this._openSettings();
    }
  },

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
  },

  // ── WebSocket Connection ─────────────────────────────────────────────────

  _resolveWsUrl() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = this._config.wsUrl;
    if (!url) return `${proto}//${location.host}/ws`;
    if (url.startsWith('/')) return `${proto}//${location.host}${url}`;
    return url; // already absolute ws:// or wss://
  },

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
            const text = new TextDecoder('latin-1').decode(data);
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
  },

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
  },

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
});

