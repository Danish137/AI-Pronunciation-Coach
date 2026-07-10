import React from "react";
import type { PracticeSession } from "../types/assessment";

type PracticePanelProps = {
  practice: PracticeSession;
};

function speak(text: string, rate: number) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = rate;
  u.lang = "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function PracticePanel({ practice }: PracticePanelProps) {
  const hasDrills = practice.drills.length > 0;
  const hasSentences = practice.context_sentences.length > 0;

  if (!hasDrills && !hasSentences) return null;

  return (
    <section className="practice-card">
      <div className="section-header">
        <div>
          <span className="small-label">Practice session</span>
          <h3>{practice.focus}</h3>
          <p>Work through each progression: isolated word → short phrase → full sentence.</p>
        </div>
      </div>

      {hasDrills ? (
        <div className="drill-groups">
          {practice.drills.map((drill) => (
            <div key={drill.theme} className="drill-group">
              <span className="small-label">{drill.theme}</span>
              <ol className="sentence-list">
                {drill.progression.map((step, i) => (
                  <li key={i} className="sentence-item">
                    <div className="sentence-body">
                      <p className="sentence-text">{highlightWords(step, drill.words)}</p>
                      <div className="sentence-actions">
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={() => speak(step, 0.92)}
                        >
                          Hear it
                        </button>
                        <button
                          className="ghost-button"
                          type="button"
                          onClick={() => speak(step, 0.6)}
                        >
                          Slow
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      ) : null}

      {hasSentences ? (
        <div className="context-sentences">
          <span className="small-label">From your recording</span>
          <ol className="sentence-list">
            {practice.context_sentences.map((sentence) => (
              <li key={sentence} className="sentence-item">
                <div className="sentence-body">
                  <p className="sentence-text">{sentence}</p>
                  <div className="sentence-actions">
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => speak(sentence, 0.92)}
                    >
                      Hear it
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() => speak(sentence, 0.6)}
                    >
                      Slow
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

function highlightWords(text: string, words: string[]): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  for (const word of words) {
    const idx = remaining.toLowerCase().indexOf(word.toLowerCase());
    if (idx === -1) continue;
    if (idx > 0) parts.push(<span key={key++}>{remaining.slice(0, idx)}</span>);
    parts.push(
      <mark key={key++} className="focus-word">
        {remaining.slice(idx, idx + word.length)}
      </mark>,
    );
    remaining = remaining.slice(idx + word.length);
  }
  if (remaining) parts.push(<span key={key++}>{remaining}</span>);
  return parts.length ? parts : [<span key={0}>{text}</span>];
}
