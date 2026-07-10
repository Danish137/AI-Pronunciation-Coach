const RETENTION_DAYS = 90;
const CONTACT_EMAIL = "imdanishakhtar7@gmail.com";

export function PrivacyNoticePage() {
  return (
    <div className="privacy-shell">
      <main className="privacy-card">
        <a className="privacy-back-link" href="/">
          Back to coach
        </a>

        <header className="privacy-header">
          <span className="small-label">Privacy notice</span>
          <h1>PronounceAI Privacy Notice</h1>
          <p>
            This notice explains what PronounceAI processes, why it is processed, how long it is kept,
            and how deletion works for pronunciation coaching sessions.
          </p>
        </header>

        <section className="privacy-section">
          <h2>What we collect</h2>
          <p>
            We process your audio recording transiently so we can generate a transcript, pronunciation
            scores, and coaching feedback. We retain the recognized transcript, derived scores, word-level
            coaching, practice guidance, and related result payloads for your session history.
          </p>
          <p>
            Transcripts can contain identifying personal data if you speak your name, institution, city,
            employer, or other details in the recording. Deleting raw audio does not remove that fact, so
            transcript content is treated as personal data.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Why we process it</h2>
          <p>
            Your recording, transcript, and derived pronunciation data are used only to provide
            pronunciation assessment, coaching explanations, and practice recommendations. This application
            does not use that content for advertising or unrelated secondary purposes.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Processors and data flow</h2>
          <p>
            Azure Speech is used for speech recognition and pronunciation assessment. In this deployment,
            the configured Azure Speech region is Central India.
          </p>
          <p>
            Groq is used to generate coaching text from the transcript and pronunciation diagnostics. That
            means transcript content and derived diagnostic context are sent to Groq as a named
            sub-processor. Groq processing is not India-hosted, so this step can involve cross-border
            processing.
          </p>
          <p>
            The deployed application may also rely on a hosting provider to run the web app and API. This
            repository does not fix a single production hosting vendor, so you should name your hosting
            provider in deployment-specific legal copy before launch.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Retention</h2>
          <p>
            Raw audio files are deleted immediately after analysis finishes. Session results, including the
            transcript, scores, and stored response payloads, are kept for up to {RETENTION_DAYS} days from
            creation or until you delete them, whichever comes first.
          </p>
          <p>
            A daily automated retention job deletes expired rows from the attempts table, including stored
            transcript content, result payloads, and any raw Azure payload JSON attached to the row.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Deletion</h2>
          <p>
            You can delete a single attempt or your full session history from the app while you still have
            the same browser session identifier. If you lose that browser storage, you may lose direct
            access to in-app deletion for those rows, which is why the automatic retention purge exists as a
            backstop.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Questions or requests</h2>
          <p>
            For privacy, deletion, or data-related questions, contact <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          </p>
        </section>
      </main>
    </div>
  );
}
