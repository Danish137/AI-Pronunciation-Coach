import type { PatternInsight } from "../types/assessment";

type InsightsPanelProps = {
  patterns: PatternInsight[];
};

export function InsightsPanel({ patterns }: InsightsPanelProps) {
  if (!patterns.length) return null;

  return (
    <section className="insights-card">
      <div className="section-header">
        <div>
          <span className="small-label">Speaking patterns</span>
          <h3>Recurring habits to address</h3>
        </div>
      </div>
      <div className="insights-list">
        {patterns.map((pattern) => (
          <article key={pattern.label} className="insight-row">
            <div>
              <strong>{pattern.label}</strong>
              <p>{pattern.explanation}</p>
              {pattern.affected_words.length > 0 ? (
                <div className="pattern-words">
                  {pattern.affected_words.map((w) => (
                    <span key={w} className="word-tag">{w}</span>
                  ))}
                </div>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
