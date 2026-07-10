import type { SourceType } from "../types/assessment";
import { Recorder } from "./Recorder";

type UploadCardProps = {
  acceptedTypes: string;
  consentAccepted: boolean;
  error: string;
  isSubmitting: boolean;
  onConsentChange: (value: boolean) => void;
  onFileChange: (file: File | null, sourceType: SourceType, knownDuration?: number) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  selectedFileLabel: string | null;
  canSubmit: boolean;
};

export function UploadCard({
  acceptedTypes,
  consentAccepted,
  error,
  isSubmitting,
  onConsentChange,
  onFileChange,
  onSubmit,
  selectedFileLabel,
  canSubmit,
}: UploadCardProps) {
  return (
    <section className="intake-card">
      <div className="intro-copy">
        <h1>Improve your English pronunciation</h1>
        <p>Upload or record a natural 30 to 45 second sample and receive focused, evidence-based coaching.</p>
      </div>

      <div className="intake-rules" aria-label="Recording rules">
        <span>30-45 seconds</span>
        <span>English only</span>
        <span>WAV, MP3, M4A, WEBM</span>
      </div>

      <form onSubmit={onSubmit} className="assessment-form">
        <div className="capture-layout">
          <label className="upload-dropzone">
            <input
              type="file"
              accept={acceptedTypes}
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                onFileChange(file, "upload");
              }}
            />
            <div className="upload-dropzone-icon" aria-hidden="true">
              <span className="upload-dropzone-arrow">↑</span>
            </div>
            <span className="small-label">Upload audio</span>
            <strong>Select a recording</strong>
            <p>Drag and drop an audio file here, or click to browse. You do not need a script.</p>
          </label>

          <Recorder
            onReady={(file, durationSeconds) => {
              onFileChange(file, "recording", durationSeconds);
            }}
          />
        </div>

        <label className="consent-row">
          <input type="checkbox" checked={consentAccepted} onChange={(event) => onConsentChange(event.target.checked)} />
          <span>
            I consent to my recording and transcript being processed for pronunciation coaching, as described in the <a href="/privacy">Privacy Notice</a>. Raw audio is removed after analysis; results are kept for up to 90 days or until I delete them.
          </span>
        </label>

        <div className="submit-row">
          <div className="selected-file-copy">
            <strong>{selectedFileLabel ?? "Choose or record a valid sample to begin."}</strong>
            <p>Analysis unlocks as soon as the sample is in the 30 to 45 second range and consent is checked.</p>
          </div>
          <button className="primary-button" disabled={!canSubmit || isSubmitting}>
            {isSubmitting ? "Analyzing..." : "Analyze pronunciation"}
          </button>
        </div>

        {error ? <p className="error-text">{error}</p> : null}
      </form>
    </section>
  );
}
