import { restartSession } from "../../api/sessions";
import type { AppBootstrap } from "../../api/types";
import { useSessionStore } from "../../stores/sessionStore";
import { ModeToggle } from "./ModeToggle";
import { SessionMeta } from "./SessionMeta";

interface OperatorSidebarProps {
  sessionId: string;
  bootstrap: AppBootstrap;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, textTransform: "uppercase", letterSpacing: "0.5px",
      color: "var(--text-tertiary)", marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

export function OperatorSidebar({ sessionId, bootstrap }: OperatorSidebarProps) {
  const { summary, analysis, modePending, utilityPending, switchMode, clear, analyze } = useSessionStore();

  return (
    <>
      <div>
        <SectionLabel>Input mode</SectionLabel>
        <ModeToggle
          mode={summary?.inputMode ?? "hijack"}
          disabled={modePending}
          onChange={(mode) => void switchMode(sessionId, mode)}
        />
      </div>

      <div>
        <SectionLabel>Actions</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <button type="button" style={{ textAlign: "left", width: "100%", padding: "8px 12px" }}
            disabled={utilityPending} onClick={() => void analyze(sessionId)}>
            Analyze screen
          </button>
          <a className="action-link" style={{ textAlign: "left", width: "100%", padding: "8px 12px", justifyContent: "flex-start" }}
            href={`${bootstrap.app_path}/replay/${encodeURIComponent(sessionId)}`}>
            View replay
          </a>
          <button type="button" style={{ textAlign: "left", width: "100%", padding: "8px 12px" }}
            disabled={utilityPending} onClick={() => void clear(sessionId)}>
            Clear runtime
          </button>
        </div>
      </div>

      {analysis && (
        <div>
          <SectionLabel>Analysis</SectionLabel>
          <div style={{
            fontSize: 12, padding: 8, background: "var(--bg-tertiary)",
            borderRadius: "var(--radius-md)", whiteSpace: "pre-wrap", color: "var(--text-secondary)",
          }}>
            {analysis}
          </div>
        </div>
      )}

      {summary && <SessionMeta summary={summary} />}

      <div style={{ flex: 1 }} />

      <div style={{ borderTop: "0.5px solid var(--border-primary)", paddingTop: 12 }}>
        <button type="button" style={{
          width: "100%", padding: "8px 12px",
          color: "var(--text-danger)", borderColor: "var(--border-danger)",
        }} onClick={() => {
          void restartSession(sessionId).then(() => window.location.reload());
        }}>
          Restart session
        </button>
      </div>
    </>
  );
}
