import type { RecordingEntryView } from "../../api/types";

interface ScreenPreviewProps {
  entry: RecordingEntryView | null;
  index: number;
}

export function ScreenPreview({ entry, index }: ScreenPreviewProps) {
  if (!entry) {
    return <div style={{ color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>No entries loaded.</div>;
  }

  const ts = entry.ts != null ? formatTime(entry.ts) : "—";

  return (
    <>
      <div className="screen-caption">
        Screen snapshot at event #{index + 1} ({ts})
      </div>
      <pre className="pre-block">
        {entry.screen || "(no screen data)"}
      </pre>
    </>
  );
}

function formatTime(ts: number): string {
  const h = Math.floor(ts / 3600);
  const m = Math.floor((ts % 3600) / 60);
  const s = Math.floor(ts % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
