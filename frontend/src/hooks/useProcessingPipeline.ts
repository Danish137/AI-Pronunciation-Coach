import { useEffect, useState } from "react";

const PROCESS_STEPS = [
  { label: "Uploading audio...", pct: 8 },
  { label: "Checking pronunciation details...", pct: 22 },
  { label: "Analyzing pronunciation...", pct: 48 },
  { label: "Generating AI coaching...", pct: 72 },
  { label: "Building your practice plan...", pct: 90 },
  { label: "Finishing up...", pct: 98 },
] as const;

export type PipelineStep = (typeof PROCESS_STEPS)[number];

export function useProcessingPipeline(active: boolean) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setStepIndex(0);
      return;
    }

    setStepIndex(0);
    const timers = [
      window.setTimeout(() => setStepIndex(1), 800),
      window.setTimeout(() => setStepIndex(2), 2200),
      window.setTimeout(() => setStepIndex(3), 5500),
      window.setTimeout(() => setStepIndex(4), 10000),
      window.setTimeout(() => setStepIndex(5), 14000),
    ];

    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [active]);

  return {
    steps: PROCESS_STEPS,
    stepIndex,
    progressPct: PROCESS_STEPS[stepIndex]?.pct ?? 0,
  };
}
