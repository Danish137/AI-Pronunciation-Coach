import type { RecordingSummary } from "../types/assessment";

type CoachSummaryPanelProps = {
  summary: RecordingSummary;
};

export function CoachSummaryPanel({ summary }: CoachSummaryPanelProps) {
  return (
    <section className="coach-summary-card">
      <div className="summary-heading">
        <span className="small-label">AI Coach</span>
        <h3>What your coach noticed</h3>
      </div>

      {summary.overall_habit ? (
        <p className="coach-paragraph">{summary.overall_habit}</p>
      ) : null}

      {summary.patterns.length > 0 ? (
        <div className="coach-patterns">
          <span className="small-label">Recurring patterns</span>
          {summary.patterns.map((pattern) => (
            <div key={pattern.label} className="coach-pattern">
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
          ))}
        </div>
      ) : null}

      {summary.strengths.length > 0 ? (
        <div className="summary-columns">
          <div>
            <strong>Strengths</strong>
            <ul>
              {summary.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
