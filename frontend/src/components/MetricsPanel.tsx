import type { ScoreMetric } from "../types/assessment";

type MetricsPanelProps = {
  metrics: ScoreMetric[];
};

export function MetricsPanel({ metrics }: MetricsPanelProps) {
  return (
    <section className="metrics-card">
      <div className="section-header">
        <div>
          <span className="small-label">Score breakdown</span>
          <h3>Detailed analytics</h3>
        </div>
      </div>
      <div className="metrics-list">
        {metrics.map((metric) => (
          <article key={metric.key} className="metric-row">
            <div>
              <strong>{metric.label}</strong>
              <p>{metric.explanation}</p>
            </div>
            <div className="metric-right">
              <span className="metric-score">{Math.round(metric.score)}</span>
              <span className="metric-band">{metric.band}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
