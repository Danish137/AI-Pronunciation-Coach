import { useState } from "react";

import type { WordCoaching } from "../types/assessment";

type TopIssuesSectionProps = {
  wordCoaching: WordCoaching[];
};

export function selectTopPriorityWords(wordCoaching: WordCoaching[]): WordCoaching[] {
  const sortByScore = (items: WordCoaching[]) => [...items].sort((left, right) => left.score - right.score);
  const severe = sortByScore(wordCoaching.filter((item) => item.severity === "severe"));
  const moderate = sortByScore(wordCoaching.filter((item) => item.severity === "moderate"));
  const minor = sortByScore(wordCoaching.filter((item) => item.severity === "minor"));
  const selected: WordCoaching[] = [];

  for (const item of severe) {
    if (selected.length >= 3) {
      break;
    }
    selected.push(item);
  }

  for (const item of moderate) {
    if (selected.length >= 3) {
      break;
    }
    selected.push(item);
  }

  for (const item of minor) {
    if (selected.length >= 3) {
      break;
    }
    selected.push(item);
  }

  return selected;
}

function speak(text: string, rate: number) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = rate;
  u.lang = "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

function CoachingCard({
  coaching,
  rank,
}: {
  coaching: WordCoaching;
  rank: number;
}) {
  const [expanded, setExpanded] = useState(rank === 1);

  return (
    <article className={`issue-card priority-${coaching.severity}`}>
      <button
        className="issue-card-header"
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="issue-card-title">
          <span className="issue-rank">{rank}</span>
          <div>
            <strong className="issue-word">{coaching.word}</strong>
            {coaching.native_audio_hint ? (
              <span className="issue-ipa">{coaching.native_audio_hint}</span>
            ) : null}
          </div>
        </div>
        <div className="issue-card-right">
          <span className={`issue-score score-${coaching.severity}`}>
            {Math.round(coaching.score)}
          </span>
          <span className="issue-chevron">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {expanded ? (
        <div className="issue-body">
          <p className="issue-problem">{coaching.what_happened}</p>
          <p className="issue-tip">{coaching.why}</p>

          {coaching.how_to_fix ? (
            <div className="issue-drill">
              <span className="small-label">How to fix it</span>
              <p>{coaching.how_to_fix}</p>
            </div>
          ) : null}

          {coaching.practice_drills.length > 0 ? (
            <div className="issue-drill">
              <span className="small-label">Practice progression</span>
              <ol className="drill-list">
                {coaching.practice_drills.map((drill, i) => (
                  <li key={i}>
                    <span>{drill}</span>
                    <button
                      className="ghost-button drill-hear"
                      type="button"
                      onClick={() => speak(drill, 0.85)}
                    >
                      Hear
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          <div className="issue-actions">
            <button
              className="ghost-button"
              type="button"
              onClick={() => speak(coaching.word, 0.92)}
            >
              ▶ Native
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => speak(coaching.word, 0.45)}
            >
              ▶ Slow
            </button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function TopIssuesSection({ wordCoaching }: TopIssuesSectionProps) {
  const visibleItems = selectTopPriorityWords(wordCoaching);

  if (!visibleItems.length) return null;

  return (
    <section className="issues-card">
      <div className="section-header">
        <div>
          <span className="small-label">Top priorities</span>
          <h3>Fix these first</h3>
          <p>Showing up to three highest-impact words, prioritized by severity and lowest score.</p>
        </div>
      </div>
      <div className="issue-list">
        {visibleItems.map((coaching, index) => (
          <CoachingCard
            key={`${coaching.word}-${coaching.start_ms}`}
            coaching={coaching}
            rank={index + 1}
          />
        ))}
      </div>
    </section>
  );
}
