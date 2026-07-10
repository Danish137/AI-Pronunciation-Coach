import { useDeferredValue, useMemo, useState } from "react";

import type { WordCoaching } from "../types/assessment";

type FilterValue = "all" | "severe" | "moderate" | "minor";

type TranscriptViewerProps = {
  transcript: string;
  wordCoaching: WordCoaching[];
  selectedStartMs: number | null;
  onSelectWord: (word: WordCoaching) => void;
};

const FILTER_OPTIONS: { value: FilterValue; label: string }[] = [
  { value: "all", label: "All flagged" },
  { value: "severe", label: "Severe" },
  { value: "moderate", label: "Moderate" },
  { value: "minor", label: "Minor" },
];

function speak(text: string, rate: number) {
  if (!("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = rate;
  utterance.lang = "en-US";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

export function TranscriptViewer({
  transcript,
  wordCoaching,
  selectedStartMs,
  onSelectWord,
}: TranscriptViewerProps) {
  const [filter, setFilter] = useState<FilterValue>("all");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);

  // Build a lookup from word (lowercase) → coaching item for transcript highlighting
  const coachingByWord = useMemo(() => {
    const map = new Map<string, WordCoaching>();
    for (const wc of wordCoaching) {
      // Keep the worst-scoring instance if same word appears twice (shouldn't after dedup, but safe)
      const existing = map.get(wc.word.toLowerCase());
      if (!existing || wc.score < existing.score) {
        map.set(wc.word.toLowerCase(), wc);
      }
    }
    return map;
  }, [wordCoaching]);

  const filteredCoaching = useMemo(() => {
    return wordCoaching.filter((wc) => {
      const matchesFilter = filter === "all" ? true : wc.severity === filter;
      const matchesSearch = deferredSearch.trim()
        ? wc.word.toLowerCase().includes(deferredSearch.trim().toLowerCase())
        : true;
      return matchesFilter && matchesSearch;
    });
  }, [deferredSearch, filter, wordCoaching]);

  const selectedWord =
    filteredCoaching.find((wc) => wc.start_ms === selectedStartMs) ??
    wordCoaching.find((wc) => wc.start_ms === selectedStartMs) ??
    null;

  // Render transcript as tokens, highlighting coached words
  const transcriptTokens = useMemo(() => {
    if (!transcript) return [];
    return transcript.split(/(\s+)/).map((token, i) => {
      const clean = token.replace(/[.,!?;:'"]/g, "").toLowerCase();
      const coaching = coachingByWord.get(clean);
      return { token, coaching, key: i };
    });
  }, [transcript, coachingByWord]);

  return (
    <section className="transcript-card">
      <div className="section-header">
        <div>
          <span className="small-label">Interactive transcript</span>
          <h3>Click any highlighted word to see its coaching</h3>
          <p className="transcript-click-hint">
            Highlighted words are clickable. Filled highlights are higher priority; outlined words are lower priority.
          </p>
        </div>
      </div>

      {/* Full transcript with inline highlights */}
      {transcript ? (
        <div className="transcript-flow transcript-prose">
          {transcriptTokens.map(({ token, coaching, key }) => {
            if (!coaching || /^\s+$/.test(token)) {
              return <span key={key}>{token}</span>;
            }
            const isSelected = selectedStartMs === coaching.start_ms;
            return (
              <button
                key={key}
                className={`word-pill ${coaching.severity} ${isSelected ? "selected" : ""}`}
                type="button"
                onClick={() => onSelectWord(coaching)}
              >
                {token}
              </button>
            );
          })}
        </div>
      ) : null}

      {/* Toolbar for filtered word list */}
      {wordCoaching.length > 0 ? (
        <>
          <div className="transcript-toolbar">
            <div className="filter-row" role="tablist" aria-label="Severity filters">
              {FILTER_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  className={`filter-chip ${filter === option.value ? "active" : ""}`}
                  type="button"
                  onClick={() => setFilter(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <input
              className="transcript-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search a word"
              aria-label="Search coached words"
            />
          </div>

          <div className="word-analysis-grid">
            {filteredCoaching.map((wc) => (
              <article
                key={`${wc.word}-${wc.start_ms}`}
                className={`analysis-card ${wc.severity} ${selectedStartMs === wc.start_ms ? "selected" : ""}`}
                onClick={() => onSelectWord(wc)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onSelectWord(wc)}
              >
                <div className="analysis-topline">
                  <strong>{wc.word}</strong>
                  <span>{Math.round(wc.score)}/100</span>
                </div>
                <p>{wc.what_happened}</p>
              </article>
            ))}
          </div>
        </>
      ) : null}

      {/* Selected word detail drawer */}
      {selectedWord ? (
        <article className={`word-drawer ${selectedWord.severity}`}>
          <div className="word-drawer-header">
            <div>
              <span className="small-label">Word detail</span>
              <h4>{selectedWord.word}</h4>
              {selectedWord.native_audio_hint ? (
                <span className="issue-ipa">{selectedWord.native_audio_hint}</span>
              ) : null}
            </div>
            <strong>{Math.round(selectedWord.score)}/100</strong>
          </div>

          <div className="word-detail-grid">
            <p>
              <strong>What happened:</strong> {selectedWord.what_happened}
            </p>
            <p>
              <strong>Why it matters:</strong> {selectedWord.why}
            </p>
            <p>
              <strong>How to fix it:</strong> {selectedWord.how_to_fix}
            </p>
          </div>

          {selectedWord.practice_drills.length > 0 ? (
            <div className="issue-drill">
              <span className="small-label">Practice progression</span>
              <ol className="drill-list">
                {selectedWord.practice_drills.map((drill, i) => (
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

          <div className="button-row">
            <button
              className="ghost-button"
              type="button"
              onClick={() => speak(selectedWord.word, 0.92)}
            >
              ▶ Native
            </button>
            <button
              className="ghost-button"
              type="button"
              onClick={() => speak(selectedWord.word, 0.45)}
            >
              ▶ Slow
            </button>
          </div>
        </article>
      ) : null}
    </section>
  );
}
