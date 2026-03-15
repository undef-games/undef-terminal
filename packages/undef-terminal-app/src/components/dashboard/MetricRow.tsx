import { MetricCard } from "../common/MetricCard";

interface MetricRowProps {
  total: number;
  live: number;
  errors: number;
  recording: number;
}

export function MetricRow({ total, live, errors, recording }: MetricRowProps) {
  return (
    <div className="metric-grid">
      <MetricCard label="Sessions" value={total} />
      <MetricCard label="Live" value={live} color="var(--success)" />
      <MetricCard label="Errors" value={errors} color="var(--danger)" />
      <MetricCard label="Recording" value={recording} />
    </div>
  );
}
