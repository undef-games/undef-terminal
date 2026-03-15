import type { RecordingEntryView } from "../../api/types";

interface EventDetailProps {
  entry: RecordingEntryView | null;
}

export function EventDetail({ entry }: EventDetailProps) {
  if (!entry) {
    return (
      <div style={{ padding: "12px 14px", fontSize: 12, color: "var(--text-secondary)" }}>
        No event selected.
      </div>
    );
  }

  const ts = entry.ts != null ? formatTimestamp(entry.ts) : "—";
  const dataStr = JSON.stringify(entry.payload, null, 2);
  const bytes = entry.payload.data
    ? String(entry.payload.data).length
    : dataStr.length;

  return (
    <>
      <div style={{
        padding: "12px 14px",
        borderBottom: "0.5px solid var(--border-primary)",
      }}>
        <div style={{
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          color: "var(--text-tertiary)",
          marginBottom: 4,
        }}>
          Event detail
        </div>
        <div style={{ fontSize: 13, fontWeight: 500 }}>{entry.event}</div>
      </div>
      <div style={{ padding: "12px 14px", fontSize: 12, flex: 1, overflow: "auto" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <MetaRow label="Timestamp" value={ts} />
          <MetaRow label="Event" value={entry.event} />
          <MetaRow label="Bytes" value={String(bytes)} />
        </div>
        <div style={{
          marginTop: 12,
          padding: 8,
          background: "var(--bg-tertiary)",
          borderRadius: "var(--radius-md)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--text-secondary)",
          wordBreak: "break-all",
          whiteSpace: "pre-wrap",
          maxHeight: 200,
          overflow: "auto",
        }}>
          {dataStr}
        </div>
      </div>
    </>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{value}</span>
    </div>
  );
}

function formatTimestamp(ts: number): string {
  const totalSec = Math.floor(ts);
  const ms = Math.round((ts - totalSec) * 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}
