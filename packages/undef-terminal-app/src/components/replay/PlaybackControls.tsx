import { useReplayStore } from "../../stores/replayStore";
import styles from "./ReplayPage.module.css";

interface PlaybackControlsProps {
  sessionId: string;
}

export function PlaybackControls({ sessionId }: PlaybackControlsProps) {
  const { entries, index, filter, limit, playing, speed, load, setFilter, setLimit, first, prev, next, last, setPlaying, setSpeed } = useReplayStore();

  return (
    <div className={styles.controlBar}>
      <div className={styles.navButtons}>
        <NavButton onClick={first} label="|&lt;" />
        <NavButton onClick={prev} label="&lt;" />
        <button
          type="button"
          onClick={() => setPlaying(!playing)}
          style={{
            fontSize: 14, padding: "6px 14px", width: 44, textAlign: "center",
            background: "var(--bg-info)", borderColor: "var(--border-info)", color: "var(--text-info)",
          }}
        >
          {playing ? "\u23F8" : "\u25B6"}
        </button>
        <NavButton onClick={next} label="&gt;" />
        <NavButton onClick={last} label="&gt;|" />
      </div>

      <select value={String(speed)}
        onChange={(e) => setSpeed(Number(e.target.value) as 0.5 | 1 | 2 | 4)}
        style={{ width: "auto", fontSize: 12, padding: "6px 10px" }}>
        <option value="0.5">0.5x</option>
        <option value="1">1x</option>
        <option value="2">2x</option>
        <option value="4">4x</option>
      </select>

      <select value={filter}
        onChange={(e) => { setFilter(e.target.value); void load(sessionId); }}
        style={{ width: "auto", fontSize: 12, padding: "6px 10px" }}>
        <option value="">All events</option>
        <option value="read">read</option>
        <option value="send">send</option>
        <option value="runtime_started">runtime_started</option>
        <option value="runtime_error">runtime_error</option>
      </select>

      <select value={String(limit)}
        onChange={(e) => { setLimit(Number(e.target.value)); void load(sessionId); }}
        style={{ width: "auto", fontSize: 12, padding: "6px 10px" }}>
        <option value="25">25</option>
        <option value="100">100</option>
        <option value="200">200</option>
      </select>

      <div style={{ flex: 1 }} />
      <span className={styles.eventCount}>
        Event {entries.length > 0 ? index + 1 : 0} of {entries.length}
      </span>
    </div>
  );
}

function NavButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick}
      // biome-ignore lint/security/noDangerouslySetInnerHtml: static nav symbols
      dangerouslySetInnerHTML={{ __html: label }}
      style={{ fontSize: 14, padding: "6px 12px", width: 36, textAlign: "center" }}
    />
  );
}
