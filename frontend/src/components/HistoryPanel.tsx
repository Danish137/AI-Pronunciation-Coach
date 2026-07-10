import type { Assessment } from "../types/assessment";

type HistoryPanelProps = {
  attempts: Assessment[];
  activeAttemptId: number | null;
  onSelect: (attempt: Assessment) => void;
  onDelete: (id: number) => void;
  onDeleteAll: () => void;
  deletingAll: boolean;
};

export function HistoryPanel({
  attempts,
  activeAttemptId,
  onSelect,
  onDelete,
  onDeleteAll,
  deletingAll,
}: HistoryPanelProps) {
  return (
    <section className="history-card">
      <div className="section-copy history-header">
        <div>
          <span className="section-kicker">History</span>
          <h3>Recent attempts</h3>
        </div>
        <button
          className="ghost-button"
          type="button"
          onClick={onDeleteAll}
          disabled={!attempts.length || deletingAll}
        >
          Delete history
        </button>
      </div>

      {attempts.length ? (
        <div className="history-list">
          {attempts.map((attempt, index) => {
            const previous = attempts[index + 1];
            const delta = previous
              ? Math.round(attempt.overall_score - previous.overall_score)
              : null;
            const flaggedCount = attempt.word_coaching.length;

            return (
              <article
                key={attempt.id}
                className={`history-item ${attempt.id === activeAttemptId ? "active" : ""}`}
                onClick={() => onSelect(attempt)}
              >
                <div className="history-core">
                  <strong>{Math.round(attempt.overall_score)}/100</strong>
                  <p>{new Date(attempt.created_at).toLocaleString()}</p>
                </div>
                <div className="history-meta">
                  <span>{Math.round(attempt.duration_seconds)}s</span>
                  <span>{flaggedCount} flagged</span>
                  {delta !== null ? (
                    <span className={delta >= 0 ? "positive-text" : "negative-text"}>
                      {delta >= 0 ? `+${delta}` : delta}
                    </span>
                  ) : null}
                </div>
                <div className="history-actions">
                  <button
                    className="inline-button"
                    type="button"
                    onClick={() => onSelect(attempt)}
                  >
                    View details
                  </button>
                  <button
                    className="inline-button destructive"
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(attempt.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="empty-history">
          <span className="section-kicker">No attempts yet</span>
          <h4>Record your first pronunciation sample.</h4>
          <p>
            Your best practice words and improvement trend will appear here after the first
            analysis.
          </p>
        </div>
      )}
    </section>
  );
}
