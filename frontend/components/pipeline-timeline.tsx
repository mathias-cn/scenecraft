import { PIPELINE_STEPS, pipelineStepState } from "@/lib/pipeline";
import type { ProjectStage, ProjectStatus } from "@/lib/types";

type PipelineTimelineProps = {
  currentStage: ProjectStage;
  status: ProjectStatus;
};

const STATE_DOT: Record<string, string> = {
  complete: "border-brass-500 bg-brass-500 text-ink-950",
  current: "border-brass-400 bg-ink-950 ring-2 ring-brass-400/40",
  failed: "border-red-400 bg-red-400",
  upcoming: "border-white/20 bg-ink-950",
};

const STATE_TEXT: Record<string, string> = {
  complete: "text-brass-400",
  current: "text-white",
  failed: "text-red-300",
  upcoming: "text-white/35",
};

export function PipelineTimeline({ currentStage, status }: PipelineTimelineProps) {
  return (
    <ol className="flex flex-col md:flex-row md:items-start" aria-label="Estágios do pipeline">
      {PIPELINE_STEPS.map((step, index) => {
        const state = pipelineStepState(index, currentStage, status);
        const last = index === PIPELINE_STEPS.length - 1;
        return (
          <li key={step.id} className="flex min-h-0 md:min-w-0 md:flex-1 md:flex-col">
            <div className="flex shrink-0 flex-col items-center self-stretch md:w-full md:flex-row md:items-center">
              <span
                className={`inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${STATE_DOT[state]}`}
                aria-current={state === "current" ? "step" : undefined}
              >
                {state === "complete" ? (
                  <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" aria-hidden>
                    <path
                      d="M2.5 6.2 5 8.5 9.5 3.5"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : null}
              </span>
              {last ? null : (
                <span
                  className={`mt-1 w-px min-h-[1.25rem] flex-1 md:mt-0 md:ml-1 md:h-px md:min-h-0 md:w-auto md:flex-1 ${
                    state === "complete" ? "bg-brass-500/50" : "bg-white/10"
                  }`}
                />
              )}
            </div>
            <div className="pb-5 pl-3 md:pb-0 md:pl-0 md:pt-2 md:pr-2">
              <p className={`font-mono text-[10px] tracking-wide uppercase ${STATE_TEXT[state]}`}>
                {step.label}
              </p>
              {state === "current" ? (
                <p className="mt-0.5 font-mono text-[10px] text-white/40">atual</p>
              ) : state === "complete" ? (
                <p className="mt-0.5 font-mono text-[10px] text-brass-500/70">ok</p>
              ) : state === "failed" ? (
                <p className="mt-0.5 font-mono text-[10px] text-red-400/80">falhou</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
