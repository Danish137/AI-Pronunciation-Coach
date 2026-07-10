import type { Assessment } from "../types/assessment";

type ResultHeaderProps = {
  assessment: Assessment;
  improvementDelta: number | null;
};

export function ResultHeader({ assessment, improvementDelta }: ResultHeaderProps) {
  const dur = Math.round(assessment.duration_seconds);
  const providerLabel = assessment.provider_mode === "azure" ? "Live analysis" : "Mock mode";
  const { summary } = assessment;

  return (
    <section className="result-header">
      {/* Score + level */}
      <div className="result-main">
        <div className="score-block">
          <span className="score-big">{Math.round(assessment.overall_score)}</span>
          <span className="score-denom">/100</span>
        </div>
        <div className="result-text">
          <h2>{summary.level_label}</h2>
          <p>{summary.overall_habit}</p>
        </div>
      </div>

      {/* Pills */}
      <div className="result-pills">
        <span className="result-pill">{dur}s</span>
        <span className="result-pill">{providerLabel}</span>
        {improvementDelta !== null ? (
          <span className={`result-pill ${improvementDelta >= 0 ? "pill-positive" : "pill-negative"}`}>
            {improvementDelta > 0 ? `+${improvementDelta}` : improvementDelta} from last attempt
          </span>
        ) : null}
      </div>

      {/* Primary action */}
      <div className="result-highlight">
        <p className="celebration-note">{summary.primary_action}</p>
        <p className="result-subcopy">{summary.gain_estimate}</p>
      </div>

      {/* Strengths */}
      {summary.strengths.length > 0 ? (
        <div className="result-strengths">
          <span className="small-label">What's working</span>
          <ul>
            {summary.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Recurring habit */}
      {summary.patterns.length > 0 ? (
        <div className="result-recurring-habit">
          <span className="small-label">Recurring habit</span>
          <strong>{summary.patterns[0].label}</strong>
          <p>{summary.patterns[0].explanation}</p>
        </div>
      ) : null}
    </section>
  );
}
