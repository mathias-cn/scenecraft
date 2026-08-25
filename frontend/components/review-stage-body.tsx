import type { ProjectDetail, ProjectStage } from "@/lib/types";

type ReviewBodyProps = {
  project: ProjectDetail;
};

function EmptyNote({ text }: { text: string }) {
  return <p className="text-sm text-white/40">{text}</p>;
}

function SceneReview({ project, withMedia }: ReviewBodyProps & { withMedia: boolean }) {
  const scenes = project.scenes ?? [];
  if (scenes.length === 0) {
    return <EmptyNote text="Nenhuma cena gerada ainda." />;
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {scenes.map((scene) => (
        <li key={scene.id} className="overflow-hidden rounded-lg border border-white/10 bg-ink-950">
          {withMedia && scene.media_url ? (
            scene.media_type === "video" ? (
              <video src={scene.media_url} controls className="aspect-video w-full bg-black" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element -- URLs do storage são dinâmicas
              <img src={scene.media_url} alt="" className="aspect-video w-full object-cover" />
            )
          ) : (
            <div className="flex aspect-video items-center justify-center bg-white/5 font-mono text-[10px] text-white/25">
              {withMedia ? "sem mídia" : `cena ${scene.index}`}
            </div>
          )}
          <div className="p-3">
            <p className="font-mono text-[10px] text-white/35">#{scene.index}</p>
            <p className="mt-1 text-sm text-white/75">{scene.visual_prompt}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function AudioReview({ project }: ReviewBodyProps) {
  const tracks = project.audio_tracks ?? [];
  if (tracks.length === 0) {
    return <EmptyNote text="Nenhuma faixa de áudio ainda." />;
  }
  return (
    <ul className="space-y-3">
      {tracks.map((track) => (
        <li key={track.id} className="rounded-lg border border-white/10 p-3">
          <p className="font-mono text-[10px] uppercase text-white/40">{track.source}</p>
          {track.file_url ? (
            <audio controls src={track.file_url} className="mt-2 w-full" />
          ) : (
            <p className="mt-2 text-sm text-white/40">Arquivo ainda não disponível.</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function RenderReview({ project }: ReviewBodyProps) {
  const url = project.video_assembly?.output_url;
  if (!url) {
    return <EmptyNote text="Montagem ainda não disponível." />;
  }
  return <video controls src={url} className="w-full rounded-lg bg-black" />;
}

function latest<T>(items: T[] | undefined): T | undefined {
  if (!items?.length) return undefined;
  return items[items.length - 1];
}

function ThumbnailReview({ project }: ReviewBodyProps) {
  const thumb = latest(project.thumbnails);
  if (!thumb) {
    return <EmptyNote text="Nenhuma thumbnail gerada." />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={thumb.file_url} alt="Thumbnail" className="max-h-64 w-full rounded-lg object-contain" />
  );
}

function DescriptionReview({ project }: ReviewBodyProps) {
  const description = latest(project.descriptions);
  const thumb = latest(project.thumbnails);
  return (
    <div className="space-y-4">
      {thumb ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumb.file_url} alt="" className="max-h-40 rounded-lg object-contain" />
      ) : null}
      {description ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/75">{description.text}</p>
      ) : (
        <EmptyNote text="Descrição ainda não gerada." />
      )}
    </div>
  );
}

export function reviewTitle(stage: ProjectStage): string {
  switch (stage) {
    case "transcript_review":
      return "Revisar transcrição";
    case "scene_review":
      return "Revisar cenas";
    case "media_review":
      return "Revisar mídia";
    case "audio_stage":
      return "Áudio do projeto";
    case "audio_review":
      return "Revisar áudio";
    case "render_review":
      return "Revisar render";
    case "thumbnail_stage":
      return "Revisar thumbnail";
    case "description_stage":
      return "Revisar descrição";
    case "ready_to_publish":
      return "Revisar publicação";
    default:
      return "Revisão manual";
  }
}

export function ReviewStageBody({ project }: ReviewBodyProps) {
  switch (project.current_stage) {
    case "scene_review":
      return <SceneReview project={project} withMedia={false} />;
    case "media_review":
      return <SceneReview project={project} withMedia />;
    case "audio_review":
      return <AudioReview project={project} />;
    case "render_review":
      return <RenderReview project={project} />;
    case "thumbnail_stage":
      return <ThumbnailReview project={project} />;
    case "description_stage":
    case "ready_to_publish":
      return <DescriptionReview project={project} />;
    default:
      return <EmptyNote text="Nada para revisar neste estágio." />;
  }
}
