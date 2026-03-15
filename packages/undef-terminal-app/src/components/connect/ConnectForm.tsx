import { useState } from "react";
import { quickConnect } from "../../api/sessions";
import type { AppBootstrap } from "../../api/types";
import { saveRecent } from "./ConnectPage";
import styles from "./ConnectPage.module.css";

const labelStyle = { fontSize: 12, color: "var(--text-secondary)", display: "block", marginBottom: 4 } as const;

interface ConnectFormProps {
  bootstrap: AppBootstrap;
}

export function ConnectForm({ bootstrap: _bootstrap }: ConnectFormProps) {
  const [connType, setConnType] = useState("telnet");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("23");
  const [portEdited, setPortEdited] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [recording, setRecording] = useState(true);
  const [autoReconnect, setAutoReconnect] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const needsHost = connType === "ssh" || connType === "telnet";

  function handleTypeChange(value: string) {
    setConnType(value);
    if (!portEdited) {
      setPort(value === "telnet" ? "23" : "22");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (needsHost && !host.trim()) {
      setError(`Host is required for ${connType.toUpperCase()} connections.`);
      return;
    }
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = { connector_type: connType };
      if (needsHost) {
        payload.host = host.trim();
        payload.port = parseInt(port, 10) || (connType === "telnet" ? 23 : 22);
      }
      if (connType === "ssh") {
        if (username.trim()) payload.username = username.trim();
        if (password) payload.password = password;
      }
      if (recording) payload.recording_enabled = true;
      if (autoReconnect) payload.auto_start = true;
      // biome-ignore lint/suspicious/noExplicitAny: quickConnect payload
      const result = await quickConnect(payload as any);
      if (needsHost) {
        saveRecent({
          host: host.trim(), transport: connType,
          port: parseInt(port, 10) || 23, lastUsed: new Date().toISOString(),
        });
      }
      window.location.href = result.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)}>
      <div className={styles.formGrid}>
        <label>
          <span style={labelStyle}>Host</span>
          <input type="text" value={needsHost ? host : "(local)"}
            onChange={needsHost ? (e) => setHost(e.target.value) : undefined}
            placeholder="bbs.example.com" disabled={!needsHost} readOnly={!needsHost} />
        </label>
        <label>
          <span style={labelStyle}>Transport</span>
          <select value={connType} onChange={(e) => handleTypeChange(e.target.value)}>
            <option value="telnet">telnet</option>
            <option value="ssh">ssh</option>
            <option value="shell">shell</option>
          </select>
        </label>
        <label>
          <span style={labelStyle}>Port</span>
          <input type="text" value={port}
            onChange={(e) => { setPort(e.target.value); setPortEdited(true); }}
            placeholder="23" disabled={!needsHost} />
        </label>
      </div>

      {connType === "ssh" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
          <label>
            <span style={labelStyle}>Username</span>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
          </label>
          <label>
            <span style={labelStyle}>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" />
          </label>
        </div>
      )}

      <div className={styles.formRow}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)" }}>
          <input type="checkbox" checked={recording} onChange={(e) => setRecording(e.target.checked)} style={{ width: 14, height: 14 }} />
          Record session
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)", marginLeft: 16 }}>
          <input type="checkbox" checked={autoReconnect} onChange={(e) => setAutoReconnect(e.target.checked)} style={{ width: 14, height: 14 }} />
          Auto-reconnect
        </label>
        <div style={{ flex: 1 }} />
        <button type="submit" disabled={submitting} style={{
          fontSize: 13, padding: "8px 20px",
          background: "var(--bg-info)", borderColor: "var(--border-info)",
          color: "var(--text-info)", fontWeight: 500,
        }}>
          {submitting ? "Connecting…" : "Connect"}
        </button>
      </div>

      {error && <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-danger)" }}>{error}</div>}
    </form>
  );
}
