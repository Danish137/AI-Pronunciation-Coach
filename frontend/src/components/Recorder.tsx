import { useEffect, useRef, useState } from "react";
import { MAX_SECONDS, MIN_SECONDS } from "../lib/audio";

type RecorderProps = {
  onReady: (file: File | null, durationSeconds?: number) => void;
};

export function Recorder({ onReady }: RecorderProps) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animationRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const secondsRef = useRef(0);

  const [isRecording, setIsRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => { secondsRef.current = seconds; }, [seconds]);

  useEffect(() => {
    if (!isRecording) return;
    const timer = window.setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  useEffect(() => {
    if (!isRecording) return;
    if (seconds >= MAX_SECONDS) stopRecording();
  }, [isRecording, seconds]);

  useEffect(() => { return () => cleanup(); }, []);

  function cleanup() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioContextRef.current?.close().catch(() => undefined);
    if (animationRef.current) window.cancelAnimationFrame(animationRef.current);
    streamRef.current = null;
    audioContextRef.current = null;
    analyserRef.current = null;
    animationRef.current = null;
  }

  function drawWaveform() {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const render = () => {
      if (!analyserRef.current) return;
      analyser.getByteFrequencyData(data);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const bars = 40;
      const barW = canvas.width / bars;
      for (let i = 0; i < bars; i++) {
        const v = data[i * 2] ?? 0;
        const h = (v / 255) * canvas.height * 0.88;
        const pct = v / 255;
        ctx.fillStyle = pct > 0.6 ? "#f59e0b" : pct > 0.25 ? "#0f9982" : "#c8dedd";
        const w = Math.max(3, barW - 5);
        ctx.beginPath();
        ctx.roundRect(i * barW + (barW - w) / 2, canvas.height - h, w, Math.max(2, h), 3);
        ctx.fill();
      }
      animationRef.current = window.requestAnimationFrame(render);
    };
    render();
  }

  async function startRecording() {
    setError("");
    setSeconds(0);
    secondsRef.current = 0;
    onReady(null);
    try {
      cleanup();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      streamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        const dur = secondsRef.current;
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" });
        const valid = dur >= MIN_SECONDS && dur <= MAX_SECONDS;
        onReady(valid ? file : null, valid ? dur : undefined);
        cleanup();
      };
      recorder.start(250);
      setIsRecording(true);
      drawWaveform();
    } catch {
      setError("Microphone access denied. You can upload an existing audio file instead.");
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") return;
    mediaRecorderRef.current.stop();
    setIsRecording(false);
  }

      const isValidWindow = seconds >= MIN_SECONDS && seconds <= MAX_SECONDS;
  const maxReached = seconds >= MAX_SECONDS;
  const progressPct = Math.min(100, (seconds / MAX_SECONDS) * 100);

  return (
    <div className="recorder-card">
      <div className="recorder-topline">
        <div>
          <span className="small-label">Microphone</span>
          <strong>{isRecording ? "Recording live" : "Ready to record"}</strong>
        </div>
        <span className={`rec-badge ${isRecording ? "active" : ""}`}>{isRecording ? "● REC" : "Standby"}</span>
      </div>

      <canvas ref={canvasRef} width={560} height={64} className="waveform" aria-hidden="true" />

      <div className="rec-progress-row">
        <div className="rec-bar-shell">
          <div className={`rec-bar-fill ${isValidWindow ? "valid" : ""}`} style={{ width: `${progressPct}%` }} />
        </div>
        <span className={`rec-time ${isValidWindow ? "valid" : ""}`}>{seconds}s / {MAX_SECONDS}s</span>
      </div>

      <p className={`rec-hint ${isValidWindow ? "valid" : ""} ${maxReached ? "max-reached" : ""}`}>
        {maxReached
          ? "✓ Max duration reached — click Analyze pronunciation below"
          : isValidWindow
          ? "✓ Ready — recording is in the 30–45 second window"
          : seconds === 0
          ? `Speak for at least ${MIN_SECONDS} seconds to enable analysis`
          : `${MIN_SECONDS - seconds}s more needed`}
      </p>

      <div className="button-row">
        <button className="secondary-button" type="button" onClick={startRecording} disabled={isRecording}>
          {isRecording ? "Recording…" : "Start recording"}
        </button>
        <button className="ghost-button" type="button" onClick={stopRecording} disabled={!isRecording}>
          Stop
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}
    </div>
  );
}
