interface MetricCardProps {
  label: string;
  value: number;
  color?: string;
}

export function MetricCard({ label, value, color }: MetricCardProps) {
  return (
    <div className="card">
      <div className="card-label">{label}</div>
      <div className="card-value" style={{ color: color ?? "var(--text-primary)" }}>{value}</div>
    </div>
  );
}
