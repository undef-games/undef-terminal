import type { SessionSummary } from "../../api/types";

interface SessionMetaProps {
  summary: SessionSummary;
}

export function SessionMeta({ summary }: SessionMetaProps) {
  return (
    <>
      <div style={{ borderTop: "0.5px solid var(--border-primary)", paddingTop: 16 }}>
        <SectionLabel>Session info</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
          <MetaRow label="Connector" value={summary.connectorType} />
          <MetaRow label="State" value={summary.lifecycleState} />
          <MetaRow label="Owner" value={summary.owner ?? "—"} />
          <MetaRow label="Visibility" value={summary.visibility} />
          <MetaRow
            label="Auto-start"
            value={summary.autoStart ? "yes" : "no"}
            valueColor={summary.autoStart ? "var(--text-success)" : undefined}
          />
        </div>
      </div>

      {summary.tags.length > 0 && (
        <div style={{ borderTop: "0.5px solid var(--border-primary)", paddingTop: 16 }}>
          <SectionLabel>Tags</SectionLabel>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {summary.tags.map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: "var(--radius-pill)",
                  border: "0.5px solid var(--border-primary)",
                  color: "var(--text-secondary)",
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11,
      textTransform: "uppercase",
      letterSpacing: "0.5px",
      color: "var(--text-tertiary)",
      marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function MetaRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span style={{ color: valueColor }}>{value}</span>
    </div>
  );
}
