interface MetricCardProps {
  label: string;
  value: number;
  color?: string;
}

export function MetricCard({ label, value, color }: MetricCardProps) {
  return (
    <div style={{
      background: "var(--bg-secondary)",
      borderRadius: "var(--radius-md)",
      padding: "1rem",
    }}>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 500, color: color ?? "var(--text-primary)" }}>{value}</div>
    </div>
  );
}
