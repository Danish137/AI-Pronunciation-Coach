export type SourceType = "upload" | "recording";

// ---------------------------------------------------------------------------
// Word-level coaching (only words scoring < 90)
// ---------------------------------------------------------------------------

export type WordCoaching = {
  word: string;
  score: number;
  severity: "minor" | "moderate" | "severe";
  what_happened: string;
  why: string;
  how_to_fix: string;
  practice_drills: string[];
  native_audio_hint: string | null;
  start_ms: number;
  end_ms: number;
};

// ---------------------------------------------------------------------------
// Pattern-level insight (cross-word speaking habits)
// ---------------------------------------------------------------------------

export type PatternInsight = {
  label: string;
  affected_words: string[];
  explanation: string;
  priority: number;
};

// ---------------------------------------------------------------------------
// Recording-level summary
// ---------------------------------------------------------------------------

export type RecordingSummary = {
  headline: string;
  level_label: string;
  overall_habit: string;
  strengths: string[];
  patterns: PatternInsight[];
  primary_action: string;
  gain_estimate: string;
};

// ---------------------------------------------------------------------------
// Practice session
// ---------------------------------------------------------------------------

export type PracticeDrill = {
  theme: string;
  words: string[];
  progression: string[];
};

export type PracticeSession = {
  focus: string;
  drills: PracticeDrill[];
  context_sentences: string[];
};

// ---------------------------------------------------------------------------
// Score metrics
// ---------------------------------------------------------------------------

export type ScoreMetric = {
  key: "overall" | "accuracy" | "prosody" | "fluency" | "completeness";
  label: string;
  score: number;
  band: string;
  explanation: string;
};

// ---------------------------------------------------------------------------
// Main assessment shape
// ---------------------------------------------------------------------------

export type Assessment = {
  id: number;
  source_type: SourceType;
  reference_text: string;
  transcript: string;
  overall_score: number;
  accuracy_score: number;
  fluency_score: number;
  prosody_score: number;
  completeness_score: number;
  duration_seconds: number;
  provider_mode: "mock" | "azure";
  summary: RecordingSummary;
  metrics: ScoreMetric[];
  word_coaching: WordCoaching[];
  practice: PracticeSession;
  created_at: string;
};

export type CreateAssessmentPayload = {
  file: File;
  sourceType: SourceType;
  consentAccepted: boolean;
  referenceText: string;
};
