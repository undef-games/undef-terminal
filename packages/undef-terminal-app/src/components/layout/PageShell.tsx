import type { ReactNode } from "react";

interface PageShellProps {
  children: ReactNode;
}

export function PageShell({ children }: PageShellProps) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      minHeight: "100%",
      background: "var(--bg-primary)",
    }}>
      {children}
    </div>
  );
}
