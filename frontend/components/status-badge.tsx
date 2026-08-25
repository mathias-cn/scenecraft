import { STATUS_CLASS, STATUS_LABEL, statusTone } from "@/lib/project-ui";
import type { ProjectStatus } from "@/lib/types";

type StatusBadgeProps = {
  status: ProjectStatus;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const tone = statusTone(status);
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 font-mono text-[10px] tracking-wide uppercase ${STATUS_CLASS[tone]}`}
    >
      {STATUS_LABEL[tone]}
    </span>
  );
}
